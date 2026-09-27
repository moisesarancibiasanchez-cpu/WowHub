"""RFM (Recency, Frequency, Monetary) analysis tasks (Celery).

HU_36 — Cola rfm: recalcular segmentos RFM de clientes
para el Growth Coach y el dashboard de Loyalty.

Ejecutar análisis RFM:
    from app.tasks.rfm import run_rfm_analysis
    run_rfm_analysis.delay(tenant_id=tenant_id, branch_id=None)
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from celery import Task
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.celery_app import celery_app
from app.database import SessionLocal

logger = logging.getLogger("wowhub.tasks.rfm")


@celery_app.task(bind=True, name="rfm.run_analysis", max_retries=1)
def run_rfm_analysis(
    self: Task,
    tenant_id: int,
    branch_id: Optional[str] = None,
    lookback_days: int = 90,
) -> dict:
    """Calculate RFM segments for all customers of a tenant.

    Args:
        tenant_id: ID del tenant.
        branch_id: Filtrar por sucursal (None = todas).
        lookback_days: Días hacia atrás para el análisis (default 90).

    Returns:
        {"tenant_id": ..., "segments": {"champions": N, "loyal": N, ...},
         "scores": [{"customer_id": ..., "r": 1-5, "f": 1-5, "m": 1-5, "rfm": "515"}, ...}}.
    """
    logger.info(
        "run_rfm_analysis — tenant=%d, branch=%s, lookback=%d",
        tenant_id, branch_id, lookback_days,
    )
    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)

    try:
        with SessionLocal() as db:
            from app.models.order import Order, OrderStatus
            from app.models.customer import Customer

            # Build base query for orders in the lookback window
            q = (
                select(
                    Order.customer_id,
                    func.max(Order.created_at).label("recency"),
                    func.count(Order.id).label("frequency"),
                    func.sum(Order.total_cents).label("monetary"),
                )
                .where(Order.tenant_id == tenant_id)
                .where(Order.created_at >= cutoff)
                .where(Order.status.notin_([OrderStatus.CANCELADO]))
            )
            if branch_id:
                q = q.where(Order.branch_id == branch_id)
            q = q.group_by(Order.customer_id)

            rows = db.execute(q).all()

            # Calculate RFM scores (1-5 each, 5=best)
            scores = []
            now = datetime.now(timezone.utc)
            total_customers = len(rows)

            if total_customers == 0:
                segments = {"champions": 0, "loyal": 0, "potential": 0, "new": 0, "at_risk": 0, "lost": 0}
                return {"tenant_id": tenant_id, "segments": segments, "scores": [], "total": 0}

            # Compute percentile thresholds
            recencies = sorted([(now - r.recency).days for r in rows])
            frequencies = sorted([r.frequency for r in rows])
            monetaries = sorted([float(r.monetary or 0) for r in rows])

            def pctile(values, p):
                idx = int(len(values) * p / 100)
                return values[min(idx, len(values) - 1)]

            r_thresh = [pctile(recencies, 20), pctile(recencies, 40), pctile(recencies, 60), pctile(recencies, 80)]
            f_thresh = [pctile(frequencies, 20), pctile(frequencies, 40), pctile(frequencies, 60), pctile(frequencies, 80)]
            m_thresh = [pctile(monetaries, 20), pctile(monetaries, 40), pctile(monetaries, 60), pctile(monetaries, 80)]

            def score(val, thresh):
                for i, t in enumerate(thresh):
                    if val <= t:
                        return i + 1
                return 5

            segment_counts = {"champions": 0, "loyal": 0, "potential": 0, "new": 0, "at_risk": 0, "lost": 0}

            for row in rows:
                recency_days = (now - row.recency).days
                r = score(recency_days, r_thresh)
                f = score(row.frequency, f_thresh)
                m = score(float(row.monetary or 0), m_thresh)
                rfm_str = f"{r}{f}{m}"
                seg = _rfm_to_segment(r, f, m)
                segment_counts[seg] = segment_counts.get(seg, 0) + 1

                scores.append({
                    "customer_id": str(row.customer_id),
                    "recency_days": recency_days,
                    "frequency": row.frequency,
                    "monetary_cents": row.monetary or 0,
                    "r": r, "f": f, "m": m,
                    "rfm": rfm_str,
                    "segment": seg,
                })

            # TODO: guardar segmentos en Customer.rfm_segment
            # (requires adding rfm_segment column to Customer model first)

            logger.info(
                "run_rfm_analysis done — tenant=%d, customers=%d, segments=%s",
                tenant_id, total_customers, segment_counts,
            )
            return {
                "tenant_id": tenant_id,
                "branch_id": branch_id,
                "lookback_days": lookback_days,
                "segments": segment_counts,
                "scores": scores,
                "total": total_customers,
            }

    except Exception as exc:
        logger.error("run_rfm_analysis failed — tenant=%d, error=%s", tenant_id, exc)
        raise self.retry(exc=exc, countdown=300)


def _rfm_to_segment(r: int, f: int, m: int) -> str:
    """Map R, F, M scores to RFM segment name."""
    high = 4
    if r >= high and f >= high and m >= high:
        return "champions"
    if f >= high and m >= high:
        return "loyal"
    if r >= high and f < high:
        return "new"
    if 2 <= r < high and 2 <= f < high:
        return "potential"
    if r < 2 and f >= 3:
        return "at_risk"
    return "lost"
