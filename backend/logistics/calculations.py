"""Чистые расчёты: модель, предпросмотр и сохранение используют одну формулу."""
from decimal import Decimal


def calculate_financials(*, client_cost, driver_cost, fuel_expenses, distance_km):
    # None означает автоподсчёт; явный ноль пользователь может сохранить вручную.
    if fuel_expenses is None:
        fuel_expenses = max(distance_km or Decimal('0'), Decimal('0')) / 100 * Decimal('30') * Decimal('82')
    fuel_expenses = Decimal(fuel_expenses)
    # Сохраняем историческое правило: сторонние расходы хранятся отдельно.
    return {'fuel_expenses': fuel_expenses, 'profit': Decimal(client_cost) - Decimal(driver_cost) - fuel_expenses}
