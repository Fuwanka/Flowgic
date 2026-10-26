"""One complete HTTP journey through URL routing, middleware, JWT and PostGIS."""
import json
from io import BytesIO
from urllib.request import Request, urlopen
from zipfile import ZipFile

import pytest

from .demo import seed_demo_company
from .models import Order
from marketplace.models import OfferClickLog

pytestmark = [pytest.mark.integration, pytest.mark.django_db(transaction=True)]


def test_demo_billing_marketplace_and_documents_over_http(live_server):
    result = seed_demo_company(slug='http-showroom', password='HTTP-demo-password-42!')

    def request(path, *, body=None, token=None):
        headers = {'Content-Type': 'application/json'}
        if token:
            headers['Authorization'] = f'Bearer {token}'
        req = Request(f'{live_server.url}{path}', data=json.dumps(body).encode() if body is not None else None, headers=headers)
        with urlopen(req, timeout=20) as response:
            return response.status, response.headers, response.read()

    status, _, raw = request('/api/accounts/token', body={
        'email': result.login_emails[1], 'password': 'HTTP-demo-password-42!',
    })
    assert status == 200
    token = json.loads(raw)['access']
    status, _, raw = request('/api/billing/subscription', token=token)
    profile = json.loads(raw)
    assert status == 200 and profile['company_id'] == str(result.company.pk)
    assert profile['usage']['vehicles'] == 3 and profile['plan']['plan_type'] == 'FREE'
    order = Order.objects.filter(client__company=result.company, agreed_price__gte=100000).first()
    status, _, raw = request(f'/api/marketplace/offers?context_type=order_detail&order_id={order.pk}', token=token)
    offers = json.loads(raw)
    assert status == 200 and {o['category'] for o in offers} == {'INSURANCE', 'FACTORING', 'FUEL', 'TELEMATICS'}
    status, _, raw = request(f'/api/marketplace/offers/{offers[0]["id"]}/click', token=token, body={'order_id': str(order.pk)})
    assert status == 201
    assert OfferClickLog.objects.filter(company=result.company, order=order).count() == 1
    for kind in ('application', 'ttn'):
        status, headers, raw = request(f'/api/logistics/orders/{order.pk}/document/docx?document_type={kind}', token=token)
        assert status == 200 and headers['Content-Type'].endswith('wordprocessingml.document')
        assert f'{kind}.docx' in headers['Content-Disposition']
        assert ZipFile(BytesIO(raw)).testzip() is None
