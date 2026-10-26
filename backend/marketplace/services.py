from decimal import Decimal

from django.db import transaction

from . import selectors
from .exceptions import MarketplaceError
from .models import OfferClickLog, PartnerOffer
from .permissions import require_operator


@transaction.atomic
def record_offer_click(user, *, offer_id, order_id=None):
    require_operator(user)
    offer = selectors.get_active_offer(user.company, offer_id)
    context = selectors.get_offer_context(user.company, order_id=order_id)
    order = context['order']
    available = {
        PartnerOffer.Category.INSURANCE: (
            order is not None and (order.agreed_price or Decimal('0.00')) >= offer.minimum_order_value
        ),
        PartnerOffer.Category.FACTORING: context['has_unpaid_financials'],
        PartnerOffer.Category.FUEL: context['has_vehicles'],
        PartnerOffer.Category.TELEMATICS: context['has_vehicles'],
    }
    if not available.get(offer.category, False):
        raise MarketplaceError('Предложение недоступно в текущем контексте.', code='offer_unavailable')
    return OfferClickLog.objects.create(
        company=user.company, user=user, offer=offer, order=order,
    )


@transaction.atomic
def seed_demo_offers(company):
    """Create only reserved tenant-scoped demo rows; never overwrite catalog data."""
    if company is None or not company.pk or not getattr(company, 'is_demo', False):
        raise MarketplaceError('Для демо-предложений требуется демонстрационная компания.', code='demo_company_required')
    catalog = [
        (PartnerOffer.Category.INSURANCE, 'Страхование груза', 'insurance', 10),
        (PartnerOffer.Category.FACTORING, 'Факторинг', 'factoring', 20),
        (PartnerOffer.Category.FUEL, 'Топливная карта', 'fuel', 30),
        (PartnerOffer.Category.TELEMATICS, 'Подключение телематики', 'telematics', 40),
    ]
    result = []
    for category, title, suffix, priority in catalog:
        slug = f'flowgic-demo-{company.pk.hex}-{suffix}'
        data = {
            'category': category, 'title': f'Демо: {title}',
            'description': 'Демонстрационное предложение. Реальный партнёр не подключён.',
            'target_url': f'https://example.com/flowgic-demo/{suffix}',
            'company': company, 'is_demo': True, 'priority': priority,
            'minimum_order_value': Decimal('100000.00') if category == PartnerOffer.Category.INSURANCE else Decimal('0.00'),
        }
        candidate = PartnerOffer(slug=slug, **data)
        candidate.full_clean(validate_unique=False)
        offer, _ = PartnerOffer.objects.get_or_create(slug=slug, defaults=data)
        if not offer.is_demo or offer.company_id != company.pk:
            raise MarketplaceError('Служебный slug занят реальным предложением.', code='demo_slug_conflict', status=409)
        result.append(offer)
    return result
