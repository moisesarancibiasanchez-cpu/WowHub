"""HU_12 — Variantes y modificadores de productos.

Modelos:
  - ProductVariant      : SKU/presentación alternativa de un Product (size, color, etc.)
  - Modifier            : Grupo de modificadores (extras, sin cebolla, punto de cocción)
  - ModifierOption      : Opción concreta dentro de un Modifier
  - product_modifier_groups : tabla pivot product <-> modifier con sort_order

Todas las tablas heredan TenantMixin (multi-tenant). SKU único por tenant.
"""
from __future__ import annotations

import enum
from typing import Optional

from sqlalchemy import (
    Boolean, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, Index,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import GUID, BaseModel, TenantMixin


# ── Enums ──────────────────────────────────────────────────
class ModifierType(str, enum.Enum):
    """Tipo de selección del modifier.

    SINGLE  : radio buttons (elige 1) — ej. 'Punto de cocción'
    MULTI   : checkboxes (elige N)   — ej. 'Extras'
    """
    SINGLE = "single"
    MULTI = "multi"


# ── Product Variant ────────────────────────────────────────
class ProductVariant(BaseModel, TenantMixin):
    """Variante de un producto (talla, color, sabor, etc.).

    SKU único POR TENANT. Una variante sobrescribe el precio/stock del
    Product padre cuando se vende.
    """
    __tablename__ = "product_variants"

    product_id: Mapped[str] = mapped_column(
        GUID(), ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    sku: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)

    # Pricing — en centavos (mismo patrón que Product)
    price_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cost_cents: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Inventario
    stock: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    track_inventory: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Presentación
    image_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Atributos libres (color, talla, etc.) por si el owner quiere
    # filtrar por atributo en el front sin declarar columnas nuevas.
    attributes: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "sku", name="uq_variant_sku_per_tenant"),
        Index("ix_product_variants_product_active", "product_id", "is_active"),
    )


# ── Modifier ───────────────────────────────────────────────
class Modifier(BaseModel, TenantMixin):
    """Grupo de modificadores asociado a un producto.

    Ejemplos:
      - "Extras" (MULTI, no requerido): +Queso, +Bacon, +Palta
      - "Punto de cocción" (SINGLE, requerido): Medio, Bien cocido, Tres cuartos
    """
    __tablename__ = "modifiers"

    product_id: Mapped[str] = mapped_column(
        GUID(), ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    type: Mapped[str] = mapped_column(
        String(16), default=ModifierType.SINGLE.value, nullable=False,
    )
    required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    options: Mapped[list["ModifierOption"]] = relationship(
        back_populates="modifier",
        cascade="all, delete-orphan",
        order_by="ModifierOption.sort_order",
    )

    __table_args__ = (
        Index("ix_modifiers_product_active", "product_id", "is_active"),
    )


# ── Modifier Option ────────────────────────────────────────
class ModifierOption(BaseModel):
    """Una opción concreta dentro de un Modifier.

    Hereda sólo BaseModel (no TenantMixin) porque la pertenencia al
    tenant se obtiene transitivamente vía Modifier.
    """
    __tablename__ = "modifier_options"

    modifier_id: Mapped[str] = mapped_column(
        GUID(), ForeignKey("modifiers.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    # Delta en centavos (puede ser negativo para descuentos del modifier)
    price_delta_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    modifier: Mapped["Modifier"] = relationship(back_populates="options")


# ── Pivot: product_modifier_groups ─────────────────────────
class ProductModifierGroup(BaseModel, TenantMixin):
    """Tabla pivot product <-> modifier con orden de presentación.

    Por qué existe como modelo propio (no association table clásica):
      - Permite reordenar los grupos de modificadores sin tocar Modifier
      - Permite que el mismo Modifier se aplique a varios productos con
        un sort_order independiente por producto.
    """
    __tablename__ = "product_modifier_groups"

    product_id: Mapped[str] = mapped_column(
        GUID(), ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    modifier_id: Mapped[str] = mapped_column(
        GUID(), ForeignKey("modifiers.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    __table_args__ = (
        UniqueConstraint("product_id", "modifier_id", name="uq_product_modifier"),
        Index("ix_pmg_tenant_product", "tenant_id", "product_id"),
    )
