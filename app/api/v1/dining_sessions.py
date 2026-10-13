"""HU_19 — Router de sesiones de mesa (DiningSession).

Endpoints:
  POST /tenants/{tid}/dining-sessions                          abrir mesa
  POST /tenants/{tid}/dining-sessions/{dsid}/orders           agregar OrderItem a la mesa
  GET  /tenants/{tid}/dining-sessions/{dsid}/split            división equitativa
  POST /tenants/{tid}/dining-sessions/{dsid}/close            cerrar mesa (snapshot)
  PATCH /tenants/{tid}/dining-sessions/{dsid}/tip             agregar propina
  POST /tenants/{tid}/dining-sessions/{dsid}/cancel            cancelar mesa
  GET  /tenants/{tid}/dining-sessions/{dsid}                  ver detalle
  GET  /tenants/{tid}/dining-sessions                         listar (filtros simples)
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_membership, get_current_user
from app.models.user import User
from app.schemas.dining_session import (
    DiningSessionClose,
    DiningSessionCreate,
    DiningSessionItemCreate,
    DiningSessionItemOut,
    DiningSessionOut,
    DiningSessionSplitOut,
    DiningSessionTip,
)
from app.services.dining_session_service import DiningSessionService

router = APIRouter(
    prefix="/tenants/{tenant_id}/dining-sessions",
    tags=["dining-sessions"],
)


def _svc(db: Session, tenant_id: UUID) -> DiningSessionService:
    return DiningSessionService(db, tenant_id=str(tenant_id))


@router.post("", response_model=DiningSessionOut, status_code=status.HTTP_201_CREATED)
def open_session(
    tenant_id: UUID,
    payload: DiningSessionCreate,
    user: User = Depends(get_current_user),
    membership=Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    """Abre una nueva mesa."""
    return _svc(db, tenant_id).open(payload.model_dump(mode="json"))


@router.get("", response_model=list[DiningSessionOut])
def list_sessions(
    tenant_id: UUID,
    status: Optional[str] = Query(None, pattern="^(open|closed|cancelled)$"),
    branch_id: Optional[UUID] = None,
    user: User = Depends(get_current_user),
    membership=Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    """Lista sesiones de mesa (filtros simples)."""
    from sqlalchemy import select
    from app.models.dining_session import DiningSession
    q = select(DiningSession).where(DiningSession.tenant_id == str(tenant_id))
    if status:
        q = q.where(DiningSession.status == status)
    if branch_id:
        q = q.where(DiningSession.branch_id == str(branch_id))
    q = q.order_by(DiningSession.opened_at.desc()).limit(200)
    return list(db.execute(q).scalars())


@router.get("/{session_id}", response_model=DiningSessionOut)
def get_session(
    tenant_id: UUID,
    session_id: UUID,
    user: User = Depends(get_current_user),
    membership=Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    return _svc(db, tenant_id)._get_session(session_id)


@router.post(
    "/{session_id}/orders",
    response_model=DiningSessionItemOut,
    status_code=status.HTTP_201_CREATED,
)
def add_order(
    tenant_id: UUID,
    session_id: UUID,
    payload: DiningSessionItemCreate,
    user: User = Depends(get_current_user),
    membership=Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    """Asocia un OrderItem a la mesa."""
    return _svc(db, tenant_id).add_order_item(
        session_id=session_id,
        order_item_id=payload.order_item_id,
        assigned_to=payload.assigned_to,
        share_cents=payload.share_cents,
        notes=payload.notes,
    )


@router.get(
    "/{session_id}/split",
    response_model=DiningSessionSplitOut,
)
def get_split(
    tenant_id: UUID,
    session_id: UUID,
    user: User = Depends(get_current_user),
    membership=Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    """Calcula la división equitativa de la cuenta."""
    return _svc(db, tenant_id).split_equally(session_id)


@router.post(
    "/{session_id}/close",
    response_model=DiningSessionOut,
)
def close_session(
    tenant_id: UUID,
    session_id: UUID,
    payload: Optional[DiningSessionClose] = None,
    user: User = Depends(get_current_user),
    membership=Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    """Cierra la mesa y congela el snapshot final."""
    payload = payload or DiningSessionClose()
    return _svc(db, tenant_id).close(
        session_id=session_id,
        paid_cents=payload.paid_cents,
        notes=payload.notes,
    )


@router.patch(
    "/{session_id}/tip",
    response_model=DiningSessionOut,
)
def add_tip(
    tenant_id: UUID,
    session_id: UUID,
    payload: DiningSessionTip,
    user: User = Depends(get_current_user),
    membership=Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    """Agrega propina a la mesa (acumulable)."""
    return _svc(db, tenant_id).add_tip(session_id=session_id, tip_cents=payload.tip_cents)


@router.post(
    "/{session_id}/cancel",
    response_model=DiningSessionOut,
)
def cancel_session(
    tenant_id: UUID,
    session_id: UUID,
    user: User = Depends(get_current_user),
    membership=Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    return _svc(db, tenant_id).cancel(session_id)
