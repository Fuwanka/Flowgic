# HTTP-граница не делает ORM-запросов: чтение делегировано selectors, запись и расчёты — services.
"""Тонкие HTTP-адаптеры: ORM и правила находятся в selectors/services."""
from io import BytesIO
from typing import Literal
from uuid import UUID

from django.http import FileResponse
from ninja import Router, Status

from accounts.authentication import jwt_auth
from accounts.schemas import ErrorOut
from billing.schemas import QuotaErrorOut

from . import selectors, services
from .documents import generate_order_document
from .schemas import OrderCreateIn, OrderOut, VehicleCreateIn, VehicleOut, VehicleStatusIn
from .schemas import (CalendarOut, ClientIn, ClientOut, FinancialIn, FinancialOut, OrderDetailOut,
                      OrderPageOut, OrderState, OrderStatusIn, OrderUpdateIn, OverviewOut)
from datetime import date
from pydantic import Field
from typing import Annotated

router = Router(tags=['logistics'], auth=jwt_auth)
DOCX_MIME = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'


@router.get('/orders', response={200: OrderPageOut, 401: ErrorOut, 403: ErrorOut}, operation_id='listOrders')
def orders(request, status: OrderState | None = None, q: Annotated[str, Field(max_length=100)] = '',
           page: Annotated[int, Field(ge=1)] = 1, page_size: Annotated[int, Field(ge=1, le=100)] = 20):
    return selectors.list_orders(request.auth, status=status, q=q, page=page, page_size=page_size)


@router.get('/overview', response={200: OverviewOut, 401: ErrorOut, 403: ErrorOut}, operation_id='getOverview')
def overview(request):
    return selectors.get_overview(request.auth)


@router.get('/calendar', response={200: CalendarOut, 400: ErrorOut, 401: ErrorOut, 403: ErrorOut}, operation_id='getCalendar')
def calendar(request, start: date, end: date):
    return selectors.get_calendar(request.auth, start=start, end=end)


@router.get('/orders/{order_id}', response={200: OrderDetailOut, 401: ErrorOut, 404: ErrorOut}, operation_id='getOrder')
def order(request, order_id: UUID):
    return selectors.get_order_detail(request.auth, order_id)


@router.put('/orders/{order_id}', response={200: OrderDetailOut, 400: ErrorOut, 401: ErrorOut, 403: ErrorOut, 404: ErrorOut}, operation_id='updateOrder')
def edit_order(request, order_id: UUID, payload: OrderUpdateIn):
    return services.update_order(request.auth, order_id, **payload.model_dump())


@router.patch('/orders/{order_id}/status', response={200: OrderDetailOut, 400: ErrorOut, 401: ErrorOut, 403: ErrorOut, 404: ErrorOut}, operation_id='changeOrderStatus')
def order_status(request, order_id: UUID, payload: OrderStatusIn):
    return services.change_order_status(request.auth, order_id, **payload.model_dump())


@router.post('/orders/{order_id}/financial/preview', response={200: FinancialOut, 400: ErrorOut, 401: ErrorOut, 403: ErrorOut, 404: ErrorOut}, operation_id='previewFinancials')
def preview_financials(request, order_id: UUID, payload: FinancialIn):
    return services.preview_financials(request.auth, order_id, **payload.model_dump())


@router.put('/orders/{order_id}/financial', response={200: FinancialOut, 400: ErrorOut, 401: ErrorOut, 403: ErrorOut, 404: ErrorOut}, operation_id='saveFinancials')
def financials(request, order_id: UUID, payload: FinancialIn):
    return services.save_financials(request.auth, order_id, **payload.model_dump())


@router.get('/clients', response={200: list[ClientOut], 401: ErrorOut, 403: ErrorOut}, operation_id='listClients')
def clients(request):
    return selectors.list_clients(request.auth)


@router.post('/clients', response={201: ClientOut, 400: ErrorOut, 401: ErrorOut, 403: ErrorOut}, operation_id='createClient')
def create_client(request, payload: ClientIn):
    return Status(201, services.create_client(request.auth, **payload.model_dump()))


@router.put('/clients/{client_id}', response={200: ClientOut, 400: ErrorOut, 401: ErrorOut, 403: ErrorOut, 404: ErrorOut}, operation_id='updateClient')
def edit_client(request, client_id: UUID, payload: ClientIn):
    return services.update_client(request.auth, client_id, **payload.model_dump())


@router.get('/vehicles', response={200: list[VehicleOut], 401: ErrorOut, 403: ErrorOut}, operation_id='listVehicles')
def vehicles(request):
    return selectors.list_vehicles(request.auth)


@router.put('/vehicles/{vehicle_id}', response={200: VehicleOut, 400: ErrorOut, 401: ErrorOut, 402: QuotaErrorOut, 403: ErrorOut, 404: ErrorOut}, operation_id='updateVehicle')
def edit_vehicle(request, vehicle_id: UUID, payload: VehicleCreateIn):
    return services.update_vehicle(request.auth, vehicle_id, **payload.model_dump())


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
