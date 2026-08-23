"""Product endpoints.

Fase 3 (V8): el listado y el detalle ahora incluyen los derivados
de pricing (costo real, margen, salud). Hay además un endpoint
``GET /products/{id}/pricing`` que devuelve el breakdown completo
para alimentar la calculadora del modal de edición.
"""
from uuid import UUID
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_tenant_for_membership
from app.models.product import ProductStatus
from app.models.tenant import Tenant
from app.schemas.common import Page
from app.schemas.product import ProductCreate, ProductOut, ProductUpdate, ProductListItem
from app.services.product_service import ProductService

router = APIRouter(prefix="/tenants/{tenant_id}/products", tags=["products"])


@router.get("", response_model=Page[ProductListItem])
def list_products(
    tenant: Tenant = Depends(get_tenant_for_membership),
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    search: str | None = None,
    status: ProductStatus | None = None,
    category_id: UUID | None = None,
    is_featured: bool | None = None,
    order_by: str = Query("position", pattern="^(position|name|price|created|sold)$"),
):
    return ProductService(db).list(
        tenant.id,
        page=page,
        page_size=page_size,
        search=search,
        status=status,
        category_id=category_id,
        is_featured=is_featured,
        order_by=order_by,
    )


@router.post("", response_model=ProductOut, status_code=201)
def create_product(
    payload: ProductCreate,
    tenant: Tenant = Depends(get_tenant_for_membership),
    db: Session = Depends(get_db),
):
    p = ProductService(db).create(tenant.id, payload)
    return ProductService(db).to_out(p)


@router.get("/{product_id}", response_model=ProductOut)
def get_product(
    product_id: UUID,
    tenant: Tenant = Depends(get_tenant_for_membership),
    db: Session = Depends(get_db),
    increment_view: bool = False,
):
    svc = ProductService(db)
    p = svc.get(tenant.id, product_id)
    if increment_view:
        svc.increment_view(p)
    return svc.to_out(p)


@router.get("/{product_id}/pricing", response_model=ProductOut)
def get_product_pricing(
    product_id: UUID,
    tenant: Tenant = Depends(get_tenant_for_membership),
    db: Session = Depends(get_db),
):
    """Devuelve el producto con todos los derivados de pricing (Fase 3).

    Útil para la calculadora del modal: la UI puede pedirla cada vez
    que el usuario cambia `cost_cents`, `production_time_min` o
    `price_cents` y mostrar el resultado en vivo.
    """
    svc = ProductService(db)
    p = svc.get(tenant.id, product_id)
    return svc.to_out(p)


@router.patch("/{product_id}", response_model=ProductOut)
def update_product(
    product_id: UUID,
    payload: ProductUpdate,
    tenant: Tenant = Depends(get_tenant_for_membership),
    db: Session = Depends(get_db),
):
    svc = ProductService(db)
    p = svc.get(tenant.id, product_id)
    p = svc.update(p, payload)
    return svc.to_out(p)


@router.delete("/{product_id}", status_code=204)
def delete_product(
    product_id: UUID,
    tenant: Tenant = Depends(get_tenant_for_membership),
    db: Session = Depends(get_db),
):
    svc = ProductService(db)
    p = svc.get(tenant.id, product_id)
    svc.delete(p)
