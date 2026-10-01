"""HU_49 — Status page API público.

Endpoints (todos sin auth, accesibles públicamente):
- GET /api/v1/status        → JSON con estado + uptime + history
- GET /api/v1/status/uptime → JSON con sólo los % de uptime

El HTML status page se sirve desde ``/status`` (main.py).
"""
from __future__ import annotations

from fastapi import APIRouter, Query

from app.services.uptime_monitor import get_uptime_monitor

router = APIRouter(prefix="/status", tags=["status"])


@router.get("/summary", summary="Status actual + uptime + historial (HU_49)")
def get_status_summary(
    history_days: int = Query(30, ge=1, le=90, description="Días de historial (1-90)."),
):
    """Devuelve estado operacional, uptime por ventana y historial diario.

    Sin auth: este endpoint es **público** — clientes, integradores y
   监控系统 externos pueden consultarlo sin credenciales.

    NOTA: ruta ``/status/summary`` (no ``/status``) para evitar shadowing
    con otros routers que tengan prefijo ``/tenants/{tenant_id}`` y
    capturen ``/status`` como ``tenant_id``.
    """
    monitor = get_uptime_monitor()
    return monitor.as_dict(days=history_days)


# Backward-compat: ``/api/v1/status`` se mantiene como alias de ``/status/summary``.
@router.get("", include_in_schema=False)
def get_status_root():
    """Alias de ``/status/summary`` para retro-compatibilidad."""
    return get_status_summary()


@router.get("/uptime", summary="Solo % de uptime (HU_49)")
def get_uptime(
    days: int = Query(30, ge=1, le=90, description="Ventana en días (1-90)."),
):
    """Devuelve el % de uptime operacional de los últimos ``days`` días."""
    monitor = get_uptime_monitor()
    return {
        "window_days": days,
        "uptime_pct": monitor.uptime_pct(days),
        "current_status": monitor.current_status()["status"],
    }