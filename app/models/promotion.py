"""Promotion: promociones/descuentos. Tipos: porcentaje, monto fijo, 2x1, bundle."""
import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel, TenantMixin


class PromotionType(str, enum.Enum):
    PERCENT = "percent"             # % descuento
    FIXED = "fixed"                 # monto fijo descuento
    BUY_X_GET_Y = "buy_x_get_y"     # 2x1, 3x2
    FREE_SHIPPING = "free_shipping"
    BUNDLE = "bundle"               # combo


class DiscountType(str, enum.Enum):
    PERCENT = "percent"
    FIXED = "fixed"


class Promotion(BaseModel, TenantMixin):
    __tablename__ = "promotions"

    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    code: Mapped[str] = mapped_column(String(40), nullable=True, index=True)  # cupón opcional

    # Configuración del descuento
    promo_type: Mapped[PromotionType] = mapped_column(
        Enum(PromotionType, name="promotion_type"),
        default=PromotionType.PERCENT,
        nullable=False,
    )
    discount_type: Mapped[DiscountType] = mapped_column(
        Enum(DiscountType, name="discount_type"),
        default=DiscountType.PERCENT,
        nullable=False,
    )
    discount_value: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    min_purchase_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_discount_cents: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Vigencia
    starts_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    ends_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Límites de uso
    usage_limit: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    usage_limit_per_customer: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    used_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Aplicabilidad
    applies_to_all: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    product_ids: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    category_ids: Mapped[list] = mapped_column(JSON, default=list, nullable=False)

    # Estado
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_public: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Visual
    badge_text: Mapped[str] = mapped_column(String(40), nullable=True)
    color: Mapped[str] = mapped_column(String(20), nullable=True)
    image_url: Mapped[str] = mapped_column(String(500), nullable=True)
