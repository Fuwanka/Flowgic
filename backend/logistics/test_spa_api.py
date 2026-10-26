"""Регрессии SPA-контракта: права, FK, расчёты, пагинация и отсутствие записей при чтении."""
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.utils import timezone
from ninja.testing import TestClient

from accounts.models import User
from accounts.services import login_with_tokens
from flowgic.api import api
from .models import Financial, Order, OrderEvent, Vehicle
from .factories import OrderFactory, VehicleFactory

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.fixture
def operator(dispatcher_a):
    tokens = login_with_tokens(email=dispatcher_a.email, password='testpass123')
    return TestClient(api, headers={'Authorization': f'Bearer {tokens["access"]}'})


def test_lists_search_pagination_and_overview_are_tenant_scoped(operator, order_a, order_b):
    response = operator.get('/logistics/orders?page_size=1')
    assert response.status_code == 200
    body = response.json()
    assert body['total'] == 1 and body['items'][0]['id'] == str(order_a.pk)
    assert operator.get('/logistics/orders?status=completed').json()['items'] == []
    assert operator.get(f'/logistics/orders?q={order_a.order_number}').json()['total'] == 1
    assert operator.get('/logistics/orders?q=NoMatch').json()['total'] == 0
    assert operator.get('/logistics/overview').json()['total'] == 1
    for url in ('/logistics/orders?page=0', '/logistics/orders?page_size=101', '/logistics/orders?status=invalid'):
        assert operator.get(url).status_code == 422


def test_detail_has_resources_and_history_without_writing(operator, order_a, order_b):
    response = operator.get(f'/logistics/orders/{order_a.pk}')
    assert response.status_code == 200
    assert response.json()['financial'] is None
    assert response.json()['vehicle']['id'] == str(order_a.vehicle_id)
    assert not Financial.objects.filter(order=order_a).exists()
    assert operator.get(f'/logistics/orders/{order_b.pk}').status_code == 404


def test_corrupt_legacy_assignment_does_not_leak_resources(operator, order_a, driver_b, vehicle_b):
    order_a.driver, order_a.vehicle = driver_b, vehicle_b
    order_a.save()
    body = operator.get(f'/logistics/orders/{order_a.pk}').json()
    assert body['driver'] is body['vehicle'] is body['driver_id'] is body['vehicle_id'] is None


def test_calendar_validates_range_and_filters_tenant(operator, order_a, order_b):
    start = (order_a.pickup_datetime - timedelta(days=1)).date()
    end = (order_a.delivery_datetime + timedelta(days=1)).date()
    response = operator.get(f'/logistics/calendar?start={start}&end={end}')
    assert response.status_code == 200 and len(response.json()['items']) == 1
    assert operator.get(f'/logistics/calendar?start={end}&end={start}').status_code == 400
    assert operator.get(f'/logistics/calendar?start={start}&end={start + timedelta(days=63)}').status_code == 400


def finance(**changes):
    return {'client_cost': '100000.00', 'driver_cost': '20000.00', 'fuel_expenses': None,
            'third_party_cost': '5000.00', 'payment_status': 'partially_paid', **changes}


def test_financial_preview_read_only_and_save_matches_model(operator, order_a):
    order_a.distance_km = Decimal('123.47')
    order_a.save()
    before = OrderEvent.objects.filter(order=order_a).count()
    url = f'/logistics/orders/{order_a.pk}/financial'
    preview = operator.post(f'{url}/preview', json=finance())
    assert preview.status_code == 200, preview.content
    assert not Financial.objects.filter(order=order_a).exists()
    saved = operator.put(url, json=finance())
    assert saved.status_code == 200, saved.content
    assert saved.json() == preview.json()
    row = Financial.objects.get(order=order_a)
    assert row.profit == Decimal('100000') - Decimal('20000') - Decimal('3037.36')
    assert row.third_party_cost == 5000
    assert OrderEvent.objects.filter(order=order_a).count() == before + 1


def test_financial_save_rolls_back_when_history_fails(operator, order_a):
    with patch('logistics.services.OrderEvent.objects.create', side_effect=RuntimeError('history failed')):
        with pytest.raises(RuntimeError):
            operator.put(f'/logistics/orders/{order_a.pk}/financial', json=finance(fuel_expenses='0.00'))
    assert not Financial.objects.filter(order=order_a).exists()


def test_financial_cross_tenant_and_validation(operator, order_b, order_a):
    assert operator.put(f'/logistics/orders/{order_b.pk}/financial', json=finance()).status_code == 404
    assert operator.put(f'/logistics/orders/{order_a.pk}/financial', json=finance(driver_cost='-1')).status_code == 422
    # Большая отрицательная прибыль не превращается в необработанную ошибку NUMERIC в PostgreSQL.
    assert operator.post(f'/logistics/orders/{order_a.pk}/financial/preview', json=finance(client_cost='0', driver_cost='9999999999.99', fuel_expenses='9999999999.99')).status_code == 400


def test_status_history_and_idempotence(operator, order_a):
    url = f'/logistics/orders/{order_a.pk}/status'
    assert operator.patch(url, json={'status': 'in_transit'}).status_code == 200
    event = OrderEvent.objects.filter(order=order_a).get()
    assert event.event_data['new_status'] == 'in_transit'
    assert operator.patch(url, json={'status': 'in_transit'}).status_code == 200
    assert OrderEvent.objects.filter(order=order_a).count() == 1


def test_directory_isolation_and_writes(operator, client_a, client_b, vehicle_a, vehicle_b, driver_a, driver_b):
    assert [x['id_client'] for x in operator.get('/logistics/clients').json()] == [str(client_a.pk)]
    assert [x['id'] for x in operator.get('/logistics/vehicles').json()] == [str(vehicle_a.pk)]
    assert [x['id'] for x in operator.get('/accounts/drivers').json()] == [driver_a.pk]
    body = {'name': 'Обновлённый клиент', 'email': 'client@example.test', 'phone': None}
    assert operator.put(f'/logistics/clients/{client_b.pk}', json=body).status_code == 404
    assert operator.put(f'/logistics/clients/{client_a.pk}', json=body).json()['name'] == body['name']
    assert operator.patch(f'/accounts/drivers/{driver_b.pk}', json={'full_name': 'Fake', 'status': 'blocked'}).status_code == 404
    assert operator.post('/logistics/clients', json={**body, 'company': str(client_b.company_id)}).status_code == 422


def test_driver_creation_cannot_set_role_or_take_over_email(operator, dispatcher_a):
    body = {'full_name': 'Новый водитель', 'email': 'new-driver@example.test', 'phone': '+70000000000', 'password': 'Driver-password-42!'}
    assert operator.post('/accounts/drivers', json={**body, 'role': 'manager'}).status_code == 422
    response = operator.post('/accounts/drivers', json=body)
    assert response.status_code == 201
    driver = User.objects.get(pk=response.json()['id'])
    assert driver.company == dispatcher_a.company and driver.role == 'driver' and driver.check_password(body['password'])
    assert 'password' not in response.content.decode()
    assert operator.post('/accounts/drivers', json=body).status_code == 409
    assert operator.patch(f'/accounts/drivers/{driver.pk}', json={'full_name': driver.full_name, 'status': 'blocked'}).status_code == 200
    assert TestClient(api).post('/accounts/token', json={'email': driver.email, 'password': body['password']}).status_code == 401


def test_vehicle_edit_cannot_bypass_activation_quota(operator, company_a):
    for _ in range(3):
        VehicleFactory.create(company=company_a)
    blocked = VehicleFactory.create(company=company_a, status='blocked')
    body = {'reg_number': blocked.reg_number, 'type': blocked.type, 'capacity_kg': blocked.capacity_kg, 'status': 'available'}
    assert operator.put(f'/logistics/vehicles/{blocked.pk}', json=body).status_code == 402
    blocked.refresh_from_db()
    assert blocked.status == 'blocked'


def test_order_edit_validates_relations_and_dates(operator, order_a, client_b):
    body = {
        'client_id': str(order_a.client_id), 'driver_id': order_a.driver_id,
        'vehicle_id': str(order_a.vehicle_id), 'cargo_type': 'Обновлённый груз', 'cargo_mass_kg': 2000,
        'origin': 'Красноярск', 'destination': 'Томск', 'status': 'assigned',
        'pickup_datetime': order_a.pickup_datetime.isoformat(), 'delivery_datetime': order_a.delivery_datetime.isoformat(),
        'agreed_price': '150000.00', 'distance_km': '800',
    }
    url = f'/logistics/orders/{order_a.pk}'
    assert operator.put(url, json={**body, 'client_id': str(client_b.pk)}).status_code == 404
    assert operator.put(url, json={**body, 'delivery_datetime': (order_a.pickup_datetime - timedelta(days=1)).isoformat()}).status_code == 400
    response = operator.put(url, json=body)
    assert response.status_code == 200 and response.json()['cargo_type'] == body['cargo_type']
    assert response.json()['events'][0]['event_data']['action'] == 'order_edited'


def test_openapi_has_distinct_order_and_vehicle_enums():
    schemas = api.get_openapi_schema()['components']['schemas']
    assert 'in_transit' in schemas['OrderState']['enum'] and 'available' not in schemas['OrderState']['enum']
    assert 'available' in schemas['VehicleState']['enum'] and 'in_transit' not in schemas['VehicleState']['enum']


@pytest.mark.parametrize('url', ['/logistics/orders', '/logistics/clients', '/logistics/vehicles', '/accounts/drivers', '/logistics/overview'])
def test_spa_directories_and_overview_reject_driver(url, driver_a):
    token = login_with_tokens(email=driver_a.email, password='testpass123')['access']
    assert TestClient(api, headers={'Authorization': f'Bearer {token}'}).get(url).status_code == 403
