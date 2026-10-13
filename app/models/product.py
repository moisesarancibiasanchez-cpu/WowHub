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
