"""RFM (Recency, Frequency, Monetary) analysis tasks (Celery + sync).

HU_26 — Real RFM segmentation: calcular segmentos por quintiles 1-5 para
Recency, Frequency y Monetary, y PERSISTIR los resultados en las columnas
RFM de ``Customer`` (ver migración ``2026_10_07_0001``).

Hay dos formas de invocar el cálculo:

1. **Asíncrono (Celery)** — para correrlo en background, típicamente desde
   un cron nocturno o tras acumular muchas órdenes::

       from app.tasks.rfm import run_rfm_analysis
       run_rfm_analysis.delay(tenant_id=tenant_id, branch_id=None,
                               lookback_days=90)

2. **Síncrono** — desde un endpoint API (``POST .../customers/rfm/recalculate``)
   para refrescar al vuelo sin esperar la cola Celery::

       from app.tasks.rfm import compute_rfm_for_tenant_sync
       with SessionLocal() as db:
           result = compute_rfm_for_tenant_sync(db, tenant_id=tenant_id,
                                                lookback_days=365)

Ambas rutas comparten ``_compute_and_persist_rfm`` para que la lógica de
cálculo y persistencia esté en un solo lugar.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from celery import Task
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.celery_app import celery_app
from app.core.time import now_chile
from app.database import SessionLocal

logger = logging.getLogger("wowhub.tasks.rfm")


# ── Segmentos RFM soportados ─────────────────────────────────────────
# Orden canónico para exponerlos en el dashboard y para inicializar
# contadores sin perder ninguno. Mantener alineado con la taxonomía que
# documenta ``_rfm_to_segment``.
RFM_SEGMENTS = (
    "champions",
    "loyal",
    "potential",
    "new",
    "about_to_sleep",
    "at_risk",
    "hibernating",
    "lost",
)


def _empty_segment_counts() -> dict:
    """Contadores inicializados en 0 para todos los segmentos conocidos."""
    return {seg: 0 for seg in RFM_SEGMENTS}


# ── Mapeo quintil RFM → nombre de segmento ──────────────────────────
def _rfm_to_segment(r: int, f: int, m: int) -> str:
    """Map R, F, M quintiles (1-5, 5=best) to a segment name.

    Taxonomía estándar RFM (referencia: en.wikipedia.org/wiki/RFM_(market_research)),
    extendida con ``about_to_sleep`` y ``hibernating`` que el spec de
    WowHub V134.2 pide explícitamente.

    Reglas (en orden de precedencia):

    1. ``champions``       — R≥4 AND F≥4 AND M≥4. Los mejores.
    2. ``loyal``           — F≥4 AND M≥4 (independiente del R).
    3. ``new``             — R≥4 AND F≤2. Muy recientes, baja frecuencia.
    4. ``potential``       — R≥3 AND F=2-3 AND M≤3. Casi recurrentes.
    5. ``about_to_sleep``  — R=2-3 AND F≤2. Están por dormirse.
    6. ``at_risk``         — R≤2 AND F≥3. Solían comprar, ahora ausentes.
    7. ``hibernating``     — R≤2 AND F≤2 AND M≤2. Muy dormidos, casi perdidos.
    8. ``lost``            — Catch-all para clientes con scores bajos.
    """
    if r >= 4 and f >= 4 and m >= 4:
        return "champions"
    if f >= 4 and m >= 4:
        return "loyal"
    if r >= 4 and f <= 2:
        return "new"
    if r >= 3 and 2 <= f <= 3 and m <= 3:
        return "potential"
    if 2 <= r <= 3 and f <= 2:
        return "about_to_sleep"
    if r <= 2 and f >= 3:
        return "at_risk"
    if r <= 2 and f <= 2 and m <= 2:
        return "hibernating"
    return "lost"


def _classify_inactive(last_order_at_iso: Optional[str], now: datetime) -> str:
    """Clasifica a un cliente que NO tiene órdenes en la ventana RFM,
    basándose en su última compra histórica (``last_order_at``).

    Si nunca compró → ``new``. Si su última compra fue hace más de 365
    días → ``hibernating``. En cualquier otro caso → ``lost``.
    """
    if not last_order_at_iso:
        return "new"
    try:
        last = datetime.fromisoformat(last_order_at_iso.replace("Z", "+00:00"))
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        days_since = (now - last).days
    except (ValueError, TypeError, AttributeError):
        return "lost"
    if days_since > 365:
        return "hibernating"
    return "lost"


def _pctile(sorted_values: list, p: int):
    """Devuelve el percentil ``p`` (0-100) de una lista ya ordenada."""
    if not sorted_values:
        return 0
    idx = int(len(sorted_values) * p / 100)
    return sorted_values[min(idx, len(sorted_values) - 1)]


def _score(value, thresholds):
    """Convierte un valor crudo en un quintil 1-5 según los thresholds dados.

    Si ``value <= thresholds[0]`` → 1. Si ``value <= thresholds[1]`` → 2.
    Etc. Si supera todos los thresholds → 5.

    Nota: para recency ``thresholds`` son días desde la última compra,
    por lo que MENOR valor = MEJOR quintil (más reciente). Para frequency
    y monetary es al revés: MAYOR valor = MEJOR quintil.
    """
    for i, t in enumerate(thresholds):
        if value <= t:
            return i + 1
    return 5


# ── Núcleo compartido: calcular + persistir ────────────────────────
def _compute_and_persist_rfm(
    db: Session,
    tenant_id: int,
    branch_id: Optional[str] = None,
    lookback_days: int = 365,
) -> dict:
    """Calcula RFM por quintiles para todos los clientes del ``tenant_id``
    y PERSISTE los resultados en las columnas RFM de ``Customer``.

    También actualiza ``total_orders``, ``total_spent_cents`` y
    ``last_order_at`` desde la agregación real de ``orders`` (no desde
    contadores potencialmente desactualizados).

    Args:
        db: sesión SQLAlchemy abierta.
        tenant_id: ID del tenant a recalcular.
        branch_id: si se pasa, filtra también por sucursal (no se persiste
            en Customer porque ``branch_id`` no es una dimensión del
            modelo; solo afecta qué órdenes entran al cálculo).
        lookback_days: ventana hacia atrás para R/F/M (default 365).
            Para el cálculo de recency SOLO se usan órdenes dentro de
            esta ventana. Para las métricas totales (total_orders, etc.)
            se usa TODO el historial sin filtrar.

    Returns:
        ``{"tenant_id": ..., "segments": {seg_name: count, ...},
          "total_customers": N, "updated": N}``
    """
    # Importación local para evitar ciclos al cargar celery_app.
    from app.models.customer import Customer
    from app.models.order import Order, OrderStatus

    now = now_chile()
    cutoff = now - timedelta(days=lookback_days)

    # ── 1. Métricas totales (sin filtro de lookback) ─────────────
    # Para cada cliente del tenant, contar todas sus órdenes NO canceladas,
    # sumar el gasto y obtener la fecha del último pedido. Esto se usa
    # para mantener sincronizadas las columnas ``total_orders``,
    # ``total_spent_cents`` y ``last_order_at`` con la realidad de la
    # tabla ``orders`` (un cliente puede haber sido editado o migrado
    # y los contadores pueden haber quedado desfasados).
    metrics_q = (
        select(
            Order.customer_id,
            func.count(Order.id).label("n_orders"),
            func.coalesce(func.sum(Order.total_cents), 0).label("total_cents"),
            func.max(Order.created_at).label("last_order"),
        )
        .where(Order.tenant_id == tenant_id)
        .where(Order.status != OrderStatus.CANCELADO)
        .where(Order.customer_id.isnot(None))
    )
    if branch_id:
        metrics_q = metrics_q.where(Order.branch_id == branch_id)
    metrics_q = metrics_q.group_by(Order.customer_id)
    metrics_rows = db.execute(metrics_q).all()

    metrics_by_cust: dict[str, dict] = {}
    for r in metrics_rows:
        cust_id = str(r.customer_id)
        metrics_by_cust[cust_id] = {
            "total_orders": int(r.n_orders or 0),
            "total_spent_cents": int(r.total_cents or 0),
            "last_order_at": r.last_order.isoformat() if r.last_order else None,
        }

    # ── 2. RFM por quintiles (con filtro de lookback) ────────────
    rfm_q = (
        select(
            Order.customer_id,
            func.max(Order.created_at).label("recency"),
            func.count(Order.id).label("frequency"),
            func.sum(Order.total_cents).label("monetary"),
        )
        .where(Order.tenant_id == tenant_id)
        .where(Order.created_at >= cutoff)
        .where(Order.status != OrderStatus.CANCELADO)
        .where(Order.customer_id.isnot(None))
    )
    if branch_id:
        rfm_q = rfm_q.where(Order.branch_id == branch_id)
    rfm_q = rfm_q.group_by(Order.customer_id)
    rfm_rows = db.execute(rfm_q).all()

    rfm_scores_by_cust: dict[str, dict] = {}
    if rfm_rows:
        # Umbrales de quintil (percentiles 20/40/60/80) por dimensión.
        recencies = sorted([(now - r.recency).days for r in rfm_rows])
        frequencies = sorted([int(r.frequency or 0) for r in rfm_rows])
        monetaries = sorted([float(r.monetary or 0) for r in rfm_rows])

        r_thresh = [
            _pctile(recencies, 20),
            _pctile(recencies, 40),
            _pctile(recencies, 60),
            _pctile(recencies, 80),
        ]
        f_thresh = [
            _pctile(frequencies, 20),
            _pctile(frequencies, 40),
            _pctile(frequencies, 60),
            _pctile(frequencies, 80),
        ]
        m_thresh = [
            _pctile(monetaries, 20),
            _pctile(monetaries, 40),
            _pctile(monetaries, 60),
            _pctile(monetaries, 80),
        ]

        now_iso = now.isoformat()
        for row in rfm_rows:
            recency_days = (now - row.recency).days
            r = _score(recency_days, r_thresh)
            f = _score(int(row.frequency or 0), f_thresh)
            m = _score(float(row.monetary or 0), m_thresh)
            seg = _rfm_to_segment(r, f, m)
            rfm_scores_by_cust[str(row.customer_id)] = {
                "rfm_segment": seg,
                "r_score": r,
                "f_score": f,
                "m_score": m,
                "rfm_cell": f"{r}{f}{m}",
                "rfm_updated_at": now_iso,
            }

    # ── 3. Cargar todos los clientes del tenant y persistir ──────
    customers = db.execute(
        select(Customer).where(Customer.tenant_id == tenant_id)
    ).scalars().all()

    now_iso = now.isoformat()
    updated = 0
    for c in customers:
        cust_id = str(c.id)
        metrics = metrics_by_cust.get(cust_id)
        if metrics:
            c.total_orders = metrics["total_orders"]
            c.total_spent_cents = metrics["total_spent_cents"]
            c.last_order_at = metrics["last_order_at"]
        else:
            # Cliente sin órdenes en su historial: resetear.
            c.total_orders = 0
            c.total_spent_cents = 0
            c.last_order_at = None

        rfm = rfm_scores_by_cust.get(cust_id)
        if rfm:
            c.rfm_segment = rfm["rfm_segment"]
            c.r_score = rfm["r_score"]
            c.f_score = rfm["f_score"]
            c.m_score = rfm["m_score"]
            c.rfm_cell = rfm["rfm_cell"]
            c.rfm_updated_at = rfm["rfm_updated_at"]
        else:
            # Sin órdenes en la ventana de RFM: clasificar por recencia histórica.
            c.rfm_segment = _classify_inactive(c.last_order_at, now)
            c.r_score = None
            c.f_score = None
            c.m_score = None
            c.rfm_cell = None
            c.rfm_updated_at = now_iso
        updated += 1

    db.commit()

    # ── 4. Resumen por segmento ──────────────────────────────────
    segment_counts = _empty_segment_counts()
    for c in customers:
        seg = c.rfm_segment or "unknown"
        # Por si el histórico tenía un valor fuera del set canónico.
        if seg not in segment_counts:
            segment_counts[seg] = 0
        segment_counts[seg] += 1

    logger.info(
        "RFM persistido — tenant=%d customers=%d segments=%s",
        tenant_id, len(customers), segment_counts,
    )

    return {
        "tenant_id": tenant_id,
        "branch_id": branch_id,
        "lookback_days": lookback_days,
        "segments": segment_counts,
        "total_customers": len(customers),
        "updated": updated,
    }


# ── API síncrona para /customers/rfm/recalculate ───────────────────
def compute_rfm_for_tenant_sync(
    db: Session,
    tenant_id: int,
    lookback_days: int = 365,
) -> dict:
    """Calcula y persiste RFM para un tenant SIN pasar por Celery.

    Pensada para ser llamada desde el endpoint
    ``POST /tenants/{tid}/customers/rfm/recalculate`` cuando el usuario
    pide una actualización inmediata desde el dashboard.

    Args:
        db: sesión SQLAlchemy abierta (la caller la cierra con ``close()``
            o un context manager).
        tenant_id: ID del tenant a recalcular.
        lookback_days: ventana hacia atrás para R/F/M (default 365, más
            generoso que el default de Celery=90 porque la ejecución es
            bajo demanda del usuario).

    Returns:
        ``{"tenant_id": ..., "segments": {seg: count, ...},
          "total_customers": N, "updated": N}``
    """
    return _compute_and_persist_rfm(
        db=db,
        tenant_id=tenant_id,
        branch_id=None,
        lookback_days=lookback_days,
    )


# ── Tarea Celery ────────────────────────────────────────────────────
@celery_app.task(bind=True, name="rfm.run_analysis", max_retries=1)
def run_rfm_analysis(
    self: Task,
    tenant_id: int,
    branch_id: Optional[str] = None,
    lookback_days: int = 90,
) -> dict:
    """Calcula y persiste los segmentos RFM para todos los clientes de un
    tenant (tarea Celery).

    Args:
        tenant_id: ID del tenant.
        branch_id: Filtrar por sucursal (None = todas). NOTA: cuando se
            filtra por sucursal, las métricas RFM se calculan solo con
            las órdenes de esa sucursal; pero las métricas totales de
            ``Customer`` (``total_orders``, ``total_spent_cents``,
            ``last_order_at``) NO se actualizan en ese caso porque
            pertenecen al tenant completo (no por sucursal). Para evitar
            inconsistencias, recomendamos siempre pasar ``branch_id=None``
            salvo que se sepa lo que se está haciendo.
        lookback_days: Días hacia atrás para el análisis (default 90).

    Returns:
        ``{"tenant_id": ..., "segments": {seg: count, ...},
          "total_customers": N, "updated": N, "scores": [...]}``
    """
    logger.info(
        "run_rfm_analysis — tenant=%d, branch=%s, lookback=%d",
        tenant_id, branch_id, lookback_days,
    )
    try:
        with SessionLocal() as db:
            summary = _compute_and_persist_rfm(
                db=db,
                tenant_id=tenant_id,
                branch_id=branch_id,
                lookback_days=lookback_days,
            )

            # Mantener compatibilidad: la firma previa de este task
            # retornaba también una lista ``scores`` con detalle por
            # cliente. La conservamos para no romper consumidores.
            from app.models.order import Order, OrderStatus
            now = now_chile()
            cutoff = now - timedelta(days=lookback_days)
            detail_q = (
                select(
                    Order.customer_id,
                    func.max(Order.created_at).label("recency"),
                    func.count(Order.id).label("frequency"),
                    func.sum(Order.total_cents).label("monetary"),
                )
                .where(Order.tenant_id == tenant_id)
                .where(Order.created_at >= cutoff)
                .where(Order.status != OrderStatus.CANCELADO)
                .where(Order.customer_id.isnot(None))
            )
            if branch_id:
                detail_q = detail_q.where(Order.branch_id == branch_id)
            detail_q = detail_q.group_by(Order.customer_id)
            detail_rows = db.execute(detail_q).all()

            scores = []
            for row in detail_rows:
                recency_days = (now - row.recency).days
                scores.append({
                    "customer_id": str(row.customer_id),
                    "recency_days": recency_days,
                    "frequency": int(row.frequency or 0),
                    "monetary_cents": int(row.monetary or 0),
                })

            return {**summary, "scores": scores}

    except Exception as exc:
        logger.error("run_rfm_analysis failed — tenant=%d, error=%s", tenant_id, exc)
        raise self.retry(exc=exc, countdown=300)