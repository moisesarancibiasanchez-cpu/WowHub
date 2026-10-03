"""Schemas de Product.

Fase 3 (V8) — se agrega ``production_time_min`` (minutos de mano de obra)
y campos derivados en las respuestas: ``cost_real_cents``,
``suggested_price_cents``, ``current_margin_pct`` y ``health``.
"""
from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.product import ProductStatus


Health = Literal["healthy", "warning", "danger", "unknown"]


class ProductBase(BaseModel):
    sku: str = Field(..., min_length=1, max_length=60)
    name: str = Field(..., min_length=2, max_length=200)
    slug: str = Field(..., min_length=2, max_length=220)
    short_description: Optional[str] = Field(None, max_length=300)
    description: Optional[str] = None
    category_id: Optional[UUID] = None
    price_cents: int = Field(..., ge=0)
    compare_at_cents: Optional[int] = Field(None, ge=0)
    cost_cents: Optional[int] = Field(None, ge=0)
    # Fase 3: minutos de mano de obra → entra al costo real.
    production_time_min: int = Field(0, ge=0, le=24 * 60)
    track_inventory: bool = False
    stock: int = Field(0, ge=0)
    low_stock_threshold: int = Field(5, ge=0)
    image_url: Optional[str] = None
    gallery: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    status: ProductStatus = ProductStatus.DRAFT
    is_featured: bool = False
    position: int = 0

    @field_validator("compare_at_cents")
    @classmethod
    def compare_gt_price(cls, v, info):
        price = info.data.get("price_cents")
        if v is not None and price is not None and v > 0 and v < price:
            raise ValueError("compare_at_cents debe ser >= price_cents (es un 'precio tachado')")
        return v


class ProductCreate(ProductBase):
    pass


class ProductUpdate(BaseModel):
    sku: Optional[str] = None
    name: Optional[str] = None
    slug: Optional[str] = None
    short_description: Optional[str] = None
    description: Optional[str] = None
    category_id: Optional[UUID] = None
    price_cents: Optional[int] = Field(None, ge=0)
    compare_at_cents: Optional[int] = Field(None, ge=0)
    cost_cents: Optional[int] = Field(None, ge=0)
    # Fase 3
    production_time_min: Optional[int] = Field(None, ge=0, le=24 * 60)
    track_inventory: Optional[bool] = None
    stock: Optional[int] = Field(None, ge=0)
    low_stock_threshold: Optional[int] = Field(None, ge=0)
    image_url: Optional[str] = None
    gallery: Optional[list[str]] = None
    tags: Optional[list[str]] = None
    status: Optional[ProductStatus] = None
    is_featured: Optional[bool] = None
    position: Optional[int] = None


class ProductOut(ProductBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    view_count: int
    sold_count: int
    created_at: datetime
    updated_at: datetime
    # Helpers de presentación
    on_sale: bool = False
    discount_pct: Optional[int] = None
    # Fase 3 — derivados (poblados por el service cuando hay BusinessCosts
    # configurado). Si el tenant aún no configuró Costos, quedan en 0/None.
    cost_real_cents: int = 0
    suggested_price_cents: int = 0
    current_margin_pct: Optional[float] = None
    target_margin_pct: Optional[int] = None
    cost_hour_used_cents: int = 0
    health: Health = "unknown"
    health_message: Optional[str] = None


# ════════════════════════════════════════════════════════════
# HU_11 — Margen de producto + simulación
# ════════════════════════════════════════════════════════════
class MarginOut(BaseModel):
    """Snapshot del margen actual de un producto (HU_11).

    Combina el `Product` con el `ProductPricing` derivado de
    `BusinessCosts` del tenant. Pensado para que la UI de pricing
    (modal de edición, dashboard) muestre en una sola llamada:

    - costo cargado (insumos) vs costo real (insumos + mano de obra)
    - margen absoluto (cents) y porcentual
    - precio sugerido según margen objetivo
    - estado de salud (healthy / warning / danger / unknown)
    """
    product_id: UUID
    cost_cents: int                       # costo de insumos cargado en el producto
    cost_real_cents: int                  # costo real (insumos + mano de obra)
    price_cents: int                      # precio de venta actual
    margin_cents: int                     # price_cents - cost_real_cents
    margin_pct: Optional[float]           # (price - cost_real) / price * 100
    target_margin_pct: Optional[int]      # margen objetivo del tenant
    suggested_price_cents: int            # precio sugerido según target
    cost_hour_used_cents: int             # costo_hora usado en el cálculo
    health: Health
    health_message: Optional[str]


class MarginSimulateIn(BaseModel):
    """Body para simular un cambio de costo en un producto (HU_11).

    Solo se modifica el costo de insumos (`cost_cents`). La mano de
    obra se mantiene porque depende de `production_time_min` y
    `BusinessCosts.cost_hour_cents` — el simulador NO persiste
    cambios, solo proyecta el margen resultante.
    """
    new_cost_cents: int = Field(..., ge=0)


class MarginSimulateOut(BaseModel):
    """Proyección del margen tras aplicar `new_cost_cents` (HU_11).

    Devuelve el snapshot actual (`current`) más la proyección
    (`projected_*`) para que la UI pueda pintar la comparación
    lado-a-lado (cuánto margen gano/perdo si cambio el costo).
    """
    current: MarginOut
    projected_cost_cents: int
    projected_cost_real_cents: int
    projected_margin_cents: int
    projected_margin_pct: Optional[float]
    projected_suggested_price_cents: int
    projected_health: Health
    projected_health_message: Optional[str]


class ProductListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    sku: str
    name: str
    slug: str
    short_description: Optional[str] = None
    category_id: Optional[UUID] = None
    price_cents: int
    compare_at_cents: Optional[int] = None
    image_url: Optional[str] = None
    status: ProductStatus
    is_featured: bool
    position: int
    stock: int
    track_inventory: bool
    on_sale: bool = False
    discount_pct: Optional[int] = None
    # Fase 3 — derivados para la tabla del dashboard
    production_time_min: int = 0
    cost_real_cents: int = 0
    current_margin_pct: Optional[float] = None
    target_margin_pct: Optional[int] = None
    health: Health = "unknown"
    health_message: Optional[str] = None


# ════════════════════════════════════════════════════════════
# HU_12 — Variantes y modificadores
# ════════════════════════════════════════════════════════════
class ProductVariantBase(BaseModel):
    sku: str = Field(..., min_length=1, max_length=80)
    name: str = Field(..., min_length=1, max_length=200)
    price_cents: int = Field(0, ge=0)
    cost_cents: Optional[int] = Field(None, ge=0)
    stock: int = Field(0, ge=0)
    track_inventory: bool = False
    image_url: Optional[str] = Field(None, max_length=500)
    sort_order: int = 0
    is_active: bool = True
    attributes: dict = Field(default_factory=dict)


class ProductVariantIn(ProductVariantBase):
    pass


class ProductVariantUpdate(BaseModel):
    """PATCH — todos opcionales."""
    sku: Optional[str] = Field(None, min_length=1, max_length=80)
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    price_cents: Optional[int] = Field(None, ge=0)
    cost_cents: Optional[int] = Field(None, ge=0)
    stock: Optional[int] = Field(None, ge=0)
    track_inventory: Optional[bool] = None
    image_url: Optional[str] = Field(None, max_length=500)
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None
    attributes: Optional[dict] = None


class ProductVariantOut(ProductVariantBase):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    tenant_id: UUID
    product_id: UUID
    created_at: datetime
    updated_at: datetime


# ── Modifier Option ─────────────────────────────────────────
class ModifierOptionBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    price_delta_cents: int = Field(0)
    is_default: bool = False
    sort_order: int = 0
    is_active: bool = True


class ModifierOptionIn(ModifierOptionBase):
    pass


class ModifierOptionUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=120)
    price_delta_cents: Optional[int] = None
    is_default: Optional[bool] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None


class ModifierOptionOut(ModifierOptionBase):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    modifier_id: UUID
    created_at: datetime
    updated_at: datetime


# ── Modifier (grupo) ───────────────────────────────────────
class ModifierBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    type: str = Field("single", pattern="^(single|multi)$")
    required: bool = False
    sort_order: int = 0
    is_active: bool = True
    description: Optional[str] = None


class ModifierIn(ModifierBase):
    options: list[ModifierOptionIn] = Field(default_factory=list)


class ModifierUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=120)
    type: Optional[str] = Field(None, pattern="^(single|multi)$")
    required: Optional[bool] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None
    description: Optional[str] = None


class ModifierOut(ModifierBase):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    tenant_id: UUID
    product_id: UUID
    options: list[ModifierOptionOut] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
