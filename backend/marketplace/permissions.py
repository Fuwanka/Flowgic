from .exceptions import MarketplaceError


def require_operator(user):
    if (
        not user.is_authenticated or not user.is_active or user.status != 'active'
        or not user.company_id or user.role not in {'dispatcher', 'manager'}
    ):
        raise MarketplaceError(
            'Предложения доступны диспетчеру и руководителю своей компании.',
            code='permission_denied', status=403,
        )
