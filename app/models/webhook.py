"""Webhook: configuración de webhooks salientes por tenant."""
import enum
from typing import Optional

from sqlalchemy import Boolean, Enum, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel, TenantMixin


class WebhookEvent(str, enum.Enum):
    ORDER_CREATED = "order.created"
    ORDER_PAID = "order.paid"
    ORDER_CANCELED = "order.canceled"
    CUSTOMER_CREATED = "customer.created"
    QR_SCANNED = "qr.scanned"
    PRODUCT_LOW_STOCK = "product.low_stock"
    MEMBERSHIP_INVITED = "membership.invited"


class Webhook(BaseModel, TenantMixin):
    __tablename__ = "webhooks"

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    secret: Mapped[str] = mapped_column(String(120), nullable=False)  # HMAC secret
    events: Mapped[list] = mapped_column(JSON, default=list, nullable=False)  # ["order.created", ...]
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Métricas
    total_deliveries: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    successful_deliveries: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_deliveries: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_triggered_at: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    last_status_code: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)


class WebhookDelivery(BaseModel, TenantMixin):
    __tablename__ = "webhook_deliveries"

    webhook_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    event: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    # Estado
    success: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status_code: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    response_body: Mapped[Optional[str]] = mapped_column(String(2000), nullable=True)
    error: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Reintentos
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    next_retry_at: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
