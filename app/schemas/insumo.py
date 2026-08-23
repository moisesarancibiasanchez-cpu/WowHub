"""Schemas de Insumo y Receta (V8 P0.1)."""
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ── Insumo ──────────────────────────────────────────────────
class InsumoBase(BaseModel):
    sku: str = Field(..., min_length=1, max_length=60)
    name: str = Field(..., min_length=2, max_length=200)
    description: Optional[str] = None
    unit: str = Field(default="unidad", max_length=20)
    stock: float = 0.0
    reserved: float = 0.0
    min_stock: Optional[float] = None
    reorder_point: Optional[float] = None
    reorder_lead_time_days: Optional[int] = None
    waste_pct: float = 0.0
    last_cost_cents: int = 0
    avg_cost_cents: int = 0
    supplier: Optional[str] = Field(None, max_length=200)
    location: Optional[str] = Field(None, max_length=200)
    lot: Optional[str] = Field(None, max_length=100)
    expires_at: Optional[str] = None
    image_url: Optional[str] = Field(None, max_length=500)
    tags: list[str] = Field(default_factory=list)
    is_active: bool = True
    # Lista de campos marcados como N/A (ver spec V8)
    is_na: list[str] = Field(default_factory=list)


class InsumoCreate(InsumoBase):
    pass


class InsumoUpdate(BaseModel):
    sku: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    unit: Optional[str] = None
    stock: Optional[float] = None
    reserved: Optional[float] = None
    min_stock: Optional[float] = None
    reorder_point: Optional[float] = None
    reorder_lead_time_days: Optional[int] = None
    waste_pct: Optional[float] = None
    last_cost_cents: Optional[int] = None
    avg_cost_cents: Optional[int] = None
    supplier: Optional[str] = None
    location: Optional[str] = None
    lot: Optional[str] = None
    expires_at: Optional[str] = None
    image_url: Optional[str] = None
    tags: Optional[list[str]] = None
    is_active: Optional[bool] = None
    is_na: Optional[list[str]] = None


class InsumoOut(InsumoBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    # Derivados (calculados desde stock/reserved/min_stock)
    available: float = 0.0
    stock_value_cents: int = 0
    low_stock_alert: bool = False
    created_at: datetime
    updated_at: datetime


# ── Receta (BOM) ────────────────────────────────────────────
class RecetaBase(BaseModel):
    product_id: UUID
    insumo_id: UUID
    quantity: float = Field(default=1.0, ge=0)
    notes: Optional[str] = Field(None, max_length=200)


class RecetaCreate(RecetaBase):
    pass


class RecetaUpdate(BaseModel):
    quantity: Optional[float] = None
    notes: Optional[str] = None


class RecetaOut(RecetaBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    # Costo de esta línea = insumo.avg_cost_cents * quantity
    line_cost_cents: int = 0
    # Info del insumo embebida
    insumo_name: Optional[str] = None
    insumo_unit: Optional[str] = None
    insumo_sku: Optional[str] = None


# ── Stats ───────────────────────────────────────────────────
class InsumoStats(BaseModel):
    """Estadísticas globales del inventario de Insumos de un tenant."""
    total_insumos: int = 0
    total_stock_value_cents: int = 0
    low_stock_count: int = 0
    out_of_stock_count: int = 0
    active_insumos: int = 0
