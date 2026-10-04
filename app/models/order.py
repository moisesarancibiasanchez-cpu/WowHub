"""Order: pedido realizado por un cliente final. OrderItem: líneas del pedido."""
import enum
from typing import Optional

from sqlalchemy import Enum, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import GUID, BaseModel, TenantMixin


class OrderStatus(str, enum.Enum):
    """Estados de pedido según spec V134.2 (HU_15).

    Todos los valores en español para consistencia con mercado LATAM.
    """
    RECIBIDO = "recibido"
    CONFIRMADO = "confirmado"
    EN_PREPARACION = "en_preparacion"
    LISTO = "listo"
    ENTREGADO = "entregado"
    CANCELADO = "cancelado"
    PAGADO = "pagado"  # nuevo: pago confirmado post-entrega


class Order(BaseModel, TenantMixin):
    __tablename__ = "orders"

    # Numeración amigable
    number: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    status: Mapped[OrderStatus] = mapped_column(
        Enum(OrderStatus, name="order_status"),
        default=OrderStatus.RECIBIDO,
        nullable=False,
        index=True,
    )

    # Relaciones
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
        index=True,
    )

    # Montos (centavos)
    subtotal_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    discount_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    shipping_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tax_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="CLP", nullable=False)

    # Promociones aplicadas
    promotion_ids: Mapped[list] = mapped_column(JSON, default=list, nullable=False)

    # Datos de envío
    customer_name: Mapped[str] = mapped_column(String(200), nullable=True)
    customer_phone: Mapped[str] = mapped_column(String(40), nullable=True)
    customer_email: Mapped[str] = mapped_column(String(255), nullable=True)
    shipping_address: Mapped[str] = mapped_column(String(500), nullable=True)
    notes: Mapped[str] = mapped_column(Text, nullable=True)

    # Metadata
    # Origen del pedido. Valores libres (String sin Enum) para no romper
    # datos existentes ni romper el webhook de WhatsApp (HU_16).
    # Valores válidos: "web", "qr", "pos", "kiosk", "whatsapp", "api", "test", etc.
    # HU_16 — "whatsapp" explícitamente aceptado para pedidos desde el canal WhatsApp.
    source: Mapped[str] = mapped_column(String(40), default="web", nullable=False)  # web, qr, pos, kiosk, whatsapp, api
    qr_code_id: Mapped[Optional[str]] = mapped_column(GUID(), nullable=True, index=True)

    items: Mapped[list["OrderItem"]] = relationship(  # noqa: F821
        back_populates="order",
        cascade="all, delete-orphan",
    )


class OrderItem(BaseModel):
    __tablename__ = "order_items"

    order_id: Mapped[str] = mapped_column(
        GUID(),
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_id: Mapped[Optional[str]] = mapped_column(
        GUID(),
        ForeignKey("products.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Snapshot del producto al momento de la compra
    product_name: Mapped[str] = mapped_column(String(200), nullable=False)
    product_sku: Mapped[str] = mapped_column(String(60), nullable=True)
    product_image: Mapped[str] = mapped_column(String(500), nullable=True)
    quantity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    unit_price_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    total_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    options: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    order: Mapped["Order"] = relationship(back_populates="items")
