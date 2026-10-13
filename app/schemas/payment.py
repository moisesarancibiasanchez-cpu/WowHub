"""Schemas para Payment."""
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.payment import PaymentMethod, PaymentStatus


class PaymentCreate(BaseModel):
    order_id: UUID
    method: PaymentMethod = PaymentMethod.MERCADO_PAGO
    notes: Optional[str] = None


class PaymentListItem(BaseModel):
    id: UUID
    order_id: UUID
    method: PaymentMethod
    status: PaymentStatus
    amount_cents: int
    currency: str
    provider: str
    created_at: datetime


class PaymentOut(BaseModel):
    id: UUID
    tenant_id: UUID
    order_id: UUID
    method: PaymentMethod
    status: PaymentStatus
    amount_cents: int
    fee_cents: int
    net_cents: int
    currency: str
    provider: str
    provider_payment_id: Optional[str] = None
    provider_preference_id: Optional[str] = None
    init_point: Optional[str] = None
    paid_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    created_at: datetime


class PaymentConfirm(BaseModel):
    paid: bool = True
    notes: Optional[str] = None
