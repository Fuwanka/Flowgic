"""Tenant-scoped reads used by the existing template views.

Order has no company field in the legacy schema: its tenant is client.company.
"""
from django.shortcuts import get_object_or_404

from .models import Financial, Order, Vehicle


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
