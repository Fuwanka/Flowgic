# Идентичность при входе ищется до определения компании; все последующие прикладные чтения
# ограничены tenant.
"""Read-only account queries and data for the legacy dashboards."""
import json

from django.core.serializers.json import DjangoJSONEncoder

from logistics.selectors import get_user_orders

from .models import PasswordResetCode, User
from .security import normalize_email
from .permissions import require_operator


def get_company_drivers(user):
    require_operator(user)
    return User.objects.filter(company=user.company, role=User.Role.Driver).select_related('company').order_by('full_name', 'id')


def find_user_by_email(email):
    # Authentication/reset resolve identity before a tenant is known.
    return User.objects.select_related('company').filter(
        email__iexact=normalize_email(email)
    ).order_by('pk').first()


def find_token_user(user_id):
    if not isinstance(user_id, (str, int)) or isinstance(user_id, bool):
        return None
    try:
        user_id = int(user_id)
        if not 0 < user_id <= 9223372036854775807:
            return None
        return User.objects.select_related('company').filter(
            pk=user_id, is_active=True, status=User.Status.ACTIVE,
            company__isnull=False,
        ).first()
    except (ValueError, TypeError, OverflowError):
        return None


def get_profile(user):
    return User.objects.select_related('company').filter(
        company=user.company, pk=user.pk
    ).get()


def get_latest_reset_code(user):
    return PasswordResetCode.objects.select_related('user').filter(
        user=user
    ).order_by('-created_at', '-pk').first()


def get_home_context(user):
    orders = get_user_orders(user)
    if user.role == User.Role.Driver:
        orders = orders.order_by('is_viewed_by_driver', '-created_at')
    events = [
        {
            'title': f'Заказ {order.order_number}: {order.client.name or "Клиент"}',
            'start': order.pickup_datetime.isoformat(),
            'end': order.delivery_datetime.isoformat(),
            'color': '#3788d8',
            'textColor': 'white',
            'extendedProps': {'cargo': order.cargo_type, 'status': order.get_status_display()},
        }
        for order in orders.filter(
            pickup_datetime__isnull=False, delivery_datetime__isnull=False
        )
    ]
    context = {
        'user': user, 'requests': orders,
        'events_json': json.dumps(events, cls=DjangoJSONEncoder, ensure_ascii=False),
    }
    if user.role == User.Role.Driver:
        context['unread_count'] = orders.filter(is_viewed_by_driver=False).count()
    return context
