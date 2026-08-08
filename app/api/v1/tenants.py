"""Tenant endpoints."""
from uuid import UUID
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user, get_tenant_for_membership
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.tenant import (
    TenantCreate, TenantOut, TenantUpdate,
    TenantMembershipCreate, TenantMembershipOut, TenantMembershipUpdate,
)
from app.services.tenant_service import TenantService

router = APIRouter(prefix="/tenants", tags=["tenants"])


@router.post("", response_model=TenantOut, status_code=201)
def create_tenant(
    payload: TenantCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Crea un nuevo tenant y asigna al usuario actual como OWNER."""
    return TenantService(db).create(user, payload)


@router.get("/{tenant_id}", response_model=TenantOut)
def get_tenant(tenant: Tenant = Depends(get_tenant_for_membership)):
    return tenant


@router.patch("/{tenant_id}", response_model=TenantOut)
def update_tenant(
    payload: TenantUpdate,
    tenant: Tenant = Depends(get_tenant_for_membership),
    db: Session = Depends(get_db),
):
    return TenantService(db).update(tenant, payload)


# ── Membresías ─────────────────────────────────────────
membership_router = APIRouter(prefix="/tenants/{tenant_id}/members", tags=["members"])


@membership_router.get("", response_model=list[TenantMembershipOut])
def list_members(tenant: Tenant = Depends(get_tenant_for_membership), db: Session = Depends(get_db)):
    return TenantService(db).list_members(tenant)


@membership_router.post("", response_model=TenantMembershipOut, status_code=201)
def add_member(
    payload: TenantMembershipCreate,
    tenant: Tenant = Depends(get_tenant_for_membership),
    db: Session = Depends(get_db),
):
    return TenantService(db).add_member(tenant, payload)


@membership_router.patch("/{member_id}", response_model=TenantMembershipOut)
def update_member(
    member_id: UUID,
    payload: TenantMembershipUpdate,
    tenant: Tenant = Depends(get_tenant_for_membership),
    db: Session = Depends(get_db),
):
    return TenantService(db).update_member(tenant, member_id, payload)
