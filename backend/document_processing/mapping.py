"""Explicit, conservative bridge from reviewed document fields to an order."""
from decimal import Decimal, InvalidOperation
import re

from .exceptions import ProcessingError

ORDER_FIELDS = ('cargo_type', 'cargo_mass_kg', 'origin', 'destination', 'agreed_price')


def serialize_value(value):
    return None if value is None else str(value)


def order_snapshot(order):
    return {key: serialize_value(getattr(order, key) if not isinstance(order, dict) else order.get(key)) for key in ORDER_FIELDS}


def _decimal(value):
    normalized = re.sub(r'[\s\u00a0\u202f]', '', value).replace(',', '.')
    if not re.fullmatch(r'\d+(?:\.\d+)?', normalized):
        raise ValueError('not a number')
    result = Decimal(normalized)
    if not result.is_finite():
        raise ValueError('not finite')
    return result


def proposed_order_fields(fields, *, strict=False):
    result = {}
    for source, target, limit in [('cargo_description', 'cargo_type', 100), ('loading_address', 'origin', 255), ('unloading_address', 'destination', 255)]:
        value = fields.get(source)
        if value:
            if len(value) > limit:
                if strict:
                    raise ProcessingError(f'Поле {source} длиннее {limit} символов.', code='invalid_order_fields', status=422)
                continue
            result[target] = value
    try:
        mass, unit = fields.get('cargo_mass'), (fields.get('cargo_mass_unit') or '').strip().lower().rstrip('.')
        if mass and unit in {'кг', 'kg', 'т', 't', 'тонн', 'тонна', 'тонны'}:
            kilograms = _decimal(mass) * (1000 if unit not in {'кг', 'kg'} else 1)
            if kilograms <= 0 or kilograms != kilograms.to_integral_value() or kilograms > 2_147_483_647:
                raise ValueError('mass')
            result['cargo_mass_kg'] = int(kilograms)
        elif mass and strict:
            raise ValueError('unit')
        freight = fields.get('freight_amount')
        if freight:
            currency = (fields.get('currency') or '').strip().upper().rstrip('.')
            if currency not in {'RUB', 'РУБ', 'РУБЛЬ', 'РУБЛЕЙ', '₽', '643'}:
                raise ValueError('currency')
            amount = _decimal(freight)
            if amount < 0 or amount > Decimal('99999999.99') or amount != amount.quantize(Decimal('.01')):
                raise ValueError('amount')
            result['agreed_price'] = amount
    except (InvalidOperation, ValueError):
        if strict:
            raise ProcessingError('Проверьте массу, единицу измерения, стоимость перевозки и валюту RUB. Стоимость товара не переносится в цену рейса.', code='invalid_order_fields', status=422)
    return result


def changes_for_order(order, fields):
    current = order_snapshot(order)
    return {key: {'current': current[key], 'proposed': serialize_value(value)} for key, value in proposed_order_fields(fields).items() if current[key] != serialize_value(value)}
