"""HU_19 — Schemas para DiningSession (mesero virtual / cuenta dividida)."""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DiningSessionCreate(BaseModel):
    """POST /dining-sessions — abre una mesa."""
    branch_id: UUID
    table_id: Optional[UUID] = None
    table_label: str = Field(..., min_length=1, max_length=60)
    customer_count: int = Field(1, ge=1, le=100)
    server_user_id: Optional[UUID] = None
    notes: Optional[str] = Field(None, max_length=2000)


class DiningSessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    branch_id: UUID
    table_id: Optional[UUID] = None
    table_label: str
    status: str
    opened_at: datetime
    closed_at: Optional[datetime] = None
    total_cents: int
    paid_cents: int
    tip_cents: int
    customer_count: int
    server_user_id: Optional[UUID] = None
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class DiningSessionClose(BaseModel):
    """POST /dining-sessions/{dsid}/close — cerrar mesa."""
    paid_cents: Optional[int] = Field(None, ge=0)
    notes: Optional[str] = Field(None, max_length=2000)


class DiningSessionTip(BaseModel):
    """PATCH /dining-sessions/{dsid}/tip."""
    tip_cents: int = Field(..., ge=0)


class DiningSessionItemCreate(BaseModel):
    """Línea para asociar un OrderItem a la sesión."""
    order_item_id: UUID
    assigned_to: Optional[str] = Field(None, max_length=80)
    share_cents: Optional[int] = Field(None, ge=0)
    notes: Optional[str] = Field(None, max_length=300)


class DiningSessionItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    session_id: UUID
    order_item_id: UUID
    assigned_to: Optional[str] = None
    share_cents: Optional[int] = None
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class SplitShareOut(BaseModel):
    """Una parte de la división. Asignada a 'assigned_to' o equitativa."""
    label: str
    amount_cents: int
    items: list[DiningSessionItemOut] = Field(default_factory=list)


class DiningSessionSplitOut(BaseModel):
    """Resultado de GET /dining-sessions/{dsid}/split."""
    session_id: UUID
    customer_count: int
    total_cents: int
    paid_cents: int
    tip_cents: int
    # División final: cuánto paga cada comensal.
    shares: list[SplitShareOut]
    # Si la división no es perfectamente entera, queda un remanente.
    remainder_cents: int = 0
