from uuid import UUID

from ninja import File, Form, Router
from ninja.files import UploadedFile

from accounts.authentication import jwt_auth
from accounts.schemas import ErrorOut

from . import selectors, services
from .schemas import ConfirmIn, ProcessingListOut, ProcessingOut, UploadDocumentType

router = Router(tags=['document-processing'], auth=jwt_auth)
ERRORS = {400: ErrorOut, 401: ErrorOut, 403: ErrorOut, 404: ErrorOut, 409: ErrorOut, 422: ErrorOut, 429: ErrorOut}


@router.get('/orders/{order_id}/documents', response={200: ProcessingListOut, **ERRORS}, operation_id='listOrderDocuments')
def list_documents(request, order_id: UUID):
    return selectors.list_order_documents(request.auth, order_id)


@router.post('/orders/{order_id}/documents', response={200: ProcessingOut, **ERRORS}, operation_id='uploadOrderDocument')
def upload(request, order_id: UUID, file: File[UploadedFile], upload_key: Form[UUID], document_type: Form[UploadDocumentType] = 'auto'):
    return services.upload_document(request.auth, order_id, upload=file, upload_key=upload_key, document_type=document_type)


@router.get('/documents/{document_id}', response={200: ProcessingOut, **ERRORS}, operation_id='getProcessedDocument')
def detail(request, document_id: UUID):
    return selectors.get_document_data(request.auth, document_id)


@router.get('/documents/{document_id}/file', response={200: bytes, **ERRORS}, operation_id='downloadProcessedDocument')
def download(request, document_id: UUID):
    return selectors.download_document(request.auth, document_id)


@router.post('/documents/{document_id}/retry', response={200: ProcessingOut, **ERRORS}, operation_id='retryProcessedDocument')
def retry(request, document_id: UUID):
    services.retry_document(request.auth, document_id)
    return selectors.get_document_data(request.auth, document_id)


@router.post('/documents/{document_id}/confirm', response={200: ProcessingOut, **ERRORS}, operation_id='confirmProcessedDocument')
def confirm(request, document_id: UUID, payload: ConfirmIn):
    return services.confirm_document(request.auth, document_id, **payload.model_dump())
