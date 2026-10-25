"""Tenant-scoped reads used by the existing template views.

Order has no company field in the legacy schema: its tenant is client.company.
"""
from .models import Order


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
