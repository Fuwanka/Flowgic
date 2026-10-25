"""Public write operations used by account onboarding and legacy forms."""
from django.core.exceptions import PermissionDenied
from django.db import transaction

from .models import Client, Company, Vehicle


@transaction.atomic
def create_company(*, name, company_type=Company.Type.LOGISTICS):
    # Onboarding always creates a new tenant; a name is never proof of membership.
    company = Company(name=name, type=company_type)
    company.full_clean()
    company.save()
    return company


def _require_operator(user):
    if not user.company_id or user.role not in {'dispatcher', 'manager'}:
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
    vehicle = Vehicle(company=user.company, **data)
    vehicle.full_clean()
    vehicle.save()
    return vehicle
