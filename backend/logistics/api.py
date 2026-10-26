from io import BytesIO
from typing import Literal
from uuid import UUID

from django.http import FileResponse
from ninja import Router, Status

from accounts.authentication import jwt_auth
from accounts.schemas import ErrorOut
from billing.schemas import QuotaErrorOut

from . import services
from .documents import generate_order_document
from .schemas import OrderCreateIn, OrderOut, VehicleCreateIn, VehicleOut, VehicleStatusIn

router = Router(tags=['logistics'], auth=jwt_auth)
DOCX_MIME = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'


@router.post('/orders', response={201: OrderOut, 400: ErrorOut, 401: ErrorOut, 402: QuotaErrorOut, 403: ErrorOut, 404: ErrorOut}, operation_id='createOrder')
def create_order(request, payload: OrderCreateIn):
    return Status(201, services.create_order(request.auth, **payload.model_dump()))


@router.post('/vehicles', response={201: VehicleOut, 400: ErrorOut, 401: ErrorOut, 402: QuotaErrorOut, 403: ErrorOut}, operation_id='createVehicle')
def create_vehicle(request, payload: VehicleCreateIn):
    return Status(201, services.create_vehicle(request.auth, **payload.model_dump()))


@router.patch('/vehicles/{vehicle_id}/status', response={200: VehicleOut, 400: ErrorOut, 401: ErrorOut, 402: QuotaErrorOut, 403: ErrorOut, 404: ErrorOut}, operation_id='updateVehicleStatus')
def update_vehicle_status(request, vehicle_id: UUID, payload: VehicleStatusIn):
    return services.update_vehicle_status(request.auth, vehicle_id, payload.status)


@router.get(
    '/orders/{order_id}/document/docx',
    response={200: None, 400: ErrorOut, 401: ErrorOut, 404: ErrorOut},
    operation_id='downloadOrderDocument',
    openapi_extra={'responses': {200: {
        'description': 'Заполненный редактируемый DOCX',
        'content': {DOCX_MIME: {'schema': {'type': 'string', 'format': 'binary'}}},
    }}},
)
def order_document(request, order_id: UUID, document_type: Literal['application', 'ttn'] = 'application'):
    document = generate_order_document(request.auth, order_id, document_type)
    return FileResponse(
        BytesIO(document.content), as_attachment=True,
        filename=document.filename, content_type=document.content_type,
    )
