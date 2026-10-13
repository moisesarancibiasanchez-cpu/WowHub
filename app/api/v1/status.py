"""HU_49 — Status page API público.

Endpoints (todos sin auth, accesibles públicamente):
- GET /api/v1/system/status         → JSON con estado + uptime + history
- GET /api/v1/system/status/uptime  → JSON con sólo los % de uptime
- GET /api/v1/system/status/summary → alias de /api/v1/system/status

El HTML status page se sirve desde ``/status`` (main.py).

NOTA: Los endpoints se montan bajo ``/system/...`` (no ``/status``) porque
la ruta ``/api/v1/status`` (sin prefix adicional) entraba en conflicto
con otros routers que tienen prefijo ``/tenants/{tenant_id}/...`` y
capturaban ``/status`` como ``tenant_id`` (devolvía 401).
"""
from __future__ import annotations

from fastapi import APIRouter, Query

from app.services.uptime_monitor import get_uptime_monitor

# Prefijo ``/system/...`` para evitar shadowing con ``/tenants/{tenant_id}``.
router = APIRouter(prefix="/system/status", tags=["system-status"])


@router.get("", summary="Status actual + uptime + historial (HU_49)")
def get_status_root(
    history_days: int = Query(30, ge=1, le=90, description="Días de historial (1-90)."),
):
    """Devuelve estado operacional, uptime por ventana y historial diario.

    Sin auth: este endpoint es **público** — clientes, integradores y
   监控系统 externos pueden consultarlo sin credenciales.
    """
    monitor = get_uptime_monitor()
    return monitor.as_dict(days=history_days)


@router.get("/summary", summary="Alias de GET / (HU_49)")
def get_status_summary(
    history_days: int = Query(30, ge=1, le=90, description="Días de historial (1-90)."),
):
    """Alias de la ruta raíz para retro-compatibilidad con documentación previa."""
    return get_status_root(history_days=history_days)


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