from datetime import datetime
from uuid import UUID

from ninja import Schema

from .models import SubscriptionPlan


class PlanOut(Schema):
    id: int
    plan_type: SubscriptionPlan.PlanType
    name: str
    max_vehicles: int | None
    max_orders_per_month: int | None
    iot_enabled: bool


class UsageOut(Schema):
    vehicles: int
    orders: int
    period_start: datetime
    period_end: datetime


class SubscriptionOut(Schema):
    company_id: UUID
    plan: PlanOut
    usage: UsageOut


class QuotaErrorOut(Schema):
    detail: str
    code: str
    resource: str
    limit: int
    current: int
    plan_type: SubscriptionPlan.PlanType
