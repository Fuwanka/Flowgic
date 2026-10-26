"""Generate editable order drafts using trusted DOCX templates and scoped data."""
from dataclasses import dataclass
from decimal import Decimal
from io import BytesIO
from pathlib import Path
import re

from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone
from docxtpl import DocxTemplate
from jinja2 import StrictUndefined
from jinja2.sandbox import SandboxedEnvironment

from .selectors import get_user_orders

DOCX_CONTENT_TYPE = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
TEMPLATE_DIRECTORY = Path(__file__).resolve().parent / 'document_templates'
DOCUMENT_TEMPLATES = {'application': 'application.docx', 'ttn': 'ttn.docx'}
_INVALID_XML_CHARACTERS = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f]')
NOT_PROVIDED = 'Не указано'


class InvalidDocumentTypeError(ValueError):
    pass


class DocumentDataError(ValueError):
    pass


@dataclass(frozen=True)
class GeneratedOrderDocument:
    content: bytes
    filename: str
    content_type: str = DOCX_CONTENT_TYPE


def _text(value, fallback=NOT_PROVIDED):
    if value is None:
        return fallback
    value = _INVALID_XML_CHARACTERS.sub('', str(value)).strip()
    return value or fallback


def _amount(value):
    if value is None:
        return NOT_PROVIDED
    return f'{Decimal(value):,.2f}'.replace(',', ' ').replace('.', ',')


def _date(value):
    if value is None:
        return NOT_PROVIDED
    return timezone.localtime(value).strftime('%d.%m.%Y %H:%M')


def _address(value):
    if not value:
        return NOT_PROVIDED
    if isinstance(value, dict):
        return ', '.join(
            _text(value[key], '')
            for key in ('postcode', 'region', 'city', 'street', 'building')
            if value.get(key)
        ) or NOT_PROVIDED
    return _text(value)


def _document_context(order):
    company = order.client.company
    driver, vehicle = order.driver, order.vehicle
    # Do not expose data from corrupt legacy assignments across tenant boundaries.
    if driver and (driver.company_id != company.pk or driver.role != 'driver'):
        raise DocumentDataError('Назначенный водитель не относится к компании заказа.')
    if vehicle and vehicle.company_id != company.pk:
        raise DocumentDataError('Назначенный транспорт не относится к компании заказа.')
    return {
        'order_number': _text(order.order_number),
        'order_id': str(order.pk),
        'issued_date': timezone.localdate().strftime('%d.%m.%Y'),
        'company_name': _text(company.name),
        'company_inn': _text(company.inn),
        'company_address': _address(company.address),
        'client_name': _text(order.client.name),
        'client_phone': _text(order.client.phone),
        'client_email': _text(order.client.email),
        'origin': _text(order.origin),
        'destination': _text(order.destination),
        'pickup_datetime': _date(order.pickup_datetime),
        'delivery_datetime': _date(order.delivery_datetime),
        'timezone_name': timezone.get_current_timezone_name(),
        'cargo_type': _text(order.cargo_type),
        'cargo_mass_kg': _text(order.cargo_mass_kg),
        'distance_km': _amount(order.distance_km),
        # agreed_price is the freight charge, not the declared cargo value.
        'agreed_price': _amount(order.agreed_price),
        'vehicle_number': _text(vehicle.reg_number if vehicle else None),
        'vehicle_model': _text(vehicle.model if vehicle else None),
        'vehicle_type': _text(vehicle.type if vehicle else None),
        'vehicle_capacity': _text(vehicle.capacity_kg if vehicle else None),
        'driver_name': _text(driver.full_name if driver else None),
        'driver_phone': _text(driver.phone if driver else None),
        'status': _text(order.get_status_display()),
    }


def generate_order_document(user, order_id, document_type='application'):
    """Return a draft without writing files or document records to shared state."""
    if document_type not in DOCUMENT_TEMPLATES:
        raise InvalidDocumentTypeError('Допустимые типы документа: application и ttn.')
    if (
        not user.is_authenticated or not user.is_active
        or user.status != 'active' or not user.company_id
    ):
        raise Http404('Заказ не найден.')
    order = get_object_or_404(get_user_orders(user), pk=order_id)
    context = _document_context(order)
    template = DocxTemplate(TEMPLATE_DIRECTORY / DOCUMENT_TEMPLATES[document_type])
    environment = SandboxedEnvironment(undefined=StrictUndefined, autoescape=True)
    template.render(context, jinja_env=environment, autoescape=True)
    output = BytesIO()
    template.save(output)
    return GeneratedOrderDocument(
        content=output.getvalue(),
        filename=f'order-{order.order_number.lower()}-{document_type}.docx',
    )
