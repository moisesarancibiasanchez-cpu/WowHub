"""Onboarding API — wizard de configuración inicial por tenant."""
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.database import get_db
from app.deps import get_current_membership
from app.models.onboarding import OnboardingState
from app.models.tenant import Tenant, TenantMembership

router = APIRouter(prefix="/tenants/{tenant_id}/onboarding", tags=["onboarding"])


class OnboardingUpdate(BaseModel):
    current_step: Optional[str] = None
    completed_steps: Optional[list[str]] = None
    wizard_data: Optional[dict] = None


@router.get("")
def get_state(
    tenant_id: UUID,
    membership: TenantMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    state = _get_or_create(tenant_id, db)
    return {
        "current_step": state.current_step,
        "completed_steps": state.completed_steps or [],
        "wizard_data": state.wizard_data or {},
        "wow_score": state.wow_score,
        "is_completed": state.is_completed,
    }


@router.post("/step")
def update_step(
    tenant_id: UUID,
    payload: OnboardingUpdate,
    membership: TenantMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    state = _get_or_create(tenant_id, db)
    if payload.current_step:
        state.current_step = payload.current_step
    if payload.completed_steps:
        existing = set(state.completed_steps or [])
        existing.update(payload.completed_steps)
        state.completed_steps = sorted(existing)
    if payload.wizard_data:
        merged = dict(state.wizard_data or {})
        merged.update(payload.wizard_data)
        state.wizard_data = merged
    # Calcular wow_score (cada paso vale 14 puntos, 7 pasos = 100)
    state.wow_score = min(100, len(state.completed_steps or []) * 14)
    state.is_completed = state.wow_score >= 100
    # También actualizar Tenant.wow_score
    tenant = db.get(Tenant, tenant_id)
    if tenant:
        tenant.wow_score = state.wow_score
    db.commit()
    db.refresh(state)
    return {
        "current_step": state.current_step,
        "completed_steps": state.completed_steps or [],
        "wizard_data": state.wizard_data or {},
        "wow_score": state.wow_score,
        "is_completed": state.is_completed,
    }


@router.post("/complete")
def complete(
    tenant_id: UUID,
    membership: TenantMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    state = _get_or_create(tenant_id, db)
    state.is_completed = True
    state.wow_score = 100
    db.commit()
    return {"ok": True}


def _get_or_create(tenant_id: UUID, db: Session) -> OnboardingState:
    state = db.execute(
        select(OnboardingState).where(OnboardingState.tenant_id == str(tenant_id))
    ).scalar_one_or_none()
    if not state:
        tenant = db.get(Tenant, tenant_id)
        if not tenant:
            raise NotFoundError("Tenant")
        state = OnboardingState(tenant_id=str(tenant_id))
        db.add(state)
        db.commit()
        db.refresh(state)
    return state
