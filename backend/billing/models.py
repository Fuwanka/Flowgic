from django.db import models


class SubscriptionPlan(models.Model):
    class PlanType(models.TextChoices):
        FREE = 'FREE', 'Бесплатный'
        PRO = 'PRO', 'Профессиональный'
        ENTERPRISE = 'ENTERPRISE', 'Корпоративный'

    plan_type = models.CharField(max_length=20, choices=PlanType.choices, unique=True)
    name = models.CharField(max_length=100)
    max_vehicles = models.PositiveIntegerField(null=True, blank=True, help_text='NULL означает без лимита.')
    max_orders_per_month = models.PositiveIntegerField(null=True, blank=True, help_text='NULL означает без лимита.')
    iot_enabled = models.BooleanField(default=False)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return self.name


class CompanySubscription(models.Model):
    company = models.OneToOneField('logistics.Company', on_delete=models.CASCADE, related_name='billing_subscription')
    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.PROTECT, related_name='subscriptions')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.company_id}: {self.plan_id}'
