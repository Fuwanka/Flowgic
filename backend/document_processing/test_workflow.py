"""Private originals, tenant/RBAC boundaries, asynchronous state and explicit review."""
from datetime import timedelta
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.utils import timezone
from PIL import Image
from pypdf import PdfWriter

from accounts.services import login_with_tokens
from logistics.models import Financial, OrderEvent
from . import selectors, services
from .exceptions import ProcessingError
from .extraction import extract_document
from .mapping import proposed_order_fields
from .models import DocumentReview, ProcessedDocument
from .ocr_client import validate_response
from .storage import MAX_BYTES, private_storage, validate_upload
from .tasks import process_document

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def image_upload(name='накладная.png'):
    stream = BytesIO()
    Image.new('RGB', (64, 64), 'white').save(stream, format='PNG')
    return SimpleUploadedFile(name, stream.getvalue(), content_type='image/png')


@pytest.fixture(autouse=True)
def private_files(settings, tmp_path):
    settings.OCR_PRIVATE_ROOT = tmp_path / 'originals'
    with patch('document_processing.tasks.process_document.apply_async') as queued:
        yield queued


def api(user):
    tokens = login_with_tokens(email=user.email, password='testpass123')
    return Client(HTTP_AUTHORIZATION='Bearer ' + tokens['access'])


def uploaded(user, order, **kwargs):
    result = services.upload_document(user, order.pk, upload=image_upload(), upload_key=kwargs.pop('upload_key', uuid4()), **kwargs)
    return ProcessedDocument.objects.get(pk=result['id'])


def reviewable(user, order):
    document = uploaded(user, order)
    document.status, document.document_type = 'needs_review', 'ttn'
    document.fields = extract_document([{'number': 1, 'lines': []}], document_type='ttn')['fields']
    document.save()
    return document


def confirm(user, document, **kwargs):
    return services.confirm_document(user, document.pk, version=kwargs.pop('version', document.version),
                                     document_type=kwargs.pop('document_type', 'ttn'), fields=kwargs.pop('fields', {}), **kwargs)


def test_http_upload_list_private_original_and_idempotency(dispatcher_a, order_a, django_capture_on_commit_callbacks, private_files):
    client, key = api(dispatcher_a), uuid4()
    url = f'/api/document-processing/orders/{order_a.pk}/documents'
    with django_capture_on_commit_callbacks(execute=True):
        response = client.post(url, {'file': image_upload(), 'upload_key': str(key), 'document_type': 'auto'})
    assert response.status_code == 200, response.content
    body = response.json()
    assert body['status'] == 'queued' and body['version'] == 1 and body['order_changes'] == {}
    assert private_files.call_count == 1 and private_files.call_args.kwargs['queue'] == 'documents'
    assert client.get(url).json()['items'][0]['id'] == body['id']
    download = client.get(f'/api/document-processing/documents/{body["id"]}/file')
    assert download.status_code == 200 and b''.join(download.streaming_content).startswith(b'\x89PNG')
    assert download['Cache-Control'] == 'private, no-store'
    assert download['X-Content-Type-Options'] == 'nosniff'
    duplicate = client.post(url, {'file': image_upload(), 'upload_key': str(key)})
    assert duplicate.json()['id'] == body['id']
    assert ProcessedDocument.objects.filter(company=dispatcher_a.company).count() == 1
    conflict = client.post(url, {'file': image_upload(), 'upload_key': str(key), 'document_type': 'ttn'})
    assert conflict.status_code == 409


def test_all_document_operations_are_company_scoped(dispatcher_a, dispatcher_b, order_a, order_b):
    document = reviewable(dispatcher_b, order_b)
    client, path = api(dispatcher_a), f'/api/document-processing/documents/{document.pk}'
    assert client.get(f'/api/document-processing/orders/{order_b.pk}/documents').status_code == 404
    assert client.post(f'/api/document-processing/orders/{order_b.pk}/documents', {'file': image_upload(), 'upload_key': str(uuid4())}).status_code == 404
    assert client.get(path).status_code == 404
    assert client.get(path + '/file').status_code == 404
    assert client.post(path + '/retry').status_code == 404
    assert client.post(path + '/confirm', {'version': document.version, 'document_type': 'ttn', 'fields': {}}, content_type='application/json').status_code == 404
    assert not DocumentReview.objects.exists()


def test_driver_and_unauthenticated_cannot_access_ocr(driver_a, dispatcher_a, order_a):
    document = reviewable(dispatcher_a, order_a)
    url = f'/api/document-processing/documents/{document.pk}'
    for suffix in ('', '/file'):
        assert api(driver_a).get(url + suffix).status_code == 403
        assert Client().get(url + suffix).status_code == 401
    assert api(driver_a).post(f'/api/document-processing/orders/{order_a.pk}/documents', {'file': image_upload(), 'upload_key': str(uuid4())}).status_code == 403


def test_corrupt_cross_company_order_relation_hidden(dispatcher_a, order_b, order_a):
    document = uploaded(dispatcher_a, order_a)
    document.order = order_b
    document.save()
    assert api(dispatcher_a).get(f'/api/document-processing/documents/{document.pk}').status_code == 404
    process_document(str(document.pk), str(dispatcher_a.company_id), document.version)
    document.refresh_from_db()
    assert document.status == 'queued'


@pytest.mark.parametrize('data,name', [(b'', 'empty.pdf'), (b'<html>document</html>', 'fake.pdf'), (b'%PDF-1.7\ninvalid', 'broken.pdf'), (b'x' * (MAX_BYTES + 1), 'large.png')],
                         ids=['empty', 'html', 'broken-pdf', 'oversize'])
def test_invalid_files_rejected_without_db_or_files(dispatcher_a, order_a, data, name):
    with pytest.raises(ProcessingError) as error:
        services.upload_document(dispatcher_a, order_a.pk, upload=SimpleUploadedFile(name, data), upload_key=uuid4())
    assert error.value.status == 422
    assert not ProcessedDocument.objects.exists()
    assert not list(Path(private_storage().location).glob('**/original.*'))


def test_pdf_page_and_encryption_limits():
    for count, password in [(11, None), (1, 'secret')]:
        writer, stream = PdfWriter(), BytesIO()
        for _ in range(count):
            writer.add_blank_page(width=600, height=800)
        if password:
            writer.encrypt(password)
        writer.write(stream)
        with pytest.raises(ProcessingError):
            validate_upload(SimpleUploadedFile('scan.pdf', stream.getvalue()))


def test_actual_content_wins_over_filename_and_mime():
    data, content_type, extension, filename = validate_upload(image_upload('evil.pdf'))
    assert content_type == 'image/png' and extension == 'png' and data.startswith(b'\x89PNG')


def test_lost_original_returns_safe_404(dispatcher_a, order_a):
    document = uploaded(dispatcher_a, order_a)
    private_storage().delete(document.storage_key)
    response = api(dispatcher_a).get(f'/api/document-processing/documents/{document.pk}/file')
    assert response.status_code == 404
    assert 'storage_key' not in response.content.decode()


def test_storage_file_removed_if_db_creation_rolls_back(dispatcher_a, order_a):
    with patch.object(ProcessedDocument.objects, 'create', side_effect=RuntimeError('db failure')):
        with pytest.raises(RuntimeError):
            uploaded(dispatcher_a, order_a)
    assert not list(Path(private_storage().location).glob('**/original.*'))


def test_broker_outage_is_failed_and_retryable(dispatcher_a, order_a, django_capture_on_commit_callbacks, private_files):
    private_files.side_effect = OSError('secret broker URL must never appear')
    with django_capture_on_commit_callbacks(execute=True):
        document = uploaded(dispatcher_a, order_a)
    document.refresh_from_db()
    assert document.status == 'failed' and 'secret' not in document.error
    private_files.side_effect = None
    with django_capture_on_commit_callbacks(execute=True):
        services.retry_document(dispatcher_a, document.pk)
    document.refresh_from_db()
    assert document.status == 'queued'


def test_task_reads_bytes_extracts_evidence_and_duplicate_is_noop(dispatcher_a, order_a):
    document = uploaded(dispatcher_a, order_a)
    payload = {'engine': 'test-local', 'pages': [{'number': 1, 'width': 1000, 'height': 1400, 'lines': [
        {'text': 'Транспортная накладная № 123 от 29.10.2026', 'confidence': .98, 'bbox': [1, 1, 80, 4]},
        {'text': 'Стоимость перевозки: 12 345,67 руб.', 'confidence': .99, 'bbox': [1, 10, 80, 4]},
    ]}]}
    with patch('document_processing.tasks.recognize', return_value=payload) as engine:
        process_document(str(document.pk), str(document.company_id), document.version)
        process_document(str(document.pk), str(document.company_id), document.version)
    document.refresh_from_db()
    assert engine.call_count == 1 and engine.call_args.args[0].startswith(b'\x89PNG')
    assert document.status == 'needs_review' and document.attempts == 1 and document.engine == 'test-local'
    assert document.fields['freight_amount']['value'] == '12345.67'
    assert document.fields['freight_amount']['evidence'][0]['page'] == 1
    assert document.fields['freight_amount']['review_required'] is True
    order_a.refresh_from_db()
    assert order_a.agreed_price != Decimal('12345.67')


def test_task_failure_safe_and_revoked_user_not_processed(dispatcher_a, order_a):
    document = uploaded(dispatcher_a, order_a)
    with patch('document_processing.tasks.recognize', side_effect=OSError('private service details')):
        process_document(str(document.pk), str(document.company_id), document.version)
    document.refresh_from_db()
    assert document.status == 'failed' and 'private' not in document.error
    other = uploaded(dispatcher_a, order_a)
    dispatcher_a.is_active = False
    dispatcher_a.save()
    with patch('document_processing.tasks.recognize') as engine:
        process_document(str(other.pk), str(other.company_id), other.version)
        engine.assert_not_called()
    other.refresh_from_db()
    assert other.status == 'failed'


def test_old_worker_cannot_overwrite_retried_run(dispatcher_a, order_a):
    document = uploaded(dispatcher_a, order_a)
    claimed = services.claim_document(document.pk, document.company_id, document.version)
    ProcessedDocument.objects.filter(company=document.company, pk=document.pk).update(updated_at=timezone.now() - timedelta(minutes=16))
    services.retry_document(dispatcher_a, document.pk)
    document.refresh_from_db()
    new_claim = services.claim_document(document.pk, document.company_id, document.version)
    assert new_claim.run_token != claimed.run_token
    assert services.complete_document(claimed, error='obsolete result') is False
    assert services.complete_document(new_claim, error='current error') is True
    document.refresh_from_db()
    assert document.error == 'current error'


def test_retry_in_progress_and_max_attempts_blocked(dispatcher_a, order_a):
    document = uploaded(dispatcher_a, order_a)
    with pytest.raises(ProcessingError, match='15 минут'):
        services.retry_document(dispatcher_a, document.pk)
    document.status, document.attempts = 'failed', 3
    document.save()
    with pytest.raises(ProcessingError, match='три попытки'):
        services.retry_document(dispatcher_a, document.pk)


def test_confirmation_preserves_original_candidates_and_order_without_opt_in(dispatcher_a, order_a):
    document = reviewable(dispatcher_a, order_a)
    fields = {'cargo_description': 'Щебень гранитный', 'cargo_mass': '20,5', 'cargo_mass_unit': 'т', 'freight_amount': '50000', 'currency': 'RUB'}
    before = order_a.cargo_type, order_a.cargo_mass_kg, order_a.agreed_price
    result = confirm(dispatcher_a, document, fields=fields)
    order_a.refresh_from_db()
    document.refresh_from_db()
    assert (order_a.cargo_type, order_a.cargo_mass_kg, order_a.agreed_price) == before
    assert result['status'] == 'confirmed' and result['fields']['cargo_description']['value'] == 'Щебень гранитный'
    assert document.fields['cargo_description']['value'] is None
    assert DocumentReview.objects.get(company=dispatcher_a.company, document=document).actor == dispatcher_a
    assert OrderEvent.objects.filter(order__client__company=dispatcher_a.company, order=order_a, event_type='document_reviewed').count() == 1
    assert confirm(dispatcher_a, document, fields=fields)['status'] == 'confirmed'
    assert DocumentReview.objects.count() == 1
    with pytest.raises(ProcessingError) as error:
        confirm(dispatcher_a, document, fields={'cargo_description': 'Другая версия'})
    assert error.value.status == 409


def test_explicit_apply_updates_only_whitelist_not_financials(dispatcher_a, order_a):
    document = reviewable(dispatcher_a, order_a)
    before = order_a.status, order_a.driver_id, order_a.vehicle_id
    result = confirm(dispatcher_a, document, apply_to_order=True, fields={
        'cargo_description': 'Песок строительный', 'cargo_mass': '20,5', 'cargo_mass_unit': 'т',
        'loading_address': 'Карьер, Москва', 'unloading_address': 'Стройплощадка, Тула',
        'freight_amount': '12 345,67', 'currency': 'RUB', 'cargo_value': '900000',
    })
    order_a.refresh_from_db()
    assert result['status'] == 'confirmed'
    assert order_a.cargo_type == 'Песок строительный' and order_a.cargo_mass_kg == 20500
    assert order_a.agreed_price == Decimal('12345.67') and order_a.origin == 'Карьер, Москва'
    assert (order_a.status, order_a.driver_id, order_a.vehicle_id) == before
    assert not Financial.objects.filter(order__client__company=dispatcher_a.company, order=order_a).exists()
    assert DocumentReview.objects.get(company=dispatcher_a.company, document=document).order_changes['cargo_mass_kg']['after'] == '20500'


def test_version_conflict_and_changed_order_cannot_be_overwritten(dispatcher_a, order_a):
    document = reviewable(dispatcher_a, order_a)
    with pytest.raises(ProcessingError) as error:
        confirm(dispatcher_a, document, version=document.version + 1)
    assert error.value.code == 'version_conflict'
    order_a.cargo_type = 'Изменено другим диспетчером'
    order_a.save()
    with pytest.raises(ProcessingError) as error:
        confirm(dispatcher_a, document, fields={'cargo_description': 'Устаревшие сведения'}, apply_to_order=True)
    assert error.value.code == 'order_conflict'
    document.refresh_from_db()
    assert document.status == 'needs_review' and not DocumentReview.objects.exists()


def test_review_and_order_changes_roll_back_if_audit_write_fails(dispatcher_a, order_a):
    document = reviewable(dispatcher_a, order_a)
    old = order_a.cargo_type
    with patch.object(DocumentReview.objects, 'create', side_effect=RuntimeError('audit failure')):
        with pytest.raises(RuntimeError):
            confirm(dispatcher_a, document, fields={'cargo_description': 'Не сохранить'}, apply_to_order=True)
    order_a.refresh_from_db()
    document.refresh_from_db()
    assert order_a.cargo_type == old and document.status == 'needs_review'
    assert not OrderEvent.objects.filter(order__client__company=dispatcher_a.company, order=order_a, event_type='document_reviewed').exists()


@pytest.mark.parametrize('fields', [{'unknown': 'injected'}, {'document_number': 'x' * 2001}, {'cargo_description': '\x00bad'}])
def test_review_rejects_unknown_and_unbounded_fields(dispatcher_a, order_a, fields):
    document = reviewable(dispatcher_a, order_a)
    with pytest.raises(ProcessingError) as error:
        confirm(dispatcher_a, document, fields=fields)
    assert error.value.status == 422


def test_capacity_limits_do_not_block_idempotent_retry(dispatcher_a, order_a):
    first = uploaded(dispatcher_a, order_a)
    for _ in range(9):
        uploaded(dispatcher_a, order_a)
    assert uploaded(dispatcher_a, order_a, upload_key=first.upload_key).pk == first.pk
    with pytest.raises(ProcessingError) as error:
        uploaded(dispatcher_a, order_a)
    assert error.value.status == 429


@pytest.mark.parametrize('fields', [
    {'cargo_mass': '12.0001', 'cargo_mass_unit': 'т'},
    {'cargo_mass': '20', 'cargo_mass_unit': 'м3'},
    {'freight_amount': '10000', 'currency': 'USD'},
    {'freight_amount': '10000'},
    {'freight_amount': '-100', 'currency': 'RUB'},
    {'cargo_description': 'x' * 101},
])
def test_invalid_or_ambiguous_order_values_not_applied(fields):
    with pytest.raises(ProcessingError):
        proposed_order_fields(fields, strict=True)


def test_cargo_value_never_becomes_freight():
    assert proposed_order_fields({'cargo_value': '550000', 'currency': 'RUB'}, strict=True) == {}


def test_original_removed_only_after_record_deletion_commits(dispatcher_a, order_a, django_capture_on_commit_callbacks):
    document = uploaded(dispatcher_a, order_a)
    key = document.storage_key
    assert private_storage().exists(key)
    with django_capture_on_commit_callbacks(execute=True):
        document.delete()
        assert private_storage().exists(key)
    assert not private_storage().exists(key)


def test_upd_cannot_overwrite_freight_order(dispatcher_a, order_a):
    document = reviewable(dispatcher_a, order_a)
    with pytest.raises(ProcessingError) as error:
        confirm(dispatcher_a, document, document_type='upd', fields={'cargo_description': 'Товар'}, apply_to_order=True)
    assert error.value.status == 422


@pytest.mark.parametrize('payload', [{}, {'engine': 'a', 'pages': []}, {'engine': 'a', 'pages': [{'number': 1, 'width': 10, 'height': 10, 'lines': [{'text': 'x', 'confidence': float('nan'), 'bbox': [0, 0, 1, 1]}]}]}])
def test_invalid_engine_responses_rejected(payload):
    with pytest.raises((ValueError, KeyError, AttributeError)):
        validate_response(payload)
