"""Schemas para PaymentRecord y DebtAdjustment (HU_56, HU_57)."""
from __future__ import annotations
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class PaymentRecordCreate(BaseModel):
    """HU_56 — registrar pago manual (efectivo/transfer)."""
    customer_id: UUID
    order_id: Optional[UUID] = None
    amount_cents: int = Field(..., gt=0, le=10_000_000_00)  # max $10M CLP
    payment_method: str = Field("cash", pattern="^(cash|transfer|credit|debit|other)$")
    reference: Optional[str] = Field(None, max_length=100)
    notes: Optional[str] = Field(None, max_length=500)


class PaymentRecordOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    tenant_id: UUID
    customer_id: UUID
    order_id: Optional[UUID] = None
    amount_cents: int
    payment_method: str
    reference: Optional[str] = None
    notes: Optional[str] = None
    order_total_cents: int
    order_paid_cents: int
    order_debt_cents: int
    created_at: datetime


class DebtAdjustmentCreate(BaseModel):
    """HU_57 — aplicar condonación de deuda (inmutable una vez creado)."""
    customer_id: UUID
    order_id: Optional[UUID] = None
    # amount_cents negativo = condona; positivo = nota de débito
    amount_cents: int = Field(..., description="Negativo para condonar, positivo para nota de débito")
    reason: str = Field(..., min_length=3, max_length=200)


class DebtAdjustmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    tenant_id: UUID
    customer_id: UUID
    order_id: Optional[UUID] = None
    amount_cents: int
    reason: str
    adjusted_by_user_id: UUID
    created_at: datetime


class CustomerDebtSummary(BaseModel):
    """Resumen de deuda de un cliente."""
    customer_id: UUID
    total_debt_cents: int
    pending_orders: int
    overdue_orders: int
    last_payment_at: Optional[datetime] = None
    last_adjustment_at: Optional[datetime] = None
