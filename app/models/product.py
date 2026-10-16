"""Product: producto del catálogo. Precio en centavos (entero) — evitar floats."""
import enum
from typing import Optional

from sqlalchemy import Boolean, Enum, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import GUID, BaseModel, TenantMixin


class ProductStatus(str, enum.Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    OUT_OF_STOCK = "out_of_stock"
    ARCHIVED = "archived"


class ProductType(str, enum.Enum):
    """HU_51, HU_52 — tipo de producto para decidir auto-creación de ProductionJob.

    STANDARD     → producto comercial genérico (no genera job de producción)
    PRINT        → producto de impresión con template (flyer, poster, etc.)
    M2           → producto vendido por metro cuadrado (pendones, imanes, trovicel)
    PRODUCTION_ONLY → solo para producción, no en catálogo público
    """
    STANDARD = "standard"
    PRINT = "print"
    M2 = "m2"
    PRODUCTION_ONLY = "production_only"


class PrintTemplateType(str, enum.Enum):
    """HU_54 — templates de impresión predefinidos (de WowPrint V1354_R2)."""
    FLYER_A6 = "flyer-a6"
    FLYER_A5 = "flyer-a5"
    POSTER_A3 = "poster-a3"
    POSTER_A4 = "poster-a4"
    MAGNET_5X7 = "magnet-5x7"
    MAGNET_9X7 = "magnet-9x7"
    BUSINESS_CARD = "business-card"
    TROVICEL = "trovicel"
    PVC = "pvc"
    CUSTOM = "custom"


# Medidas canónicas en cm (de WowPrint línea 142)
TEMPLATE_DIMENSIONS_CM = {
    PrintTemplateType.FLYER_A6: (10.5, 14.8),
    PrintTemplateType.FLYER_A5: (14.8, 21.0),
    PrintTemplateType.POSTER_A3: (29.7, 42.0),
    PrintTemplateType.POSTER_A4: (21.0, 29.7),
    PrintTemplateType.MAGNET_5X7: (12.7, 17.8),
    PrintTemplateType.MAGNET_9X7: (22.9, 17.8),
    PrintTemplateType.BUSINESS_CARD: (9.0, 5.5),
    PrintTemplateType.TROVICEL: (60.0, 40.0),
    PrintTemplateType.PVC: (60.0, 40.0),
}


class Product(BaseModel, TenantMixin):
    __tablename__ = "products"

    # Identidad
    sku: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(220), nullable=False, index=True)
    short_description: Mapped[str] = mapped_column(String(300), nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=True)

    # Categoría (opcional)
    category_id: Mapped[Optional[str]] = mapped_column(
        GUID(),
        ForeignKey("categories.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Pricing — TODO en centavos de la moneda del tenant (CLP/EUR/USD...)
    # Para CLP sin decimales: 1 unidad = 1 CLP.
    price_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    compare_at_cents: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    cost_cents: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Fase 3 (V8) — tiempo de producción en minutos. Se usa junto a
    # `BusinessCosts.cost_hour_cents` para calcular el costo real del
    # producto (mano de obra) y sugerir un precio con margen objetivo.
    production_time_min: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Inventario
    track_inventory: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    stock: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    low_stock_threshold: Mapped[int] = mapped_column(Integer, default=5, nullable=False)

    # Media
    image_url: Mapped[str] = mapped_column(String(500), nullable=True)
    gallery: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    tags: Mapped[list] = mapped_column(JSON, default=list, nullable=False)

    # Estado
    status: Mapped[ProductStatus] = mapped_column(
        Enum(ProductStatus, name="product_status"),
        default=ProductStatus.DRAFT,
        nullable=False,
        index=True,
    )
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Métricas
    view_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sold_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # ═══════════════════════════════════════════════════════════════════════
    # TOBE v134.2-Producción-v2 (HU_51, HU_52, HU_54, HU_58)
    # ═══════════════════════════════════════════════════════════════════════
    # Tipo de producto: decide si genera ProductionJob al confirmar Order.
    # STANDARD: producto comercial genérico (no producción)
    # PRINT: producto de impresión con template
    # M2: producto por metro cuadrado (pendones, imanes, trovicel)
    # PRODUCTION_ONLY: solo producción, no aparece en catálogo público
    product_type: Mapped[str] = mapped_column(
        String(30),
        default="standard",
        nullable=False,
        index=True,
        comment="HU_51, HU_52: standard|print|m2|production_only",
    )
    # Template de impresión (HU_54): solo aplica si product_type ∈ (print, m2)
    template_type: Mapped[Optional[str]] = mapped_column(
        String(30), nullable=True, index=True,
        comment="HU_54: flyer-a5, poster-a3, magnet-5x7, business-card, etc.",
    )
    # Precio por m² (HU_58): solo para product_type='m2'
    m2_price_cents: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False,
        comment="HU_58: precio por metro cuadrado (solo product_type=m2)",
    )
