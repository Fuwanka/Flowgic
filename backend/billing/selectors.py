# Селекторы не создают FREE-подписку: ленивое подключение и любые записи остаются в публичных
# сервисах.
"""Read-only queries; a caller must supply its already-authorized company."""
from .models import CompanySubscription, SubscriptionPlan


def find_company_subscription(company):
    return CompanySubscription.objects.filter(company=company).select_related('plan', 'company').first()


def get_plan_catalog():
    return SubscriptionPlan.objects.all().order_by('id')
