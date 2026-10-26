"""Atomic, repeatable demo data provisioning; never resets existing tenant data."""
import re
import secrets
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from uuid import NAMESPACE_URL, uuid5

from django.db import transaction
from django.utils import timezone

from accounts.services import provision_demo_users
from billing import services as billing_services
from marketplace.services import seed_demo_offers

from .factories import ClientFactory, FinancialFactory, OrderEventFactory, OrderFactory, VehicleFactory
from .models import Client, Company, Order, OrderEvent, Vehicle


@dataclass(frozen=True)
class DemoSeedResult:
    company: Company
    created: bool
    generated_password: str | None
    login_emails: tuple[str, ...]


def demo_company_id(slug):
    return uuid5(NAMESPACE_URL, f'https://flowgic.example.test/demo/{slug}')


@transaction.atomic
def seed_demo_company(*, slug='flowgic-demo', name='Flowgic · Демо-перевозки',
                      orders=12, plan_type=None, password=None):
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,39}', slug):
        raise ValueError('Slug: от 1 до 40 строчных латинских букв, цифр или дефисов.')
    if not isinstance(orders, int) or not 1 <= orders <= 100:
        raise ValueError('Количество заказов должно быть от 1 до 100.')
    if not name.strip() or len(name) > 255:
        raise ValueError('Название компании: от 1 до 255 символов.')
    if plan_type is not None and plan_type not in billing_services.DEFAULT_PLANS:
        raise ValueError('Неизвестный тариф.')
    company, _ = Company.objects.get_or_create(
        id_company=demo_company_id(slug),
        defaults={'name': name, 'inn': '0000000000', 'is_demo': True, 'demo_slug': slug,
                  'address': {'city': 'Красноярск', 'street': 'Демонстрационная', 'building': '1'}},
    )
    company = Company.objects.select_for_update(no_key=True).get(pk=company.pk)
    if not company.is_demo or company.demo_slug != slug:
        raise ValueError('Идентификатор занят обычной компанией. Данные не изменены.')
    emails = tuple(f'{key}+{slug}@demo.example.test' for key in ('manager', 'dispatcher', 'driver1', 'driver2', 'driver3'))
    if company.demo_seeded_at:
        if plan_type is not None:
            billing_services.set_company_plan(company, plan_type)
        return DemoSeedResult(company, False, None, emails)
    if Client.objects.filter(company=company).exists() or Vehicle.objects.filter(company=company).exists() or Order.objects.filter(client__company=company).exists():
        raise ValueError('Демо-компания уже содержит данные. Автоматическая перезапись запрещена.')
    subscription = billing_services.set_company_plan(company, plan_type or 'FREE')
    if subscription.plan.max_orders_per_month is not None and orders > subscription.plan.max_orders_per_month:
        raise ValueError('Количество демонстрационных заказов превышает месячный лимит выбранного тарифа.')
    if subscription.plan.max_vehicles is not None and subscription.plan.max_vehicles < 3:
        raise ValueError('Демо-набор требует тариф с лимитом не менее 3 транспортных средств.')
    generated_password = secrets.token_urlsafe(24) if password is None else None
    users = provision_demo_users(company, password=password or generated_password)
    clients = [ClientFactory.create(
        company=company, name=f'Демо: {title}', phone='+70000000000', email=f'client{i}@{slug}.example.test',
    ) for i, title in enumerate(('Сибирский лес', 'Ангара Продукт', 'Стройкомплект', 'Енисей Снабжение'), 1)]
    vehicles = [VehicleFactory.create(
        company=company, reg_number=f'ДЕМО-{i:03d}', model=model, type=kind, capacity_kg=capacity,
        status=Vehicle.Status.IN_TRIP if i < 3 else Vehicle.Status.AVAILABLE,
        last_maintenance=timezone.localdate() - timedelta(days=20 + i),
    ) for i, (model, kind, capacity) in enumerate([
        ('Volvo FH', 'Тент', 20000), ('Scania R450', 'Рефрижератор', 20000), ('ГАЗ Next', 'Фургон', 5000),
    ], 1)]
    routes = [
        ('Красноярск', 'Новосибирск', 'Пиломатериалы', 800, 125000),
        ('Новосибирск', 'Кемерово', 'Продукты питания', 260, 85000),
        ('Красноярск', 'Иркутск', 'Стройматериалы', 1060, 210000),
        ('Томск', 'Красноярск', 'Оборудование', 960, 165000),
        ('Абакан', 'Красноярск', 'Промышленные товары', 420, 95000),
        ('Иркутск', 'Новосибирск', 'Упаковка', 1850, 290000),
    ]
    statuses = [Order.Status.COMPLETED, Order.Status.DELIVERED, Order.Status.IN_TRANSIT,
                Order.Status.LOADING, Order.Status.ASSIGNED, Order.Status.CREATED,
                Order.Status.DELAYED, Order.Status.CANCELLED]
    now = timezone.now().replace(minute=0, second=0, microsecond=0)
    for i in range(orders):
        origin, destination, cargo, distance, price = routes[i % len(routes)]
        status = statuses[i % len(statuses)]
        vehicle = vehicles[i % 3]
        pickup = now + timedelta(days=(-4 if status in {Order.Status.COMPLETED, Order.Status.DELIVERED} else i % 4 - 1))
        order = OrderFactory.create(
            client=clients[i % 4], created_by=users['dispatcher'], driver=users[f'driver{i % 3 + 1}'],
            vehicle=vehicle, status=status, cargo_type=cargo, cargo_mass_kg=min(12000, vehicle.capacity_kg - 1000),
            origin=origin, destination=destination, agreed_price=Decimal(price), distance_km=Decimal(distance),
            pickup_datetime=pickup, delivery_datetime=pickup + timedelta(days=2),
            planned_route=f'{origin} → {destination}',
            delay_reason='Демо: ожидание разгрузки' if status == Order.Status.DELAYED else None,
        )
        created_at = min(pickup - timedelta(days=2), now)
        Order.objects.filter(client__company=company, pk=order.pk).update(created_at=created_at)
        FinancialFactory.create(
            order=order, client_cost=Decimal(price), driver_cost=Decimal(price) * Decimal('0.25'),
            third_party_cost=Decimal('2500.00'), fuel_expenses=None,
            payment_status=['paid', 'unpaid', 'partially_paid'][i % 3],
        )
        for moment, old, new in [(created_at, None, 'created'), (min(pickup, now), 'created', status)]:
            event = OrderEventFactory.create(order=order, event_data={
                'old_status': old, 'new_status': new, 'actor_id': users['dispatcher'].pk, 'demo': True,
            })
            OrderEvent.objects.filter(order__client__company=company, pk=event.pk).update(created_at=moment)
    seed_demo_offers(company)
    company.demo_seeded_at = timezone.now()
    company.save(update_fields=['demo_seeded_at'])
    transaction.on_commit(lambda: billing_services.invalidate_company_usage(company))
    return DemoSeedResult(company, True, generated_password, emails)
