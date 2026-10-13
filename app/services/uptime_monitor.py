"""HU_49 — Monitor de uptime para el status page público.

Mantiene un historial en memoria (deque + dict) con los resultados de los
últimos ``_HISTORY_DAYS`` días. Cada ``_POLL_INTERVAL`` segundos registra
un check interno (DB ping + self HTTP probe) y guarda el estado.

API:
- ``record(status)``   : registra un check (operational/degraded/outage).
- ``current_status()`` : estado actual (operational/degraded/outage).
- ``uptime_pct(days)`` : % uptime últimos N días (1-90).
- ``history(days)``    : lista diaria con ``date`` + ``status`` + ``uptime_pct``.
- ``as_dict()``        : serialización completa para el endpoint JSON.

Concurrencia:
- El check automático corre en un thread daemon iniciado en ``start()``.
- El ``_lock`` protege todas las lecturas/escrituras al historial.

NOTA: el monitor es **best-effort** — NO es un sistema distribuido de
uptime (eso requeriría probes externos como Pingdom/UptimeRobot). Sirve
como señal interna para que el status page tenga datos sin depender de
un servicio de pago.
"""
from __future__ import annotations

import logging
import threading
import time
from collections import deque
from datetime import datetime, timedelta, timezone
from typing import Literal

from app.core.time import now_chile

logger = logging.getLogger("wowhub.uptime")

Status = Literal["operational", "degraded", "outage", "unknown"]

_HISTORY_DAYS = 90  # ventana máxima que el status page muestra
_POLL_INTERVAL = 60  # segundos entre checks automáticos


class UptimeMonitor:
    """Monitor de uptime en memoria (thread-safe)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # Cada entrada es (timestamp_utc, status). deque acotada a ~1 entrada/seg
        # durante 90 días = ~7.7M puntos (demasiado). Mejor: agrupar por día.
        # Estructura: dict {YYYY-MM-DD: {"operational": int, "degraded": int, "outage": int}}
        self._by_day: dict[str, dict[str, int]] = {}
        # Estado del último check (para current_status()).
        self._last_check_at: datetime | None = None
        self._last_status: Status = "unknown"
        # Contadores globales (desde el arranque del proceso).
        self._started_at = datetime.now(timezone.utc)
        self._total_checks = 0
        self._total_operational = 0
        self._total_degraded = 0
        self._total_outage = 0
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    # ── Lifecycle ───────────────────────────────────────────────────────
    def start(self) -> None:
        """Inicia el thread daemon de polling automático."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop, name="uptime-monitor", daemon=True,
        )
        self._thread.start()
        logger.info("UptimeMonitor started (interval=%ds)", _POLL_INTERVAL)

    def stop(self) -> None:
        """Detiene el thread daemon."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)

    def _run_loop(self) -> None:
        """Loop principal del thread daemon."""
        while not self._stop_event.is_set():
            try:
                self._probe_once()
            except Exception as exc:  # noqa: BLE001
                logger.warning("uptime probe failed: %s", exc)
                self.record("unknown")
            # Espera con cancellation check.
            self._stop_event.wait(_POLL_INTERVAL)

    def _probe_once(self) -> None:
        """Hace un health check interno (DB ping)."""
        try:
            from sqlalchemy import text
            from app.database import SessionLocal
            with SessionLocal() as s:
                s.execute(text("SELECT 1"))
            self.record("operational")
        except Exception as exc:  # noqa: BLE001
            logger.warning("uptime DB probe failed: %s", exc)
            self.record("outage")

    # ── API pública ─────────────────────────────────────────────────────
    def record(self, status: Status) -> None:
        """Registra un check externo o interno.

        Llamar manualmente desde ``/health`` o desde Celery beat para
        inyectar checks adicionales al historial.
        """
        # Usar Chile-time para day_key: debe coincidir con las lookups de
        # uptime_pct()/history() que también usan now_chile().date().
        now = now_chile()
        day_key = now.date().isoformat()
        with self._lock:
            if day_key not in self._by_day:
                self._by_day[day_key] = {"operational": 0, "degraded": 0, "outage": 0, "unknown": 0}
            self._by_day[day_key][status] = self._by_day[day_key].get(status, 0) + 1
            self._last_check_at = now
            self._last_status = status
            self._total_checks += 1
            if status == "operational":
                self._total_operational += 1
            elif status == "degraded":
                self._total_degraded += 1
            elif status == "outage":
                self._total_outage += 1

    def current_status(self) -> dict:
        """Devuelve estado actual del servicio."""
        with self._lock:
            if self._total_checks == 0:
                return {"status": "unknown", "since": None}
            return {
                "status": self._last_status,
                "since": self._last_check_at.isoformat() if self._last_check_at else None,
                "checks_total": self._total_checks,
            }

    def uptime_pct(self, days: int = 30) -> float:
        """% uptime operacional en los últimos ``days`` días (1-90)."""
        days = max(1, min(days, _HISTORY_DAYS))
        with self._lock:
            total = 0
            ok = 0
            now = now_chile().date()
            for i in range(days):
                d = (now - timedelta(days=i)).isoformat()
                bucket = self._by_day.get(d)
                if not bucket:
                    continue
                # unknown no cuenta como up ni como down (es "sin dato")
                total += bucket.get("operational", 0) + bucket.get("degraded", 0) + bucket.get("outage", 0)
                ok += bucket.get("operational", 0)
        if total == 0:
            return 100.0  # sin datos, asumimos OK
        return round(ok / total * 100.0, 3)

    def history(self, days: int = 30) -> list[dict]:
        """Lista de días con su estado agregado (operational/degraded/outage)."""
        days = max(1, min(days, _HISTORY_DAYS))
        with self._lock:
            out = []
            now = now_chile().date()
            for i in range(days):
                d = (now - timedelta(days=i)).isoformat()
                bucket = self._by_day.get(d)
                if not bucket:
                    out.append({
                        "date": d,
                        "status": "unknown",
                        "checks": 0,
                        "uptime_pct": None,
                    })
                    continue
                ops = bucket.get("operational", 0)
                deg = bucket.get("degraded", 0)
                out_ = bucket.get("outage", 0)
                total = ops + deg + out_
                # Determinar estado agregado del día (peor caso).
                if out_ > 0:
                    day_status = "outage"
                elif deg > 0:
                    day_status = "degraded"
                elif ops > 0:
                    day_status = "operational"
                else:
                    day_status = "unknown"
                out.append({
                    "date": d,
                    "status": day_status,
                    "checks": total,
                    "uptime_pct": round(ops / total * 100.0, 2) if total > 0 else None,
                })
        # Ordenar cronológicamente (más antiguo primero → más reciente al final).
        return list(reversed(out))

    def as_dict(self, days: int = 30) -> dict:
        """Serialización completa para el endpoint JSON."""
        with self._lock:
            started_at = self._started_at.isoformat()
            total_checks = self._total_checks
            total_operational = self._total_operational
            total_degraded = self._total_degraded
            total_outage = self._total_outage

        current = self.current_status()
        return {
            "service": "wowhub-api",
            "started_at": started_at,
            "current": current,
            "uptime": {
                "last_24h": self.uptime_pct(1),
                "last_7d": self.uptime_pct(7),
                "last_30d": self.uptime_pct(30),
                "last_90d": self.uptime_pct(90),
            },
            "components": {
                "api": self.current_status()["status"],
                "database": self.current_status()["status"],
            },
            "totals": {
                "checks": total_checks,
                "operational": total_operational,
                "degraded": total_degraded,
                "outage": total_outage,
            },
            "history": self.history(days),
        }


# ── Singleton global ────────────────────────────────────────────────────
_monitor: UptimeMonitor | None = None
_monitor_lock = threading.Lock()


def get_uptime_monitor() -> UptimeMonitor:
    """Devuelve el singleton del monitor (thread-safe)."""
    global _monitor
    with _monitor_lock:
        if _monitor is None:
            _monitor = UptimeMonitor()
        return _monitor