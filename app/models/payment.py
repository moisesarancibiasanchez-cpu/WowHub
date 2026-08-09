"""Payment: registro de pagos (MercadoPago, manual, transferencia)."""
import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import GUID, BaseModel, TenantMixin


class PaymentMethod(str, enum.Enum):
    MERCADO_PAGO = "mercado_pago"
    TRANSFER = "transfer"
    CASH = "cash"
    CARD_ON_DELIVERY = "card_on_delivery"
    OTHER = "other"


class PaymentStatus(str, enum.Enum):
    PENDING = "pending"
    AUTHORIZED = "authorized"
    PAID = "paid"
    FAILED = "failed"
    REFUNDED = "refunded"
    CANCELED = "canceled"


class Payment(BaseModel, TenantMixin):
    __tablename__ = "payments"

    order_id: Mapped[str] = mapped_column(
        GUID(),
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    method: Mapped[PaymentMethod] = mapped_column(
        Enum(PaymentMethod, name="payment_method"),
        default=PaymentMethod.MERCADO_PAGO,
        nullable=False,
    )
    status: Mapped[PaymentStatus] = mapped_column(
        Enum(PaymentStatus, name="payment_status"),
        default=PaymentStatus.PENDING,
        nullable=False,
        index=True,
    )

    # Montos (centavos)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    fee_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    net_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="CLP", nullable=False)

    # IDs externos (MercadoPago, etc.)
    provider: Mapped[str] = mapped_column(String(40), default="mercadopago", nullable=False)
    provider_payment_id: Mapped[Optional[str]] = mapped_column(String(120), nullable=True, index=True)
    provider_preference_id: Mapped[Optional[str]] = mapped_column(String(120), nullable=True, index=True)
    provider_status_detail: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    # URLs
    init_point: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)  # URL para redirigir al cliente
    sandbox_init_point: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Metadata del proveedor
    provider_response: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    # Fechas
    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
