"""Orders API — gestión de pedidos del tenant."""
from datetime import timedelta
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func as _func, select as _select
from sqlalchemy.orm import Session

# HU_38 — RBAC granular con Casbin. Los endpoints de orders ya
# declaran ``membership`` explícito, así que el decorator
# ``@requires_permission`` puede resolver el rol sin cambios extra.
from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.core.security import requires_permission
from app.core.time import now_chile
from app.database import get_db
from app.deps import get_current_membership, get_current_user, get_tenant_for_membership
from app.models.tenant import Tenant
from app.models.tenant import TenantMembership
from app.models.user import User
from app.models.order import Order, OrderItem, OrderStatus, OrderSource
from app.schemas.order import OrderCreate, OrderOut, OrderTransition, OrderListItem
from app.schemas.common import Page
from app.services.order_service import OrderService
from app.services.plugin_hooks import trigger_hooks


# HU_22 — Body para aplicar un cupón/descuento a una orden existente.
class ApplyDiscountBody(BaseModel):
    code: str = Field(..., min_length=1, max_length=40, description="Código del cupón/promoción")

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
@requires_permission("order", "write")
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
    # HU_45 — Hook: notificar a plugins del tenant.
    # Errores individuales se loggean dentro del dispatcher y NO
    # bloquean la creación del pedido (los hooks son best-effort).
    trigger_hooks(
        db=db,
        tenant_id=tenant_id,
        event="on_order_created",
        payload={
            "order_id": str(order.id) if order else None,
            "tenant_id": str(tenant_id),
            "total_cents": getattr(order, "total_cents", None),
            "customer_id": str(payload.customer_id) if payload.customer_id else None,
            "source": getattr(payload.source, "value", str(payload.source)) if payload.source else None,
        },
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
@requires_permission("order", "write")
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
    from sqlalchemy import func as _func, select as _select
    from app.core.time import now_chile, today_start_chile
    now = now_chile()
    start_of_day = today_start_chile()
    # Pedidos del día excluyendo cancelados
    q = (
        _select(
            _func.coalesce(_func.sum(Order.total_cents), 0).label("total_cents"),
            _func.count(Order.id).label("orders_count"),
        )
        .where(
            Order.tenant_id == str(tenant_id),
            Order.created_at >= start_of_day,
            Order.status != OrderStatus.CANCELADO,
        )
    )
    row = db.execute(q).one()
    return {
        "date": now.date().isoformat(),
        "total_cents": int(row.total_cents or 0),
        "orders_count": int(row.orders_count or 0),
    }


@router.get("/sales-7d")
def orders_sales_7d(
    tenant_id: UUID,
    membership: TenantMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    """Resumen de ventas de los últimos 7 días (P2 #1 — chart Dashboard).

    Devuelve una serie diaria `series: [{date, total_cents, orders_count}]`
    para los últimos 7 días (incluyendo hoy). Los días sin pedidos
    aparecen con `total_cents=0` y `orders_count=0` para mantener la
    serie continua y lista para graficar.
    """
    from datetime import timedelta
    from sqlalchemy import func as _func, select as _select
    from app.core.time import now_chile, today_start_chile
    now = now_chile()
    today_start = today_start_chile()
    start_window = today_start - timedelta(days=6)  # 7 días contando hoy
    # Agrupar por día con date_trunc (compatible con PostgreSQL y SQLite)
    q = (
        _select(
            _func.date(Order.created_at).label("d"),
            _func.coalesce(_func.sum(Order.total_cents), 0).label("total_cents"),
            _func.count(Order.id).label("orders_count"),
        )
        .where(
            Order.tenant_id == str(tenant_id),
            Order.created_at >= start_window,
            Order.status != OrderStatus.CANCELADO,
        )
        .group_by("d")
        .order_by("d")
    )
    rows = db.execute(q).all()
    by_day = {str(r.d): r for r in rows}
    series = []
    total_period = 0
    total_orders = 0
    for i in range(7):
        d = (start_window + timedelta(days=i)).date()
        r = by_day.get(d.isoformat())
        cents = int(r.total_cents or 0) if r else 0
        oc = int(r.orders_count or 0) if r else 0
        total_period += cents
        total_orders += oc
        series.append({
            "date": d.isoformat(),
            "total_cents": cents,
            "orders_count": oc,
        })
    return {
        "window_days": 7,
        "from": start_window.date().isoformat(),
        "to": now.date().isoformat(),
        "total_cents": total_period,
        "orders_count": total_orders,
        "avg_per_day_cents": total_period // 7,
        "series": series,
    }


# ── HU_16 — Channel stats (multi-canal) ─────────────────────────────────
@router.get("/channel-stats")
def orders_channel_stats(
    tenant_id: UUID,
    days: int = Query(30, ge=1, le=365, description="Ventana de agregación en días"),
    branch_id: Optional[UUID] = Query(None, description="Filtrar por sucursal"),
    membership: TenantMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    """Pedidos agregados por canal (OrderSource).

    Devuelve, para cada canal conocido (``pos``, ``web``, ``whatsapp``,
    ``qr``, ``kiosk``, ``api``, ``test``), la cantidad de pedidos, el
    revenue total en centavos y el ticket promedio en el período
    seleccionado. Excluye pedidos cancelados del cómputo de revenue.

    - Query params:
      - ``days``: ventana en días (1..365, default 30)
      - ``branch_id``: filtro opcional por sucursal
    - Respuesta:
      ```json
      {
        "channels": [
          {"channel": "pos", "count": 45,
           "revenue_cents": 450000, "avg_ticket_cents": 10000},
          ...
        ],
        "total_orders": 100,
        "total_revenue_cents": 1500000,
        "days": 30
      }
      ```
    """
    cutoff = now_chile() - timedelta(days=days)
    q = (
        _select(
            Order.source.label("channel"),
            _func.count(Order.id).label("count"),
            _func.coalesce(
                _func.sum(
                    # SQLAlchemy no soporta CASE WHEN directo en .condition()
                    # con SUM multi-DB; usamos el filtro de status CANCELADO
                    # en WHERE para no cobrar pedidos cancelados.
                    Order.total_cents
                ),
                0,
            ).label("revenue_cents"),
        )
        .where(
            Order.tenant_id == str(tenant_id),
            Order.created_at >= cutoff,
        )
        .group_by(Order.source)
    )
    if branch_id:
        q = q.where(Order.branch_id == str(branch_id))

    rows = db.execute(q).all()

    channels: list[dict] = []
    total_orders = 0
    total_revenue = 0
    for r in rows:
        # ``channel`` viene como ``OrderSource`` o como string crudo según el
        # dialecto; normalizamos al ``value`` string (lowercase: "web", "qr"...).
        ch_value = getattr(r.channel, "value", None) or str(r.channel)
        cnt = int(r.count or 0)
        rev = int(r.revenue_cents or 0)
        # Excluir revenue de cancelados con query adicional:
        # es más simple sumar la columna ya filtrada abajo.
        channels.append({
            "channel": ch_value,
            "count": cnt,
            "revenue_cents": rev,
            "avg_ticket_cents": (rev // cnt) if cnt > 0 else 0,
        })
        total_orders += cnt
        total_revenue += rev

    # Recalcular revenue EXCLUYENDO cancelados (la query principal los
    # incluye porque solo filtra por fecha; aplicamos el filtro por canal).
    # Hacemos una segunda pasada para mantener el shape del contrato sin
    # usar CASE WHEN (que rompe SQLite sin BooleanExpression correcta).
    if rows:
        from sqlalchemy import and_
        rev_rows = db.execute(
            _select(
                Order.source.label("channel"),
                _func.coalesce(_func.sum(Order.total_cents), 0).label("revenue_cents"),
                _func.count(Order.id).label("count"),
            )
            .where(
                Order.tenant_id == str(tenant_id),
                Order.created_at >= cutoff,
                Order.status != OrderStatus.CANCELADO,
            )
            .group_by(Order.source)
        ).all()
        rev_by_ch: dict[str, tuple[int, int]] = {}
        total_orders_excl = 0
        total_revenue_excl = 0
        for r in rev_rows:
            ch_value = getattr(r.channel, "value", None) or str(r.channel)
            rev_by_ch[ch_value] = (int(r.revenue_cents or 0), int(r.count or 0))
            total_orders_excl += int(r.count or 0)
            total_revenue_excl += int(r.revenue_cents or 0)
        # Reescribir channels con revenue y count SIN cancelados
        channels = [
            {
                "channel": c["channel"],
                "count": rev_by_ch.get(c["channel"], (0, 0))[1],
                "revenue_cents": rev_by_ch.get(c["channel"], (0, 0))[0],
                "avg_ticket_cents": (
                    rev_by_ch[c["channel"]][0] // rev_by_ch[c["channel"]][1]
                    if rev_by_ch.get(c["channel"], (0, 0))[1] > 0 else 0
                ),
            }
            for c in channels
        ]
        # Ordenar por revenue desc
        channels.sort(key=lambda x: (-x["revenue_cents"], x["channel"]))
        total_orders = total_orders_excl
        total_revenue = total_revenue_excl

    return {
        "channels": channels,
        "total_orders": total_orders,
        "total_revenue_cents": total_revenue,
        "days": days,
    }


@router.post("/{order_id}/cancel", response_model=OrderOut)
@requires_permission("order", "delete")
def cancel_order(
    tenant_id: UUID,
    order_id: UUID,
    reason: Optional[str] = None,
    membership: TenantMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    o = OrderService(db).get(tenant_id, order_id)
    return _to_out(OrderService(db).cancel(o, reason=reason))


@router.post("/{order_id}/apply-discount", response_model=OrderOut)
@requires_permission("order", "write")
def apply_discount(
    tenant_id: UUID,
    order_id: UUID,
    payload: ApplyDiscountBody,
    membership: TenantMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    """Aplica un código de promoción/descuento a una orden existente.

    Valida el cupón en la tabla ``promotions`` (HU_22) y recalcula
    ``discount_cents`` y ``total_cents``. Si la orden ya tenía un
    descuento previo, lo sobreescribe con el nuevo.

    Restricciones:
    - Sólo se permite en estados no terminales (no en ENTREGADO /
      PAGADO / CANCELADO).
    - Si el código es inválido, devuelve 404.
    - Si el código está expirado o agotado, devuelve 422.
    """
    from app.services.promotion_engine import PromotionEngine

    order = OrderService(db).get(tenant_id, order_id)
    if order.status in (OrderStatus.ENTREGADO, OrderStatus.PAGADO, OrderStatus.CANCELADO):
        raise ConflictError(
            f"No se puede aplicar descuento a un pedido {order.status.value}"
        )

    code = payload.code.strip().upper()
    if not code:
        raise ValidationError("Código de descuento vacío")

    engine = PromotionEngine(db)
    # `apply_to_order` valida el código (raise NotFoundError/ValidationError
    # si es inválido o expirado) y devuelve el descuento total en centavos.
    discount_cents = engine.apply_to_order(order, [code])
    if discount_cents <= 0:
        raise ValidationError(
            f"El cupón '{code}' no aplica descuento a esta orden "
            "(verifica compra mínima o productos aplicables)"
        )

    order.discount_cents = discount_cents
    order.total_cents = max(
        0,
        order.subtotal_cents + order.shipping_cents + order.tax_cents - discount_cents,
    )
    db.commit()
    db.refresh(order)
    return _to_out(order)


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
