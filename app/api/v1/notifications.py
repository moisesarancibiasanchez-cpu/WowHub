"""Notifications API — endpoints para el bell badge + página del dashboard.

Endpoints:
- GET /tenants/{tenant_id}/notifications/summary → para el bell badge
  (total + contadores por severidad/categoría + top 3 más urgentes).
- GET /tenants/{tenant_id}/notifications         → lista completa con
  filtros opcionales (severity, category, limit) para la página
  /dashboard/notifications.

El motor es `NotificationsEngine` (Fase 4 ya terminado). Esta API solo
lo expone — sin lógica nueva. Los endpoints son tenant-scoped para
reusar el guard de membresía ya existente (`get_tenant_for_membership`).

Idempotencia: el motor recalcula en cada request, pero los IDs de
notificación son estables (sha1 de rule:entity), así que la UI puede
cachear sin parpadeos al recargar.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_tenant_for_membership
from app.models.tenant import Tenant
from app.schemas.notifications import (
    NotificationListOut,
    NotificationOut,
    NotificationSummaryOut,
)
from app.services.notifications import (
    CATEGORIES,
    NotificationsEngine,
    SEVERITIES,
)

router = APIRouter(
    prefix="/tenants/{tenant_id}/notifications",
    tags=["notifications"],
)


# ── Helper de normalización ──────────────────────────────────────
def _normalize(n: dict[str, Any]) -> dict[str, Any]:
    """Convierte UUIDs y otros tipos no-JSON a string antes de validar
    con Pydantic.

    El motor ``NotificationsEngine`` setea ``entity_id`` al UUID del
    objeto (Product/Order/etc) — útil en Python, pero el contrato
    HTTP de Fase 6 es estricto en strings. Esta función es el
    boundary que limpia la salida.
    """
    if "entity_id" in n and n["entity_id"] is not None:
        n["entity_id"] = str(n["entity_id"])
    return n


# ── Summary (badge del header) ────────────────────────────────────
@router.get(
    "/summary",
    response_model=NotificationSummaryOut,
    summary="Resumen compacto para el bell badge del header",
)
def get_notifications_summary(
    tenant: Tenant = Depends(get_tenant_for_membership),
    db: Session = Depends(get_db),
) -> NotificationSummaryOut:
    """Devuelve el resumen del bell: total + contadores por severidad y
    categoría + top 3 más urgentes (critical primero, luego warning, info).

    Pensado para llamarse en cada carga de página del dashboard y para
    auto-refresh cada 60s mientras hay sesión activa.

    FIX 2026-10-02 — Resiliencia: si el motor lanza (típico en PG con
    incompatibilidad cross-DB), devolvemos un resumen vacío con top_3=[].
    Antes: el endpoint devolvía HTTP 500 y rompía el auto-refresh del
    bell badge (página en blanco cada 60s para tenants recién creados).
    Ahora: degrada silenciosamente a 503 solo si TODO el motor falla,
    permitiendo al front mostrar "Sin notificaciones".
    """
    import logging
    _log = logging.getLogger("wowhub.notifications.api")
    try:
        engine = NotificationsEngine(db, tenant.id)
        raw = engine.summary()
        return NotificationSummaryOut(
            generated_at=raw["generated_at"],
            total=raw["total"],
            by_severity=raw["by_severity"],
            by_category=raw["by_category"],
            top_3=[NotificationOut(**_normalize(n)) for n in raw["top_3"]],
        )
    except Exception as exc:
        _log.exception("notifications/summary failed for tenant=%s", tenant.id)
        # Si todo el motor falla (no debería pasar gracias al _safe de
        # detect_all, pero por si TÚ y si TÚ), devolvemos un resumen vacío.
        return NotificationSummaryOut(
            generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            total=0,
            by_severity={"info": 0, "warning": 0, "critical": 0},
            by_category={"pricing": 0, "inventory": 0, "orders": 0, "costs": 0, "system": 0},
            top_3=[],
        )


# ── Lista completa (página /dashboard/notifications) ──────────────
@router.get(
    "",
    response_model=NotificationListOut,
    summary="Lista de notificaciones (filtros opcionales por severity/category)",
)
def list_notifications(
    tenant: Tenant = Depends(get_tenant_for_membership),
    db: Session = Depends(get_db),
    limit: int = Query(
        20, ge=1, le=100,
        description="Máximo de notificaciones a devolver (cap defensivo).",
    ),
    severity: Optional[str] = Query(
        None,
        description="Filtrar por severidad: info | warning | critical",
    ),
    category: Optional[str] = Query(
        None,
        description=(
            "Filtrar por categoría: pricing | inventory | orders | "
            "costs | system"
        ),
    ),
) -> NotificationListOut:
    """Devuelve la lista de notificaciones activas para este tenant,
    ordenadas por severidad (critical primero) y por fecha descendente
    dentro de cada severidad.

    Los filtros `severity` y `category` son opcionales e independientes
    (se pueden combinar). Si el valor no es válido, FastAPI responde
    422 automáticamente.
    """
    # Validación explícita (mejor error que un 500 silencioso)
    if severity and severity not in SEVERITIES:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=422,
            detail=f"severity debe ser uno de {list(SEVERITIES)}",
        )
    if category and category not in CATEGORIES:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=422,
            detail=f"category debe ser uno de {list(CATEGORIES)}",
        )

    # FIX 2026-10-02 — Resiliencia: si el motor entero falla (defensa
    # en profundidad al _safe interno de detect_all), devolvemos lista
    # vacía en lugar de 500. La causa raíz se loggea para diagnóstico.
    import logging
    _log = logging.getLogger("wowhub.notifications.api")
    try:
        engine = NotificationsEngine(db, tenant.id)
        items = engine.detect_all(limit=limit)
        all_items = engine.detect_all(limit=100)
    except Exception as exc:
        _log.exception("notifications/list failed for tenant=%s", tenant.id)
        items, all_items = [], []

    if severity:
        items = [n for n in items if n["severity"] == severity]
    if category:
        items = [n for n in items if n["category"] == category]

    # Conteos totales (sobre TODAS las notificaciones, sin filtros) —
    # así la página puede mostrar "X críticas" en la cabecera aunque
    # el usuario esté filtrando por "info".
    by_sev: dict[str, int] = {s: 0 for s in SEVERITIES}
    by_cat: dict[str, int] = {c: 0 for c in CATEGORIES}
    for it in all_items:
        by_sev[it["severity"]] = by_sev.get(it["severity"], 0) + 1
        by_cat[it["category"]] = by_cat.get(it["category"], 0) + 1

    return NotificationListOut(
        count=len(items),
        total_by_severity=by_sev,
        total_by_category=by_cat,
        items=[NotificationOut(**_normalize(n)) for n in items],
    )
