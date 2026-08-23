"""Orders API — gestión de pedidos del tenant."""
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.database import get_db
from app.deps import get_current_membership, get_current_user, get_tenant_for_membership
from app.models.tenant import Tenant
from app.models.tenant import TenantMembership
from app.models.user import User
from app.models.order import Order, OrderItem, OrderStatus
from app.schemas.order import OrderCreate, OrderOut, OrderTransition, OrderListItem
from app.schemas.common import Page
from app.services.order_service import OrderService

router = APIRouter(prefix="/tenants/{tenant_id}/orders", tags=["orders"])


@router.get("", response_model=Page[OrderListItem])
def list_orders(
    tenant_id: UUID,
    status: Optional[OrderStatus] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    membership: TenantMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    """Lista pedidos del tenant."""
    return OrderService(db).list(tenant_id, status=status, page=page, page_size=page_size)


@router.post("", response_model=OrderOut, status_code=201)
def create_order(
    tenant_id: UUID,
    payload: OrderCreate,
    membership: TenantMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    """Crea un pedido desde el panel del tenant."""
    tenant = db.get(Tenant, tenant_id)
    if not tenant:
        raise NotFoundError("Tenant")
    order = OrderService(db).create(
        tenant,
        items=[{"product_id": it.product_id, "quantity": it.quantity, "options": it.options} for it in payload.items],
        customer_id=payload.customer_id,
        customer_name=payload.customer_name,
        customer_phone=payload.customer_phone,
        customer_email=payload.customer_email,
        shipping_address=payload.shipping_address,
        notes=payload.notes,
        source=payload.source,
        promotion_codes=payload.promotion_codes,
    )
    return _to_out(order)


@router.get("/{order_id}", response_model=OrderOut)
def get_order(
    tenant_id: UUID,
    order_id: UUID,
    membership: TenantMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    o = OrderService(db).get(tenant_id, order_id)
    return _to_out(o)


@router.get("/by-number/{number}", response_model=OrderOut)
def get_order_by_number(
    tenant_id: UUID,
    number: str,
    membership: TenantMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    o = OrderService(db).get_by_number(tenant_id, number)
    return _to_out(o)


@router.post("/{order_id}/transition", response_model=OrderOut)
def transition_order(
    tenant_id: UUID,
    order_id: UUID,
    payload: OrderTransition,
    membership: TenantMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    """Cambia el estado del pedido (state machine)."""
    o = OrderService(db).get(tenant_id, order_id)
    o = OrderService(db).transition(o, payload.new_status)
    # Disparar webhook
    try:
        from app.services.webhook_service import WebhookDispatcher
        WebhookDispatcher(db).dispatch(
            tenant_id=str(o.tenant_id),
            event=f"order.{payload.new_status.value}",
            payload={
                "order_id": str(o.id),
                "number": o.number,
                "status": o.status.value,
                "total_cents": o.total_cents,
                "currency": o.currency,
            },
        )
    except Exception:
        pass
    return _to_out(o)


@router.get("/today-summary")
def orders_today_summary(
    tenant_id: UUID,
    membership: TenantMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    """Resumen de ventas del día en curso (P1.6 — Dashboard hero card).

    Devuelve el total facturado hoy y la cantidad de pedidos. Solo
    cuenta pedidos que NO están cancelados (status != 'canceled').
    Es una agregación ligera: una sola query SQL con SUM/COUNT.
    """
    from datetime import datetime, time, timezone
    from sqlalchemy import func as _func, select as _select
    now = datetime.now(timezone.utc)
    start_of_day = datetime.combine(now.date(), time.min, tzinfo=timezone.utc)
    # Pedidos del día excluyendo cancelados
    q = (
        _select(
            _func.coalesce(_func.sum(Order.total_cents), 0).label("total_cents"),
            _func.count(Order.id).label("orders_count"),
        )
        .where(
            Order.tenant_id == str(tenant_id),
            Order.created_at >= start_of_day,
            Order.status != OrderStatus.CANCELED,
        )
    )
    row = db.execute(q).one()
    return {
        "date": now.date().isoformat(),
        "total_cents": int(row.total_cents or 0),
        "orders_count": int(row.orders_count or 0),
    }


@router.post("/{order_id}/cancel", response_model=OrderOut)
def cancel_order(
    tenant_id: UUID,
    order_id: UUID,
    reason: Optional[str] = None,
    membership: TenantMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    o = OrderService(db).get(tenant_id, order_id)
    return _to_out(OrderService(db).cancel(o, reason=reason))


def _to_out(o: Order) -> OrderOut:
    return OrderOut(
        id=o.id,
        tenant_id=o.tenant_id if isinstance(o.tenant_id, UUID) else UUID(str(o.tenant_id)),
        number=o.number,
        status=o.status,
        customer_id=o.customer_id if (o.customer_id and isinstance(o.customer_id, UUID)) else (UUID(o.customer_id) if o.customer_id else None),
        branch_id=o.branch_id if (o.branch_id and isinstance(o.branch_id, UUID)) else (UUID(o.branch_id) if o.branch_id else None),
        subtotal_cents=o.subtotal_cents,
        discount_cents=o.discount_cents,
        shipping_cents=o.shipping_cents,
        tax_cents=o.tax_cents,
        total_cents=o.total_cents,
        currency=o.currency,
        promotion_ids=o.promotion_ids or [],
        customer_name=o.customer_name,
        customer_phone=o.customer_phone,
        customer_email=o.customer_email,
        shipping_address=o.shipping_address,
        notes=o.notes,
        source=o.source,
        qr_code_id=o.qr_code_id if (o.qr_code_id and isinstance(o.qr_code_id, UUID)) else (UUID(o.qr_code_id) if o.qr_code_id else None),
        items=[
            {
                "id": it.id,
                "product_id": UUID(it.product_id) if it.product_id and not isinstance(it.product_id, UUID) else it.product_id,
                "product_name": it.product_name,
                "product_sku": it.product_sku,
                "product_image": it.product_image,
                "quantity": it.quantity,
                "unit_price_cents": it.unit_price_cents,
                "total_cents": it.total_cents,
                "options": it.options or {},
            } for it in (o.items or [])
        ],
        created_at=o.created_at,
        updated_at=o.updated_at,
    )
