"""Customer endpoints."""
from datetime import datetime, timezone
from uuid import UUID
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select, func
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.core.time import now_chile
# HU_38 — RBAC granular con Casbin. Ver app/api/v1/products.py.
from app.core.security import requires_permission
from app.database import get_db
from app.deps import get_current_membership, get_tenant_for_membership
from app.models.branch import Branch
from app.models.customer import Customer
from app.models.order import Order, OrderItem, OrderStatus
from app.models.payment import Payment
from app.models.tenant import Tenant
from app.models.tenant import TenantMembership
from app.schemas.common import Page
from app.schemas.customer import (
    CustomerCreate,
    CustomerInsightsOut,
    CustomerOut,
    CustomerUpdate,
)
from app.schemas.order_list import CustomerOrderListItem, CustomerTimelineEvent
from app.services.plugin_hooks import trigger_hooks

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
        # HU_26 — campos RFM persistentes (None si nunca se corrió el cálculo).
        rfm_segment=c.rfm_segment,
        r_score=c.r_score,
        f_score=c.f_score,
        m_score=c.m_score,
        rfm_cell=c.rfm_cell,
        rfm_updated_at=c.rfm_updated_at,
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
@requires_permission("customer", "write")
def create_customer(
    payload: CustomerCreate,
    tenant: Tenant = Depends(get_tenant_for_membership),
    db: Session = Depends(get_db),
    # HU_38 — ver create_product en products.py.
    membership: TenantMembership = Depends(get_current_membership),
):
    """HU_38 — crear cliente requiere ``customer.write``."""
    c = Customer(**payload.model_dump(), tenant_id=str(tenant.id))
    db.add(c)
    db.commit()
    db.refresh(c)
    # HU_45 — Hook: notificar a plugins del tenant.
    trigger_hooks(
        db=db,
        tenant_id=tenant.id,
        event="on_customer_created",
        payload={
            "customer_id": str(c.id),
            "tenant_id": str(tenant.id),
            "full_name": c.full_name,
            "email": c.email,
        },
    )
    return to_out(c)


@router.get("/segments")
def customers_segments(
    tenant: Tenant = Depends(get_tenant_for_membership),
    db: Session = Depends(get_db),
):
    """HU_26 — Segmentación RFM persistente (vista agregada por buckets).

    Recorre todos los clientes del tenant y los agrupa en 5 categorías
    según el spec:
      - ``vip``        → lifetime_value >= $1M CLP
      - ``recurrente`` → 3+ pedidos
      - ``regular``    → 1-2 pedidos
      - ``nuevo``      → sin pedidos
      - ``inactivo``   → sin pedidos en los últimos 90 días

    Devuelve una lista ``[{name, count, criteria}, ...]`` con el conteo
    por bucket y el criterio legible. El cálculo es al vuelo (no requiere
    migraciones ni columna ``rfm_segment`` en la tabla ``customers``).
    """
    rows = db.execute(
        select(Customer).where(Customer.tenant_id == tenant.id)
    ).scalars().all()

    counts: dict[str, int] = {k: 0 for k in _SEG_ORDER}
    for c in rows:
        counts[_classify_for_segment_listing(c)] += 1

    return [
        {"name": name, "count": counts[name], "criteria": _SEG_CRITERIA[name]}
        for name in _SEG_ORDER
    ]


# ── HU_26 — RFM real (persistente en columnas ``customers.rfm_*``) ──
# Endpoints nuevos para el cálculo y exposición de la segmentación RFM
# basada en quintiles (ver ``app.tasks.rfm``). Las rutas viven bajo
# ``/rfm/`` para no colisionar con el endpoint legacy ``/segments`` de
# arriba (que devuelve los 5 buckets del spec V8 P0.3 — vip/recurrente/
# regular/nuevo/inactivo) ni con ``/{customer_id}``.
@router.post("/rfm/recalculate")
@requires_permission("customer", "write")
def recalculate_rfm(
    tenant: Tenant = Depends(get_tenant_for_membership),
    db: Session = Depends(get_db),
    lookback_days: int = Query(365, ge=30, le=730,
                               description="Ventana hacia atrás en días para R/F/M (default 365)."),
    # HU_38 — ver create_product en products.py. RBAC granular:
    # recalcular RFM requiere ``customer.write`` (no es de solo lectura).
    membership: TenantMembership = Depends(get_current_membership),
):
    """Recalcula los segmentos RFM de todos los clientes del tenant.

    Útil para refrescar la matriz tras un cambio grande (campaña masiva,
    fin de mes, etc.). El cálculo es SÍNCRONO para no depender de la
    cola Celery — puede tardar algunos segundos en tenants con miles
    de clientes.

    Devuelve el resumen con conteos por segmento y el total actualizado.
    """
    # Importación local para no introducir un ciclo de imports al cargar
    # este módulo (rfm importa modelos, que importan otros modelos).
    from app.tasks.rfm import compute_rfm_for_tenant_sync

    summary = compute_rfm_for_tenant_sync(
        db=db,
        tenant_id=tenant.id,
        lookback_days=lookback_days,
    )
    return {
        "tenant_id": str(tenant.id),
        "lookback_days": lookback_days,
        "segments": summary["segments"],
        "total_customers": summary["total_customers"],
        "updated": summary["updated"],
    }


@router.get("/rfm/segments")
def rfm_segments_distribution(
    tenant: Tenant = Depends(get_tenant_for_membership),
    db: Session = Depends(get_db),
):
    """Distribución de clientes por segmento RFM (persistente).

    Devuelve ``{segment_name: count, ...}``. Si nunca se corrió el
    cálculo RFM (``rfm_segment`` es NULL en todos los clientes), todos
    los conteos serán 0 — el frontend debe mostrar un CTA "Recalcular".
    """
    from sqlalchemy import func as _func

    rows = db.execute(
        select(Customer.rfm_segment, _func.count(Customer.id))
        .where(Customer.tenant_id == tenant.id)
        .group_by(Customer.rfm_segment)
    ).all()
    # Inicializar todos los segmentos canónicos en 0 para que el front
    # no tenga que hardcodear las claves.
    from app.tasks.rfm import RFM_SEGMENTS
    dist: dict[str, int] = {seg: 0 for seg in RFM_SEGMENTS}
    for seg, n in rows:
        key = seg or "unclassified"
        dist[key] = dist.get(key, 0) + int(n)
    return dist


@router.get("/rfm/matrix")
def rfm_matrix(
    tenant: Tenant = Depends(get_tenant_for_membership),
    db: Session = Depends(get_db),
):
    """Matriz RFM 5x5 con el conteo de clientes en cada celda.

    Devuelve ``{r: int, f: int, m: int: count, ...}`` para todas las
    celdas que tengan al menos un cliente. Las celdas vacías NO se
    incluyen (el frontend debe rellenar huecos con 0 al pintar el grid).
    """
    rows = db.execute(
        select(
            Customer.r_score,
            Customer.f_score,
            Customer.m_score,
            func.count(Customer.id),
        )
        .where(Customer.tenant_id == tenant.id)
        .where(Customer.r_score.isnot(None))
        .where(Customer.f_score.isnot(None))
        .where(Customer.m_score.isnot(None))
        .group_by(Customer.r_score, Customer.f_score, Customer.m_score)
    ).all()
    matrix: dict[str, int] = {}
    for r, f, m, n in rows:
        # Clave tipo "5-5-4" — más fácil de parsear desde el JS que una
        # tupla anidada {"r":5,"f":5,"m":4}.
        key = f"{int(r)}-{int(f)}-{int(m)}"
        matrix[key] = int(n)
    return matrix


@router.get("/rfm/top")
def rfm_top_customers(
    tenant: Tenant = Depends(get_tenant_for_membership),
    db: Session = Depends(get_db),
    segment: str = Query("champions",
                         description="Segmento RFM a listar (default 'champions')."),
    limit: int = Query(10, ge=1, le=50,
                       description="Cantidad máxima de clientes a retornar (default 10)."),
):
    """Lista los clientes top de un segmento RFM (default: ``champions``).

    Ordena por score total descendente (R+F+M). Útil para el dashboard
    RFM ("Top champions", "At risk", etc.).
    """
    rows = db.execute(
        select(Customer)
        .where(Customer.tenant_id == tenant.id)
        .where(Customer.rfm_segment == segment)
        .order_by(
            (Customer.r_score + Customer.f_score + Customer.m_score).desc(),
            Customer.total_spent_cents.desc(),
        )
        .limit(limit)
    ).scalars().all()
    return [to_out(c).model_dump(mode="json") for c in rows]


# ── HU_25 — Customer 360° ────────────────────────────────────
# Endpoints que viven bajo ``/{customer_id}/...`` DEBEN declararse ANTES del
# catch-all ``/{customer_id}`` (línea más abajo) para evitar que path params
# del estilo ``orders`` se intenten parsear como UUID.
# En la práctica FastAPI prioriza segmentos literales sobre path params, pero
# mantener el orden explícito es defensivo y deja claro el contrato.

@router.get("/{customer_id}/orders", response_model=Page[CustomerOrderListItem])
def customer_orders(
    customer_id: UUID,
    tenant: Tenant = Depends(get_tenant_for_membership),
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: Optional[str] = Query(
        None, alias="status",
        description="Filtrar por estado (ej. 'pagado', 'cancelado'). "
                    "Default = todos.",
    ),
):
    """HU_25 — Pedidos paginados de un cliente (perfil 360°).

    Devuelve la lista cronológica inversa de pedidos del cliente con un resumen
    condensado (primeros 3 productos, nombre de la sucursal). Pensado para la
    tabla del dashboard customer_360.html. La carga de items usa ``selectinload``
    para evitar N+1 en el JOIN.
    """
    # Verificar tenant isolation ANTES de calcular total — un cliente de otro
    # tenant debe ser indistinguible de uno que no existe.
    c = db.get(Customer, customer_id)
    if not c or c.tenant_id != tenant.id:
        raise NotFoundError("Customer")

    page, page_size = max(1, page), max(1, min(100, page_size))
    offset = (page - 1) * page_size

    base = select(Order).where(
        Order.customer_id == customer_id,
        Order.tenant_id == tenant.id,
    )
    if status_filter:
        base = base.where(Order.status == status_filter)
    base = base.order_by(Order.created_at.desc())

    total = db.execute(
        select(func.count()).select_from(base.subquery())
    ).scalar() or 0

    rows = list(
        db.execute(base.offset(offset).limit(page_size).execution_options(populate_existing=True)).scalars()
    )

    # Hidratar nombres de sucursal en bloque (1 query en vez de N).
    branch_ids = {o.branch_id for o in rows if o.branch_id}
    branch_name_by: dict[str, str] = {}
    if branch_ids:
        branch_rows = db.execute(
            select(Branch.id, Branch.name).where(Branch.id.in_(branch_ids))
        ).all()
        for bid, bname in branch_rows:
            branch_name_by[bid] = bname

    items: list[CustomerOrderListItem] = []
    for o in rows:
        # Snapshot de items: nombres de los primeros 3 productos + conteo total.
        item_names = [it.product_name for it in (o.items or [])][:3]
        items.append(
            CustomerOrderListItem(
                id=o.id,
                short_id=o.number,
                status=o.status.value if hasattr(o.status, "value") else str(o.status),
                total_cents=int(o.total_cents or 0),
                created_at=o.created_at,
                source=o.source.value if hasattr(o.source, "value") else str(o.source),
                branch_name=branch_name_by.get(o.branch_id),
                items_count=len(o.items or []),
                items_summary=item_names,
            )
        )

    return Page.build([i.model_dump(mode="json") for i in items], int(total), page, page_size)


@router.get("/{customer_id}/timeline", response_model=list[CustomerTimelineEvent])
def customer_timeline(
    customer_id: UUID,
    tenant: Tenant = Depends(get_tenant_for_membership),
    db: Session = Depends(get_db),
    limit: int = Query(50, ge=1, le=200),
):
    """HU_25 — Línea de tiempo cronológica del cliente.

    Combina eventos de 4 fuentes:
      - ``customer`` → alta del cliente (created_at)
      - ``order``    → pedidos del cliente
      - ``payment``  → pagos confirmados ligados a esos pedidos
      - ``rfm``      → última corrida de recálculo RFM del cliente

    Devuelve los ``limit`` eventos más recientes ordenados desc por fecha.
    """
    c = db.get(Customer, customer_id)
    if not c or c.tenant_id != tenant.id:
        raise NotFoundError("Customer")

    events: list[CustomerTimelineEvent] = []

    # 1. Evento de alta del cliente
    events.append(CustomerTimelineEvent(
        type="customer",
        date=c.created_at,
        title="Cliente registrado",
        detail=f"Alta en el sistema: {c.full_name}",
        amount_cents=None,
    ))

    # 2. Pedidos (limit +1 por si hay pagos)
    order_rows = list(
        db.execute(
            select(Order)
            .where(Order.customer_id == customer_id, Order.tenant_id == tenant.id)
            .order_by(Order.created_at.desc())
            .limit(limit)
        ).scalars()
    )
    order_ids = [o.id for o in order_rows]
    for o in order_rows:
        events.append(CustomerTimelineEvent(
            type="order",
            date=o.created_at,
            title=f"Pedido {o.number} · {o.status.value if hasattr(o.status, 'value') else str(o.status)}",
            detail=f"Total ${o.total_cents / 100:,.0f} CLP".replace(",", "."),
            amount_cents=int(o.total_cents or 0),
        ))

    # 3. Pagos ligados a esos pedidos (subset)
    if order_ids:
        pay_rows = list(
            db.execute(
                select(Payment)
                .where(
                    Payment.order_id.in_(order_ids),
                    Payment.tenant_id == tenant.id,
                )
                .order_by(Payment.paid_at.desc().nullslast(), Payment.created_at.desc())
                .limit(limit)
            ).scalars()
        )
        for p in pay_rows:
            date = p.paid_at or p.created_at
            method = p.method.value if hasattr(p.method, "value") else str(p.method)
            status_val = p.status.value if hasattr(p.status, "value") else str(p.status)
            events.append(CustomerTimelineEvent(
                type="payment",
                date=date,
                title=f"Pago {status_val} · {method}",
                detail=f"Monto ${p.amount_cents / 100:,.0f} CLP".replace(",", "."),
                amount_cents=int(p.amount_cents or 0),
            ))

    # 4. RFM (evento único, sólo si el cliente tiene rfm_updated_at)
    if c.rfm_updated_at:
        try:
            from datetime import datetime as _dt
            rfm_date = _dt.fromisoformat(str(c.rfm_updated_at).replace("Z", "+00:00"))
        except (ValueError, TypeError):
            rfm_date = c.created_at
        events.append(CustomerTimelineEvent(
            type="rfm",
            date=rfm_date,
            title="Recálculo RFM",
            detail=f"Celda {c.rfm_cell or '—'} → segmento {c.rfm_segment or '—'}",
            amount_cents=None,
        ))

    # Ordenar cronológicamente DESC y truncar a ``limit``.
    events.sort(key=lambda e: e.date, reverse=True)
    return events[:limit] if len(events) > limit else events


@router.get("/{customer_id}", response_model=CustomerOut)
def get_customer(customer_id: UUID, tenant: Tenant = Depends(get_tenant_for_membership), db: Session = Depends(get_db)):
    c = db.get(Customer, customer_id)
    if not c or c.tenant_id != tenant.id:
        raise NotFoundError("Customer")
    return to_out(c)


@router.patch("/{customer_id}", response_model=CustomerOut)
@requires_permission("customer", "write")
def update_customer(
    customer_id: UUID,
    payload: CustomerUpdate,
    tenant: Tenant = Depends(get_tenant_for_membership),
    db: Session = Depends(get_db),
    # HU_38 — ver create_product en products.py.
    membership: TenantMembership = Depends(get_current_membership),
):
    """HU_38 — actualizar cliente requiere ``customer.write``."""
    c = db.get(Customer, customer_id)
    if not c or c.tenant_id != tenant.id:
        raise NotFoundError("Customer")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(c, k, v)
    db.commit()
    db.refresh(c)
    return to_out(c)


@router.delete("/{customer_id}", status_code=204)
@requires_permission("customer", "delete")
def delete_customer(
    customer_id: UUID,
    tenant: Tenant = Depends(get_tenant_for_membership),
    db: Session = Depends(get_db),
    # HU_38 — ver create_product en products.py.
    membership: TenantMembership = Depends(get_current_membership),
):
    """HU_38 — eliminar cliente requiere ``customer.delete``.

    Roles permitidos (matriz default seed): OWNER, ADMIN.
    STAFF/VIEWER quedan fuera (sin policy de delete).
    """
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
    from datetime import timedelta
    from sqlalchemy import func as _func, select as _select
    from app.core.time import now_chile
    total = db.execute(
        _select(_func.count(Customer.id)).where(Customer.tenant_id == tenant.id)
    ).scalar_one() or 0

    # Activos: tienen al menos 1 pedido en los últimos `active_days` días.
    # Lo medimos contra la tabla de Orders, no contra `last_order_at` (que
    # puede no estar actualizado en tenants viejos). Si no hay orders
    # la subquery devuelve 0 — está bien, es un tenant sin ventas.
    threshold = now_chile() - timedelta(days=active_days)
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


# ── HU_26 — Segmentación RFM persistente ────────────────────
# Umbrales del spec para el endpoint de list-buckets (NO tocan
# compute_segmento, que usa thresholds distintos para /insights).
SEG_VIP_LIFETIME_CENTS = 100_000_000  # 1 millón CLP en centavos
SEG_RECURRENTE_MIN_ORDERS = 3
SEG_REGULAR_MAX_ORDERS = 2
SEG_INACTIVE_DAYS = 90

# Criterios legibles que se exponen al cliente del API.
# Se mantienen en español para alinear con el resto del dashboard.
_SEG_CRITERIA = {
    "vip":        f"lifetime_value >= $1M CLP (total_spent_cents >= {SEG_VIP_LIFETIME_CENTS})",
    "recurrente": f"orders >= {SEG_RECURRENTE_MIN_ORDERS}",
    "regular":    f"orders entre 1 y {SEG_REGULAR_MAX_ORDERS}",
    "nuevo":      "sin pedidos (total_orders == 0)",
    "inactivo":   f"sin pedidos en los últimos {SEG_INACTIVE_DAYS} días",
}

# Orden canónico de los buckets para la respuesta.
_SEG_ORDER = ["vip", "recurrente", "regular", "nuevo", "inactivo"]


def _classify_for_segment_listing(c: Customer) -> str:
    """Devuelve el bucket RFM-like del spec de HU_26.

    Es mutuamente excluyente y NO comparte lógica con ``compute_segmento``
    (que usa thresholds distintos para ``/insights`` y ``/stats``).
    Orden de evaluación:
      1. inactivo  — tiene órdenes pero la última es > SEG_INACTIVE_DAYS
      2. nuevo     — sin órdenes
      3. vip       — gastó >= 1M CLP lifetime
      4. recurrente— 3+ órdenes
      5. regular   — 1-2 órdenes
    """
    days = days_since(c.last_order_at)
    if c.total_orders > 0 and days is not None and days > SEG_INACTIVE_DAYS:
        return "inactivo"
    if c.total_orders == 0:
        return "nuevo"
    if c.total_spent_cents >= SEG_VIP_LIFETIME_CENTS:
        return "vip"
    if c.total_orders >= SEG_RECURRENTE_MIN_ORDERS:
        return "recurrente"
    if c.total_orders >= 1:
        return "regular"
    return "nuevo"


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
                Order.status != OrderStatus.CANCELADO,
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
        # HU_25 — perfil 360°: incluir objeto customer + last_order_at crudo
        # para que el front pueda mostrar nombre, email, fecha sin hacer
        # un segundo GET a /customers/{id}.
        customer=to_out(c),
        last_order_at=c.last_order_at,
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
