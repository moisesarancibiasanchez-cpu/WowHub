"""Category endpoints."""
from uuid import UUID
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

# HU_38 — RBAC granular con Casbin. Ver app/api/v1/products.py para
# detalles del patrón aplicado (decorator + membership explícito).
from app.core.errors import NotFoundError
from app.core.security import requires_permission
from app.database import get_db
from app.deps import get_current_membership, get_tenant_for_membership
from app.models.category import Category
from app.models.tenant import Tenant
from app.models.tenant import TenantMembership
from app.schemas.category import CategoryCreate, CategoryOut, CategoryUpdate

router = APIRouter(prefix="/tenants/{tenant_id}/categories", tags=["categories"])


def _get(tenant_id: UUID, cat_id: UUID, db: Session) -> Category:
    c = db.get(Category, cat_id)
    if not c or c.tenant_id != tenant_id:
        raise NotFoundError("Category")
    return c


@router.get("", response_model=list[CategoryOut])
def list_categories(tenant: Tenant = Depends(get_tenant_for_membership), db: Session = Depends(get_db)):
    return list(db.execute(
        select(Category)
        .where(Category.tenant_id == str(tenant.id))
        .order_by(Category.position, Category.name)
    ).scalars())


@router.post("", response_model=CategoryOut, status_code=201)
@requires_permission("category", "write")
def create_category(
    payload: CategoryCreate,
    tenant: Tenant = Depends(get_tenant_for_membership),
    db: Session = Depends(get_db),
    # HU_38 — ver create_product en products.py. Patrón de inyección.
    membership: TenantMembership = Depends(get_current_membership),
):
    """HU_38 — crear categoría requiere ``category.write``."""
    data = payload.model_dump()
    if data.get("parent_id"):
        data["parent_id"] = str(data["parent_id"])
    c = Category(**data, tenant_id=str(tenant.id))
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


@router.get("/{category_id}", response_model=CategoryOut)
def get_category(category_id: UUID, tenant: Tenant = Depends(get_tenant_for_membership), db: Session = Depends(get_db)):
    return _get(tenant.id, category_id, db)


@router.patch("/{category_id}", response_model=CategoryOut)
@requires_permission("category", "write")
def update_category(
    category_id: UUID,
    payload: CategoryUpdate,
    tenant: Tenant = Depends(get_tenant_for_membership),
    db: Session = Depends(get_db),
    # HU_38 — ver create_product en products.py.
    membership: TenantMembership = Depends(get_current_membership),
):
    """HU_38 — actualizar categoría requiere ``category.write``."""
    c = _get(tenant.id, category_id, db)
    data = payload.model_dump(exclude_unset=True)
    if "parent_id" in data and data["parent_id"] is not None:
        data["parent_id"] = str(data["parent_id"])
    for k, v in data.items():
        setattr(c, k, v)
    db.commit()
    db.refresh(c)
    return c


@router.delete("/{category_id}", status_code=204)
@requires_permission("category", "delete")
def delete_category(category_id: UUID, tenant: Tenant = Depends(get_tenant_for_membership), db: Session = Depends(get_db), membership: TenantMembership = Depends(get_current_membership)):
    """HU_38 — eliminar categoría requiere ``category.delete``.

    Roles permitidos (matriz default seed): OWNER, ADMIN.
    STAFF/VIEWER quedan fuera (sin policy de delete).
    """
    c = _get(tenant.id, category_id, db)
    db.delete(c)
    db.commit()
