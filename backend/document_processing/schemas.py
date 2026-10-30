from datetime import datetime
from typing import Literal
from uuid import UUID

from ninja import Schema
from pydantic import ConfigDict, Field

DocumentType = Literal['tn', 'ttn', 'torg12', 'upd', 'request', 'other']
UploadDocumentType = Literal['auto', 'tn', 'ttn', 'torg12', 'upd', 'request', 'other']


class EvidenceOut(Schema):
    page: int
    bbox: list[float]
    text: str


class ExtractedFieldOut(Schema):
    value: str | None = None
    raw_text: str | None = None
    confidence: float | None = None
    evidence: list[EvidenceOut] = Field(default_factory=list)
    review_required: bool = True


class OrderChangeOut(Schema):
    current: str | None
    proposed: str | None


class ProcessingOut(Schema):
    id: UUID
    order_id: UUID
    status: Literal['queued', 'processing', 'needs_review', 'confirmed', 'failed']
    original_filename: str
    document_type: UploadDocumentType
    version: int
    fields: dict[str, ExtractedFieldOut]
    warnings: list[str]
    error: str | None
    created_at: datetime
    updated_at: datetime
    confirmed_at: datetime | None
    confirmed_by_id: int | None
    engine: str | None
    order_changes: dict[str, OrderChangeOut]


class ProcessingListOut(Schema):
    items: list[ProcessingOut]


class ConfirmIn(Schema):
    model_config = ConfigDict(extra='forbid')
    version: int = Field(ge=1)
    document_type: DocumentType
    fields: dict[str, str | None]
    apply_to_order: bool = False
