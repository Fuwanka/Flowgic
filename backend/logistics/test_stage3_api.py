from datetime import timedelta
from io import BytesIO
from unittest.mock import patch
from zipfile import ZipFile

import pytest
from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone
from ninja.testing import TestClient

from accounts.services import login_with_tokens
from billing import services as billing_services
from flowgic.api import api

from . import services
from .factories import OrderFactory, VehicleFactory
from .models import Financial, Order, OrderEvent, Vehicle

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def auth(user):
    pair = login_with_tokens(email=user.email, password='testpass123')
    return {'Authorization': f'Bearer {pair["access"]}'}


def payload(client, **changes):
    return {
        'client_id': str(client.pk), 'cargo_type': 'Оборудование', 'cargo_mass_kg': 2000,
        'origin': 'Красноярск', 'destination': 'Томск', 'agreed_price': '150000.00',
        'pickup_datetime': (timezone.now() + timedelta(days=1)).isoformat(),
        'delivery_datetime': (timezone.now() + timedelta(days=2)).isoformat(), **changes,
    }


def test_order_api_creates_finance_and_event(dispatcher_a, client_a, vehicle_a, driver_a):
    response = TestClient(api).post('/logistics/orders', json=payload(
        client_a, vehicle_id=str(vehicle_a.pk), driver_id=driver_a.pk,
    ), headers=auth(dispatcher_a))
    assert response.status_code == 201, response.content
    order = Order.objects.filter(client__company=dispatcher_a.company).get(pk=response.json()['id'])
    assert order.created_by == dispatcher_a and order.driver == driver_a and order.vehicle == vehicle_a
    assert order.financial.client_cost == order.financial.profit == 150000
    assert OrderEvent.objects.filter(order=order).get().event_data['new_status'] == 'created'


@pytest.mark.parametrize('foreign_field', ['client_id', 'driver_id', 'vehicle_id'])
def test_order_api_rejects_foreign_relations(dispatcher_a, client_a, client_b, driver_b, vehicle_b, foreign_field):
    value = {'client_id': str(client_b.pk), 'driver_id': driver_b.pk, 'vehicle_id': str(vehicle_b.pk)}[foreign_field]
    response = TestClient(api).post('/logistics/orders', json=payload(client_a, **{foreign_field: value}), headers=auth(dispatcher_a))
    assert response.status_code == 404
    assert not Order.objects.filter(client__company=dispatcher_a.company).exists()


def test_monthly_limit_returns_actionable_402_without_partial_writes(dispatcher_a, client_a, vehicle_a, driver_a):
    for _ in range(30):
        OrderFactory.create(client=client_a, created_by=dispatcher_a, driver=driver_a, vehicle=vehicle_a)
    start, _ = billing_services.current_period()
    cache.set(billing_services.usage_cache_key(dispatcher_a.company, start), {'vehicles': 0, 'orders': 0})
    response = TestClient(api).post('/logistics/orders', json=payload(client_a), headers=auth(dispatcher_a))
    assert response.status_code == 402
    assert response.json() == {
        'detail': response.json()['detail'], 'code': 'quota_exceeded', 'resource': 'orders',
        'limit': 30, 'current': 30, 'plan_type': 'FREE',
    }
    assert Order.objects.filter(client__company=dispatcher_a.company).count() == 30
    assert not Financial.objects.filter(order__client__company=dispatcher_a.company).exists()
    assert not OrderEvent.objects.filter(order__client__company=dispatcher_a.company).exists()
    billing_services.invalidate_company_usage(dispatcher_a.company)


def test_order_creation_rolls_back_on_event_failure(dispatcher_a, client_a):
    with patch('logistics.services.OrderEvent.objects.create', side_effect=RuntimeError('event failed')):
        with pytest.raises(RuntimeError):
            services.create_order(dispatcher_a, **{**payload(client_a), 'pickup_datetime': timezone.now(), 'delivery_datetime': timezone.now() + timedelta(days=1)})
    assert not Order.objects.filter(client__company=dispatcher_a.company).exists()
    assert not Financial.objects.filter(order__client__company=dispatcher_a.company).exists()


def test_vehicle_limit_applies_to_api_and_legacy_activation(dispatcher_a, company_a, client):
    active = [VehicleFactory.create(company=company_a) for _ in range(3)]
    api_client = TestClient(api)
    headers = auth(dispatcher_a)
    data = {'reg_number': 'ДЕМО-API', 'type': 'Фура', 'capacity_kg': 20000}
    assert api_client.post('/logistics/vehicles', json=data, headers=headers).status_code == 402
    response = api_client.post('/logistics/vehicles', json={**data, 'status': 'blocked'}, headers=headers)
    assert response.status_code == 201
    blocked_id = response.json()['id']
    assert api_client.patch(f'/logistics/vehicles/{blocked_id}/status', json={'status': 'available'}, headers=headers).status_code == 402
    client.force_login(dispatcher_a)
    assert client.post(reverse('vehicle_update_status', args=[blocked_id]), {'status': 'available'}).status_code == 402
    assert api_client.patch(f'/logistics/vehicles/{active[0].pk}/status', json={'status': 'blocked'}, headers=headers).status_code == 200
    assert api_client.patch(f'/logistics/vehicles/{blocked_id}/status', json={'status': 'available'}, headers=headers).status_code == 200
    assert Vehicle.objects.filter(company=company_a).exclude(status='blocked').count() == 3


def test_legacy_forms_cannot_bypass_limits(dispatcher_a, client_a, vehicle_a, driver_a, client):
    for _ in range(30):
        OrderFactory.create(client=client_a, created_by=dispatcher_a, driver=driver_a, vehicle=vehicle_a)
    for _ in range(2):
        VehicleFactory.create(company=dispatcher_a.company)
    client.force_login(dispatcher_a)
    data = payload(client_a)
    data['client'] = data.pop('client_id')
    data.update(status='created', driver=driver_a.pk, vehicle=str(vehicle_a.pk))
    response = client.post(reverse('new_request'), data)
    assert response.status_code == 402, response.context['form'].errors if response.context else response.content
    response = client.post(reverse('create_vehicle'), {'reg_number': 'TEST4', 'type': 'Фура', 'capacity_kg': 10000, 'status': 'available'})
    assert response.status_code == 402


def test_driver_cannot_create_orders_or_vehicles(driver_a, client_a):
    client = TestClient(api)
    headers = auth(driver_a)
    assert client.post('/logistics/orders', json=payload(client_a), headers=headers).status_code == 403
    assert client.post('/logistics/vehicles', json={'reg_number': 'TEST', 'type': 'Фура', 'capacity_kg': 1000}, headers=headers).status_code == 403


@pytest.mark.parametrize('kind', ['application', 'ttn'])
def test_docx_http_contract_and_tenant_isolation(dispatcher_a, dispatcher_b, order_a, kind):
    client = TestClient(api)
    url = f'/logistics/orders/{order_a.pk}/document/docx?document_type={kind}'
    assert client.get(url).status_code == 401
    assert client.get(url, headers=auth(dispatcher_b)).status_code == 404
    response = client.get(url, headers=auth(dispatcher_a))
    assert response.status_code == 200
    assert response['Content-Type'] == 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    assert f'{kind}.docx' in response['Content-Disposition']
    # NinjaResponse has already consumed the streaming iterator into content.
    content = response.content
    xml = ZipFile(BytesIO(content)).read('word/document.xml').decode()
    assert order_a.client.name in xml and '{{' not in xml


def test_legacy_docx_links_and_download(dispatcher_a, order_a, client):
    client.force_login(dispatcher_a)
    response = client.get(reverse('request_detail', args=[order_a.pk]))
    download_url = reverse('download_order_document', args=[order_a.pk, 'ttn'])
    assert download_url.encode() in response.content
    assert client.get(download_url).status_code == 200


def test_openapi_describes_docx_as_binary():
    schema = api.get_openapi_schema()
    content = schema['paths']['/api/logistics/orders/{order_id}/document/docx']['get']['responses'][200]['content']
    mime = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    assert content == {mime: {'schema': {'type': 'string', 'format': 'binary'}}}
