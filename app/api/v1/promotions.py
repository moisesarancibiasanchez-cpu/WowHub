"""Promotion endpoints."""
from datetime import datetime, timezone
from uuid import UUID
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.database import get_db
from app.deps import get_tenant_for_membership
from app.models.promotion import Promotion
from app.models.tenant import Tenant
from app.schemas.promotion import PromotionCreate, PromotionOut, PromotionUpdate

router = APIRouter(prefix="/tenants/{tenant_id}/promotions", tags=["promotions"])


def _is_valid_now(p: Promotion) -> bool:
    if not p.is_active:
        return False
    now = datetime.now(timezone.utc)
    if p.starts_at and p.starts_at.tzinfo is None:
        p_starts = p.starts_at.replace(tzinfo=timezone.utc)
    else:
        p_starts = p.starts_at
    if p.ends_at and p.ends_at.tzinfo is None:
        p_ends = p.ends_at.replace(tzinfo=timezone.utc)
    else:
        p_ends = p.ends_at
    if p_starts and p_starts > now:
        return False
    if p_ends and p_ends < now:
        return False
    if p.usage_limit and p.used_count >= p.usage_limit:
        return False
    return True


@router.get("", response_model=list[PromotionOut])
def list_promotions(
    tenant: Tenant = Depends(get_tenant_for_membership),
    db: Session = Depends(get_db),
    is_active: bool | None = None,
    is_public: bool | None = None,
):
    q = select(Promotion).where(Promotion.tenant_id == str(tenant.id))
    if is_active is not None:
        q = q.where(Promotion.is_active == is_active)
    if is_public is not None:
        q = q.where(Promotion.is_public == is_public)
    q = q.order_by(Promotion.priority.desc(), Promotion.created_at.desc())
    items = []
    for p in db.execute(q).scalars():
        out = PromotionOut.model_validate(p)
        out.is_valid_now = _is_valid_now(p)
        items.append(out)
    return items


@router.post("", response_model=PromotionOut, status_code=201)
def create_promotion(
    payload: PromotionCreate,
    tenant: Tenant = Depends(get_tenant_for_membership),
    db: Session = Depends(get_db),
):
    data = payload.model_dump()
    # Convertir UUIDs a str
    data["product_ids"] = [str(x) for x in data.get("product_ids", [])]
    data["category_ids"] = [str(x) for x in data.get("category_ids", [])]
    p = Promotion(**data, tenant_id=str(tenant.id))
    db.add(p)
    db.commit()
    db.refresh(p)
    out = PromotionOut.model_validate(p)
    out.is_valid_now = _is_valid_now(p)
    return out


@router.get("/{promotion_id}", response_model=PromotionOut)
def get_promotion(promotion_id: UUID, tenant: Tenant = Depends(get_tenant_for_membership), db: Session = Depends(get_db)):
    p = db.get(Promotion, promotion_id)
    if not p or p.tenant_id != tenant.id:
        raise NotFoundError("Promotion")
    out = PromotionOut.model_validate(p)
    out.is_valid_now = _is_valid_now(p)
    return out


@router.patch("/{promotion_id}", response_model=PromotionOut)
def update_promotion(
    promotion_id: UUID,
    payload: PromotionUpdate,
    tenant: Tenant = Depends(get_tenant_for_membership),
    db: Session = Depends(get_db),
):
    p = db.get(Promotion, promotion_id)
    if not p or p.tenant_id != tenant.id:
        raise NotFoundError("Promotion")
    data = payload.model_dump(exclude_unset=True)
    if "product_ids" in data:
        data["product_ids"] = [str(x) for x in data["product_ids"]]
    if "category_ids" in data:
        data["category_ids"] = [str(x) for x in data["category_ids"]]
    for k, v in data.items():
        setattr(p, k, v)
    db.commit()
    db.refresh(p)
    out = PromotionOut.model_validate(p)
    out.is_valid_now = _is_valid_now(p)
    return out


@router.delete("/{promotion_id}", status_code=204)
def delete_promotion(promotion_id: UUID, tenant: Tenant = Depends(get_tenant_for_membership), db: Session = Depends(get_db)):
    p = db.get(Promotion, promotion_id)
    if not p or p.tenant_id != tenant.id:
        raise NotFoundError("Promotion")
    db.delete(p)
    db.commit()
