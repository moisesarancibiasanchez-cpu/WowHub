"""PaymentRecord y DebtAdjustment — pagos manuales y condonaciones.
HU_56, HU_57 — Épica E8 (S5) — TOBE v134.2-Producción-v2.

Complementa Payment (Stripe — HU_23) para pagos fuera de la pasarela
(efectivo, transferencia, etc.). Replica WowPrint db.paymentRecords
y db.debtAdjustments.
"""
import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import GUID, BaseModel, TenantMixin


class PaymentMethod(str, enum.Enum):
    """Métodos de pago manual (no Stripe)."""
    CASH = "cash"
    TRANSFER = "transfer"
    CREDIT = "credit"
    DEBIT = "debit"
    OTHER = "other"


class PaymentRecord(BaseModel, TenantMixin):
    """Registro de pago manual de un pedido (HU_56).
    
    Trigger: operador registra un abono parcial o pago total desde
    el panel admin. Actualiza Order.paid_cents y Order.payment_status.
    """
    __tablename__ = "payment_records"

    tenant_id: Mapped[str] = mapped_column(GUID(), nullable=False, index=True)
    customer_id: Mapped[str] = mapped_column(
        GUID(),
        ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    order_id: Mapped[Optional[str]] = mapped_column(
        GUID(),
        ForeignKey("orders.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    payment_method: Mapped[PaymentMethod] = mapped_column(
        Enum(PaymentMethod, name="payment_method"),
        default=PaymentMethod.CASH,
        nullable=False,
    )
    reference: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Snapshot del estado del pedido al registrar el pago
    order_total_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    order_paid_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    order_debt_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False, index=True
    )

    order = relationship("Order", lazy="select", foreign_keys=[order_id])
    customer = relationship("Customer", lazy="select", foreign_keys=[customer_id])


class DebtAdjustment(BaseModel, TenantMixin):
    """Ajuste de deuda (condonación, nota de crédito) — HU_57.
    
    Inmutable: una vez creado no se puede editar ni eliminar.
    Solo OWNER/ADMIN pueden crear. Auditado en HU_40.
    """
    __tablename__ = "debt_adjustments"

    tenant_id: Mapped[str] = mapped_column(GUID(), nullable=False, index=True)
    customer_id: Mapped[str] = mapped_column(
        GUID(),
        ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    order_id: Mapped[Optional[str]] = mapped_column(
        GUID(),
        ForeignKey("orders.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # amount_cents negativo = condona deuda
    # amount_cents positivo = aumenta deuda (raro, posible nota de débito)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(String(200), nullable=False)
    adjusted_by_user_id: Mapped[str] = mapped_column(
        GUID(),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False, index=True
    )

    customer = relationship("Customer", lazy="select", foreign_keys=[customer_id])
    order = relationship("Order", lazy="select", foreign_keys=[order_id])
