import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = [('logistics', '0008_remove_financial_payment_plan')]
    operations = [
        migrations.CreateModel(
            name='SubscriptionPlan',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('plan_type', models.CharField(choices=[('FREE', 'Бесплатный'), ('PRO', 'Профессиональный'), ('ENTERPRISE', 'Корпоративный')], max_length=20, unique=True)),
                ('name', models.CharField(max_length=100)),
                ('max_vehicles', models.PositiveIntegerField(blank=True, help_text='NULL означает без лимита.', null=True)),
                ('max_orders_per_month', models.PositiveIntegerField(blank=True, help_text='NULL означает без лимита.', null=True)),
                ('iot_enabled', models.BooleanField(default=False)),
            ],
            options={'ordering': ['id']},
        ),
        migrations.CreateModel(
            name='CompanySubscription',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('company', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='billing_subscription', to='logistics.company')),
                ('plan', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='subscriptions', to='billing.subscriptionplan')),
            ],
        ),
    ]
