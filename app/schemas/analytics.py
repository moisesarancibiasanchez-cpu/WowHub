"""Schemas para Analytics (inventory + customer segments) y Campaigns."""
from typing import Literal, Optional

from pydantic import BaseModel, Field


# ── Analytics / Inventory ─────────────────────────────────────
class InventoryItem(BaseModel):
    id: str
    sku: str
    name: str
    stock: int
    low_stock_threshold: int
    price_cents: int
    image_url: Optional[str] = None
    status: str
    is_featured: bool
    sold_count: int
    view_count: int
    alert: str  # out_of_stock | low_stock | overstock | ok
    units_sold: Optional[int] = None
    revenue_cents: Optional[int] = None


class InventorySummary(BaseModel):
    total_tracked: int
    ok: int
    out_of_stock: int
    low_stock: int
    overstock: int


class InventoryResponse(BaseModel):
    category: str
    tenant_id: str
    summary: InventorySummary
    count: int
    items: list[InventoryItem]
    params: dict


# ── Analytics / Customer Segments ────────────────────────────
class CustomerSegmentItem(BaseModel):
    id: str
    full_name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    total_orders: int
    total_spent_cents: int
    points: int
    last_order_at: Optional[str] = None
    accepts_marketing: bool
    is_active: bool
    tags: list[str] = Field(default_factory=list)


class CustomerSummary(BaseModel):
    total_active: int
    accepts_marketing: int
    no_orders: int
    vip: int
    new: int
    inactive: int


class CustomerSegmentResponse(BaseModel):
    segment: str
    tenant_id: str
    summary: CustomerSummary
    count: int
    items: list[CustomerSegmentItem]
    params: dict


# ── Campaigns ────────────────────────────────────────────────
SegmentName = Literal["all", "inactive", "top", "new", "vip", "no_orders"]
ChannelName = Literal["email", "log"]  # 'log' = no enviar, solo registrar


class CampaignCreate(BaseModel):
    """Cuerpo del POST /campaigns."""

    name: str = Field(..., min_length=2, max_length=120,
                      description="Nombre interno de la campaña (para auditoría).")
    subject: str = Field(..., min_length=2, max_length=200,
                         description="Asunto del email (lo verá el cliente).")
    body: str = Field(..., min_length=2, max_length=5000,
                      description="Cuerpo del email. Puede incluir HTML básico.")
    segment: SegmentName = "all"
    channel: ChannelName = "email"
    promotion_id: Optional[str] = None
    only_marketing_opt_in: bool = True
    days_inactive: int = 60
    days_new: int = 30
    vip_min_orders: int = 5
    vip_min_spent_cents: int = 50000


class CampaignResult(BaseModel):
    sent: int
    failed: int
    skipped: int
    total_targets: int
    channel: str
    segment: str
    errors: list[str] = Field(default_factory=list)


class CampaignResponse(BaseModel):
    campaign: CampaignResult
    preview_html: Optional[str] = None
    sample_recipients: list[CustomerSegmentItem] = Field(default_factory=list)


# ── Campaigns A/B test (HU_27) ────────────────────────────────
class CampaignABTestCreate(BaseModel):
    """Cuerpo del POST /campaigns/{id}/ab-test.

    Permite definir dos variantes de asunto (A y B) y el porcentaje
    del tráfico que verá cada una. El endpoint valida y guarda las
    variantes, devolviendo un identificador estable (test_id) y una
    proyección de destinatarios por variante según el segmento actual.
    """

    variant_a: str = Field(..., min_length=2, max_length=200,
                           description="Asunto variante A.")
    variant_b: str = Field(..., min_length=2, max_length=200,
                           description="Asunto variante B.")
    split: float = Field(
        0.5,
        ge=0.0,
        le=1.0,
        description="Proporción (0.0–1.0) del tráfico que verá la variante A. "
                    "El resto verá la variante B.",
    )
    name: Optional[str] = Field(
        None,
        max_length=120,
        description="Nombre lógico del test (para auditoría).",
    )


class CampaignABTestResponse(BaseModel):
    """Respuesta del POST /campaigns/{id}/ab-test."""

    test_id: str = Field(..., description="Identificador estable (hex) del test A/B.")
    campaign_id: str = Field(..., description="Identificador lógico de campaña recibido.")
    variant_a: str
    variant_b: str
    split: float
    name: Optional[str] = None
    projected_targets_a: int
    projected_targets_b: int
    created_at: str
