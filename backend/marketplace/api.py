from uuid import UUID

from ninja import Router, Status

from accounts.authentication import jwt_auth
from accounts.schemas import ErrorOut

from . import selectors, services
from .schemas import ClickIn, ClickOut, ContextType, MarketplaceErrorOut, OfferOut

router = Router(tags=['marketplace'], auth=jwt_auth)


@router.get(
    '/offers', response={200: list[OfferOut], 400: MarketplaceErrorOut, 401: ErrorOut, 403: MarketplaceErrorOut, 404: MarketplaceErrorOut},
    operation_id='getContextualOffers',
)
def offers(request, context_type: ContextType = 'dashboard', order_id: UUID | None = None):
    return selectors.get_offers_for_user(request.auth, context_type=context_type, order_id=order_id)


@router.post(
    '/offers/{offer_id}/click',
    response={201: ClickOut, 400: MarketplaceErrorOut, 401: ErrorOut, 403: MarketplaceErrorOut, 404: MarketplaceErrorOut},
    operation_id='recordOfferClick',
)
def click(request, offer_id: UUID, payload: ClickIn):
    result = services.record_offer_click(request.auth, offer_id=offer_id, **payload.model_dump())
    return Status(201, result)
