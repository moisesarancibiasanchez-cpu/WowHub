"""Analytics API — análisis avanzado para el Asistente IA y dashboards.

Endpoints:
- GET /tenants/{tenant_id}/analytics/inventory        → análisis de inventario segmentado
- GET /tenants/{tenant_id}/analytics/customer-segments → segmentación de clientes
- GET /tenants/{tenant_id}/analytics/activity         → feed de actividad reciente (P2 #2)
- GET /tenants/{tenant_id}/analytics/sales-7d         → serie de ventas 7 días
"""
from typing import Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_membership, get_tenant_for_membership
from app.models.tenant import Tenant, TenantMembership
from app.schemas.analytics import (
    CustomerSegmentResponse,
    InventoryResponse,
)
from app.services.analytics_service import AnalyticsService

router = APIRouter(
    prefix="/tenants/{tenant_id}/analytics",
    tags=["analytics"],
)


@router.get("/inventory", response_model=InventoryResponse)
def get_inventory_analytics(
    tenant: Tenant = Depends(get_tenant_for_membership),
    db: Session = Depends(get_db),
    category: Literal["all", "low_stock", "out_of_stock", "overstock", "dead_stock", "top_selling"] = Query(
        "all",
        description="Categoría de inventario a analizar.",
    ),
    days_dead: int = Query(60, ge=1, le=365, description="Días sin ventas para considerar 'dead stock'."),
    days_top: int = Query(30, ge=1, le=365, description="Ventana para 'top_selling'."),
    overstock_threshold: int = Query(100, ge=1, description="Stock por encima del cual se considera 'overstock'."),
    low_stock_threshold: Optional[int] = Query(
        None, ge=0, description="Override del umbral de low stock (si no se da, usa el del producto).",
    ),
    limit: int = Query(50, ge=1, le=500),
):
    """Análisis de inventario segmentado.

    Devuelve un resumen (`summary`) con conteos por categoría y la lista
    de productos (`items`) con metadatos relevantes para el Asistente IA.
    """
    data = AnalyticsService(db).inventory(
        tenant.id,
        category=category,
        days_dead=days_dead,
        days_top=days_top,
        overstock_threshold=overstock_threshold,
        low_stock_threshold=low_stock_threshold,
        limit=limit,
    )
    return data


@router.get("/customer-segments", response_model=CustomerSegmentResponse)
def get_customer_segments(
    tenant: Tenant = Depends(get_tenant_for_membership),
    db: Session = Depends(get_db),
    segment: Literal["all", "inactive", "top", "new", "vip", "no_orders"] = Query(
        "all",
        description="Segmento de clientes a devolver.",
    ),
    days_inactive: int = Query(60, ge=1, le=365, description="Días sin comprar = inactivo."),
    days_new: int = Query(30, ge=1, le=365, description="Ventana para considerar 'nuevo'."),
    top_percentile: float = Query(0.2, ge=0.01, le=1.0,
                                  description="Percentil para el segmento 'top'."),
    vip_min_orders: int = Query(5, ge=1, description="Mínimo de órdenes para 'vip'."),
    vip_min_spent_cents: int = Query(50000, ge=0,
                                     description="Mínimo de gasto (centavos) para 'vip'."),
    limit: int = Query(100, ge=1, le=500),
):
    """Segmentación de clientes del tenant.

    Devuelve `summary` con conteos rápidos por categoría y la lista de
    clientes que cumplen el criterio (`items`).
    """
    data = AnalyticsService(db).customer_segments(
        tenant.id,
        segment=segment,
        days_inactive=days_inactive,
        days_new=days_new,
        top_percentile=top_percentile,
        vip_min_orders=vip_min_orders,
        vip_min_spent_cents=vip_min_spent_cents,
        limit=limit,
    )
    return data


@router.get("/activity")
def get_activity_feed(
    tenant: Tenant = Depends(get_tenant_for_membership),
    db: Session = Depends(get_db),
    limit: int = Query(20, ge=1, le=100,
                       description="Cantidad máxima de eventos a devolver."),
    days: int = Query(30, ge=1, le=90,
                      description="Ventana de búsqueda en días hacia atrás."),
):
    """Feed de actividad reciente del tenant (P2 #2 — Dashboard).

    Agrega eventos de distintas tablas (orders, customers, bookings,
    quotes, loyalty_passes) en una sola línea de tiempo ordenada por
    fecha descendente. No requiere migraciones: deriva los eventos
    de las entidades existentes.

    Cada item tiene:
      - kind:        tipo de evento (order.created, customer.created, …)
      - icon:        emoji sugerido para mostrar
      - title:       texto principal (ej. "Nuevo pedido #123")
      - subtitle:    texto secundario (cliente, monto, etc.)
      - action_url:  link a la página relevante del dashboard
      - occurred_at: ISO 8601 UTC
    """
    from datetime import datetime, timedelta, timezone
    from sqlalchemy import select as _select
    from app.models.order import Order
    from app.models.customer import Customer
    from app.models.booking import Booking
    from app.models.quote import Quote
    from app.models.loyalty_pass import CustomerPass

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)
    events = []

    # ── Orders: creado / confirmado / entregado ──────────────
    try:
        oq = (
            _select(
                Order.id, Order.number, Order.status,
                Order.customer_name, Order.total_cents, Order.currency,
                Order.created_at, Order.updated_at,
            )
            .where(Order.tenant_id == str(tenant.id))
            .where(Order.created_at >= cutoff)
            .order_by(Order.created_at.desc())
            .limit(limit)
        )
        for r in db.execute(oq).all():
            events.append({
                "kind": "order.created",
                "icon": "📦",
                "title": f"Pedido #{r.number} creado",
                "subtitle": (r.customer_name or "Cliente anónimo")
                             + f" · ${(r.total_cents or 0)/100:,.0f}",
                "action_url": f"/dashboard/orders?focus={r.id}",
                "occurred_at": r.created_at.isoformat() if r.created_at else None,
            })
            if r.status and r.status.value in ("delivered", "ready") and r.updated_at and r.updated_at != r.created_at:
                events.append({
                    "kind": f"order.{r.status.value}",
                    "icon": "✅" if r.status.value == "delivered" else "🍽️",
                    "title": f"Pedido #{r.number} {r.status.value}",
                    "subtitle": (r.customer_name or "Cliente anónimo")
                                 + f" · ${(r.total_cents or 0)/100:,.0f}",
                    "action_url": f"/dashboard/orders?focus={r.id}",
                    "occurred_at": r.updated_at.isoformat() if r.updated_at else None,
                })
    except Exception:
        pass

    # ── Customers: nuevos clientes ──────────────────────────
    try:
        cq = (
            _select(Customer.id, Customer.full_name, Customer.email, Customer.created_at)
            .where(Customer.tenant_id == str(tenant.id))
            .where(Customer.created_at >= cutoff)
            .order_by(Customer.created_at.desc())
            .limit(limit)
        )
        for r in db.execute(cq).all():
            events.append({
                "kind": "customer.created",
                "icon": "👤",
                "title": f"Nuevo cliente: {r.full_name or r.email or 'Sin nombre'}",
                "subtitle": r.email or "",
                "action_url": f"/dashboard/customers?focus={r.id}",
                "occurred_at": r.created_at.isoformat() if r.created_at else None,
            })
    except Exception:
        pass

    # ── Bookings: reservas nuevas ───────────────────────────
    try:
        bq = (
            _select(Booking.id, Booking.customer_name, Booking.status,
                    Booking.starts_at, Booking.created_at)
            .where(Booking.tenant_id == str(tenant.id))
            .where(Booking.created_at >= cutoff)
            .order_by(Booking.created_at.desc())
            .limit(limit)
        )
        for r in db.execute(bq).all():
            events.append({
                "kind": "booking.created",
                "icon": "📅",
                "title": f"Reserva: {r.customer_name or 'Sin nombre'}",
                "subtitle": (r.starts_at.strftime("%d/%m %H:%M")
                             if r.starts_at else "Sin fecha"),
                "action_url": f"/dashboard/bookings?focus={r.id}",
                "occurred_at": r.created_at.isoformat() if r.created_at else None,
            })
    except Exception:
        pass

    # ── Quotes: cotizaciones nuevas ─────────────────────────
    try:
        qq = (
            _select(Quote.id, Quote.number, Quote.recipient_name,
                    Quote.total_cents, Quote.created_at)
            .where(Quote.tenant_id == str(tenant.id))
            .where(Quote.created_at >= cutoff)
            .order_by(Quote.created_at.desc())
            .limit(limit)
        )
        for r in db.execute(qq).all():
            events.append({
                "kind": "quote.created",
                "icon": "📝",
                "title": f"Cotización #{r.number}",
                "subtitle": (r.recipient_name or "Cliente anónimo")
                             + f" · ${(r.total_cents or 0)/100:,.0f}",
                "action_url": f"/dashboard/quotes?focus={r.id}",
                "occurred_at": r.created_at.isoformat() if r.created_at else None,
            })
    except Exception:
        pass

    # ── Loyalty: tarjetas emitidas ──────────────────────────
    try:
        lq = (
            _select(CustomerPass.id, CustomerPass.serial_number, CustomerPass.created_at)
            .where(CustomerPass.tenant_id == str(tenant.id))
            .where(CustomerPass.created_at >= cutoff)
            .order_by(CustomerPass.created_at.desc())
            .limit(limit)
        )
        for r in db.execute(lq).all():
            events.append({
                "kind": "loyalty.issued",
                "icon": "🎟️",
                "title": "Tarjeta de fidelidad emitida",
                "subtitle": r.serial_number or "",
                "action_url": "/dashboard/loyalty",
                "occurred_at": r.created_at.isoformat() if r.created_at else None,
            })
    except Exception:
        pass

    # ── Ordenar por fecha desc y recortar a `limit` ─────────
    def _ts(e):
        try:
            return e.get("occurred_at") or ""
        except Exception:
            return ""
    events.sort(key=_ts, reverse=True)
    return {
        "window_days": days,
        "count": len(events[:limit]),
        "events": events[:limit],
    }


@router.get("/sales-7d")
def get_sales_7d(
    tenant: Tenant = Depends(get_tenant_for_membership),
    db: Session = Depends(get_db),
):
    """Serie de ventas de los últimos 7 días (P2 #1 — chart Dashboard).

    Devuelve la serie diaria `series: [{date, total_cents, orders_count}]`
    para los últimos 7 días (incluyendo hoy). Los días sin pedidos
    aparecen con `total_cents=0` y `orders_count=0` para mantener la
    serie continua y lista para graficar.
    """
    from datetime import datetime, time, timedelta, timezone
    from sqlalchemy import func as _func, select as _select
    from app.models.order import Order, OrderStatus

    now = datetime.now(timezone.utc)
    today_start = datetime.combine(now.date(), time.min, tzinfo=timezone.utc)
    start_window = today_start - timedelta(days=6)
    q = (
        _select(
            _func.date(Order.created_at).label("d"),
            _func.coalesce(_func.sum(Order.total_cents), 0).label("total_cents"),
            _func.count(Order.id).label("orders_count"),
        )
        .where(
            Order.tenant_id == str(tenant.id),
            Order.created_at >= start_window,
            Order.status != OrderStatus.CANCELED,
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
