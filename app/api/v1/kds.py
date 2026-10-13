"""HU_21 — KDS (Kitchen Display System) — Router de la cola de cocina.

Endpoints:
  GET   /tenants/{tid}/kds/queue                devuelve pedidos activos (cola KDS)
  POST  /tenants/{tid}/kds/orders/{oid}/ready   marca pedido como LISTO
  POST  /tenants/{tid}/kds/orders/{oid}/start   marca pedido como EN_PREPARACION

Reglas de estado:
  - Cola KDS = pedidos en RECIBIDO / CONFIRMADO / EN_PREPARACION.
    No se incluyen LISTO, ENTREGADO, PAGADO ni CANCELADO.
  - El endpoint respeta multi-tenant: usa `get_current_membership`
    para validar que el usuario pertenece al tenant del path.
  - El cálculo de `age_minutes` se hace en el servidor (UTC) para
    que el cliente sólo pinte, no derive.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.database import get_db
from app.deps import get_current_membership, get_tenant_for_membership
from app.models.order import Order, OrderItem, OrderStatus
from app.models.tenant import Tenant, TenantMembership

# Estados que el KDS considera "activos" (en cocina).
KDS_ACTIVE_STATUSES = (
    OrderStatus.RECIBIDO,
    OrderStatus.CONFIRMADO,
    OrderStatus.EN_PREPARACION,
)

router = APIRouter(
    prefix="/tenants/{tenant_id}/kds",
    tags=["kds"],
)


def _compute_age_minutes(created_at: Optional[datetime]) -> int:
    """Minutos transcurridos desde `created_at` hasta ahora (UTC).

    Devuelve 0 si `created_at` es None o está en el futuro (reloj desinc.).
    """
    if not created_at:
        return 0
    now = datetime.now(timezone.utc)
    # Normalizar a UTC-aware: si la columna se guardó naive, asumimos UTC.
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    delta = (now - created_at).total_seconds()
    if delta < 0:
        return 0
    return int(delta // 60)


def _compute_priority(age_minutes: int) -> str:
    """Prioridad derivada de la edad del pedido (FIFO con threshold crítico).

    Coincide con los thresholds del timer del cliente (kds.html):
      - critical: age ≥ 15 min  (rojo)
      - high:     age ≥ 10 min  (amarillo)
      - normal:   age < 10 min  (verde)
    """
    if age_minutes >= 15:
        return "critical"
    if age_minutes >= 10:
        return "high"
    return "normal"


def _serialize_order(o: Order) -> dict:
    """Serializa un pedido al shape que consume el KDS del frontend."""
    age_min = _compute_age_minutes(o.created_at)
    return {
        "order_id": str(o.id),
        "order_number": o.number,
        "status": o.status.value,
        "customer_name": o.customer_name or "",
        "customer_phone": o.customer_phone,
        "notes": o.notes,
        "source": o.source,
        "items": [
            {
                "id": str(it.id),
                "product_id": str(it.product_id) if it.product_id else None,
                "product_name": it.product_name,
                "quantity": it.quantity,
                "unit_price_cents": it.unit_price_cents,
                "total_cents": it.total_cents,
                "options": it.options or {},
            }
            for it in (o.items or [])
        ],
        "priority": _compute_priority(age_min),
        "age_minutes": age_min,
        "created_at": o.created_at.isoformat() if o.created_at else None,
    }


@router.get("/queue")
def get_kds_queue(
    tenant_id: UUID,
    membership: TenantMembership = Depends(get_current_membership),
    tenant: Tenant = Depends(get_tenant_for_membership),
    db: Session = Depends(get_db),
):
    """Devuelve la cola de pedidos activos del KDS.

    La cola incluye pedidos en `recibido`, `confirmado` y `en_preparacion`,
    ordenada por `created_at` ascendente (FIFO — el más antiguo primero).

    Args:
        tenant_id: tenant del path (validado por `get_current_membership`).
        membership: membresía activa del usuario en `tenant_id`.
        tenant: tenant resuelto (uso secundario para validación de existencia).

    Returns:
        `{"queue": [...], "count": N, "active_statuses": [...]}`.
    """
    # Doble verificación por si la membresía no matchea el tenant_id del path.
    if str(membership.tenant_id) != str(tenant_id):
        raise NotFoundError("Tenant")

    # Seleccionar pedidos activos con sus items en una sola query (evita N+1).
    stmt = (
        select(Order)
        .where(
            Order.tenant_id == str(tenant_id),
            Order.status.in_(KDS_ACTIVE_STATUSES),
        )
        .options(selectinload(Order.items))
        .order_by(Order.created_at.asc())
        .limit(200)  # Cap defensivo: el KDS muestra una pantalla, no informes.
    )
    orders = list(db.execute(stmt).scalars().all())

    return {
        "tenant_id": str(tenant_id),
        "count": len(orders),
        "active_statuses": [s.value for s in KDS_ACTIVE_STATUSES],
        "queue": [_serialize_order(o) for o in orders],
    }


@router.post("/orders/{order_id}/start")
def kds_start_order(
    tenant_id: UUID,
    order_id: UUID,
    membership: TenantMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    """Marca un pedido como `en_preparacion` (entra a cocina).

    Sólo válido si el pedido está en `recibido` o `confirmado`. Si ya
    está `en_preparacion` (o posterior), es idempotente y devuelve 200.
    """
    if str(membership.tenant_id) != str(tenant_id):
        raise NotFoundError("Tenant")

    o = db.get(Order, order_id)
    if not o or str(o.tenant_id) != str(tenant_id):
        raise NotFoundError("Pedido")

    if o.status == OrderStatus.CANCELADO or o.status == OrderStatus.ENTREGADO:
        raise ConflictError(
            f"No se puede iniciar un pedido en estado {o.status.value}"
        )

    if o.status == OrderStatus.EN_PREPARACION:
        # Idempotente: ya está en cocina, no hacer nada.
        return {"ok": True, "order_id": str(o.id), "status": o.status.value}

    if o.status not in (OrderStatus.RECIBIDO, OrderStatus.CONFIRMADO):
        raise ValidationError(
            f"Sólo pedidos recibidos/confirmados pueden pasar a preparación "
            f"(estado actual: {o.status.value})"
        )

    from app.services.order_service import OrderService
    o = OrderService(db).transition(o, OrderStatus.EN_PREPARACION)
    return {"ok": True, "order_id": str(o.id), "status": o.status.value}


@router.post("/orders/{order_id}/ready")
def kds_mark_ready(
    tenant_id: UUID,
    order_id: UUID,
    membership: TenantMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    """Marca un pedido como `listo` (sale de cocina).

    Sólo válido si el pedido está `en_preparacion`. Si ya está `listo`,
    es idempotente y devuelve 200 (la UI evita dobles clicks con un hold
    de 600ms pero el server debe ser defensivo).
    """
    if str(membership.tenant_id) != str(tenant_id):
        raise NotFoundError("Tenant")

    o = db.get(Order, order_id)
    if not o or str(o.tenant_id) != str(tenant_id):
        raise NotFoundError("Pedido")

    if o.status == OrderStatus.LISTO:
        # Idempotente: ya está listo.
        return {"ok": True, "order_id": str(o.id), "status": o.status.value}

    if o.status != OrderStatus.EN_PREPARACION:
        raise ValidationError(
            f"Sólo pedidos en preparación pueden marcarse como listos "
            f"(estado actual: {o.status.value})"
        )

    from app.services.order_service import OrderService
    o = OrderService(db).transition(o, OrderStatus.LISTO)
    return {"ok": True, "order_id": str(o.id), "status": o.status.value}