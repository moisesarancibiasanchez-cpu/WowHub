"""NotificationTemplate y NotificationLog — sistema de notificaciones multicanal.
HU_62, HU_63 — Épica E9 (S6) — TOBE v134.2-Producción-v2.

Replica WowPrint db.settings.whatsappQuoteMessage, whatsappOrderMessage, etc.
"""
import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import GUID, BaseModel, TenantMixin


class NotificationEvent(str, enum.Enum):
    """Eventos que disparan notificaciones."""
    QUOTE_SENT = "quote.sent"
    ORDER_CONFIRMED = "order.confirmed"
    ORDER_READY = "order.ready"
    ORDER_DELIVERED = "order.delivered"
    PAYMENT_RECEIVED = "payment.received"
    DEBT_ADJUSTED = "debt.adjusted"
    PRODUCTION_DELAYED = "production.delayed"


class NotificationChannel(str, enum.Enum):
    WHATSAPP = "whatsapp"
    EMAIL = "email"
    SMS = "sms"


class NotificationStatus(str, enum.Enum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    RATE_LIMITED = "rate_limited"


class NotificationTemplate(BaseModel, TenantMixin):
    """Plantilla de notificación por (event, channel) — HU_62.
    
    7 templates default pre-cargados desde WowPrint.
    Body con placeholders: {cliente}, {pedido}, {total}, {estado}, {empresa}
    """
    __tablename__ = "notification_templates"
    __table_args__ = (
        Index("ix_notif_tpl_tenant_event_channel", "tenant_id", "event", "channel", unique=True),
    )

    tenant_id: Mapped[str] = mapped_column(GUID(), nullable=False, index=True)

    event: Mapped[NotificationEvent] = mapped_column(
        Enum(NotificationEvent, name="notification_event"),
        nullable=False,
    )
    channel: Mapped[NotificationChannel] = mapped_column(
        Enum(NotificationChannel, name="notification_channel"),
        nullable=False,
    )

    template_body: Mapped[str] = mapped_column(Text, nullable=False)
    # Soporta placeholders {cliente}, {pedido}, {total}, {estado}, {empresa}, {detalle}

    is_active: Mapped[bool] = mapped_column(default=True, nullable=False, index=True)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )


class NotificationLog(BaseModel, TenantMixin):
    """Log de notificaciones enviadas — HU_63.
    
    Retención: 90 días hot + archive a S3.
    """
    __tablename__ = "notification_logs"

    tenant_id: Mapped[str] = mapped_column(GUID(), nullable=False, index=True)
    customer_id: Mapped[Optional[str]] = mapped_column(
        GUID(),
        ForeignKey("customers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    order_id: Mapped[Optional[str]] = mapped_column(
        GUID(),
        ForeignKey("orders.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    channel: Mapped[NotificationChannel] = mapped_column(
        Enum(NotificationChannel, name="notification_channel_log", create_type=False),
        nullable=False,
    )
    event: Mapped[NotificationEvent] = mapped_column(
        Enum(NotificationEvent, name="notification_event_log", create_type=False),
        nullable=False,
    )
    status: Mapped[NotificationStatus] = mapped_column(
        Enum(NotificationStatus, name="notification_status"),
        default=NotificationStatus.PENDING,
        nullable=False,
        index=True,
    )

    content_rendered: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, index=True)
