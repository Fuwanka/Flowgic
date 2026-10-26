# Redis ускоряет отображение, но не разрешает запись: решение о квоте принимает PostgreSQL под
# транзакционной блокировкой.
"""Freemium rules, subscription writes and Redis-backed usage presentation.

Quota checks deliberately count authoritative rows while the caller holds the
subscription lock. Redis is used for displayed usage; stale/missing cache values
can never grant additional capacity or reject an otherwise valid creation.
"""
from contextlib import contextmanager

from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

from accounts.exceptions import AccountError

from . import selectors
from .exceptions import QuotaExceededError
from .models import CompanySubscription, SubscriptionPlan

USAGE_CACHE_TIMEOUT = 60
DEFAULT_PLANS = {
    SubscriptionPlan.PlanType.FREE: {'name': 'Старт', 'max_vehicles': 3, 'max_orders_per_month': 30, 'iot_enabled': False},
    SubscriptionPlan.PlanType.PRO: {'name': 'Профессиональный', 'max_vehicles': 100, 'max_orders_per_month': 3000, 'iot_enabled': True},
    SubscriptionPlan.PlanType.ENTERPRISE: {'name': 'Корпоративный', 'max_vehicles': None, 'max_orders_per_month': None, 'iot_enabled': True},
}


def _require_company(company):
    if company is None or company.pk is None:
        raise AccountError('Требуется компания.', code='company_required', status=403)


def _require_operator(user):
    if not user.company_id or user.role not in {'dispatcher', 'manager'}:
        raise AccountError('Тарифы доступны диспетчеру и руководителю своей компании.', code='permission_denied', status=403)


@transaction.atomic
def ensure_default_plans():
    for plan_type, defaults in DEFAULT_PLANS.items():
        SubscriptionPlan.objects.get_or_create(plan_type=plan_type, defaults=defaults)


@transaction.atomic
def get_company_subscription(company):
    _require_company(company)
    subscription = selectors.find_company_subscription(company)
    if subscription is not None:
        return subscription
    free_plan, _ = SubscriptionPlan.objects.get_or_create(
        plan_type=SubscriptionPlan.PlanType.FREE,
        defaults=DEFAULT_PLANS[SubscriptionPlan.PlanType.FREE],
    )
    subscription, _ = CompanySubscription.objects.get_or_create(company=company, defaults={'plan': free_plan})
    return selectors.find_company_subscription(company)


@contextmanager
def company_quota_lock(company):
    """Serialize all quota-changing writes for this tenant, including plan changes."""
    _require_company(company)
    with transaction.atomic():
        subscription = get_company_subscription(company)
        locked = CompanySubscription.objects.select_for_update().filter(company=company, pk=subscription.pk).get()
        yield locked


def current_period():
    # timezone.now() is UTC; quotas use UTC calendar months for every company.
    now = timezone.now()
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    end = start.replace(year=start.year + 1, month=1) if start.month == 12 else start.replace(month=start.month + 1)
    return start, end


def usage_cache_key(company, period_start):
    return f'billing:usage:v1:{company.pk}:{period_start:%Y-%m}'


def _authoritative_usage(company, period_start, period_end):
    # Cross-module reads use a public selector; billing never queries logistics models.
    from logistics.selectors import get_company_usage_counts
    return get_company_usage_counts(company, period_start, period_end)


def get_company_usage(company, *, force=False):
    _require_company(company)
    start, end = current_period()
    key = usage_cache_key(company, start)
    counts = None if force else cache.get(key)
    if counts is None:
        counts = _authoritative_usage(company, start, end)
        cache.set(key, counts, timeout=USAGE_CACHE_TIMEOUT)
    return {'vehicles': counts['vehicles'], 'orders': counts['orders'], 'period_start': start, 'period_end': end}


def invalidate_company_usage(company):
    _require_company(company)
    start, _ = current_period()
    cache.delete(usage_cache_key(company, start))


def _check_limit(company, resource, limit_field):
    subscription = get_company_subscription(company)
    limit = getattr(subscription.plan, limit_field)
    if limit is None:
        return
    start, end = current_period()
    current = _authoritative_usage(company, start, end)[resource]
    if current >= limit:
        raise QuotaExceededError(resource=resource, limit=limit, current=current, plan_type=subscription.plan.plan_type)


def check_company_order_limit(company):
    _check_limit(company, 'orders', 'max_orders_per_month')


def check_company_vehicle_limit(company):
    _check_limit(company, 'vehicles', 'max_vehicles')


@transaction.atomic
def set_company_plan(company, plan_type):
    if plan_type not in DEFAULT_PLANS:
        raise AccountError('Неизвестный тариф.', code='invalid_plan')
    ensure_default_plans()
    with company_quota_lock(company) as subscription:
        subscription.plan = SubscriptionPlan.objects.get(plan_type=plan_type)
        subscription.save(update_fields=['plan', 'updated_at'])
        transaction.on_commit(lambda: invalidate_company_usage(company))
    return get_company_subscription(company)


def get_billing_profile(user):
    _require_operator(user)
    subscription = get_company_subscription(user.company)
    return {
        'company_id': user.company_id, 'plan': subscription.plan,
        'usage': get_company_usage(user.company),
    }


def get_available_plans(user):
    _require_operator(user)
    ensure_default_plans()
    return selectors.get_plan_catalog()
