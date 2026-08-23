"""Customer endpoints."""
from datetime import datetime, timezone
from uuid import UUID
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select, func
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.database import get_db
from app.deps import get_tenant_for_membership
from app.models.customer import Customer
from app.models.order import Order, OrderItem, OrderStatus
from app.models.tenant import Tenant
from app.schemas.common import Page
from app.schemas.customer import (
    CustomerCreate,
    CustomerInsightsOut,
    CustomerOut,
    CustomerUpdate,
)

router = APIRouter(prefix="/tenants/{tenant_id}/customers", tags=["customers"])


# ── Helpers de segmento y métricas ───────────────────────────
# Umbrales calibrados para PyMEs chilenas. Si el cliente tiene un
# `segmento` manual seteado en la UI, ése gana; si no, se calcula
# automáticamente. (Ver audit P0.3 — spec V8 sección Clientes.)
POINTS_VIP = 500
POINTS_REGULAR = 100
DAYS_INACTIVE = 60  # sin compras → "inactivo"


def compute_segmento(c: Customer) -> str:
    """Devuelve el segmento efectivo. Si el cliente lo fijó manual, gana.
    Si no, se calcula por puntos + recencia."""
    if c.segmento:
        return c.segmento
    # Sin compras = nuevo
    if c.total_orders == 0:
        return "nuevo"
    # Inactivo: hace más de DAYS_INACTIVE días
    days = days_since(c.last_order_at)
    if days is not None and days > DAYS_INACTIVE:
        return "inactivo"
    # VIP: muchos puntos
    if c.points >= POINTS_VIP:
        return "vip"
    # Recurrente: 2+ pedidos en los últimos 30 días
    if c.total_orders >= 2 and (days is None or days <= 30):
        return "recurrente"
    # Regular: 1+ pedido
    if c.points >= POINTS_REGULAR:
        return "regular"
    return "nuevo"


def days_since(iso: Optional[str]) -> Optional[int]:
    """Calcula los días entre hoy y la fecha ISO. None si no hay fecha."""
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    return max(0, (now - dt).days)


def to_out(c: Customer) -> CustomerOut:
    """Convierte el modelo a CustomerOut rellenando campos calculados."""
    days = days_since(c.last_order_at)
    avg_ticket = 0
    if c.total_orders > 0:
        avg_ticket = int(c.total_spent_cents / c.total_orders)
    return CustomerOut(
        id=c.id,
        tenant_id=c.tenant_id,
        full_name=c.full_name,
        email=c.email,
        phone=c.phone,
        address=c.address,
        city=c.city,
        notes=c.notes,
        tags=c.tags or [],
        accepts_marketing=c.accepts_marketing,
        is_active=c.is_active,
        segmento=c.segmento,
        segmento_effective=compute_segmento(c),
        total_orders=c.total_orders,
        total_spent_cents=c.total_spent_cents,
        points=c.points,
        last_order_at=c.last_order_at,
        avg_ticket_cents=avg_ticket,
        days_since_last_order=days,
        created_at=c.created_at,
    )


@router.get("", response_model=Page[CustomerOut])
def list_customers(
    tenant: Tenant = Depends(get_tenant_for_membership),
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    search: str | None = None,
    segmento: str | None = Query(None, description="Filtrar por segmento (nuevo, regular, vip, inactivo, recurrente)"),
):
    offset = (page - 1) * page_size
    q = select(Customer).where(Customer.tenant_id == str(tenant.id))
    if search:
        like = f"%{search.lower()}%"
        q = q.where(or_(
            func.lower(Customer.full_name).like(like),
            func.lower(Customer.email).like(like),
            Customer.phone.like(f"%{search}%"),
        ))
    items_raw = list(db.execute(q.order_by(Customer.created_at.desc())).scalars())
    # Filtrar por segmento calculado (en Python para no duplicar lógica SQL)
    if segmento:
        items_raw = [c for c in items_raw if compute_segmento(c) == segmento]
    total = len(items_raw)
    items_paged = items_raw[offset:offset + page_size]
    items = [to_out(c).model_dump(mode="json") for c in items_paged]
    return Page.build(items, total, page, page_size)


@router.post("", response_model=CustomerOut, status_code=201)
def create_customer(
    payload: CustomerCreate,
    tenant: Tenant = Depends(get_tenant_for_membership),
    db: Session = Depends(get_db),
):
    c = Customer(**payload.model_dump(), tenant_id=str(tenant.id))
    db.add(c)
    db.commit()
    db.refresh(c)
    return to_out(c)


@router.get("/{customer_id}", response_model=CustomerOut)
def get_customer(customer_id: UUID, tenant: Tenant = Depends(get_tenant_for_membership), db: Session = Depends(get_db)):
    c = db.get(Customer, customer_id)
    if not c or c.tenant_id != tenant.id:
        raise NotFoundError("Customer")
    return to_out(c)


@router.patch("/{customer_id}", response_model=CustomerOut)
def update_customer(
    customer_id: UUID,
    payload: CustomerUpdate,
    tenant: Tenant = Depends(get_tenant_for_membership),
    db: Session = Depends(get_db),
):
    c = db.get(Customer, customer_id)
    if not c or c.tenant_id != tenant.id:
        raise NotFoundError("Customer")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(c, k, v)
    db.commit()
    db.refresh(c)
    return to_out(c)


@router.delete("/{customer_id}", status_code=204)
def delete_customer(customer_id: UUID, tenant: Tenant = Depends(get_tenant_for_membership), db: Session = Depends(get_db)):
    c = db.get(Customer, customer_id)
    if not c or c.tenant_id != tenant.id:
        raise NotFoundError("Customer")
    db.delete(c)
    db.commit()


@router.get("/stats")
def customers_stats(
    tenant: Tenant = Depends(get_tenant_for_membership),
    db: Session = Depends(get_db),
    active_days: int = Query(90, ge=1, le=365,
                             description="Ventana para 'clientes activos' (default 90 días)."),
):
    """Estadísticas agregadas de clientes del tenant (P1.6 — Dashboard).

    Devuelve:
    - `total`: cantidad total de clientes del tenant
    - `active_count`: clientes con al menos un pedido en los últimos N días
    - `active_days`: la ventana usada
    - `by_segment`: { segment_name: count } para mostrar desglose
    - `with_email`, `with_phone`: para el CTA de "completar datos"
    """
    from datetime import datetime, timedelta, timezone
    from sqlalchemy import func as _func, select as _select
    total = db.execute(
        _select(_func.count(Customer.id)).where(Customer.tenant_id == tenant.id)
    ).scalar_one() or 0

    # Activos: tienen al menos 1 pedido en los últimos `active_days` días.
    # Lo medimos contra la tabla de Orders, no contra `last_order_at` (que
    # puede no estar actualizado en tenants viejos). Si no hay orders
    # la subquery devuelve 0 — está bien, es un tenant sin ventas.
    threshold = datetime.now(timezone.utc) - timedelta(days=active_days)
    from app.models.order import Order
    active_q = (
        _select(_func.count(_func.distinct(Order.customer_id)))
        .where(
            Order.tenant_id == tenant.id,
            Order.created_at >= threshold,
            Order.customer_id.isnot(None),
        )
    )
    active_count = db.execute(active_q).scalar_one() or 0

    # By segment
    seg_rows = db.execute(
        _select(Customer.segmento, _func.count(Customer.id))
        .where(Customer.tenant_id == tenant.id)
        .group_by(Customer.segmento)
    ).all()
    by_segment = { (s or "sin_segmento"): int(n) for s, n in seg_rows }

    with_email = db.execute(
        _select(_func.count(Customer.id)).where(
            Customer.tenant_id == tenant.id,
            Customer.email.isnot(None),
        )
    ).scalar_one() or 0
    with_phone = db.execute(
        _select(_func.count(Customer.id)).where(
            Customer.tenant_id == tenant.id,
            Customer.phone.isnot(None),
        )
    ).scalar_one() or 0

    return {
        "total": int(total),
        "active_count": int(active_count),
        "active_days": int(active_days),
        "by_segment": by_segment,
        "with_email": int(with_email),
        "with_phone": int(with_phone),
    }


@router.get("/{customer_id}/insights", response_model=CustomerInsightsOut)
def customer_insights(
    customer_id: UUID,
    tenant: Tenant = Depends(get_tenant_for_membership),
    db: Session = Depends(get_db),
):
    """Insights IA derivados del historial de un cliente (V8 P0.3).
    Combina métricas propias con historial de pedidos para dar:
    - LTV (lifetime value)
    - Ticket promedio
    - Días desde última compra
    - Top productos comprados
    - Segmento efectivo
    - Riesgo de churn (0-100)
    - Promoción recomendada y próxima acción
    """
    c = db.get(Customer, customer_id)
    if not c or c.tenant_id != tenant.id:
        raise NotFoundError("Customer")

    days = days_since(c.last_order_at)
    avg_ticket = int(c.total_spent_cents / c.total_orders) if c.total_orders > 0 else 0
    segmento = compute_segmento(c)

    # Top productos del cliente
    top_products = []
    if c.total_orders > 0:
        rows = db.execute(
            select(
                OrderItem.product_name,
                func.sum(OrderItem.quantity).label("qty"),
                func.sum(OrderItem.total_cents).label("revenue_cents"),
            )
            .join(Order, OrderItem.order_id == Order.id)
            .where(
                Order.customer_id == customer_id,
                Order.tenant_id == str(tenant.id),
                Order.status != OrderStatus.CANCELED,
            )
            .group_by(OrderItem.product_name)
            .order_by(func.sum(OrderItem.quantity).desc())
            .limit(5)
        ).all()
        top_products = [
            {"name": r.product_name or "—", "quantity": int(r.qty or 0), "revenue_cents": int(r.revenue_cents or 0)}
            for r in rows
        ]

    # Churn risk: depende de recencia + frecuencia
    if c.total_orders == 0:
        churn_risk_pct, churn_risk_label = 0, "bajo"
    elif days is None:
        churn_risk_pct, churn_risk_label = 30, "bajo"
    elif days > 180:
        churn_risk_pct, churn_risk_label = 90, "alto"
    elif days > 90:
        churn_risk_pct, churn_risk_label = 65, "medio"
    elif days > 30:
        churn_risk_pct, churn_risk_label = 30, "bajo"
    else:
        churn_risk_pct, churn_risk_label = 5, "bajo"

    # Promoción recomendada + próxima acción por segmento
    if segmento == "vip":
        recommended_promotion = "20% descuento en próxima compra + regalo"
        next_action = "Invitar a programa VIP / agradecimiento personal"
    elif segmento == "inactivo":
        recommended_promotion = "Cupón de reactivación 15% off"
        next_action = "Enviar campaña de reactivación por email"
    elif segmento == "recurrente":
        recommended_promotion = "5% descuento adicional en 3ra compra"
        next_action = "Cross-sell de productos complementarios"
    elif segmento == "regular":
        recommended_promotion = "Cupón 10% en su próxima compra"
        next_action = "Incentivar upgrade a recurrente con bundle"
    else:  # nuevo
        recommended_promotion = "Cupón bienvenida 10% en 2da compra"
        next_action = "Hacer seguimiento post-primera-compra a los 7 días"

    return CustomerInsightsOut(
        customer_id=c.id,
        lifetime_value_cents=c.total_spent_cents,
        avg_ticket_cents=avg_ticket,
        total_orders=c.total_orders,
        points=c.points,
        days_since_last_order=days,
        top_products=top_products,
        recommended_promotion=recommended_promotion,
        churn_risk_pct=churn_risk_pct,
        churn_risk_label=churn_risk_label,
        segmento=segmento,
        next_action=next_action,
    )
