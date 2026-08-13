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
    if user.role not in (UserRole.OWNER, UserRole.ADMIN):
        raise HTTPException(status_code=403, detail="Requiere rol OWNER o ADMIN")


def _user_tenants(db: Session, user_id: str) -> list[str]:
    rows = db.execute(
        select(TenantMembership.tenant_id).where(
            TenantMembership.user_id == user_id,
            TenantMembership.is_active == True,  # noqa
        )
    ).all()
    return [str(r[0]) for r in rows]


@router.get("/overview", response_model=AIOverviewOut)
def get_overview(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AIOverviewOut:
    _require_admin(user)
    tenant_ids = _user_tenants(db, str(user.id))
    if not tenant_ids:
        raise HTTPException(status_code=400, detail="Sin tenants asignados")

    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    last_24h = db.execute(
        select(AIMetricDaily)
        .where(
            AIMetricDaily.day >= today,
            AIMetricDaily.tenant_id.in_(tenant_ids),
        )
        .order_by(desc(AIMetricDaily.requests))
        .limit(1)
    ).scalar_one_or_none()
    if last_24h is None:
        # Devolvemos un "vacío"
        last_24h = AIMetricDaily(
            id=UUID(int=0),
            tenant_id=tenant_ids[0],
            day=today,
            agent=AgentKind.MARKETING,
        )

    last_7d = db.execute(
        select(AIMetricDaily)
        .where(
            AIMetricDaily.day >= today - timedelta(days=7),
            AIMetricDaily.tenant_id.in_(tenant_ids),
        )
        .order_by(AIMetricDaily.day.asc())
    ).scalars().all()

    from app.models.ai import AIConversation, AIMessage
    total_conv = db.execute(
        select(func.count(AIConversation.id))
        .where(AIConversation.tenant_id.in_(tenant_ids))
    ).scalar_one() or 0
    total_msgs = db.execute(
        select(func.count(AIMessage.id))
        .where(AIMessage.tenant_id.in_(tenant_ids))
    ).scalar_one() or 0
    active_users = db.execute(
        select(func.count(func.distinct(AIMessage.user_id)))
        .where(
            AIMessage.tenant_id.in_(tenant_ids),
            AIMessage.created_at >= today - timedelta(days=7),
        )
    ).scalar_one() or 0

    return AIOverviewOut(
        last_24h=MetricDailyOut.model_validate(last_24h),
        last_7d=[MetricDailyOut.model_validate(m) for m in last_7d],
        circuit_state=get_circuit().snapshot(),
        llm_enabled=settings.llm_enabled,
        total_conversations=int(total_conv),
        total_messages=int(total_msgs),
        active_users_7d=int(active_users),
    )


@router.get("/metrics", response_model=list[MetricDailyOut])
def get_metrics(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    days: int = Query(7, ge=1, le=90),
    agent: Optional[AgentKind] = None,
) -> list[MetricDailyOut]:
    _require_admin(user)
    tenant_ids = _user_tenants(db, str(user.id))
    if not tenant_ids:
        return []
    since = datetime.now(timezone.utc) - timedelta(days=days)
    stmt = (
        select(AIMetricDaily)
        .where(
            AIMetricDaily.tenant_id.in_(tenant_ids),
            AIMetricDaily.day >= since,
        )
        .order_by(AIMetricDaily.day.asc())
    )
    if agent:
        stmt = stmt.where(AIMetricDaily.agent == agent)
    rows = db.execute(stmt).scalars().all()
    return [MetricDailyOut.model_validate(r) for r in rows]


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
    tenant_ids = _user_tenants(db, str(user.id))
    if not tenant_ids:
        return LogListOut(items=[], total=0, page=page, page_size=page_size)
    base = select(AILog).where(AILog.tenant_id.in_(tenant_ids))
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
