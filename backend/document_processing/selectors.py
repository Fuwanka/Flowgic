from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404

from accounts.permissions import require_operator
from logistics.selectors import get_order_detail

from .mapping import changes_for_order
from .models import ProcessedDocument
from .storage import private_storage


def user_documents(user):
    require_operator(user)
    return ProcessedDocument.objects.filter(company=user.company, order__client__company=user.company).select_related('order', 'order__client', 'confirmed_by')


def get_document(user, document_id):
    return get_object_or_404(user_documents(user), pk=document_id)


def document_data(document):
    fields = {key: dict(value) for key, value in document.fields.items()}
    if document.status == ProcessedDocument.Status.CONFIRMED:
        for key, value in document.confirmed_fields.items():
            fields[key] = {**fields.get(key, {}), 'value': value, 'review_required': False}
    values = {key: field.get('value') for key, field in fields.items()}
    return {
        **{key: getattr(document, key) for key in ('id', 'order_id', 'status', 'original_filename', 'document_type', 'version', 'warnings', 'error', 'created_at', 'updated_at', 'confirmed_at', 'confirmed_by_id', 'engine')},
        'fields': fields, 'order_changes': changes_for_order(document.order, values),
    }


def get_document_data(user, document_id):
    return document_data(get_document(user, document_id))


def list_order_documents(user, order_id):
    require_operator(user)
    get_order_detail(user, order_id)
    return {'items': [document_data(document) for document in user_documents(user).filter(order_id=order_id)[:50]]}


def download_document(user, document_id):
    document = get_document(user, document_id)
    try:
        original = private_storage().open(document.storage_key, 'rb')
    except FileNotFoundError as exc:
        raise Http404 from exc
    response = FileResponse(original, content_type=document.content_type, as_attachment=False, filename=document.original_filename)
    response['Cache-Control'] = 'private, no-store'
    response['X-Content-Type-Options'] = 'nosniff'
    response['Content-Security-Policy'] = "sandbox; default-src 'none'"
    return response
