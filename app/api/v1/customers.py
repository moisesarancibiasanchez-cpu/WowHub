"""Customer endpoints."""
from uuid import UUID
from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select, func
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.database import get_db
from app.deps import get_tenant_for_membership
from app.models.customer import Customer
from app.models.tenant import Tenant
from app.schemas.common import Page
from app.schemas.customer import CustomerCreate, CustomerOut, CustomerUpdate

router = APIRouter(prefix="/tenants/{tenant_id}/customers", tags=["customers"])


@router.get("", response_model=Page[CustomerOut])
def list_customers(
    tenant: Tenant = Depends(get_tenant_for_membership),
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    search: str | None = None,
):
    offset = (page - 1) * page_size
    q = select(Customer).where(Customer.tenant_id == str(tenant.id))
    if search:
        like = f"%{search.lower()}%"
        q = q.where(or_(
            func.lower(Customer.full_name).like(like),
            func.lower(Customer.email).like(like),
            Customer.phone.like(f"%{search}%"),
        ))
    total = db.execute(select(func.count()).select_from(q.subquery())).scalar() or 0
    items = list(db.execute(q.order_by(Customer.created_at.desc()).offset(offset).limit(page_size)).scalars())
    return Page.build(items, total, page, page_size)


@router.post("", response_model=CustomerOut, status_code=201)
def create_customer(
    payload: CustomerCreate,
    tenant: Tenant = Depends(get_tenant_for_membership),
    db: Session = Depends(get_db),
):
    c = Customer(**payload.model_dump(), tenant_id=str(tenant.id))
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


@router.get("/{customer_id}", response_model=CustomerOut)
def get_customer(customer_id: UUID, tenant: Tenant = Depends(get_tenant_for_membership), db: Session = Depends(get_db)):
    c = db.get(Customer, customer_id)
    if not c or c.tenant_id != tenant.id:
        raise NotFoundError("Customer")
    return c


@router.patch("/{customer_id}", response_model=CustomerOut)
def update_customer(
    customer_id: UUID,
    payload: CustomerUpdate,
    tenant: Tenant = Depends(get_tenant_for_membership),
    db: Session = Depends(get_db),
):
    c = db.get(Customer, customer_id)
    if not c or c.tenant_id != tenant.id:
        raise NotFoundError("Customer")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(c, k, v)
    db.commit()
    db.refresh(c)
    return c


@router.delete("/{customer_id}", status_code=204)
def delete_customer(customer_id: UUID, tenant: Tenant = Depends(get_tenant_for_membership), db: Session = Depends(get_db)):
    c = db.get(Customer, customer_id)
    if not c or c.tenant_id != tenant.id:
        raise NotFoundError("Customer")
    db.delete(c)
    db.commit()
