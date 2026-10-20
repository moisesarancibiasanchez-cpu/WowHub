"""Quote: cotización / presupuesto enviado al cliente (todavía no es pedido).

Una cotización es un documento no vinculante que el dueño del negocio envía
a un cliente (o lead) con una lista de productos/servicios y precios. El cliente
la puede aceptar (→ Order) o rechazar. Vive en el flujo de ventas previo al pedido.

Estados:
  DRAFT     → en edición, no se muestra al cliente
  SENT      → enviada al cliente (por email/WhatsApp)
  VIEWED    → el cliente abrió el link público
  ACCEPTED  → el cliente la aceptó (se puede convertir a Order)
  REJECTED  → el cliente la rechazó o el dueño la canceló
  EXPIRED   → pasó la fecha de validez
"""
import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean, DateTime, Enum, ForeignKey, Integer, JSON, String, Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import GUID, BaseModel, TenantMixin


class QuoteStatus(str, enum.Enum):
    DRAFT = "draft"
    SENT = "sent"
    VIEWED = "viewed"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    EXPIRED = "expired"


class Quote(BaseModel, TenantMixin):
    __tablename__ = "quotes"

    # Numeración amigable (ej. "COT-0001")
    number: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[QuoteStatus] = mapped_column(
        Enum(QuoteStatus, name="quote_status"),
        default=QuoteStatus.DRAFT,
        nullable=False,
        index=True,
    )

    # Relaciones
    customer_id: Mapped[Optional[str]] = mapped_column(
        GUID(), ForeignKey("customers.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    branch_id: Mapped[Optional[str]] = mapped_column(
        GUID(), ForeignKey("branches.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )

    # Snapshot del destinatario (puede no ser cliente aún)
    recipient_name: Mapped[str] = mapped_column(String(200), nullable=False)
    recipient_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    recipient_phone: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)

    # Montos (centavos)
    subtotal_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    discount_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tax_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="CLP", nullable=False)

    # Texto libre
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    terms: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Vigencia
    valid_until: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    viewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    accepted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    rejected_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Token público (UUID corto) para ver la cotización sin login
    public_token: Mapped[str] = mapped_column(
        String(40), nullable=False, unique=True, index=True,
    )

    # Si fue convertida en pedido
    converted_order_id: Mapped[Optional[str]] = mapped_column(
        GUID(), ForeignKey("orders.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Metadata
    extra: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    items: Mapped[list["QuoteItem"]] = relationship(  # noqa: F821
        back_populates="quote",
        cascade="all, delete-orphan",
    )


class QuoteItem(BaseModel):
    __tablename__ = "quote_items"

    quote_id: Mapped[str] = mapped_column(
        GUID(), ForeignKey("quotes.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    product_id: Mapped[Optional[str]] = mapped_column(
        GUID(), ForeignKey("products.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Snapshot al momento de cotizar
    product_name: Mapped[str] = mapped_column(String(200), nullable=False)
    product_sku: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    quantity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    unit_price_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    discount_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_cents: Mapped[int] = mapped_column(Integer, nullable=False)

    quote: Mapped["Quote"] = relationship(back_populates="items")
