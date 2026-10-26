# У Order нет прямого company: изоляция проходит через client__company; у Financial/Event — через
# order__client__company.
"""Tenant-scoped reads used by the existing template views.

Order has no company field in the legacy schema: its tenant is client.company.
"""
from django.shortcuts import get_object_or_404
from django.db.models import Count, Q, Sum
from django.utils import timezone
from django.core.exceptions import ValidationError
from decimal import Decimal
from datetime import datetime, time
from accounts.permissions import require_operator

from .models import Client, Financial, Order, OrderEvent, Vehicle


def order_row(order):
    """Не выдаём чужие ресурсы даже при повреждённой старой FK-связи."""
    company_id = order.client.company_id
    driver = order.driver if order.driver and order.driver.company_id == company_id else None
    vehicle = order.vehicle if order.vehicle and order.vehicle.company_id == company_id else None
    return {
        **{field: getattr(order, field) for field in (
            'id', 'order_number', 'client_id', 'cargo_type', 'cargo_mass_kg', 'status', 'agreed_price',
            'origin', 'destination', 'pickup_datetime', 'delivery_datetime', 'distance_km', 'created_at', 'updated_at',
        )},
        'client': order.client, 'driver': driver, 'vehicle': vehicle,
        'driver_id': driver.pk if driver else None, 'vehicle_id': vehicle.pk if vehicle else None,
        'financial': getattr(order, 'financial', None),
    }


def list_orders(user, *, status=None, q='', page=1, page_size=20):
    require_operator(user)
    orders = get_user_orders(user)
    if status:
        orders = orders.filter(status=status)
    if q.strip():
        search = q.strip()
        orders = orders.filter(Q(client__name__icontains=search) | Q(cargo_type__icontains=search)
                               | Q(origin__icontains=search) | Q(destination__icontains=search)
                               | Q(id__icontains=search))
    total = orders.count()
    return {'items': [order_row(o) for o in orders.order_by('-created_at', '-id')[(page - 1) * page_size:page * page_size]],
            'total': total, 'page': page, 'page_size': page_size}


def get_order_detail(user, order_id):
    order = get_object_or_404(get_user_orders(user), pk=order_id)
    # Последние 100 событий удерживают размер ответа ограниченным без N+1.
    events = OrderEvent.objects.filter(order__client__company=user.company, order=order).order_by('-created_at', '-pk')[:100]
    return {**order_row(order), 'events': list(events), 'delay_reason': order.delay_reason, 'planned_route': order.planned_route}


def get_overview(user):
    require_operator(user)
    orders = get_user_orders(user)
    closed = [Order.Status.COMPLETED, Order.Status.CANCELLED, Order.Status.DELIVERED]
    counts = orders.aggregate(
        total=Count('pk'), active=Count('pk', filter=~Q(status__in=closed)),
        completed=Count('pk', filter=Q(status=Order.Status.COMPLETED)),
        overdue=Count('pk', filter=Q(delivery_datetime__lt=timezone.now()) & ~Q(status__in=closed)),
    )
    start = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    # Это сумма выставленных перевозок месяца, а не сумма полученных платежей.
    revenue = Financial.objects.filter(order__client__company=user.company, order__created_at__gte=start).aggregate(total=Sum('client_cost'))['total']
    return {**counts, 'monthly_revenue': revenue or Decimal('0')}


def get_calendar(user, *, start, end):
    require_operator(user)
    if end <= start or (end - start).days > 62:
        raise ValidationError('Выберите интервал календаря от 1 до 62 дней.')
    first = timezone.make_aware(datetime.combine(start, time.min))
    last = timezone.make_aware(datetime.combine(end, time.min))
    orders = list(get_user_orders(user).filter(pickup_datetime__lt=last, delivery_datetime__gte=first).order_by('pickup_datetime', 'id')[:1001])
    return {'items': [order_row(o) for o in orders[:1000]], 'truncated': len(orders) > 1000}


def list_clients(user):
    require_operator(user)
    return Client.objects.filter(company=user.company).select_related('company').order_by('name', 'pk')


def list_vehicles(user):
    require_operator(user)
    return Vehicle.objects.filter(company=user.company).select_related('company').order_by('reg_number', 'pk')


def get_user_orders(user):
    orders = Order.objects.select_related(
        'client__company', 'driver', 'vehicle', 'created_by', 'financial'
    )
    if not user.is_authenticated or not user.company_id:
        return orders.none()
    orders = orders.filter(client__company=user.company)
    if user.role == 'driver':
        return orders.filter(driver=user)
    if user.role in {'dispatcher', 'manager'}:
        return orders
    return orders.none()


def get_company_usage_counts(company, period_start, period_end):
    return {
        'vehicles': Vehicle.objects.filter(company=company).exclude(status=Vehicle.Status.BLOCKED).count(),
        'orders': Order.objects.filter(
            client__company=company, created_at__gte=period_start, created_at__lt=period_end
        ).count(),
    }


def get_company_offer_context(company, order_id=None):
    order = None
    if order_id is not None:
        order = get_object_or_404(
            Order.objects.filter(client__company=company).select_related(
                'client__company', 'driver', 'vehicle', 'financial'
            ), pk=order_id,
        )
    return {
        'order': order,
        'has_unpaid_financials': Financial.objects.filter(
            order__client__company=company,
            payment_status__in=[Financial.PaymentStatus.UNPAID, Financial.PaymentStatus.PARTIALLY_PAID],
            client_cost__gt=0,
        ).exists(),
        'has_vehicles': Vehicle.objects.filter(company=company).exclude(status=Vehicle.Status.BLOCKED).exists(),
    }
