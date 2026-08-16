"""AI Core — endpoints ADMIN (logs, métricas, trazas, control del circuit).

Protegido por rol `UserRole.OWNER` o `UserRole.ADMIN`.

- GET  /api/v1/admin/ai/overview
- GET  /api/v1/admin/ai/metrics?days=7
- GET  /api/v1/admin/ai/logs?page=1&page_size=50
- GET  /api/v1/admin/ai/logs/{log_id}/traces
- POST /api/v1/admin/ai/circuit/close
- POST /api/v1/admin/ai/circuit/open
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.deps import get_current_user
from app.models.ai import (
    AILog, AIMetricDaily, AITrace, AgentKind, LogStatus,
)
from app.models.tenant import TenantMembership
from app.models.user import User, UserRole
from app.schemas.ai import (
    AIOverviewOut, LogListOut, LogOut, MetricDailyOut, TraceListOut, TraceOut,
)
from app.services.llm_client import get_circuit

logger = logging.getLogger("wowhub.ai.admin")
router = APIRouter(prefix="/admin/ai", tags=["admin-ai"])


def _require_admin(user: User) -> None:
    """Permite OWNER/ADMIN del tenant o SUPERUSER (plataforma).

    SUPERUSER no tiene rol de tenant (no es miembro de TenantMembership);
    debe poder operar la consola AI Core incluso sin impersonación activa.
    """
    # El modelo User tiene `default_role` (no `role`). Soportamos ambos por compat.
    role = getattr(user, "role", None) or getattr(user, "default_role", None)
    if getattr(user, "is_superuser", False):
        return
    if role not in (UserRole.OWNER, UserRole.ADMIN):
        raise HTTPException(status_code=403, detail="Requiere rol OWNER o ADMIN")


def _is_platform_admin(user: User) -> bool:
    return bool(getattr(user, "is_superuser", False))


def _user_tenants(db: Session, user_id: str) -> list[str]:
    rows = db.execute(
        select(TenantMembership.tenant_id).where(
            TenantMembership.user_id == user_id,
            TenantMembership.is_active == True,  # noqa
        )
    ).all()
    return [str(r[0]) for r in rows]


def _platform_tenants(db: Session) -> list[str]:
    """Devuelve TODOS los tenant_id de la plataforma (uso exclusivo SUPERUSER)."""
    from app.models.tenant import Tenant
    rows = db.execute(select(Tenant.id)).all()
    return [str(r[0]) for r in rows]


def _resolve_tenant_scope(db: Session, user: User) -> Optional[list[str]]:
    """Resuelve el scope de tenants a consultar.

    - SUPERUSER: ve TODA la plataforma.
    - OWNER/ADMIN: ve solo los tenants donde es miembro.
    - Resto: None (no tiene acceso a esta vista).
    """
    if _is_platform_admin(user):
        return _platform_tenants(db)
    role = getattr(user, "role", None) or getattr(user, "default_role", None)
    if role not in (UserRole.OWNER, UserRole.ADMIN):
        return None
    return _user_tenants(db, str(user.id))


@router.get("/overview", response_model=AIOverviewOut)
def get_overview(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AIOverviewOut:
    _require_admin(user)
    tenant_ids = _resolve_tenant_scope(db, user)
    if tenant_ids is None:
        raise HTTPException(status_code=403, detail="Requiere rol OWNER o ADMIN")
    if not tenant_ids:
        # Usuario admin sin tenants asignados: devolvemos overview vacío
        # (no es un error, simplemente no tiene datos para mostrar).
        return AIOverviewOut(
            last_24h=MetricDailyOut(
                day=datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0),
                agent=AgentKind.MARKETING,
                requests=0, success=0, fallback=0, errors=0,
                timeouts=0, rate_limited=0, tokens_in=0, tokens_out=0,
                avg_latency_ms=0, p95_latency_ms=0, unique_users=0,
            ),
            last_7d=[],
            circuit_state=str(get_circuit().snapshot()),
            llm_enabled=settings.llm_enabled,
            llm_model=getattr(settings, "llm_model", None),
            llm_provider=getattr(settings, "llm_provider", None),
            total_conversations=0,
            total_messages=0,
            active_users_7d=0,
        )

    # Convertir a UUID para todas las queries (PostgreSQL requiere UUID nativo)
    tenant_uuids = [UUID(t) if isinstance(t, str) else t for t in tenant_ids]

    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    last_24h = None
    try:
        last_24h = db.execute(
            select(AIMetricDaily)
            .where(
                AIMetricDaily.day >= today,
                AIMetricDaily.tenant_id.in_(tenant_uuids),
            )
            .order_by(desc(AIMetricDaily.requests))
            .limit(1)
        ).scalar_one_or_none()
    except Exception as e:
        logger.warning("[admin/overview] error consultando AIMetricDaily: %s", e)
        db.rollback()

    if last_24h is None:
        # Devolvemos un "vacío" con todos los campos inicializados a 0
        # para que Pydantic pueda validarlo correctamente.
        last_24h = AIMetricDaily(
            id=UUID(int=0),
            tenant_id=tenant_uuids[0],
            day=today,
            agent=AgentKind.MARKETING,
            requests=0,
            success=0,
            fallback=0,
            errors=0,
            timeouts=0,
            rate_limited=0,
            tokens_in=0,
            tokens_out=0,
            avg_latency_ms=0,
            p95_latency_ms=0,
            unique_users=0,
        )

    last_7d: list = []
    try:
        last_7d = db.execute(
            select(AIMetricDaily)
            .where(
                AIMetricDaily.day >= today - timedelta(days=7),
                AIMetricDaily.tenant_id.in_(tenant_uuids),
            )
            .order_by(AIMetricDaily.day.asc())
        ).scalars().all()
    except Exception as e:
        logger.warning("[admin/overview] error consultando last_7d: %s", e)
        db.rollback()

    from app.models.ai import AIConversation, AIMessage
    total_conv = 0
    total_msgs = 0
    active_users = 0
    try:
        total_conv = db.execute(
            select(func.count(AIConversation.id))
            .where(AIConversation.tenant_id.in_(tenant_uuids))
        ).scalar_one() or 0
    except Exception as e:
        logger.warning("[admin/overview] error contando conversaciones: %s", e)
        db.rollback()
    try:
        total_msgs = db.execute(
            select(func.count(AIMessage.id))
            .where(AIMessage.tenant_id.in_(tenant_uuids))
        ).scalar_one() or 0
    except Exception as e:
        logger.warning("[admin/overview] error contando mensajes: %s", e)
        db.rollback()
    try:
        active_users = db.execute(
            select(func.count(func.distinct(AIMessage.user_id)))
            .where(
                AIMessage.tenant_id.in_(tenant_uuids),
                AIMessage.created_at >= today - timedelta(days=7),
            )
        ).scalar_one() or 0
    except Exception as e:
        logger.warning("[admin/overview] error contando usuarios activos: %s", e)
        db.rollback()

    try:
        return AIOverviewOut(
            last_24h=MetricDailyOut.model_validate(last_24h),
            last_7d=[MetricDailyOut.model_validate(m) for m in last_7d],
            circuit_state=str(get_circuit().snapshot()),
            llm_enabled=settings.llm_enabled,
            llm_model=getattr(settings, "llm_model", None),
            llm_provider=getattr(settings, "llm_provider", None),
            total_conversations=int(total_conv),
            total_messages=int(total_msgs),
            active_users_7d=int(active_users),
        )
    except Exception as e:
        logger.exception("[admin/overview] error construyendo respuesta: %s", e)
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error en overview: {e}")


@router.get("/metrics", response_model=list[MetricDailyOut])
def get_metrics(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    days: int = Query(7, ge=1, le=90),
    agent: Optional[AgentKind] = None,
) -> list[MetricDailyOut]:
    _require_admin(user)
    tenant_ids = _resolve_tenant_scope(db, user)
    if tenant_ids is None:
        raise HTTPException(status_code=403, detail="Requiere rol OWNER o ADMIN")
    if not tenant_ids:
        return []
    tenant_uuids = [UUID(t) if isinstance(t, str) else t for t in tenant_ids]
    since = datetime.now(timezone.utc) - timedelta(days=days)
    stmt = (
        select(AIMetricDaily)
        .where(
            AIMetricDaily.tenant_id.in_(tenant_uuids),
            AIMetricDaily.day >= since,
        )
        .order_by(AIMetricDaily.day.asc())
    )
    if agent:
        stmt = stmt.where(AIMetricDaily.agent == agent)
    try:
        rows = db.execute(stmt).scalars().all()
        return [MetricDailyOut.model_validate(r) for r in rows]
    except Exception as e:
        logger.exception("[admin/metrics] error: %s", e)
        db.rollback()
        return []


@router.get("/logs", response_model=LogListOut)
def get_logs(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    status_filter: Optional[LogStatus] = Query(None, alias="status"),
    agent: Optional[AgentKind] = None,
) -> LogListOut:
    _require_admin(user)
    tenant_ids = _resolve_tenant_scope(db, user)
    if tenant_ids is None:
        raise HTTPException(status_code=403, detail="Requiere rol OWNER o ADMIN")
    if not tenant_ids:
        return LogListOut(items=[], total=0, page=page, page_size=page_size)
    tenant_uuids = [UUID(t) if isinstance(t, str) else t for t in tenant_ids]
    try:
        base = select(AILog).where(AILog.tenant_id.in_(tenant_uuids))
        if status_filter:
            base = base.where(AILog.status == status_filter)
        if agent:
            base = base.where(AILog.agent == agent)
        base = base.order_by(desc(AILog.created_at))

        total = db.execute(
            select(func.count()).select_from(base.subquery())
        ).scalar_one() or 0
        rows = db.execute(
            base.offset((page - 1) * page_size).limit(page_size)
        ).scalars().all()
        return LogListOut(
            items=[LogOut.model_validate(r) for r in rows],
            total=int(total),
            page=page,
            page_size=page_size,
        )
    except Exception as e:
        logger.exception("[admin/logs] error: %s", e)
        db.rollback()
        return LogListOut(items=[], total=0, page=page, page_size=page_size)


@router.get("/logs/{log_id}/traces", response_model=TraceListOut)
def get_log_traces(
    log_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TraceListOut:
    _require_admin(user)
    log = db.get(AILog, log_id)
    if not log:
        raise HTTPException(status_code=404, detail="Log no encontrado")
    rows = db.execute(
        select(AITrace)
        .where(AITrace.log_id == log_id)
        .order_by(AITrace.created_at.asc())
    ).scalars().all()
    return TraceListOut(
        items=[TraceOut.model_validate(r) for r in rows],
        total=len(rows),
    )


@router.post("/circuit/close")
def close_circuit(
    user: User = Depends(get_current_user),
) -> dict:
    _require_admin(user)
    get_circuit().force_close()
    return {"circuit_state": get_circuit().snapshot()}


@router.post("/circuit/open")
def open_circuit(
    user: User = Depends(get_current_user),
) -> dict:
    _require_admin(user)
    get_circuit().force_open()
    return {"circuit_state": get_circuit().snapshot()}
