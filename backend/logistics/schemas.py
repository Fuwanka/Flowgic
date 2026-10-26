from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from ninja import Schema
from pydantic import AwareDatetime, Field

from accounts.schemas import InputSchema

from .models import Order, Vehicle


class OrderCreateIn(InputSchema):
    client_id: UUID
    driver_id: int | None = Field(default=None, gt=0)
    vehicle_id: UUID | None = None
    cargo_type: str = Field(min_length=1, max_length=100)
    cargo_mass_kg: int = Field(ge=0, le=2147483647)
    origin: str | None = Field(default=None, max_length=255)
    destination: str | None = Field(default=None, max_length=255)
    status: Order.Status = Order.Status.CREATED
    pickup_datetime: AwareDatetime
    delivery_datetime: AwareDatetime
    agreed_price: Decimal | None = Field(default=None, ge=0, max_digits=10, decimal_places=2)
    distance_km: Decimal | None = Field(default=None, ge=0, max_digits=8, decimal_places=2)


class OrderOut(Schema):
    id: UUID
    client_id: UUID
    driver_id: int | None
    vehicle_id: UUID | None
    cargo_type: str
    status: Order.Status
    agreed_price: Decimal | None
    created_at: datetime


class VehicleCreateIn(InputSchema):
    reg_number: str = Field(min_length=1, max_length=20)
    type: str = Field(min_length=1, max_length=50)
    model: str | None = Field(default=None, max_length=100)
    capacity_kg: int = Field(ge=0, le=2147483647)
    last_maintenance: date | None = None
    status: Vehicle.Status = Vehicle.Status.AVAILABLE


class VehicleStatusIn(InputSchema):
    status: Vehicle.Status


class VehicleOut(Schema):
    id: UUID
    reg_number: str
    type: str
    capacity_kg: int
    status: Vehicle.Status
