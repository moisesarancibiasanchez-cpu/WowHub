"""Branch endpoints."""
from uuid import UUID
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.database import get_db
from app.deps import get_tenant_for_membership
from app.models.branch import Branch
from app.models.tenant import Tenant
from app.schemas.branch import BranchCreate, BranchOut, BranchUpdate

router = APIRouter(prefix="/tenants/{tenant_id}/branches", tags=["branches"])


@router.get("", response_model=list[BranchOut])
def list_branches(tenant: Tenant = Depends(get_tenant_for_membership), db: Session = Depends(get_db)):
    return list(db.execute(
        select(Branch).where(Branch.tenant_id == str(tenant.id)).order_by(Branch.is_main.desc(), Branch.name)
    ).scalars())


@router.post("", response_model=BranchOut, status_code=201)
def create_branch(
    payload: BranchCreate,
    tenant: Tenant = Depends(get_tenant_for_membership),
    db: Session = Depends(get_db),
):
    b = Branch(**payload.model_dump(), tenant_id=str(tenant.id))
    db.add(b)
    db.commit()
    db.refresh(b)
    return b


@router.get("/{branch_id}", response_model=BranchOut)
def get_branch(branch_id: UUID, tenant: Tenant = Depends(get_tenant_for_membership), db: Session = Depends(get_db)):
    b = db.get(Branch, branch_id)
    if not b or b.tenant_id != tenant.id:
        raise NotFoundError("Branch")
    return b


@router.patch("/{branch_id}", response_model=BranchOut)
def update_branch(
    branch_id: UUID,
    payload: BranchUpdate,
    tenant: Tenant = Depends(get_tenant_for_membership),
    db: Session = Depends(get_db),
):
    b = db.get(Branch, branch_id)
    if not b or b.tenant_id != tenant.id:
        raise NotFoundError("Branch")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(b, k, v)
    db.commit()
    db.refresh(b)
    return b


@router.delete("/{branch_id}", status_code=204)
def delete_branch(branch_id: UUID, tenant: Tenant = Depends(get_tenant_for_membership), db: Session = Depends(get_db)):
    b = db.get(Branch, branch_id)
    if not b or b.tenant_id != tenant.id:
        raise NotFoundError("Branch")
    db.delete(b)
    db.commit()
