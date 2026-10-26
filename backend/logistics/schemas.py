# Схемы описывают контракт SPA, а не таблицы целиком. Уникальные имена enum сохраняют корректность
# OpenAPI/TypeScript.
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from ninja import Schema
from pydantic import AwareDatetime, Field, field_validator

from accounts.schemas import InputSchema

from .models import Financial, Order, Vehicle
from accounts.schemas import DriverOut
from typing import Any
from enum import StrEnum

# У вложенных Django-enum одинаковое имя Status. Явные имена исключают коллизии
# OpenAPI-компонентов между заказом, машиной и аккаунтом при генерации SDK.
OrderState = StrEnum('OrderState', {value.name: value.value for value in Order.Status})
VehicleState = StrEnum('VehicleState', {value.name: value.value for value in Vehicle.Status})


class ClientIn(InputSchema):
    name: str = Field(min_length=1, max_length=255)
    phone: str | None = Field(default=None, max_length=20)
    email: str | None = Field(default=None, max_length=254)

    @field_validator('name')
    @classmethod
    def nonblank_name(cls, value):
        if not value.strip():
            raise ValueError('Укажите название клиента.')
        return value.strip()


class ClientOut(Schema):
    id_client: UUID
    name: str
    phone: str | None
    email: str | None


class OrderCreateIn(InputSchema):
    client_id: UUID
    driver_id: int | None = Field(default=None, gt=0)
    vehicle_id: UUID | None = None
    cargo_type: str = Field(min_length=1, max_length=100)
    cargo_mass_kg: int = Field(ge=0, le=2147483647)
    origin: str | None = Field(default=None, max_length=255)
    destination: str | None = Field(default=None, max_length=255)
    status: OrderState = OrderState.CREATED
    pickup_datetime: AwareDatetime
    delivery_datetime: AwareDatetime
    agreed_price: Decimal | None = Field(default=None, ge=0, max_digits=10, decimal_places=2)
    distance_km: Decimal | None = Field(default=None, ge=0, max_digits=8, decimal_places=2)

    @field_validator('cargo_type')
    @classmethod
    def nonblank_cargo(cls, value):
        if not value.strip():
            raise ValueError('Укажите груз.')
        return value.strip()


class OrderOut(Schema):
    id: UUID
    client_id: UUID
    driver_id: int | None
    vehicle_id: UUID | None
    cargo_type: str
    status: OrderState
    agreed_price: Decimal | None
    created_at: datetime


class VehicleCreateIn(InputSchema):
    reg_number: str = Field(min_length=1, max_length=20)
    type: str = Field(min_length=1, max_length=50)
    model: str | None = Field(default=None, max_length=100)
    capacity_kg: int = Field(ge=0, le=2147483647)
    last_maintenance: date | None = None
    status: VehicleState = VehicleState.AVAILABLE

    @field_validator('reg_number', 'type')
    @classmethod
    def nonblank_vehicle(cls, value):
        if not value.strip():
            raise ValueError('Укажите номер и тип транспорта.')
        return value.strip()


class VehicleStatusIn(InputSchema):
    status: VehicleState


class VehicleOut(Schema):
    id: UUID
    reg_number: str
    type: str
    capacity_kg: int
    status: VehicleState
    model: str | None
    last_maintenance: date | None


class FinancialIn(InputSchema):
    client_cost: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    driver_cost: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    third_party_cost: Decimal = Field(default=Decimal('0'), ge=0, max_digits=12, decimal_places=2)
    fuel_expenses: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    payment_status: Financial.PaymentStatus = Financial.PaymentStatus.UNPAID


class FinancialOut(Schema):
    client_cost: Decimal
    driver_cost: Decimal
    third_party_cost: Decimal | None
    fuel_expenses: Decimal
    profit: Decimal
    payment_status: Financial.PaymentStatus


class OrderRowOut(OrderOut):
    order_number: str
    client: ClientOut
    driver: DriverOut | None
    vehicle: VehicleOut | None
    cargo_mass_kg: int
    origin: str | None
    destination: str | None
    pickup_datetime: datetime
    delivery_datetime: datetime
    distance_km: Decimal | None
    financial: FinancialOut | None
    updated_at: datetime


class EventOut(Schema):
    id: UUID
    event_type: str
    event_data: dict[str, Any] | None
    created_at: datetime


class OrderDetailOut(OrderRowOut):
    events: list[EventOut]
    delay_reason: str | None
    planned_route: str | None


class OrderPageOut(Schema):
    items: list[OrderRowOut]
    total: int
    page: int
    page_size: int


class OverviewOut(Schema):
    total: int
    active: int
    completed: int
    overdue: int
    monthly_revenue: Decimal


class CalendarOut(Schema):
    items: list[OrderRowOut]
    truncated: bool


class OrderUpdateIn(OrderCreateIn):
    """Полное редактирование карточки; принадлежность компании не принимается."""


class OrderStatusIn(InputSchema):
    status: OrderState
    delay_reason: str | None = Field(default=None, max_length=255)
