from django.contrib import admin

from .models import CompanySubscription, SubscriptionPlan


@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(admin.ModelAdmin):
    list_display = ('plan_type', 'name', 'max_vehicles', 'max_orders_per_month', 'iot_enabled')


@admin.register(CompanySubscription)
class CompanySubscriptionAdmin(admin.ModelAdmin):
    list_display = ('company', 'plan', 'updated_at')
    list_select_related = ('company', 'plan')
