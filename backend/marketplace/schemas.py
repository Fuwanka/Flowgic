from datetime import datetime
from typing import Literal
from uuid import UUID

from ninja import Schema
from pydantic import ConfigDict

from .models import PartnerOffer

ContextType = Literal['dashboard', 'order_detail', 'fleet', 'finance']


class OfferOut(Schema):
    id: UUID
    category: PartnerOffer.Category
    title: str
    description: str
    target_url: str
    is_demo: bool


class ClickIn(Schema):
    model_config = ConfigDict(extra='forbid')
    order_id: UUID | None = None


class ClickOut(Schema):
    id: UUID
    offer_id: UUID
    order_id: UUID | None
    created_at: datetime
    target_url: str

    @staticmethod
    def resolve_target_url(obj):
        return obj.offer.target_url


class MarketplaceErrorOut(Schema):
    detail: str
    code: str
