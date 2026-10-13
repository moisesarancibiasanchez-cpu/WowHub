"""HU_29 — Router de tiers de fidelidad.

Endpoints:
  POST   /tenants/{tid}/loyalty/campaigns/{cid}/tiers   crear tier
  GET    /tenants/{tid}/loyalty/campaigns/{cid}/tiers   listar tiers
  PATCH  /tenants/{tid}/loyalty/tiers/{tid}             actualizar tier
  DELETE /tenants/{tid}/loyalty/tiers/{tid}             eliminar tier
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_membership, get_current_user
from app.models.user import User
from app.schemas.loyalty import (
    LoyaltyTierCreate, LoyaltyTierOut, LoyaltyTierUpdate,
)
from app.services.loyalty_tier_service import LoyaltyTierService

router = APIRouter(
    prefix="/tenants/{tenant_id}/loyalty",
    tags=["loyalty-tiers"],
)


def _svc(db: Session, tenant_id: UUID) -> LoyaltyTierService:
    return LoyaltyTierService(db, tenant_id=str(tenant_id))


@router.post(
    "/campaigns/{campaign_id}/tiers",
    response_model=LoyaltyTierOut,
    status_code=status.HTTP_201_CREATED,
)
def create_tier(
    tenant_id: UUID,
    campaign_id: UUID,
    payload: LoyaltyTierCreate,
    user: User = Depends(get_current_user),
    membership=Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    """Crea un tier (Bronce, Plata, Oro, Platino, etc.) en una campaña."""
    # Sobrescribimos el campaign_id del payload con el de la URL
    # (defensa en profundidad: la URL es la fuente de verdad).
    data = payload.model_dump()
    data["campaign_id"] = campaign_id
    new_payload = LoyaltyTierCreate(**data)
    return _svc(db, tenant_id).create_tier(new_payload)


@router.get(
    "/campaigns/{campaign_id}/tiers",
    response_model=list[LoyaltyTierOut],
)
def list_tiers(
    tenant_id: UUID,
    campaign_id: UUID,
    user: User = Depends(get_current_user),
    membership=Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    return _svc(db, tenant_id).list_tiers(campaign_id)


@router.patch(
    "/tiers/{tier_id}",
    response_model=LoyaltyTierOut,
)
def update_tier(
    tenant_id: UUID,
    tier_id: UUID,
    payload: LoyaltyTierUpdate,
    user: User = Depends(get_current_user),
    membership=Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    return _svc(db, tenant_id).update_tier(tier_id, payload)


@router.delete(
    "/tiers/{tier_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_tier(
    tenant_id: UUID,
    tier_id: UUID,
    user: User = Depends(get_current_user),
    membership=Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    """Elimina el tier y limpia las referencias en customer_passes."""
    _svc(db, tenant_id).delete_tier(tier_id)
    return None
