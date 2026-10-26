"""Общий RBAC для управления справочником водителей."""
from .exceptions import AccountError


def require_operator(user):
    if (not user.is_authenticated or not user.is_active or user.status != 'active'
            or not user.company_id or user.role not in {'dispatcher', 'manager'}):
        raise AccountError('Доступно диспетчеру или руководителю своей компании.', code='permission_denied', status=403)
