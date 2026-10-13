"""HU_17 — Servicio de eventos del pedido (OrderEvent).

Crea y consulta eventos de timeline. El método ``record_status_change``
se invoca desde OrderService.transition() (hook automático cuando
cambia el status del Order).
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.models.order import Order
from app.models.order_event import OrderEvent, OrderEventType
from app.models.user import User


class OrderEventService:
    def __init__(self, db: Session, tenant_id: str):
        self.db = db
        self.tenant_id = tenant_id

    # ── Helpers ────────────────────────────────────────────
    def _get_order(self, order_id: UUID) -> Order:
        o = self.db.get(Order, order_id)
        if not o or str(o.tenant_id) != str(self.tenant_id):
            raise NotFoundError("Pedido")
        return o

    # ── Lectura ────────────────────────────────────────────
    def timeline(self, order_id: UUID) -> list[OrderEvent]:
        """Devuelve la línea de tiempo completa en orden cronológico."""
        self._get_order(order_id)
        return list(self.db.execute(
            select(OrderEvent)
            .where(
                OrderEvent.tenant_id == self.tenant_id,
                OrderEvent.order_id == str(order_id),
            )
            .order_by(OrderEvent.created_at.asc())
        ).scalars())

    # ── Creación ───────────────────────────────────────────
    def add_note(
        self, order_id: UUID, message: str,
        payload: Optional[dict] = None,
        actor: Optional[User] = None,
    ) -> OrderEvent:
        """Crea un evento NOTE (nota manual del owner/garzón)."""
        o = self._get_order(order_id)
        ev = OrderEvent(
            tenant_id=self.tenant_id,
            order_id=str(o.id),
            event_type=OrderEventType.NOTE.value,
            payload=payload or {"text": message},
            message=message,
            actor_user_id=str(actor.id) if actor and getattr(actor, "id", None) else None,
        )
        self.db.add(ev)
        self.db.commit()
        self.db.refresh(ev)
        return ev

    def record_status_change(
        self,
        order: Order,
        from_status: str,
        to_status: str,
        actor: Optional[User] = None,
        notes: Optional[str] = None,
    ) -> OrderEvent:
        """Hook automático: lo llama OrderService.transition().

        Se persiste en la MISMA transacción que el cambio de status
        para garantizar atomicidad.
        """
        ev = OrderEvent(
            tenant_id=str(order.tenant_id),
            order_id=str(order.id),
            event_type=OrderEventType.STATUS_CHANGE.value,
            payload={
                "from": from_status,
                "to": to_status,
            },
            message=notes or f"Estado: {from_status} → {to_status}",
            actor_user_id=str(actor.id) if actor and getattr(actor, "id", None) else None,
        )
        self.db.add(ev)
        # No commit aquí: el caller (OrderService.transition) hace commit.
        self.db.flush()
        return ev

    def record_payment(
        self, order: Order, payload: dict,
        actor: Optional[User] = None,
    ) -> OrderEvent:
        ev = OrderEvent(
            tenant_id=str(order.tenant_id),
            order_id=str(order.id),
            event_type=OrderEventType.PAYMENT.value,
            payload=payload,
            message=payload.get("message") or f"Pago: {payload.get('method', '')}",
            actor_user_id=str(actor.id) if actor and getattr(actor, "id", None) else None,
        )
        self.db.add(ev)
        self.db.flush()
        return ev

    def record_channel(
        self, order: Order, payload: dict,
        actor: Optional[User] = None,
    ) -> OrderEvent:
        ev = OrderEvent(
            tenant_id=str(order.tenant_id),
            order_id=str(order.id),
            event_type=OrderEventType.CHANNEL.value,
            payload=payload,
            message=payload.get("message"),
            actor_user_id=str(actor.id) if actor and getattr(actor, "id", None) else None,
        )
        self.db.add(ev)
        self.db.flush()
        return ev
