"""HU_17 — Router de eventos del pedido (timeline).

Endpoints:
  GET   /tenants/{tid}/orders/{oid}/timeline   devuelve la lista cronológica
  POST  /tenants/{tid}/orders/{oid}/events     crea un evento manual (NOTE)
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_membership, get_current_user
from app.models.user import User
from app.schemas.order import OrderEventCreate, OrderEventOut
from app.services.order_event_service import OrderEventService

router = APIRouter(
    prefix="/tenants/{tenant_id}/orders/{order_id}/events",
    tags=["order-events"],
)


@router.get("/timeline", response_model=list[OrderEventOut])
def get_timeline(
    tenant_id: UUID,
    order_id: UUID,
    user: User = Depends(get_current_user),
    membership=Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    """Línea de tiempo completa del pedido, ordenada cronológicamente."""
    svc = OrderEventService(db, tenant_id=str(tenant_id))
    return svc.timeline(order_id)


@router.post("", response_model=OrderEventOut, status_code=status.HTTP_201_CREATED)
def create_event(
    tenant_id: UUID,
    order_id: UUID,
    payload: OrderEventCreate,
    user: User = Depends(get_current_user),
    membership=Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    """Crea un evento manual (NOTE/PAYMENT/REFUND/CHANNEL) en la timeline.

    El tipo STATUS_CHANGE se crea automáticamente desde
    OrderService.transition — no se permite emitirlo manualmente.
    """
    if payload.event_type == "status_change":
        # 422 sería más correcto, pero usamos 400 para mantener
        # coherencia con errores de lógica de negocio del proyecto.
        from fastapi import HTTPException
        raise HTTPException(
            status_code=400,
            detail="status_change se emite automáticamente; usa el endpoint de transición",
        )
    svc = OrderEventService(db, tenant_id=str(tenant_id))
    if payload.event_type == "note":
        return svc.add_note(
            order_id=order_id,
            message=payload.message or "",
            payload=payload.payload,
            actor=user,
        )
    # Para los demás tipos creamos un evento genérico
    from app.models.order_event import OrderEvent, OrderEventType
    from app.core.errors import NotFoundError

    # Validar que el pedido exista (raise NotFound si no)
    svc.timeline(order_id)  # sólo para validar existencia
    from app.models.order import Order
    o = db.get(Order, order_id)
    if not o or str(o.tenant_id) != str(tenant_id):
        raise NotFoundError("Pedido")
    ev = OrderEvent(
        tenant_id=str(tenant_id),
        order_id=str(o.id),
        event_type=payload.event_type,
        payload=payload.payload or {},
        message=payload.message,
        actor_user_id=str(user.id) if user and getattr(user, "id", None) else None,
    )
    db.add(ev)
    db.commit()
    db.refresh(ev)
    return ev
