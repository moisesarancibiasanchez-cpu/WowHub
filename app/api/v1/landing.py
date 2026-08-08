"""LandingConfig endpoints."""
from uuid import UUID
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.database import get_db
from app.deps import get_tenant_for_membership
from app.models.landing import LandingConfig
from app.models.tenant import Tenant
from app.schemas.landing import LandingConfigOut, LandingConfigUpdate

router = APIRouter(prefix="/tenants/{tenant_id}/landing", tags=["landing"])


def _get_or_create(tenant: Tenant, db: Session) -> LandingConfig:
    cfg = db.query(LandingConfig).filter(LandingConfig.tenant_id == str(tenant.id)).first()
    if not cfg:
        cfg = LandingConfig(tenant_id=str(tenant.id))
        db.add(cfg)
        db.commit()
        db.refresh(cfg)
    return cfg


@router.get("", response_model=LandingConfigOut)
def get_landing(tenant: Tenant = Depends(get_tenant_for_membership), db: Session = Depends(get_db)):
    return _get_or_create(tenant, db)


@router.patch("", response_model=LandingConfigOut)
def update_landing(
    payload: LandingConfigUpdate,
    tenant: Tenant = Depends(get_tenant_for_membership),
    db: Session = Depends(get_db),
):
    cfg = _get_or_create(tenant, db)
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(cfg, k, v)
    db.commit()
    db.refresh(cfg)
    return cfg
