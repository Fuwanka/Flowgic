from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from accounts.models import User
from accounts.exceptions import AccountError
from billing.models import CompanySubscription
from marketplace.models import PartnerOffer

from .demo import demo_company_id, seed_demo_company
from .models import Client, Company, Financial, Order, OrderEvent, Vehicle

pytestmark = [pytest.mark.integration, pytest.mark.django_db]
PASSWORD = 'Demo-test-password-42!'


def test_demo_contains_realistic_relations_finances_and_offers():
    result = seed_demo_company(password=PASSWORD)
    company = result.company
    assert result.created and result.generated_password is None and company.demo_seeded_at
    assert User.objects.filter(company=company).count() == 5
    assert all(u.check_password(PASSWORD) for u in User.objects.filter(company=company))
    assert Client.objects.filter(company=company).count() == 4
    assert Vehicle.objects.filter(company=company).count() == 3
    orders = Order.objects.filter(client__company=company).select_related('client', 'driver', 'vehicle', 'financial')
    assert orders.count() == 12
    assert len({o.status for o in orders}) == 8
    for order in orders:
        assert order.driver.company_id == order.vehicle.company_id == company.pk
        assert order.delivery_datetime > order.pickup_datetime
        finance = order.financial
        assert finance.profit == finance.client_cost - finance.driver_cost - finance.fuel_expenses
        assert finance.fuel_expenses > 0 and finance.profit > 0
    assert OrderEvent.objects.filter(order__client__company=company).count() == 24
    assert PartnerOffer.objects.filter(company=company, is_demo=True).count() == 4
    assert CompanySubscription.objects.get(company=company).plan.plan_type == 'FREE'


def test_repeat_preserves_edits_passwords_and_plan():
    first = seed_demo_company(password=PASSWORD, orders=2, plan_type='PRO')
    client = Client.objects.filter(company=first.company).first()
    client.name = 'Изменено во время презентации'
    client.save()
    second = seed_demo_company(password='Ignored-new-password-42!', orders=20)
    client.refresh_from_db()
    assert not second.created and second.generated_password is None
    assert client.name == 'Изменено во время презентации'
    assert Order.objects.filter(client__company=first.company).count() == 2
    assert CompanySubscription.objects.get(company=first.company).plan.plan_type == 'PRO'
    assert User.objects.get(email=first.login_emails[0]).check_password(PASSWORD)
    seed_demo_company(plan_type='ENTERPRISE')
    assert CompanySubscription.objects.get(company=first.company).plan.plan_type == 'ENTERPRISE'


def test_live_company_collision_is_never_reused():
    company = Company.objects.create(id_company=demo_company_id('flowgic-demo'), name='Live company')
    with pytest.raises(ValueError, match='обычной компанией'):
        seed_demo_company(password=PASSWORD)
    company.refresh_from_db()
    assert not company.is_demo and company.name == 'Live company'
    assert not CompanySubscription.objects.filter(company=company).exists()


def test_email_collision_rolls_back_everything(company_a, dispatcher_a):
    dispatcher_a.email = 'driver3+flowgic-demo@demo.example.test'
    dispatcher_a.save()
    with pytest.raises(AccountError, match='email уже занят'):
        seed_demo_company(password=PASSWORD)
    assert not Company.objects.filter(demo_slug='flowgic-demo').exists()
    assert User.objects.filter(company=company_a).count() == 1
    dispatcher_a.refresh_from_db()
    assert dispatcher_a.company_id == company_a.pk and dispatcher_a.check_password('testpass123')


def test_seed_failure_is_atomic():
    with patch('logistics.demo.seed_demo_offers', side_effect=RuntimeError('catalog failure')):
        with pytest.raises(RuntimeError, match='catalog failure'):
            seed_demo_company(password=PASSWORD, orders=1)
    assert not Company.objects.filter(is_demo=True).exists()
    assert not User.objects.filter(email__endswith='@demo.example.test').exists()
    assert not Financial.objects.exists()


@pytest.mark.parametrize('options', [{'slug': '../live'}, {'orders': 0}, {'orders': 101}, {'orders': 31}, {'plan_type': 'UNKNOWN'}])
def test_invalid_seed_is_rejected_without_rows(options):
    with pytest.raises(ValueError):
        seed_demo_company(password=PASSWORD, **options)
    assert not Company.objects.filter(is_demo=True).exists()


def test_existing_unfinished_data_is_not_overwritten(company_a):
    company = Company.objects.create(id_company=demo_company_id('flowgic-demo'), name='Demo', is_demo=True, demo_slug='flowgic-demo')
    Client.objects.create(company=company, name='Already entered')
    with pytest.raises(ValueError, match='содержит данные'):
        seed_demo_company(password=PASSWORD)
    assert Client.objects.filter(company=company).get().name == 'Already entered'


def test_command_uses_environment_without_echoing_password(monkeypatch):
    monkeypatch.setenv('FLOWGIC_TEST_DEMO_PASSWORD', PASSWORD)
    output = StringIO()
    call_command('seed_demo_company', orders=1, password_env='FLOWGIC_TEST_DEMO_PASSWORD', stdout=output)
    assert PASSWORD not in output.getvalue()
    assert 'Создана' in output.getvalue()
    output = StringIO()
    call_command('seed_demo_company', stdout=output)
    assert 'Уже существует' in output.getvalue() and 'демо-пароля:' not in output.getvalue()


def test_command_generated_password_printed_only_on_first_seed():
    output = StringIO()
    call_command('seed_demo_company', orders=1, stdout=output)
    generated = output.getvalue().split('демо-пароля: ')[1].strip()
    assert len(generated) >= 24
    assert User.objects.get(email='manager+flowgic-demo@demo.example.test').check_password(generated)
    output = StringIO()
    call_command('seed_demo_company', stdout=output)
    assert generated not in output.getvalue()


def test_command_missing_password_variable_fails(monkeypatch):
    monkeypatch.delenv('FLOWGIC_TEST_DEMO_PASSWORD', raising=False)
    with pytest.raises(CommandError, match='не задана'):
        call_command('seed_demo_company', password_env='FLOWGIC_TEST_DEMO_PASSWORD')
