# Запись заказа и истории атомарна. Квота проверяется через billing под общей блокировкой подписки
# компании.
"""Public write operations used by account onboarding and legacy forms."""
from django.core.exceptions import PermissionDenied
from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404

from accounts.models import User
from billing import services as billing_services

from .models import Client, Company, Financial, Order, OrderEvent, Vehicle
from . import selectors
from .calculations import calculate_financials
from decimal import Decimal, ROUND_HALF_UP


def _validate_dates(data):
    if data['delivery_datetime'] < data['pickup_datetime']:
        raise ValidationError('Доставка не может быть раньше погрузки.')


@transaction.atomic
def update_client(user, client_id, **data):
    _require_operator(user)
    client = get_object_or_404(Client.objects.filter(company=user.company).select_for_update(), pk=client_id)
    for field in ('name', 'phone', 'email'):
        setattr(client, field, data[field])
    client.full_clean()
    client.save(update_fields=['name', 'phone', 'email'])
    return client


@transaction.atomic
def update_vehicle(user, vehicle_id, **data):
    _require_operator(user)
    # Общая блокировка с созданием: редактирование не обходит лимит активации.
    with billing_services.company_quota_lock(user.company):
        vehicle = get_object_or_404(Vehicle.objects.filter(company=user.company), pk=vehicle_id)
        if vehicle.status == 'blocked' and data['status'] != 'blocked':
            billing_services.check_company_vehicle_limit(user.company)
        for field, value in data.items():
            setattr(vehicle, field, value)
        vehicle.full_clean()
        vehicle.save()
        transaction.on_commit(lambda: billing_services.invalidate_company_usage(user.company), robust=True)
    return vehicle


def _order_relations(user, *, client_id, driver_id=None, vehicle_id=None):
    return {
        'client': get_object_or_404(Client.objects.filter(company=user.company).select_related('company'), pk=client_id),
        'driver': None if driver_id is None else get_object_or_404(
            User.objects.filter(company=user.company, role=User.Role.Driver, status='active', is_active=True), pk=driver_id),
        'vehicle': None if vehicle_id is None else get_object_or_404(
            Vehicle.objects.filter(company=user.company).exclude(status='blocked'), pk=vehicle_id),
    }


@transaction.atomic
def update_order(user, order_id, **data):
    _require_operator(user)
    _validate_dates(data)
    order = get_object_or_404(Order.objects.filter(client__company=user.company).select_for_update(), pk=order_id)
    relations = _order_relations(user, **{key: data.pop(key) for key in ('client_id', 'driver_id', 'vehicle_id')})
    old_status = order.status
    for field, value in {**data, **relations}.items():
        setattr(order, field, value)
    order.full_clean()
    order.save()
    OrderEvent.objects.create(order=order, event_type=OrderEvent.EventType.STATUS_CHANGED, event_data={
        'action': 'order_edited', 'old_status': old_status, 'new_status': order.status, 'actor_id': user.pk,
    })
    return selectors.get_order_detail(user, order.pk)


@transaction.atomic
def change_order_status(user, order_id, *, status, delay_reason=None):
    _require_operator(user)
    order = get_object_or_404(Order.objects.filter(client__company=user.company).select_for_update(), pk=order_id)
    old_status = order.status
    if status not in Order.Status.values:
        raise ValidationError('Некорректный статус заказа.')
    if old_status != status or delay_reason != order.delay_reason:
        order.status, order.delay_reason = status, delay_reason
        order.save(update_fields=['status', 'delay_reason', 'updated_at'])
        OrderEvent.objects.create(order=order, event_type=OrderEvent.EventType.STATUS_CHANGED, event_data={
            'old_status': old_status, 'new_status': status, 'actor_id': user.pk,
        })
    return selectors.get_order_detail(user, order.pk)


def _financial_values(order, data):
    result = calculate_financials(client_cost=data['client_cost'], driver_cost=data['driver_cost'],
                                  fuel_expenses=data['fuel_expenses'], distance_km=order.distance_km)
    # NUMERIC PostgreSQL округляет до копеек. Предпросмотр показывает тот же итог.
    result = {key: value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP) for key, value in result.items()}
    for key, value in result.items():
        Financial._meta.get_field(key).clean(value, Financial())
    return {**data, **result}


def preview_financials(user, order_id, **data):
    _require_operator(user)
    order = get_object_or_404(Order.objects.filter(client__company=user.company).select_related('client'), pk=order_id)
    return _financial_values(order, data)


@transaction.atomic
def save_financials(user, order_id, **data):
    _require_operator(user)
    # Блокируем заказ: даже отсутствующая финансовая строка создаётся один раз.
    order = get_object_or_404(Order.objects.filter(client__company=user.company).select_for_update(), pk=order_id)
    _financial_values(order, data)
    financial = Financial.objects.filter(order__client__company=user.company, order=order).first() or Financial(order=order)
    old_status = financial.payment_status
    for field, value in data.items():
        setattr(financial, field, value)
    financial.save()
    # Читаем округлённый PostgreSQL результат через явный tenant-фильтр.
    financial = Financial.objects.filter(order__client__company=user.company, pk=financial.pk).get()
    OrderEvent.objects.create(order=order, event_type=OrderEvent.EventType.PAYMENT_UPDATED, event_data={
        'action': 'financials_updated', 'actor_id': user.pk, 'old_status': old_status,
        'new_status': financial.payment_status, 'profit': str(financial.profit),
    })
    return financial


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
    _validate_dates(data)
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
