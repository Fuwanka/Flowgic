import logging

from celery import shared_task

from .extraction import extract_document
from .ocr_client import recognize
from .services import claim_document, complete_document
from .storage import MAX_BYTES, private_storage

logger = logging.getLogger(__name__)


@shared_task(acks_late=True, reject_on_worker_lost=True, soft_time_limit=660, time_limit=720, ignore_result=True)
def process_document(document_id, company_id, version):
    document = claim_document(document_id, company_id, version)
    if document is None:
        return
    try:
        with private_storage().open(document.storage_key, 'rb') as original:
            data = original.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise ValueError('Original too large')
        ocr = recognize(data, document.content_type)
        extracted = extract_document(ocr['pages'], document_type=document.requested_type)
        complete_document(document, result={**ocr, **extracted})
    except Exception:
        logger.warning('Document recognition failed for %s', document_id)
        complete_document(document, error='Не удалось распознать документ. Проверьте качество файла и доступность локального OCR, затем повторите обработку.')
