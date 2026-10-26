from datetime import datetime, timedelta, timezone as datetime_timezone
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier
from unittest.mock import patch

import pytest
from django.core.cache import cache
from django.db import close_old_connections, connection, connections, transaction
from django.utils import timezone
from ninja.testing import TestClient

from accounts.services import login_with_tokens
from flowgic.api import api
from logistics.models import Order, Vehicle

from . import services
from .exceptions import QuotaExceededError
from .models import CompanySubscription, SubscriptionPlan

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.fixture(autouse=True)
def isolated_usage_cache(monkeypatch):
    """Exercise the configured Redis backend without touching other tenants' keys."""
    original = services.usage_cache_key
    keys = set()

    def track_key(*args):
        key = original(*args)
        keys.add(key)
        return key

    monkeypatch.setattr(services, 'usage_cache_key', track_key)
    yield
    if keys:
        cache.delete_many(keys)


def create_orders(client, dispatcher, count, *, created_at=None):
    now = timezone.now()
    orders = [Order(
        client=client, created_by=dispatcher, cargo_type=f'Груз {index}',
        cargo_mass_kg=1000, origin='Москва', destination='Казань',
        agreed_price=Decimal('50000.00'), pickup_datetime=now + timedelta(days=1),
        delivery_datetime=now + timedelta(days=2),
    ) for index in range(count)]
    Order.objects.bulk_create(orders)
    if created_at is not None:
        Order.objects.filter(client__company=client.company, pk__in=[order.pk for order in orders]).update(created_at=created_at)
    return orders


def create_vehicles(company, count, *, status=Vehicle.Status.AVAILABLE):
    return Vehicle.objects.bulk_create([Vehicle(
        company=company, reg_number=f'TEST-{index}-{status}', type='Фура',
        capacity_kg=20000, status=status,
    ) for index in range(count)])


def test_lazy_free_subscription_defaults_and_idempotency(company_a):
    first = services.get_company_subscription(company_a)
    second = services.get_company_subscription(company_a)
    assert first.pk == second.pk
    assert CompanySubscription.objects.filter(company=company_a).count() == 1
    assert first.plan.plan_type == SubscriptionPlan.PlanType.FREE
    assert first.plan.max_vehicles == 3 and first.plan.max_orders_per_month == 30
    assert first.plan.iot_enabled is False


def test_catalog_preserves_custom_limits(company_a):
    services.ensure_default_plans()
    plan = SubscriptionPlan.objects.get(plan_type='FREE')
    plan.max_orders_per_month = 17
    plan.save(update_fields=['max_orders_per_month'])
    services.ensure_default_plans()
    assert SubscriptionPlan.objects.get(plan_type='FREE').max_orders_per_month == 17
    assert set(SubscriptionPlan.objects.values_list('plan_type', flat=True)) == {'FREE', 'PRO', 'ENTERPRISE'}


def test_vehicle_limit_boundary_and_structured_exception(company_a):
    create_vehicles(company_a, 2)
    with services.company_quota_lock(company_a):
        services.check_company_vehicle_limit(company_a)
    create_vehicles(company_a, 1, status=Vehicle.Status.IN_TRIP)
    with services.company_quota_lock(company_a):
        with pytest.raises(QuotaExceededError) as caught:
            services.check_company_vehicle_limit(company_a)
    payload = caught.value.as_dict()
    assert payload['code'] == 'quota_exceeded' and payload['resource'] == 'vehicles'
    assert payload['limit'] == 3 and payload['current'] == 3 and payload['plan_type'] == 'FREE'


def test_blocked_vehicles_do_not_consume_active_quota(company_a):
    create_vehicles(company_a, 3, status=Vehicle.Status.BLOCKED)
    services.check_company_vehicle_limit(company_a)
    assert services.get_company_usage(company_a, force=True)['vehicles'] == 0


def test_monthly_order_limit_boundary(company_a, client_a, dispatcher_a):
    create_orders(client_a, dispatcher_a, 29)
    with services.company_quota_lock(company_a):
        services.check_company_order_limit(company_a)
    create_orders(client_a, dispatcher_a, 1)
    with services.company_quota_lock(company_a):
        with pytest.raises(QuotaExceededError) as caught:
            services.check_company_order_limit(company_a)
    assert caught.value.resource == 'orders' and caught.value.current == 30


def test_cached_zero_cannot_bypass_actual_vehicle_quota(company_a):
    cached = services.get_company_usage(company_a)
    assert cached['vehicles'] == 0
    create_vehicles(company_a, 3)
    # Deliberately stale display count must not authorize a fourth active vehicle.
    assert services.get_company_usage(company_a)['vehicles'] == 0
    with services.company_quota_lock(company_a):
        with pytest.raises(QuotaExceededError):
            services.check_company_vehicle_limit(company_a)


def test_stale_high_count_cannot_block_valid_creation(company_a):
    start, _ = services.current_period()
    cache.set(services.usage_cache_key(company_a, start), {'vehicles': 99, 'orders': 99}, timeout=60)
    with services.company_quota_lock(company_a):
        services.check_company_vehicle_limit(company_a)
        services.check_company_order_limit(company_a)


def test_usage_cache_round_trip_and_invalidation(company_a):
    start, _ = services.current_period()
    assert services.get_company_usage(company_a)['vehicles'] == 0
    assert cache.get(services.usage_cache_key(company_a, start)) == {'vehicles': 0, 'orders': 0}
    create_vehicles(company_a, 1)
    assert services.get_company_usage(company_a)['vehicles'] == 0
    services.invalidate_company_usage(company_a)
    assert cache.get(services.usage_cache_key(company_a, start)) is None
    assert services.get_company_usage(company_a)['vehicles'] == 1


def test_usage_and_subscription_isolated_by_company(company_a, company_b, client_a, dispatcher_a):
    create_vehicles(company_a, 3)
    create_orders(client_a, dispatcher_a, 30)
    assert services.get_company_usage(company_a)['orders'] == 30
    assert services.get_company_usage(company_b)['orders'] == 0
    with services.company_quota_lock(company_b):
        services.check_company_order_limit(company_b)
        services.check_company_vehicle_limit(company_b)
    assert services.get_company_subscription(company_a).company_id == company_a.pk
    assert services.get_company_subscription(company_b).company_id == company_b.pk


def test_orders_from_previous_month_and_next_month_excluded(company_a, client_a, dispatcher_a):
    now = datetime(2026, 12, 15, tzinfo=datetime_timezone.utc)
    with patch('billing.services.timezone.now', return_value=now):
        start, end = services.current_period()
        assert start == datetime(2026, 12, 1, tzinfo=datetime_timezone.utc)
        assert end == datetime(2027, 1, 1, tzinfo=datetime_timezone.utc)
        create_orders(client_a, dispatcher_a, 1, created_at=start - timedelta(microseconds=1))
        create_orders(client_a, dispatcher_a, 1, created_at=start)
        create_orders(client_a, dispatcher_a, 1, created_at=end - timedelta(microseconds=1))
        create_orders(client_a, dispatcher_a, 1, created_at=end)
        assert services.get_company_usage(company_a, force=True)['orders'] == 2


def test_cache_rolls_over_with_calendar_month(company_a):
    first = datetime(2026, 12, 31, 23, 59, tzinfo=datetime_timezone.utc)
    second = datetime(2027, 1, 1, tzinfo=datetime_timezone.utc)
    with patch('billing.services.timezone.now', return_value=first):
        december = services.get_company_usage(company_a)
        old_key = services.usage_cache_key(company_a, december['period_start'])
        cache.set(old_key, {'vehicles': 7, 'orders': 30}, timeout=60)
    with patch('billing.services.timezone.now', return_value=second):
        january = services.get_company_usage(company_a)
        new_key = services.usage_cache_key(company_a, january['period_start'])
    assert old_key != new_key and january['orders'] == 0 and january['vehicles'] == 0


def test_plan_assignment_is_tenant_scoped_and_unlimited_enterprise(company_a, company_b):
    create_vehicles(company_a, 4)
    pro = services.set_company_plan(company_a, 'PRO')
    assert pro.plan.iot_enabled is True and pro.plan.max_vehicles == 100
    services.check_company_vehicle_limit(company_a)
    assert services.get_company_subscription(company_b).plan.plan_type == 'FREE'
    enterprise = services.set_company_plan(company_a, 'ENTERPRISE')
    assert enterprise.plan.max_vehicles is None and enterprise.plan.max_orders_per_month is None
    services.check_company_vehicle_limit(company_a)
    services.check_company_order_limit(company_a)


def test_invalid_plan_and_missing_company_rejected(company_a):
    from accounts.exceptions import AccountError
    with pytest.raises(AccountError):
        services.set_company_plan(company_a, 'UNKNOWN')
    with pytest.raises(AccountError):
        services.get_company_subscription(None)


def test_quota_context_uses_postgres_and_atomic_transaction(company_a):
    assert connection.vendor == 'postgresql'
    with services.company_quota_lock(company_a) as subscription:
        assert connection.in_atomic_block
        assert subscription.company_id == company_a.pk


@pytest.fixture
def billing_client(dispatcher_a):
    pair = login_with_tokens(email=dispatcher_a.email, password='testpass123')
    return TestClient(api, headers={'Authorization': f'Bearer {pair["access"]}'})


def test_subscription_api_returns_only_authenticated_company(billing_client, company_a, company_b):
    services.set_company_plan(company_b, 'ENTERPRISE')
    response = billing_client.get(f'/billing/subscription?company_id={company_b.pk}')
    assert response.status_code == 200
    data = response.json()
    assert data['company_id'] == str(company_a.pk) and data['plan']['plan_type'] == 'FREE'
    assert data['usage']['orders'] == 0 and data['usage']['vehicles'] == 0


def test_catalog_api_has_three_plans(billing_client):
    response = billing_client.get('/billing/plans')
    assert response.status_code == 200
    assert {plan['plan_type'] for plan in response.json()} == {'FREE', 'PRO', 'ENTERPRISE'}


def test_billing_api_requires_jwt_and_rejects_driver(driver_a):
    anonymous = TestClient(api)
    assert anonymous.get('/billing/subscription').status_code == 401
    pair = login_with_tokens(email=driver_a.email, password='testpass123')
    driver = TestClient(api, headers={'Authorization': f'Bearer {pair["access"]}'})
    assert driver.get('/billing/subscription').status_code == 403
    assert driver.get('/billing/plans').status_code == 403


def test_plan_change_rollback_preserves_subscription(company_a):
    services.get_company_subscription(company_a)
    with pytest.raises(RuntimeError):
        with transaction.atomic():
            services.set_company_plan(company_a, 'PRO')
            raise RuntimeError('cancel change')
    assert services.get_company_subscription(company_a).plan.plan_type == 'FREE'


@pytest.mark.django_db(transaction=True)
def test_concurrent_vehicle_creations_share_one_remaining_slot(company_a):
    create_vehicles(company_a, 2)
    services.get_company_subscription(company_a)
    ready = Barrier(2)

    def create_one(index):
        close_old_connections()
        try:
            ready.wait(timeout=10)
            with services.company_quota_lock(company_a):
                services.check_company_vehicle_limit(company_a)
                Vehicle.objects.create(
                    company=company_a, reg_number=f'CONCURRENT-{index}',
                    type='Фура', capacity_kg=20000,
                )
            return 'created'
        except QuotaExceededError:
            return 'quota'
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [future.result(timeout=20) for future in [pool.submit(create_one, i) for i in range(2)]]
    assert sorted(results) == ['created', 'quota']
    assert Vehicle.objects.filter(company=company_a).count() == 3
