"""Writes and orchestration. Candidate text never mutates an order automatically."""
import hashlib
import logging
from datetime import timedelta
from uuid import uuid4

from django.core.files.base import ContentFile
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone

from accounts.permissions import require_operator
from billing.services import company_quota_lock
from logistics import selectors as logistics_selectors, services as logistics_services

from .exceptions import ProcessingError
from .extraction import FIELD_IDS
from .mapping import order_snapshot, proposed_order_fields
from .models import DocumentReview, ProcessedDocument
from .selectors import document_data, get_document, user_documents
from .storage import private_storage, validate_upload

logger = logging.getLogger(__name__)
LEASE = timedelta(minutes=15)


def _queue(document):
    """Dispatch only committed rows. A broker outage leaves a visible, retryable state."""
    document_id, company_id, version = str(document.pk), str(document.company_id), document.version

    def send():
        from .tasks import process_document
        try:
            process_document.apply_async(args=[document_id, company_id, version], queue='documents', retry=False)
        except Exception:
            # Do not leak broker URLs or documents to logs/API.
            ProcessedDocument.objects.filter(company_id=company_id, pk=document_id, status='queued', version=version).update(
                status='failed', error='Очередь обработки недоступна. Повторите обработку позже.',
                version=version + 1, updated_at=timezone.now(),
            )
            logger.warning('Document queue dispatch failed for %s', document_id)
    transaction.on_commit(send)


def upload_document(user, order_id, *, upload, upload_key, document_type='auto'):
    require_operator(user)
    order = logistics_selectors.get_order_detail(user, order_id)
    if document_type not in ProcessedDocument.Type.values:
        raise ProcessingError('Неизвестный тип документа.', status=422)
    data, content_type, extension, filename = validate_upload(upload)
    digest = hashlib.sha256(data).hexdigest()
    saved_key = None
    try:
        with transaction.atomic(), company_quota_lock(user.company):
            existing = user_documents(user).filter(upload_key=upload_key).first()
            if existing:
                if existing.order_id != order_id or existing.sha256 != digest or existing.requested_type != document_type:
                    raise ProcessingError('Ключ загрузки уже использован для другого файла или заказа.', code='upload_conflict', status=409)
                return document_data(existing)
            documents = user_documents(user)
            if documents.filter(order_id=order_id).count() >= 50 or documents.filter(status__in=['queued', 'processing']).count() >= 10 or documents.filter(created_at__gte=timezone.now() - timedelta(days=1)).count() >= 100:
                raise ProcessingError('Достигнут лимит обработки: 50 документов на заказ, 10 в очереди или 100 загрузок в сутки на компанию.', code='processing_limit', status=429)
            identifier = uuid4()
            saved_key = private_storage().save(f'{user.company_id}/{identifier}/original.{extension}', ContentFile(data))
            document = ProcessedDocument.objects.create(
                id=identifier, company=user.company, order_id=order_id, created_by=user,
                upload_key=upload_key, original_filename=filename, content_type=content_type,
                storage_key=saved_key, sha256=digest, byte_size=len(data),
                requested_type=document_type, document_type=document_type,
                order_baseline=order_snapshot(order),
            )
            _queue(document)
    except Exception:
        if saved_key is not None:
            private_storage().delete(saved_key)
        raise
    return document_data(get_document(user, identifier))


@transaction.atomic
def retry_document(user, document_id):
    require_operator(user)
    document = get_object_or_404(user_documents(user).select_for_update(of=('self',)), pk=document_id)
    stale = document.status in {'processing', 'queued'} and document.updated_at < timezone.now() - LEASE
    if document.status != 'failed' and not stale:
        raise ProcessingError('Повтор доступен после ошибки или 15 минут без результата.', code='invalid_state', status=409)
    if document.attempts >= 3:
        raise ProcessingError('Исчерпаны три попытки. Проверьте файл и загрузите исправленную копию.', code='attempt_limit', status=409)
    document.status, document.error, document.run_token = 'queued', None, None
    document.version += 1
    document.save(update_fields=['status', 'error', 'run_token', 'version', 'updated_at'])
    _queue(document)
    return document_data(document)


def _review_fields(document, supplied):
    if len(supplied) > len(FIELD_IDS) or set(supplied) - set(FIELD_IDS):
        raise ProcessingError('Неизвестные поля документа.', code='invalid_fields', status=422)
    values = {key: document.fields.get(key, {}).get('value') for key in FIELD_IDS}
    for key, value in supplied.items():
        if value is not None and (not isinstance(value, str) or len(value) > 2000 or '\x00' in value):
            raise ProcessingError('Значение поля должно быть текстом до 2000 символов.', code='invalid_fields', status=422)
        values[key] = value.strip() or None if value is not None else None
    return values


@transaction.atomic
def confirm_document(user, document_id, *, version, document_type, fields, apply_to_order=False):
    require_operator(user)
    document = get_object_or_404(user_documents(user).select_for_update(of=('self',)), pk=document_id)
    if document_type not in set(ProcessedDocument.Type.values) - {'auto'}:
        raise ProcessingError('Выберите тип документа.', status=422)
    values = _review_fields(document, fields)
    if document.status == 'confirmed':
        review = DocumentReview.objects.filter(company=user.company, document=document).get()
        if review.fields == values and review.document_type == document_type and review.apply_to_order == apply_to_order:
            return document_data(document)
        raise ProcessingError('Документ уже подтверждён.', code='already_confirmed', status=409)
    if document.version != version:
        raise ProcessingError('Документ изменился. Обновите результат перед подтверждением.', code='version_conflict', status=409)
    if document.status != 'needs_review':
        raise ProcessingError('Дождитесь результата распознавания.', code='invalid_state', status=409)
    if apply_to_order and document_type not in {'tn', 'ttn', 'request'}:
        raise ProcessingError('Перенос в заказ доступен для ТН, ТТН и заявки на перевозку.', code='invalid_order_fields', status=422)
    changes = proposed_order_fields(values, strict=True) if apply_to_order else {}
    try:
        applied = logistics_services.record_reviewed_document(
            user, document.order_id, document_id=document.pk, changes=changes, baseline=document.order_baseline,
        )
    except logistics_services.OrderReviewConflict as exc:
        raise ProcessingError(str(exc), code='order_conflict', status=409) from exc
    DocumentReview.objects.create(company=user.company, document=document, actor=user, document_type=document_type,
                                  fields=values, order_changes=applied, apply_to_order=apply_to_order)
    document.status, document.document_type, document.confirmed_fields = 'confirmed', document_type, values
    document.confirmed_by, document.confirmed_at = user, timezone.now()
    document.version += 1
    document.save(update_fields=['status', 'document_type', 'confirmed_fields', 'confirmed_by', 'confirmed_at', 'version', 'updated_at'])
    return document_data(get_document(user, document_id))


@transaction.atomic
def claim_document(document_id, company_id, version):
    document = ProcessedDocument.objects.filter(company_id=company_id, order__client__company_id=company_id, pk=document_id).select_related('created_by').select_for_update(of=('self',)).first()
    if document is None or document.status != 'queued' or document.version != version:
        return None
    actor = document.created_by
    if not actor or actor.company_id != document.company_id or not actor.is_active or actor.status != 'active' or actor.role not in {'dispatcher', 'manager'}:
        document.status, document.error = 'failed', 'У загрузившего пользователя больше нет доступа к компании.'
        document.version += 1
        document.save(update_fields=['status', 'error', 'version', 'updated_at'])
        return None
    document.status, document.run_token = 'processing', uuid4()
    document.attempts += 1
    document.processing_started_at, document.error = timezone.now(), None
    document.version += 1
    document.save(update_fields=['status', 'run_token', 'attempts', 'processing_started_at', 'error', 'version', 'updated_at'])
    return document


@transaction.atomic
def complete_document(document, *, result=None, error=None):
    current = ProcessedDocument.objects.filter(company_id=document.company_id, order__client__company_id=document.company_id, pk=document.pk, status='processing', run_token=document.run_token).select_for_update(of=('self',)).first()
    if current is None:
        return False
    current.version += 1
    if error:
        current.status, current.error = 'failed', error
    else:
        current.status, current.error = 'needs_review', None
        current.engine, current.pages = result['engine'], result['pages']
        current.document_type, current.fields, current.warnings = result['document_type'], result['fields'], result['warnings']
    current.save()
    return True
