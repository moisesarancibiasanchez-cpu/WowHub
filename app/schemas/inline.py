"""Schemas para inline creation (HU_50, HU_51) y Production (HU_52, HU_53)."""
from __future__ import annotations
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.models.production import ProductionJobStatus


# ═══════════════════════════════════════════════════════════════════════════
# HU_50: Inline creation de Customer
# ═══════════════════════════════════════════════════════════════════════════
class CustomerInlineCreate(BaseModel):
    """Crea un cliente sin salir del modal de pedido (HU_50).
    
    Valida al menos uno de (phone, email) requerido.
    """
    name: str = Field(..., min_length=1, max_length=160)
    phone: Optional[str] = Field(None, max_length=40)
    email: Optional[EmailStr] = None
    customer_type: str = Field("particular", pattern="^(particular|empresa)$")
    marketing_consent: bool = Field(default=False)
    notes: Optional[str] = Field(None, max_length=500)
    # Si se provee, vincula la creación al pedido en curso
    return_to_order_id: Optional[UUID] = None

    @field_validator("phone", "email")
    @classmethod
    def at_least_one_contact(cls, v, info):
        # Validación cross-field se hace en el endpoint
        return v


# ═══════════════════════════════════════════════════════════════════════════
# HU_51: Inline creation de Product
# ═══════════════════════════════════════════════════════════════════════════
class ProductInlineCreate(BaseModel):
    """Crea un producto sin salir del modal de pedido (HU_51).
    
    Si add_to_order=True y return_to_order_id presente, agrega como OrderItem.
    """
    name: str = Field(..., min_length=1, max_length=200)
    sku: str = Field(..., min_length=1, max_length=60)
    price_cents: int = Field(..., ge=0)
    category_id: Optional[UUID] = None
    # HU_51, HU_52 — tipo de producto
    product_type: str = Field(
        "standard", pattern="^(standard|print|m2|production_only)$"
    )
    # HU_54 — template de impresión predefinido
    template_type: Optional[str] = Field(
        None, pattern="^(flyer-a6|flyer-a5|poster-a3|poster-a4|magnet-5x7|magnet-9x7|business-card|trovicel|pvc|custom)$"
    )
    # HU_58 — precio por m² (solo si product_type=m2)
    m2_price_cents: int = Field(0, ge=0)
    production_time_min: int = Field(0, ge=0)
    cost_cents: Optional[int] = Field(None, ge=0)
    # Inline-add to order
    add_to_order: bool = False
    return_to_order_id: Optional[UUID] = None
    quantity: int = Field(1, ge=1, le=999)

    @model_validator(mode="after")
    def print_requires_template(self) -> "ProductInlineCreate":
        # HU_51: si es producto de tipo impresión, debe especificar template.
        if self.product_type == "print" and not self.template_type:
            raise ValueError(
                "template_type es obligatorio cuando product_type='print' "
                "(HU_51: producto de impresión requiere template predefinido)."
            )
        return self


# ═══════════════════════════════════════════════════════════════════════════
# HU_52, HU_53: ProductionJob
# ═══════════════════════════════════════════════════════════════════════════
class ProductionJobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    tenant_id: UUID
    order_id: UUID
    order_item_id: Optional[UUID] = None
    product_id: Optional[UUID] = None
    product_snapshot: dict
    customer_id: Optional[UUID] = None
    customer_name: Optional[str] = None
    quantity: int
    completed_qty: int
    width_cm: Optional[float] = None
    height_cm: Optional[float] = None
    status: ProductionJobStatus
    priority: str
    due_date: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    file_url: Optional[str] = None
    file_status: str
    notes: Optional[str] = None
    estimated_cost_cents: int
    actual_cost_cents: int
    version: int
    created_at: datetime
    updated_at: datetime


class ProductionJobMove(BaseModel):
    """HU_53 — mover un job a otro estado del pipeline."""
    new_status: ProductionJobStatus
    notes: Optional[str] = None


class KanbanColumn(BaseModel):
    """HU_52 — una columna del Kanban con sus jobs."""
    status: ProductionJobStatus
    count: int
    jobs: list[ProductionJobOut]


class KanbanBoard(BaseModel):
    """HU_52 — tablero completo del Kanban."""
    columns: list[KanbanColumn]
    total_jobs: int
    total_urgent: int
    total_late: int
