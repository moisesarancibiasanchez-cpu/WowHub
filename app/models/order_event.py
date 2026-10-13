"""HU_17 — Línea de tiempo del pedido (OrderEvent).

Auditoría cronológica de todo lo que le ocurre a un Order:
cambios de estado, notas manuales, pagos, reembolsos, eventos de canal
(webhook entrante, integración POS, etc.).

El state machine de Order.status dispara automáticamente eventos
STATUS_CHANGE vía OrderService.transition (ver OrderEventService).
Las notas manuales se crean vía POST /orders/{oid}/events con
event_type=NOTE.
"""
from __future__ import annotations

import enum
from typing import Optional

from sqlalchemy import Index, String, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import GUID, BaseModel, TenantMixin


class OrderEventType(str, enum.Enum):
    """Tipo de evento en la timeline del pedido."""
    STATUS_CHANGE = "status_change"   # automático al transicionar
    NOTE = "note"                     # nota manual del owner/garzón
    PAYMENT = "payment"               # pago confirmado / fallido
    REFUND = "refund"                 # reembolso parcial o total
    CHANNEL = "channel"               # evento externo (webhook POS, delivery)


class OrderEvent(BaseModel, TenantMixin):
    """Un evento en la línea de tiempo del pedido.

    Es append-only por diseño (no hay endpoint de update/delete de
    eventos). Para "corregir" se agrega un evento nuevo.
    """
    __tablename__ = "order_events"

    order_id: Mapped[str] = mapped_column(
        GUID(), index=True, nullable=False,
    )

    event_type: Mapped[str] = mapped_column(
        String(32),
        default=OrderEventType.STATUS_CHANGE.value,
        nullable=False,
        index=True,
    )

    # Snapshot libre: para STATUS_CHANGE guarda
    #   {"from": "recibido", "to": "confirmado"}
    # para NOTE guarda
    #   {"text": "Cliente pidió sin cebolla"}
    # para PAYMENT guarda
    #   {"method": "webpay", "amount_cents": 1234, "status": "ok"}
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    actor_user_id: Mapped[Optional[str]] = mapped_column(
        GUID(), nullable=True, index=True,
    )

    # Texto corto (opcional) — para mostrar en timeline sin parsear payload.
    # Para NOTE es el texto de la nota; para STATUS_CHANGE puede ser un
    # resumen legible.
    message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    __table_args__ = (
        # Timeline cronológica por pedido
        Index("ix_order_events_order_when", "order_id", "created_at"),
        # Filtros por tenant + tipo para dashboards
        Index("ix_order_events_tenant_type", "tenant_id", "event_type"),
    )
