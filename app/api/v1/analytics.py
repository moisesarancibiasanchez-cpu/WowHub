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
            if r.status and r.status.value in ("entregado", "listo") and r.updated_at and r.updated_at != r.created_at:
                events.append({
                    "kind": f"order.{r.status.value}",
                    "icon": "✅" if r.status.value == "entregado" else "🍽️",
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


# ── HU_35 — Comparativas temporales ────────────────────────────────────
# Presets de período soportados. Mantener sincronizado con ``ALLOWED_PERIODS``.
_PERIOD_PRESETS = {
    "today": 1,
    "7d": 7,
    "14d": 14,
    "30d": 30,
    "90d": 90,
    "1y": 365,
}
ALLOWED_PERIODS = Literal["today", "7d", "14d", "30d", "90d", "1y"]


def _detect_anomalies(values: list[int], z_threshold: float = 2.0) -> list[bool]:
    """Detección simple de anomalías por Z-score.

    Marca un punto como anómalo si su Z-score (desviaciones estándar
    respecto a la media móvil) supera ``z_threshold``. Para series
    cortas (n<3) no detecta nada.

    Returns:
        Lista de bool (True = anómalo) del mismo tamaño que ``values``.
    """
    n = len(values)
    if n < 3:
        return [False] * n
    mean = sum(values) / n
    variance = sum((v - mean) ** 2 for v in values) / n
    std = variance ** 0.5
    if std < 1e-9:
        return [False] * n
    return [abs((v - mean) / std) >= z_threshold for v in values]


@router.get("/sales-7d")
def get_sales_7d(
    tenant: Tenant = Depends(get_tenant_for_membership),
    db: Session = Depends(get_db),
):
    """Serie de ventas de los últimos 7 días (back-compat con HU_30).

    Mantiene la firma original (HU_30). Internamente delega en
    ``_build_sales_series`` con período ``"7d"``.
    """
    return _build_sales_series(db, tenant.id, period="7d")


@router.get("/sales-trend")
def get_sales_trend(
    tenant: Tenant = Depends(get_tenant_for_membership),
    db: Session = Depends(get_db),
    period: ALLOWED_PERIODS = Query(
        "7d",
        description="Preset de período: today | 7d | 14d | 30d | 90d | 1y",
    ),
    detect_anomalies: bool = Query(
        True,
        description="Si True, marca días con Z-score > 2 como anómalos.",
    ),
):
    """Serie temporal de ventas con presets de período (HU_35).

    Acepta los presets definidos en ``_PERIOD_PRESETS``:
      - ``today``: solo hoy.
      - ``7d``:    últimos 7 días (default, back-compat con ``/sales-7d``).
      - ``14d``:   últimos 14 días.
      - ``30d``:   último mes.
      - ``90d``:   último trimestre.
      - ``1y``:    último año.

    Devuelve:
      - ``series``: lista diaria con ``total_cents``, ``orders_count`` y
        opcional ``is_anomaly`` (cuando ``detect_anomalies=True``).
      - ``summary``: agregados del período (totales, promedios, mejor/
        peor día, # de anomalías).
      - ``comparison``: delta vs período anterior (delta_total_cents,
        delta_orders_count, delta_pct).
    """
    return _build_sales_series(
        db, tenant.id, period=period, detect_anomalies=detect_anomalies,
    )


def _build_sales_series(
    db: Session,
    tenant_id,
    period: str = "7d",
    detect_anomalies: bool = True,
    z_threshold: float = 2.0,
) -> dict:
    """Construye la serie de ventas para un tenant y un período dado.

    Helper interno compartido por ``/sales-7d`` (HU_30, back-compat) y
    ``/sales-trend`` (HU_35, con presets y anomalías).
    """
    from datetime import datetime, time, timedelta, timezone
    from sqlalchemy import func as _func, select as _select
    from app.models.order import Order, OrderStatus

    if period not in _PERIOD_PRESETS:
        period = "7d"
    window_days = _PERIOD_PRESETS[period]

    now = datetime.now(timezone.utc)
    today_start = datetime.combine(now.date(), time.min, tzinfo=timezone.utc)
    start_window = today_start - timedelta(days=window_days - 1)
    # Período anterior: mismo número de días, inmediatamente antes.
    prev_start = start_window - timedelta(days=window_days)
    prev_end = start_window - timedelta(seconds=1)

    # ── Query principal: período actual ──
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

    # ── Query período anterior (para comparación) ──
    q_prev = (
        _select(
            _func.coalesce(_func.sum(Order.total_cents), 0).label("total_cents"),
            _func.count(Order.id).label("orders_count"),
        )
        .where(
            Order.tenant_id == str(tenant_id),
            Order.created_at >= prev_start,
            Order.created_at <= prev_end,
            Order.status != OrderStatus.CANCELADO,
        )
    )
    prev_row = db.execute(q_prev).one()
    prev_total = int(prev_row.total_cents or 0)
    prev_orders = int(prev_row.orders_count or 0)

    # ── Construir serie completa (incluyendo días sin ventas) ──
    series = []
    total_period = 0
    total_orders = 0
    daily_totals = []  # para detección de anomalías
    for i in range(window_days):
        d = (start_window + timedelta(days=i)).date()
        r = by_day.get(d.isoformat())
        cents = int(r.total_cents or 0) if r else 0
        oc = int(r.orders_count or 0) if r else 0
        total_period += cents
        total_orders += oc
        daily_totals.append(cents)
        series.append({
            "date": d.isoformat(),
            "total_cents": cents,
            "orders_count": oc,
        })

    # ── Detección de anomalías ──
    anomalies = _detect_anomalies(daily_totals, z_threshold=z_threshold) if detect_anomalies else [False] * len(series)
    for s, is_anom in zip(series, anomalies):
        s["is_anomaly"] = is_anom
    n_anomalies = sum(anomalies)

    # ── Mejor / peor día ──
    if series:
        best = max(series, key=lambda x: x["total_cents"])
        worst = min(series, key=lambda x: x["total_cents"])
        best_day = best["date"] if best["total_cents"] > 0 else None
        worst_day = worst["date"] if worst["total_cents"] > 0 else None
    else:
        best_day = worst_day = None

    # ── Comparación con período anterior ──
    delta_total = total_period - prev_total
    delta_orders = total_orders - prev_orders
    delta_pct = (delta_total / prev_total * 100.0) if prev_total > 0 else (100.0 if total_period > 0 else 0.0)

    return {
        "period": period,
        "window_days": window_days,
        "from": start_window.date().isoformat(),
        "to": now.date().isoformat(),
        "total_cents": total_period,
        "orders_count": total_orders,
        "avg_per_day_cents": total_period // max(window_days, 1),
        "best_day": best_day,
        "worst_day": worst_day,
        "anomalies_detected": n_anomalies,
        "comparison": {
            "prev_total_cents": prev_total,
            "prev_orders_count": prev_orders,
            "delta_total_cents": delta_total,
            "delta_orders_count": delta_orders,
            "delta_pct": round(delta_pct, 2),
        },
        "series": series,
    }
