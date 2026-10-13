"""Branch endpoints."""
from uuid import UUID
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

# HU_38 — RBAC granular con Casbin. Ver app/api/v1/products.py.
from app.core.errors import NotFoundError
from app.core.security import requires_permission
from app.database import get_db
from app.deps import get_current_membership, get_tenant_for_membership
from app.models.branch import Branch
from app.models.branch_product import BranchProduct
from app.models.tenant import Tenant
from app.models.tenant import TenantMembership
from app.schemas.branch import BranchCreate, BranchOut, BranchUpdate

router = APIRouter(prefix="/tenants/{tenant_id}/branches", tags=["branches"])


@router.get("", response_model=list[BranchOut])
def list_branches(tenant: Tenant = Depends(get_tenant_for_membership), db: Session = Depends(get_db)):
    return list(db.execute(
        select(Branch).where(Branch.tenant_id == str(tenant.id)).order_by(Branch.is_main.desc(), Branch.name)
    ).scalars())


@router.post("", response_model=BranchOut, status_code=201)
@requires_permission("branch", "write")
def create_branch(
    payload: BranchCreate,
    tenant: Tenant = Depends(get_tenant_for_membership),
    db: Session = Depends(get_db),
    # HU_38 — ver create_product en products.py.
    membership: TenantMembership = Depends(get_current_membership),
):
    """HU_38 — crear sucursal requiere ``branch.write``.

    Roles permitidos (matriz default seed): OWNER, ADMIN.
    STAFF/VIEWER quedan fuera (sin policy de write en branch).
    """
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
@requires_permission("branch", "write")
def update_branch(
    branch_id: UUID,
    payload: BranchUpdate,
    tenant: Tenant = Depends(get_tenant_for_membership),
    db: Session = Depends(get_db),
    # HU_38 — ver create_product en products.py.
    membership: TenantMembership = Depends(get_current_membership),
):
    """HU_38 — actualizar sucursal requiere ``branch.write``."""
    b = db.get(Branch, branch_id)
    if not b or b.tenant_id != tenant.id:
        raise NotFoundError("Branch")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(b, k, v)
    db.commit()
    db.refresh(b)
    return b


@router.delete("/{branch_id}", status_code=204)
@requires_permission("branch", "delete")
def delete_branch(
    branch_id: UUID,
    tenant: Tenant = Depends(get_tenant_for_membership),
    db: Session = Depends(get_db),
    # HU_38 — ver create_product en products.py.
    membership: TenantMembership = Depends(get_current_membership),
):
    """HU_38 — eliminar sucursal requiere ``branch.delete``.

    Roles permitidos (matriz default seed): OWNER, ADMIN.
    STAFF/VIEWER quedan fuera (sin policy de delete).
    """
    b = db.get(Branch, branch_id)
    if not b or b.tenant_id != tenant.id:
        raise NotFoundError("Branch")
    db.delete(b)
    db.commit()


# ── Sub-recurso: inventario de una sucursal ─────────────────────
# Endpoint que consume el front de Inventario
# (/dashboard/inventory). Devuelve la misma shape que
# /tenants/{tid}/branch-products?branch_id=... para mantener
# compatibilidad con el JS de inventory.html.
@router.get("/{branch_id}/products")
def list_branch_products_for_branch(
    branch_id: UUID,
    tenant: Tenant = Depends(get_tenant_for_membership),
    db: Session = Depends(get_db),
    page_size: int = Query(200, ge=1, le=500),
):
    """Lista el stock (BranchProduct) de UNA sucursal.

    Shape (estable, la consume inventory.html):
        [{ "id": ..., "branch_id": ..., "product_id": ...,
           "stock": int, "low_stock_threshold": int }, ...]
    """
    b = db.get(Branch, branch_id)
    if not b or b.tenant_id != tenant.id:
        raise NotFoundError("Branch")
    q = (
        select(BranchProduct)
        .where(BranchProduct.tenant_id == str(tenant.id))
        .where(BranchProduct.branch_id == str(branch_id))
        .order_by(BranchProduct.created_at.desc())
        .limit(page_size)
    )
    return [
        {
            "id": str(bp.id),
            "branch_id": bp.branch_id,
            "product_id": bp.product_id,
            "stock": bp.stock,
            "low_stock_threshold": bp.low_stock_threshold,
        }
        for bp in db.execute(q).scalars()
    ]


# ── Floor Layout (HU_20) ─────────────────────────────────────────────
# GET  /api/v1/tenants/{tenant_id}/branches/{branch_id}/floor-layout
# POST /api/v1/tenants/{tenant_id}/branches/{branch_id}/floor-layout


@router.get("/{branch_id}/floor-layout")
def get_floor_layout(
    branch_id: UUID,
    tenant: Tenant = Depends(get_tenant_for_membership),
    db: Session = Depends(get_db),
):
    """Devuelve el layout de mesas de una sucursal.

    Si no hay layout guardado, devuelve {"tables": []}.
    """
    b = db.get(Branch, branch_id)
    if not b or b.tenant_id != tenant.id:
        raise NotFoundError("Branch")
    layout = getattr(b, "floor_layout", None)
    tables = layout.get("tables", []) if layout else []
    return {"branch_id": str(branch_id), "tables": tables}


@router.post("/{branch_id}/floor-layout")
def save_floor_layout(
    branch_id: UUID,
    payload: dict,
    tenant: Tenant = Depends(get_tenant_for_membership),
    db: Session = Depends(get_db),
):
    """Guarda el layout de mesas de una sucursal.

    body: {"tables": [{"id": 1, "name": "Mesa 1", "shape": "round", "capacity": 4, "status": "available"}, ...]}
    """
    b = db.get(Branch, branch_id)
    if not b or b.tenant_id != tenant.id:
        raise NotFoundError("Branch")
    tables = payload.get("tables", [])
    if not isinstance(tables, list):
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="tables must be a list")
    b.floor_layout = {"tables": tables}
    db.commit()
    return {"branch_id": str(branch_id), "tables": tables}

