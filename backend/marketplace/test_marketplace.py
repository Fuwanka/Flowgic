from decimal import Decimal
from urllib.parse import urlencode
from uuid import uuid4

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from ninja.testing import TestClient

from accounts.services import login_with_tokens
from flowgic.api import api
from logistics.models import Financial, Vehicle

from . import selectors, services
from .exceptions import MarketplaceError
from .models import OfferClickLog, PartnerOffer

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


@pytest.fixture
def catalog():
    return {
        category: PartnerOffer.objects.create(
            slug=f'test-{category.lower()}-{uuid4().hex[:8]}',
            category=category, title=f'Test {category}',
            target_url=f'https://example.com/{category.lower()}',
        )
        for category in PartnerOffer.Category.values
    }


@pytest.fixture
def api_client():
    return TestClient(api)


@pytest.fixture
def headers(dispatcher_a):
    pair = login_with_tokens(email=dispatcher_a.email, password='testpass123')
    return {'Authorization': f'Bearer {pair["access"]}'}


def categories(offers):
    return {offer.category for offer in offers}


def test_dashboard_uses_own_unpaid_finances_and_fleet(company_a, vehicle_a, financial_a, catalog):
    offers = selectors.get_contextual_offers(company_a, 'dashboard')
    assert categories(offers) == {
        PartnerOffer.Category.FACTORING, PartnerOffer.Category.FUEL, PartnerOffer.Category.TELEMATICS,
    }


def test_other_company_finances_and_fleet_do_not_trigger_offers(company_a, order_b, catalog):
    Financial.objects.create(order=order_b, client_cost=Decimal('30000'), driver_cost=Decimal('10000'))
    assert selectors.get_contextual_offers(company_a, 'dashboard') == []


@pytest.mark.parametrize('price,expected', [
    (Decimal('99999.99'), False), (Decimal('100000.00'), True), (Decimal('150000.00'), True),
])
def test_insurance_threshold(company_a, order_a, catalog, price, expected):
    order_a.agreed_price = price
    order_a.save(update_fields=['agreed_price'])
    offers = selectors.get_contextual_offers(company_a, 'order_detail', order=order_a)
    assert (PartnerOffer.Category.INSURANCE in categories(offers)) is expected


def test_insurance_offer_has_configurable_minimum(company_a, order_a, catalog):
    offer = catalog[PartnerOffer.Category.INSURANCE]
    offer.minimum_order_value = Decimal('40000.00')
    offer.save(update_fields=['minimum_order_value'])
    assert offer in selectors.get_contextual_offers(company_a, 'order_detail', order=order_a)


def test_finance_and_fleet_contexts_are_distinct(company_a, financial_a, catalog):
    assert categories(selectors.get_contextual_offers(company_a, 'finance')) == {PartnerOffer.Category.FACTORING}
    assert categories(selectors.get_contextual_offers(company_a, 'fleet')) == {
        PartnerOffer.Category.FUEL, PartnerOffer.Category.TELEMATICS,
    }


def test_paid_finances_do_not_offer_factoring(company_a, financial_a, catalog):
    financial_a.payment_status = Financial.PaymentStatus.PAID
    financial_a.save(update_fields=['payment_status'])
    assert selectors.get_contextual_offers(company_a, 'finance') == []


def test_inactive_and_unsafe_offers_are_not_shown(company_a, vehicle_a, catalog):
    catalog[PartnerOffer.Category.FUEL].active = False
    catalog[PartnerOffer.Category.FUEL].save(update_fields=['active'])
    catalog[PartnerOffer.Category.TELEMATICS].target_url = 'javascript:alert(1)'
    catalog[PartnerOffer.Category.TELEMATICS].save(update_fields=['target_url'])
    assert selectors.get_contextual_offers(company_a, 'fleet') == []


def test_foreign_order_never_selects_offers(company_a, order_b, catalog):
    with pytest.raises(MarketplaceError) as error:
        selectors.get_contextual_offers(company_a, 'order_detail', order=order_b)
    assert error.value.status == 404


def test_shared_and_tenant_catalog_are_isolated(company_a, company_b, vehicle_a, catalog):
    private = PartnerOffer.objects.create(
        slug='private-company-b-fuel', company=company_b,
        category=PartnerOffer.Category.FUEL, title='Private B', target_url='https://example.com/private-b',
    )
    own = PartnerOffer.objects.create(
        slug='private-company-a-fuel', company=company_a,
        category=PartnerOffer.Category.FUEL, title='Private A', target_url='https://example.com/private-a',
    )
    offers = selectors.get_contextual_offers(company_a, 'fleet')
    assert own in offers and catalog[PartnerOffer.Category.FUEL] in offers and private not in offers


def test_contextual_query_count_does_not_grow_with_offer_relations(
    company_a, vehicle_a, catalog, django_assert_max_num_queries,
):
    for index in range(10):
        PartnerOffer.objects.create(
            slug=f'fuel-query-{index}', company=company_a,
            category=PartnerOffer.Category.FUEL, title=f'Fuel {index}',
            target_url=f'https://example.com/fuel/{index}',
        )
    with django_assert_max_num_queries(4):
        offers = selectors.get_contextual_offers(company_a, 'fleet')
        assert all(offer.company is None or offer.company.pk == company_a.pk for offer in offers)


@pytest.mark.parametrize('url', [
    'javascript:alert(1)', 'ftp://example.com/fuel', 'https://user:secret@example.com/fuel',
])
def test_offer_urls_reject_unsupported_schemes_and_embedded_credentials(url):
    offer = PartnerOffer(slug='invalid-url', category=PartnerOffer.Category.FUEL, title='Invalid', target_url=url)
    with pytest.raises(ValidationError):
        offer.full_clean()


def test_demo_offer_requires_company_at_database_level():
    with pytest.raises(IntegrityError), transaction.atomic():
        PartnerOffer.objects.create(
            slug='invalid-global-demo', category=PartnerOffer.Category.FUEL,
            title='Invalid demo', target_url='https://example.com/demo', is_demo=True,
        )


def test_click_is_persisted_for_actor_company(dispatcher_a, vehicle_a, catalog):
    offer = catalog[PartnerOffer.Category.FUEL]
    click = services.record_offer_click(dispatcher_a, offer_id=offer.pk)
    assert click.company_id == dispatcher_a.company_id
    assert click.user_id == dispatcher_a.pk and click.offer_id == offer.pk and click.order_id is None
    assert list(selectors.get_company_clicks(dispatcher_a.company)) == [click]


def test_insurance_click_links_only_own_expensive_order(dispatcher_a, order_a, catalog):
    order_a.agreed_price = Decimal('150000.00')
    order_a.save(update_fields=['agreed_price'])
    click = services.record_offer_click(
        dispatcher_a, offer_id=catalog[PartnerOffer.Category.INSURANCE].pk, order_id=order_a.pk,
    )
    assert click.order_id == order_a.pk and click.company_id == dispatcher_a.company_id


def test_foreign_order_click_is_rejected_without_log(dispatcher_a, order_b, catalog):
    with pytest.raises(MarketplaceError) as error:
        services.record_offer_click(
            dispatcher_a, offer_id=catalog[PartnerOffer.Category.FUEL].pk, order_id=order_b.pk,
        )
    assert error.value.status == 404 and OfferClickLog.objects.count() == 0


def test_foreign_offer_click_is_rejected(dispatcher_a, company_b, vehicle_a):
    offer = PartnerOffer.objects.create(
        slug='other-tenant-offer', company=company_b, category=PartnerOffer.Category.FUEL,
        title='Other tenant', target_url='https://example.com/other',
    )
    with pytest.raises(MarketplaceError) as error:
        services.record_offer_click(dispatcher_a, offer_id=offer.pk)
    assert error.value.status == 404 and OfferClickLog.objects.count() == 0


def test_driver_cannot_record_lead(driver_a, catalog):
    with pytest.raises(MarketplaceError) as error:
        services.record_offer_click(driver_a, offer_id=catalog[PartnerOffer.Category.FUEL].pk)
    assert error.value.status == 403 and OfferClickLog.objects.count() == 0


def test_inactive_click_is_not_logged(dispatcher_a, catalog):
    offer = catalog[PartnerOffer.Category.FUEL]
    offer.active = False
    offer.save(update_fields=['active'])
    with pytest.raises(MarketplaceError) as error:
        services.record_offer_click(dispatcher_a, offer_id=offer.pk)
    assert error.value.status == 404 and OfferClickLog.objects.count() == 0


def test_out_of_context_click_is_not_logged(dispatcher_a, catalog):
    with pytest.raises(MarketplaceError) as error:
        services.record_offer_click(dispatcher_a, offer_id=catalog[PartnerOffer.Category.INSURANCE].pk)
    assert error.value.code == 'offer_unavailable' and OfferClickLog.objects.count() == 0


def test_click_history_is_tenant_scoped(dispatcher_a, dispatcher_b, vehicle_a, vehicle_b, catalog):
    own = services.record_offer_click(dispatcher_a, offer_id=catalog[PartnerOffer.Category.FUEL].pk)
    other = services.record_offer_click(dispatcher_b, offer_id=catalog[PartnerOffer.Category.FUEL].pk)
    assert list(selectors.get_company_clicks(dispatcher_a.company)) == [own]
    assert other not in selectors.get_company_clicks(dispatcher_a.company)


def test_demo_offers_are_idempotent_and_private(company_a, company_b, vehicle_a, vehicle_b):
    company_a.is_demo = True
    company_a.save(update_fields=['is_demo'])
    first = services.seed_demo_offers(company_a)
    second = services.seed_demo_offers(company_a)
    assert [offer.pk for offer in first] == [offer.pk for offer in second]
    assert PartnerOffer.objects.filter(company=company_a).count() == 4
    assert all(offer.is_demo and offer.title.startswith('Демо:') for offer in first)
    assert selectors.get_contextual_offers(company_b, 'fleet') == []
    assert len(selectors.get_contextual_offers(company_a, 'fleet')) == 2


def test_real_company_cannot_be_seeded_with_demo_offers(company_a):
    with pytest.raises(MarketplaceError) as error:
        services.seed_demo_offers(company_a)
    assert error.value.code == 'demo_company_required'
    assert PartnerOffer.objects.count() == 0


def test_demo_seed_never_overwrites_existing_real_catalog(company_a):
    company_a.is_demo = True
    company_a.save(update_fields=['is_demo'])
    slug = f'flowgic-demo-{company_a.pk.hex}-insurance'
    offer = PartnerOffer.objects.create(
        slug=slug, category=PartnerOffer.Category.INSURANCE,
        title='Real catalog', target_url='https://example.com/real',
    )
    with pytest.raises(MarketplaceError) as error:
        services.seed_demo_offers(company_a)
    offer.refresh_from_db()
    assert error.value.status == 409
    assert offer.title == 'Real catalog' and not offer.is_demo and offer.company_id is None


def test_offer_api_context_and_click(api_client, headers, vehicle_a, catalog, dispatcher_a):
    response = api_client.get('/marketplace/offers?context_type=fleet', headers=headers)
    assert response.status_code == 200
    assert {item['category'] for item in response.json()} == {'FUEL', 'TELEMATICS'}
    offer = catalog[PartnerOffer.Category.FUEL]
    response = api_client.post(f'/marketplace/offers/{offer.pk}/click', json={}, headers=headers)
    assert response.status_code == 201 and response.json()['target_url'] == offer.target_url
    assert OfferClickLog.objects.get(pk=response.json()['id']).company_id == dispatcher_a.company_id


def test_offer_api_rejects_foreign_order(api_client, headers, order_b, catalog):
    query = urlencode({
        'context_type': 'order_detail', 'order_id': str(order_b.pk),
    })
    response = api_client.get(f'/marketplace/offers?{query}', headers=headers)
    assert response.status_code == 404 and response.json()['code'] == 'order_not_found'


def test_offer_api_click_rejects_foreign_order(api_client, headers, order_b, catalog):
    offer = catalog[PartnerOffer.Category.FUEL]
    response = api_client.post(f'/marketplace/offers/{offer.pk}/click', json={
        'order_id': str(order_b.pk),
    }, headers=headers)
    assert response.status_code == 404 and OfferClickLog.objects.count() == 0


def test_offer_api_requires_authentication(api_client):
    assert api_client.get('/marketplace/offers').status_code == 401


def test_driver_cannot_read_offer_api(api_client, driver_a):
    pair = login_with_tokens(email=driver_a.email, password='testpass123')
    response = api_client.get('/marketplace/offers', headers={'Authorization': f'Bearer {pair["access"]}'})
    assert response.status_code == 403


def test_offer_api_validates_context_and_order_requirement(api_client, headers):
    assert api_client.get('/marketplace/offers?context_type=unknown', headers=headers).status_code == 422
    response = api_client.get('/marketplace/offers?context_type=order_detail', headers=headers)
    assert response.status_code == 400 and response.json()['code'] == 'order_required'


def test_click_api_rejects_forged_company_field(api_client, headers, vehicle_a, catalog, company_b):
    offer = catalog[PartnerOffer.Category.FUEL]
    response = api_client.post(f'/marketplace/offers/{offer.pk}/click', json={
        'company_id': str(company_b.pk),
    }, headers=headers)
    assert response.status_code == 422 and OfferClickLog.objects.count() == 0
