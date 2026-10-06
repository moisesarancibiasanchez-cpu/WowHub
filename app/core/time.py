"""Timezone helpers — Chile (America/Santiago).

WowHub opera exclusivamente en territorio chileno. Toda la lógica de negocio
que dependa de "hoy", "esta semana", "este mes" o fechas civiles (SII,
contadores diarios, expiraciones, RFM) debe usar estas helpers en lugar de
``datetime.now(timezone.utc)`` o ``datetime.utcnow()``.

Convención:
- ``now_chile()``           → datetime *aware* en America/Santiago.
- ``today_start_chile()``    → 00:00 America/Santiago del día actual, aware.

Uso típico:
    from app.core.time import now_chile, today_start_chile
    start = today_start.chile()            # límite "desde" del día
    end   = start + timedelta(days=1)
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

CL_TZ = ZoneInfo("America/Santiago")


def now_chile() -> datetime:
    """Devuelve el ``datetime`` aware actual en America/Santiago.

    Garantiza ``tzinfo == CL_TZ`` (no naive, no UTC). Es el reemplazo
    directo de ``datetime.now(timezone.utc)`` para toda lógica de negocio
    chilena.
    """
    return datetime.now(CL_TZ)


def today_start_chile() -> datetime:
    """00:00:00 America/Santiago del día actual, tz-aware.

    Útil como límite inferior en queries de "lo de hoy". Ejemplo:
        start = today_start_chile()
        q = select(...).where(Order.created_at >= start)
    """
    return now_chile().replace(hour=0, minute=0, second=0, microsecond=0)