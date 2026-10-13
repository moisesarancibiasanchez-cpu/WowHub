"""Automation Manager™ API (Cap. 19.3).

Endpoints:
- GET  /api/v1/automation/actions          → lista acciones disponibles
- GET  /api/v1/automation/actions/{key}    → detalle de una acción
- POST /api/v1/automation/preview          → genera preview (dry_run=true)
- POST /api/v1/automation/execute          → ejecuta (dry_run=false + confirmed=true)
- GET  /api/v1/automation/history          → historial de ejecuciones del tenant

Auth: JWT + TenantMembership (mismo patrón que el resto de la API).
Rate limit: ai_daily_automation_limit por usuario (cuenta /execute, NO /preview).
Permisos: por rol de TenantMembership (OWNER/ADMIN/STAFF/VIEWER).
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_membership
from app.models.automation import AutomationExecution, AutomationStatus
from app.models.tenant import TenantMembership
from app.schemas.automation import (
    ActionSpec,
    ActionType,
    AutomationExecutionOut,
    AutomationHistoryResponse,
    AutomationRequest,
    AutomationResponse,
)
from app.services.automation_manager import (
    AutomationError,
    execute_action,
    get_action_spec,
    list_actions,
    preview_action,
)

logger = logging.getLogger("wowhub.ai.automation.api")

router = APIRouter(
    prefix="/automation",
    tags=["automation"],
)


def _role_value(membership: TenantMembership) -> str:
    """Devuelve el rol del membership como string ('owner' | 'admin' | 'staff' | 'viewer')."""
    role = membership.role
    return role.value if hasattr(role, "value") else str(role)


# ── GET /automation/actions ─────────────────────────────────────
@router.get(
    "/actions",
    response_model=list[ActionSpec],
    summary="Lista de acciones disponibles del Automation Manager",
)
def get_actions(
    membership: TenantMembership = Depends(get_current_membership),
) -> list[ActionSpec]:
    """Devuelve el catálogo completo de acciones registradas.

    El frontend filtra según el rol del usuario si quiere.
    """
    return list_actions()


# ── GET /automation/actions/{action_type} ──────────────────────
@router.get(
    "/actions/{action_type}",
    response_model=ActionSpec,
    summary="Detalle de una acción específica",
)
def get_action(
    action_type: ActionType,
    membership: TenantMembership = Depends(get_current_membership),
) -> ActionSpec:
    try:
        return get_action_spec(action_type)
    except AutomationError as e:
        raise HTTPException(status_code=e.status_code, detail={"code": e.code, "message": e.message})


# ── POST /automation/preview ───────────────────────────────────
@router.post(
    "/preview",
    response_model=AutomationResponse,
    summary="Genera un preview de la acción (NO ejecuta, NO toca DB)",
)
def post_preview(
    payload: AutomationRequest,
    membership: TenantMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
) -> AutomationResponse:
    """Resuelve la acción, valida permisos, valida params, y devuelve
    un `preview` legible. NO modifica la base de datos.
    """
    try:
        return preview_action(
            db=db,
            req=payload,
            tenant_id=membership.tenant_id,
            user_id=membership.user_id,
            user_role=_role_value(membership),
        )
    except AutomationError as e:
        raise HTTPException(
            status_code=e.status_code,
            detail={"code": e.code, "message": e.message},
        )


# ── POST /automation/execute ───────────────────────────────────
@router.post(
    "/execute",
    response_model=AutomationResponse,
    summary="Ejecuta la acción (escribe DB + audit log)",
)
def post_execute(
    payload: AutomationRequest,
    membership: TenantMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
) -> AutomationResponse:
    """Ejecuta la acción. REQUIERE `dry_run=false` Y `confirmed=true`.

    Rate limit: cuenta contra `ai_daily_automation_limit` por usuario.
    Audit: escribe una fila en `automation_executions`.
    """
    try:
        return execute_action(
            db=db,
            req=payload,
            tenant_id=membership.tenant_id,
            user_id=membership.user_id,
            user_role=_role_value(membership),
        )
    except AutomationError as e:
        raise HTTPException(
            status_code=e.status_code,
            detail={"code": e.code, "message": e.message},
        )


# ── GET /automation/history ─────────────────────────────────────
@router.get(
    "/history",
    response_model=AutomationHistoryResponse,
    summary="Historial de ejecuciones del tenant actual",
)
def get_history(
    action_type: Optional[ActionType] = Query(
        None,
        description="Filtrar por tipo de acción",
    ),
    status_filter: Optional[AutomationStatus] = Query(
        None,
        alias="status",
        description="Filtrar por estado de la ejecución",
    ),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    membership: TenantMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
) -> AutomationHistoryResponse:
    """Devuelve el historial paginado del tenant activo.

    Cada item es un `AutomationExecutionOut` (sin `params` para no leakear
    PII del body, pero el superadmin puede verlo en /admin/ai).
    """
    base = select(AutomationExecution).where(
        AutomationExecution.tenant_id == membership.tenant_id,
    )
    if action_type:
        base = base.where(AutomationExecution.action_type == action_type)
    if status_filter:
        base = base.where(AutomationExecution.status == status_filter)

    # Total (count del mismo WHERE)
    count_stmt = select(func.count()).select_from(base.subquery())
    total = db.execute(count_stmt).scalar_one() or 0

    # Página
    page_stmt = base.order_by(AutomationExecution.created_at.desc()).limit(limit).offset(offset)
    rows = db.execute(page_stmt).scalars().all()

    items = [AutomationExecutionOut.model_validate(r) for r in rows]
    return AutomationHistoryResponse(
        items=items,
        total=int(total),
        limit=limit,
        offset=offset,
    )
