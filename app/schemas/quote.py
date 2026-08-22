"""Schemas Pydantic para Cotizaciones (Quotes)."""
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.quote import QuoteStatus


# ── Items ─────────────────────────────────────────────────
class QuoteItemBase(BaseModel):
    product_id: Optional[UUID] = None
    product_name: str = Field(..., min_length=1, max_length=200)
    product_sku: Optional[str] = Field(None, max_length=60)
    description: Optional[str] = None
    quantity: int = Field(1, ge=1)
    unit_price_cents: int = Field(..., ge=0)
    discount_cents: int = Field(0, ge=0)


class QuoteItemCreate(QuoteItemBase):
    pass


class QuoteItemOut(QuoteItemBase):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    total_cents: int


# ── Quote ─────────────────────────────────────────────────
class QuoteBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    customer_id: Optional[UUID] = None
    branch_id: Optional[UUID] = None
    recipient_name: str = Field(..., min_length=1, max_length=200)
    recipient_email: Optional[str] = Field(None, max_length=255)
    recipient_phone: Optional[str] = Field(None, max_length=40)
    notes: Optional[str] = None
    terms: Optional[str] = None
    valid_until: Optional[datetime] = None
    discount_cents: int = Field(0, ge=0)
    tax_cents: int = Field(0, ge=0)
    items: list[QuoteItemCreate] = Field(default_factory=list)


class QuoteCreate(QuoteBase):
    pass


class QuoteUpdate(BaseModel):
    title: Optional[str] = None
    customer_id: Optional[UUID] = None
    branch_id: Optional[UUID] = None
    recipient_name: Optional[str] = None
    recipient_email: Optional[str] = None
    recipient_phone: Optional[str] = None
    notes: Optional[str] = None
    terms: Optional[str] = None
    valid_until: Optional[datetime] = None
    discount_cents: Optional[int] = None
    tax_cents: Optional[int] = None
    items: Optional[list[QuoteItemCreate]] = None


class QuoteListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    number: str
    title: str
    status: QuoteStatus
    recipient_name: str
    recipient_email: Optional[str] = None
    total_cents: int
    currency: str
    valid_until: Optional[datetime] = None
    created_at: datetime
    sent_at: Optional[datetime] = None


class QuoteOut(QuoteBase):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    number: str
    status: QuoteStatus
    subtotal_cents: int
    total_cents: int
    currency: str
    public_token: str
    sent_at: Optional[datetime] = None
    viewed_at: Optional[datetime] = None
    accepted_at: Optional[datetime] = None
    rejected_at: Optional[datetime] = None
    converted_order_id: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime
    items: list[QuoteItemOut] = Field(default_factory=list)


class QuoteStats(BaseModel):
    total: int
    by_status: dict[str, int]
    total_value_cents: int
    acceptance_rate: float
    draft_value_cents: int
    accepted_value_cents: int
