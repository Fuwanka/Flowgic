# Контекст учитывает только собственные финансы и автопарк. Чужие заказы исключаются до формирования
# ответа.
"""Read-only access to the shared/tenant catalog and company click history."""
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db.models import Q
from django.http import Http404

from logistics.selectors import get_company_offer_context

from .exceptions import MarketplaceError
from .models import OfferClickLog, PartnerOffer
from .permissions import require_operator
from .validators import validate_offer_url

CONTEXT_TYPES = frozenset({'dashboard', 'order_detail', 'fleet', 'finance'})


def get_offer_context(company, order_id=None):
    if company is None:
        raise MarketplaceError('Не задана компания.', code='permission_denied', status=403)
    try:
        return get_company_offer_context(company, order_id=order_id)
    except Http404 as error:
        raise MarketplaceError('Заказ не найден.', code='order_not_found', status=404) from error


def _has_safe_url(offer):
    try:
        validate_offer_url(offer.target_url)
    except (ValidationError, ValueError):
        return False
    return True


def _company_catalog(company):
    # Shared catalog rows have no owner. Tenant/demo rows must match the caller.
    return PartnerOffer.objects.filter(
        Q(company__isnull=True) | Q(company=company), active=True,
    ).select_related('company')


def _select_contextual_offers(company, context_type, context):
    if context_type not in CONTEXT_TYPES:
        raise MarketplaceError('Неизвестный контекст предложения.', code='invalid_context')
    order = context['order']
    if context_type == 'order_detail' and order is None:
        raise MarketplaceError('Для карточки заказа требуется order_id.', code='order_required')
    categories = []
    if context_type in {'dashboard', 'order_detail', 'finance'} and context['has_unpaid_financials']:
        categories.append(PartnerOffer.Category.FACTORING)
    if context_type in {'dashboard', 'order_detail', 'fleet'} and context['has_vehicles']:
        categories.extend([PartnerOffer.Category.FUEL, PartnerOffer.Category.TELEMATICS])
    if context_type == 'order_detail':
        categories.append(PartnerOffer.Category.INSURANCE)
    price = (order.agreed_price or Decimal('0.00')) if order is not None else Decimal('0.00')
    offers = _company_catalog(company).filter(category__in=categories).filter(
        ~Q(category=PartnerOffer.Category.INSURANCE) | Q(minimum_order_value__lte=price)
    )[:20]
    return [offer for offer in offers if _has_safe_url(offer)]


def get_contextual_offers(company, context_type, order=None):
    context = get_offer_context(company, order_id=order.pk if order is not None else None)
    return _select_contextual_offers(company, context_type, context)


def get_offers_for_user(user, *, context_type='dashboard', order_id=None):
    require_operator(user)
    context = get_offer_context(user.company, order_id=order_id)
    return _select_contextual_offers(user.company, context_type, context)


def get_active_offer(company, offer_id):
    offer = _company_catalog(company).filter(pk=offer_id).first()
    if offer is None or not _has_safe_url(offer):
        raise MarketplaceError('Предложение не найдено.', code='offer_not_found', status=404)
    return offer


def get_company_clicks(company):
    return OfferClickLog.objects.filter(company=company).select_related('offer', 'order', 'user')
