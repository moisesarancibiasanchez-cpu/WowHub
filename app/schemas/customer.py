"""Schemas de Customer."""
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class CustomerBase(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=160)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(None, max_length=40)
    address: Optional[str] = Field(None, max_length=500)
    city: Optional[str] = Field(None, max_length=80)
    notes: Optional[str] = Field(None, max_length=1000)
    tags: list[str] = Field(default_factory=list)
    accepts_marketing: bool = True
    is_active: bool = True
    segmento: Optional[str] = Field(None, max_length=40)


class CustomerCreate(CustomerBase):
    pass


class CustomerUpdate(BaseModel):
    full_name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    notes: Optional[str] = None
    tags: Optional[list[str]] = None
    accepts_marketing: Optional[bool] = None
    is_active: Optional[bool] = None
    segmento: Optional[str] = None


class CustomerOut(CustomerBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    total_orders: int
    total_spent_cents: int
    points: int
    last_order_at: Optional[str] = None
    # `segmento_effective` es el segmento real que se muestra en la UI:
    # si el cliente tiene `segmento` manual, ése gana; si no, se calcula
    # automáticamente desde puntos y last_order_at.
    segmento_effective: Optional[str] = None
    avg_ticket_cents: Optional[int] = None
    days_since_last_order: Optional[int] = None
    created_at: datetime


class CustomerInsightsOut(BaseModel):
    """Insights IA derivados del historial de un cliente (Fase 3 V8 P0.3)."""
    customer_id: UUID
    lifetime_value_cents: int
    avg_ticket_cents: int
    total_orders: int
    points: int
    days_since_last_order: Optional[int] = None
    top_products: list[dict] = Field(default_factory=list)
    recommended_promotion: Optional[str] = None
    churn_risk_pct: int = 0  # 0-100
    churn_risk_label: str = "bajo"  # bajo | medio | alto
    segmento: str
    next_action: Optional[str] = None
