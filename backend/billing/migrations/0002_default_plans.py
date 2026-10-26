from django.db import migrations


def seed_plans(apps, schema_editor):
    plan = apps.get_model('billing', 'SubscriptionPlan')
    defaults = {
        'FREE': {'name': 'Старт', 'max_vehicles': 3, 'max_orders_per_month': 30, 'iot_enabled': False},
        'PRO': {'name': 'Профессиональный', 'max_vehicles': 100, 'max_orders_per_month': 3000, 'iot_enabled': True},
        'ENTERPRISE': {'name': 'Корпоративный', 'max_vehicles': None, 'max_orders_per_month': None, 'iot_enabled': True},
    }
    for plan_type, values in defaults.items():
        plan.objects.using(schema_editor.connection.alias).get_or_create(plan_type=plan_type, defaults=values)


class Migration(migrations.Migration):
    dependencies = [('billing', '0001_initial')]
    operations = [migrations.RunPython(seed_plans, migrations.RunPython.noop)]
