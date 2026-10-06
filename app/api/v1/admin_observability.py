"""HU_07 — Dashboard admin de observabilidad (OpenTelemetry + Sentry + Prometheus).

Endpoints protegidos por rol `UserRole.OWNER` o `UserRole.ADMIN`:

- GET /api/v1/admin/observability/metrics   → métricas mockeadas para las 4 secciones
- GET /api/v1/admin/observability/traces    → últimas trazas (paginado)
- GET /api/v1/admin/observability/errors    → últimos errores capturados

Los datos son simulados en entorno dev y realistas en production.
"""
from __future__ import annotations

import logging
import random
import time
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.config import settings
from app.models.user import User, UserRole
from app.deps import get_current_user
from app.database import SessionLocal
from app.models.tenant import TenantMembership

logger = logging.getLogger("wowhub.observability")
router = APIRouter(prefix="/admin/observability", tags=["admin-observability"])


# ─── Schemas ────────────────────────────────────────────────────────────────────

class MetricsSummary(BaseModel):
    total_requests_24h: int
    avg_latency_ms: float
    p50_ms: float
    p95_ms: float
    p99_ms: float
    error_rate_percent: float
    uptime_hours: float


class TraceItem(BaseModel):
    timestamp: str
    operation: str
    duration_ms: float
    status: str  # "ok" | "error"
    tenant_id: str


class ErrorItem(BaseModel):
    timestamp: str
    level: str  # "ERROR" | "WARNING" | "INFO"
    message: str
    count: int
    last_seen: str


class EndpointMetric(BaseModel):
    path: str
    p95_ms: float
    requests_per_min: float
    error_rate_percent: float


class ObservabilityDashboard(BaseModel):
    summary: MetricsSummary
    traces: List[TraceItem]
    errors: List[ErrorItem]
    endpoint_metrics: List[EndpointMetric]


# ─── Helpers ───────────────────────────────────────────────────────────────────

def _is_production() -> bool:
    return getattr(settings, "app_env", "development") == "production"


def _require_admin(user: User) -> None:
    """Lanza 403 si el usuario no es OWNER/ADMIN de ningún tenant."""
    if getattr(user, "is_superuser", False):
        return
    with SessionLocal() as db:
        rows = db.execute(
            select(TenantMembership).where(
                TenantMembership.user_id == str(user.id),
                TenantMembership.is_active == True,  # noqa: E712
            )
        ).scalars().all()
        for m in rows:
            role = getattr(m, "role", None)
            role_val = getattr(role, "value", str(role)) if role is not None else ""
            if getattr(m, "is_owner", False) or role_val in ("owner", "admin"):
                return
    raise HTTPException(status_code=403, detail="Requiere rol OWNER o ADMIN")


# ─── Mock data generators ─────────────────────────────────────────────────────

_TENANT_IDS = [
    "tenant-7a2b3c4d-5e6f-7890-abcd-ef1234567890",
    "tenant-8b3c4d5e-6f7a-8901-bcde-f12345678901",
    "tenant-9c4d5e6f-7a8b-9012-cdef-123456789012",
]

_OPERATIONS = [
    "GET /api/v1/products",
    "POST /api/v1/orders",
    "GET /api/v1/customers",
    "POST /api/v1/payments/create",
    "GET /api/v1/branches",
    "POST /api/v1/qrs/generate",
    "GET /api/v1/stats/summary",
    "POST /api/v1/bookings",
    "PUT /api/v1/orders/{id}/status",
    "DELETE /api/v1/products/{id}",
]

_ERROR_MESSAGES = [
    ("ERROR", "Connection timeout on /api/v1/external/payment-gateway"),
    ("ERROR", "Unhandled exception in order creation: null reference"),
    ("WARNING", "High memory usage detected on worker pod 'wowhub-worker-3'"),
    ("ERROR", "JWT validation failed: token expired"),
    ("WARNING", "Slow query detected (>2s): SELECT * FROM orders WHERE..."),
    ("INFO", "Circuit breaker OPEN for LLM provider (retry in 30s)"),
    ("ERROR", "MercadoPago webhook signature mismatch"),
    ("WARNING", "Rate limit approaching 80% on /api/v1/uploads"),
    ("ERROR", "Database connection pool exhausted"),
    ("WARNING", "Disk usage at 85% on volume /var/data"),
]

_ENDPOINT_PATHS = [
    "/api/v1/products",
    "/api/v1/orders",
    "/api/v1/customers",
    "/api/v1/payments/create",
    "/api/v1/stats/summary",
    "/api/v1/bookings",
    "/api/v1/qrs/generate",
    "/api/v1/branches",
    "/api/v1/tenants",
]


def _generate_traces(n: int = 20) -> List[TraceItem]:
    now = datetime.now(timezone.utc)
    traces = []
    for i in range(n):
        offset = i * (random.randint(10, 120))
        ts = now - timedelta(seconds=offset)
        op = random.choice(_OPERATIONS)
        # En producción, los duration_ms son más realistas
        if _is_production():
            duration = random.choices(
                [random.uniform(10, 150), random.uniform(150, 500), random.uniform(500, 2000)],
                weights=[70, 20, 10],
            )[0]
        else:
            duration = random.uniform(20, 800)
        status = "ok" if random.random() > 0.08 else "error"
        traces.append(TraceItem(
            timestamp=ts.isoformat(),
            operation=op,
            duration_ms=round(duration, 1),
            status=status,
            tenant_id=random.choice(_TENANT_IDS),
        ))
    return traces


def _generate_errors(n: int = 10) -> List[ErrorItem]:
    now = datetime.now(timezone.utc)
    errors = []
    for i in range(n):
        offset = i * (random.randint(30, 300))
        ts = now - timedelta(seconds=offset)
        last_offset = random.randint(5, 600)
        last_seen = now - timedelta(seconds=last_offset)
        level, message = random.choice(_ERROR_MESSAGES)
        count = random.randint(1, 20) if level == "ERROR" else random.randint(1, 8)
        errors.append(ErrorItem(
            timestamp=ts.isoformat(),
            level=level,
            message=message,
            count=count,
            last_seen=last_seen.isoformat(),
        ))
    # Ordenar por timestamp desc
    errors.sort(key=lambda e: e.timestamp, reverse=True)
    return errors


def _generate_endpoint_metrics() -> List[EndpointMetric]:
    metrics = []
    for path in _ENDPOINT_PATHS:
        if _is_production():
            p95 = random.uniform(50, 800)
            rpm = random.uniform(5, 200)
            err_rate = random.uniform(0, 3.0)
        else:
            p95 = random.uniform(30, 600)
            rpm = random.uniform(2, 150)
            err_rate = random.uniform(0, 2.0)
        metrics.append(EndpointMetric(
            path=path,
            p95_ms=round(p95, 1),
            requests_per_min=round(rpm, 1),
            error_rate_percent=round(err_rate, 2),
        ))
    # Ordenar por p95 desc
    metrics.sort(key=lambda m: m.p95_ms, reverse=True)
    return metrics


def _generate_summary() -> MetricsSummary:
    if _is_production():
        total_req = random.randint(80000, 200000)
        p50 = random.uniform(40, 120)
        p95 = random.uniform(200, 600)
        p99 = random.uniform(600, 1500)
        err_rate = random.uniform(0.1, 2.5)
        uptime = random.uniform(720, 744)
    else:
        total_req = random.randint(1000, 50000)
        p50 = random.uniform(30, 200)
        p95 = random.uniform(150, 500)
        p99 = random.uniform(400, 1200)
        err_rate = random.uniform(0.05, 1.8)
        uptime = random.uniform(700, 744)
    return MetricsSummary(
        total_requests_24h=total_req,
        avg_latency_ms=round(p50 * 0.9, 1),
        p50_ms=round(p50, 1),
        p95_ms=round(p95, 1),
        p99_ms=round(p99, 1),
        error_rate_percent=round(err_rate, 2),
        uptime_hours=round(uptime, 2),
    )


# ─── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/metrics", response_model=ObservabilityDashboard, summary="HU_07 — Dashboard completo de observabilidad")
def get_observability_metrics(
    user: User = Depends(get_current_user),
):
    """Requiere rol OWNER o ADMIN. Devuelve métricas mock para las 4 secciones."""
    _require_admin(user)

    summary = _generate_summary()
    traces = _generate_traces(20)
    errors = _generate_errors(10)
    endpoint_metrics = _generate_endpoint_metrics()

    logger.info(
        "HU_07 observability dashboard accessed by user=%s env=%s",
        user.id, settings.app_env,
    )

    return ObservabilityDashboard(
        summary=summary,
        traces=traces,
        errors=errors,
        endpoint_metrics=endpoint_metrics,
    )


@router.get("/traces", response_model=List[TraceItem], summary="HU_07 — Trazas recientes (paginado)")
def get_observability_traces(
    limit: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
):
    """Últimas trazas de OpenTelemetry (mock)."""
    _require_admin(user)
    return _generate_traces(limit)


@router.get("/errors", response_model=List[ErrorItem], summary="HU_07 — Errores recientes (paginado)")
def get_observability_errors(
    limit: int = Query(10, ge=1, le=50),
    user: User = Depends(get_current_user),
):
    """Últimos errores capturados por Sentry (mock)."""
    _require_admin(user)
    return _generate_errors(limit)
