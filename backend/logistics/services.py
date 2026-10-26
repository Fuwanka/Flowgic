"""Public write operations used by account onboarding and legacy forms."""
from django.core.exceptions import PermissionDenied
from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404

from accounts.models import User
from billing import services as billing_services

from .models import Client, Company, Financial, Order, OrderEvent, Vehicle


@transaction.atomic
def create_company(*, name, company_type=Company.Type.LOGISTICS):
    # Onboarding always creates a new tenant; a name is never proof of membership.
    company = Company(name=name, type=company_type)
    company.full_clean()
    company.save()
    billing_services.get_company_subscription(company)
    return company


def _require_operator(user):
    if not user.is_authenticated or not user.is_active or user.status != 'active' or not user.company_id or user.role not in {'dispatcher', 'manager'}:
        raise PermissionDenied('Создание доступно диспетчеру или руководителю своей компании.')


@transaction.atomic
def create_client(user, **data):
    _require_operator(user)
    client = Client(company=user.company, **data)
    client.full_clean()
    client.save()
    return client


@transaction.atomic
def create_vehicle(user, **data):
    _require_operator(user)
    with billing_services.company_quota_lock(user.company):
        if data.get('status', Vehicle.Status.AVAILABLE) != Vehicle.Status.BLOCKED:
            billing_services.check_company_vehicle_limit(user.company)
        vehicle = Vehicle(company=user.company, **data)
        vehicle.full_clean()
        vehicle.save()
        transaction.on_commit(lambda: billing_services.invalidate_company_usage(user.company))
    return vehicle


@transaction.atomic
def update_vehicle_status(user, vehicle_id, status):
    _require_operator(user)
    if status not in Vehicle.Status.values:
        raise ValidationError('Некорректный статус транспорта.')
    with billing_services.company_quota_lock(user.company):
        vehicle = get_object_or_404(Vehicle.objects.filter(company=user.company), pk=vehicle_id)
        if vehicle.status == Vehicle.Status.BLOCKED and status != Vehicle.Status.BLOCKED:
            billing_services.check_company_vehicle_limit(user.company)
        vehicle.status = status
        vehicle.save(update_fields=['status'])
        transaction.on_commit(lambda: billing_services.invalidate_company_usage(user.company))
    return vehicle


@transaction.atomic
def create_order(user, *, client_id, driver_id=None, vehicle_id=None, **data):
    _require_operator(user)
    allowed = {
        'cargo_type', 'cargo_mass_kg', 'origin', 'destination', 'status',
        'pickup_datetime', 'delivery_datetime', 'agreed_price', 'distance_km',
    }
    if set(data) - allowed:
        raise ValidationError('Недопустимые поля заказа.')
    client = get_object_or_404(Client.objects.filter(company=user.company).select_related('company'), pk=client_id)
    driver = None if driver_id is None else get_object_or_404(
        User.objects.filter(company=user.company, role=User.Role.Driver, is_active=True, status=User.Status.ACTIVE), pk=driver_id,
    )
    vehicle = None if vehicle_id is None else get_object_or_404(
        Vehicle.objects.filter(company=user.company).exclude(status=Vehicle.Status.BLOCKED), pk=vehicle_id,
    )
    with billing_services.company_quota_lock(user.company):
        billing_services.check_company_order_limit(user.company)
        order = Order(client=client, driver=driver, vehicle=vehicle, created_by=user, **data)
        order.full_clean()
        order.save()
        financial = Financial(
            order=order, client_cost=order.agreed_price or 0, driver_cost=0,
            fuel_expenses=0, third_party_cost=0,
        )
        # Existing Financial.save() computes profit before the non-null check.
        financial.save()
        OrderEvent.objects.create(
            order=order, event_type=OrderEvent.EventType.STATUS_CHANGED,
            event_data={'old_status': None, 'new_status': order.status, 'actor_id': user.pk},
        )
        transaction.on_commit(lambda: billing_services.invalidate_company_usage(user.company))
    return order
