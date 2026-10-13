"""Branch Products API — inventario multi-sucursal."""
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError
from app.database import get_db
from app.deps import get_current_membership
from app.models.branch import Branch
from app.models.branch_product import BranchProduct
from app.models.product import Product
from app.models.tenant import TenantMembership

router = APIRouter(prefix="/tenants/{tenant_id}/branch-products", tags=["branch-products"])


class BranchProductIn(BaseModel):
    branch_id: UUID
    product_id: UUID
    stock: int = 0
    low_stock_threshold: int = 5


class BranchProductUpdate(BaseModel):
    stock: Optional[int] = None
    low_stock_threshold: Optional[int] = None


@router.get("")
def list_branch_products(
    tenant_id: UUID,
    branch_id: Optional[UUID] = Query(None),
    membership: TenantMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    q = select(BranchProduct).where(BranchProduct.tenant_id == str(tenant_id))
    if branch_id:
        q = q.where(BranchProduct.branch_id == str(branch_id))
    q = q.order_by(BranchProduct.created_at.desc())
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


@router.post("", status_code=201)
def create_branch_product(
    tenant_id: UUID,
    payload: BranchProductIn,
    membership: TenantMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    branch = db.get(Branch, payload.branch_id)
    if not branch or branch.tenant_id != tenant_id:
        raise NotFoundError("Sucursal")
    product = db.get(Product, payload.product_id)
    if not product or product.tenant_id != tenant_id:
        raise NotFoundError("Producto")
    existing = db.execute(
        select(BranchProduct).where(
            BranchProduct.branch_id == str(payload.branch_id),
            BranchProduct.product_id == str(payload.product_id),
        )
    ).scalar_one_or_none()
    if existing:
        raise ConflictError("Ya existe inventario para este producto en esta sucursal")
    bp = BranchProduct(
        tenant_id=str(tenant_id),
        branch_id=str(payload.branch_id),
        product_id=str(payload.product_id),
        stock=payload.stock,
        low_stock_threshold=payload.low_stock_threshold,
    )
    db.add(bp)
    db.commit()
    db.refresh(bp)
    return {
        "id": str(bp.id), "branch_id": bp.branch_id, "product_id": bp.product_id,
        "stock": bp.stock, "low_stock_threshold": bp.low_stock_threshold,
    }


@router.patch("/{bp_id}")
def update_branch_product(
    tenant_id: UUID,
    bp_id: UUID,
    payload: BranchProductUpdate,
    membership: TenantMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    bp = db.get(BranchProduct, bp_id)
    if not bp or bp.tenant_id != tenant_id:
        raise NotFoundError("Inventario")
    if payload.stock is not None:
        bp.stock = payload.stock
    if payload.low_stock_threshold is not None:
        bp.low_stock_threshold = payload.low_stock_threshold
    db.commit()
    db.refresh(bp)
    return {
        "id": str(bp.id), "branch_id": bp.branch_id, "product_id": bp.product_id,
        "stock": bp.stock, "low_stock_threshold": bp.low_stock_threshold,
    }


@router.delete("/{bp_id}", status_code=204)
def delete_branch_product(
    tenant_id: UUID,
    bp_id: UUID,
    membership: TenantMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    bp = db.get(BranchProduct, bp_id)
    if not bp or bp.tenant_id != tenant_id:
        raise NotFoundError("Inventario")
    db.delete(bp)
    db.commit()
