"""Cart: carrito persistente (anónimo por session_id, identificado por customer_id)."""
from typing import Optional

from sqlalchemy import ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import GUID, BaseModel, TenantMixin


class Cart(BaseModel, TenantMixin):
    __tablename__ = "carts"

    session_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    customer_id: Mapped[Optional[str]] = mapped_column(
        GUID(),
        ForeignKey("customers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    branch_id: Mapped[Optional[str]] = mapped_column(
        GUID(),
        ForeignKey("branches.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Totales (centavos)
    subtotal_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    discount_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="CLP", nullable=False)

    # Promoción aplicada
    promotion_code: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    promotion_ids: Mapped[list] = mapped_column(JSON, default=list, nullable=False)

    # Contacto
    contact_name: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    contact_phone: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    contact_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)


class CartItem(BaseModel):
    __tablename__ = "cart_items"

    cart_id: Mapped[str] = mapped_column(
        GUID(),
        ForeignKey("carts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_id: Mapped[str] = mapped_column(
        GUID(),
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    product_name: Mapped[str] = mapped_column(String(200), nullable=False)
    product_sku: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    product_image: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    unit_price_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    total_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    options: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
