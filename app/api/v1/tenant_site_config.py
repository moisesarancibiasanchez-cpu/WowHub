"""TenantSiteConfig API — V134.2.

GET /tenants/{tid}/site-config
PATCH /tenants/{tid}/site-config

Fix del bug: client llama /tenants/{tid}/site-config (no existía).
"""
import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.tenant import Tenant
from app.schemas.tenant_site_config import (
    TenantSiteConfigOut,
    TenantSiteConfigUpdate,
)
from app.services.tenant_site_config_service import TenantSiteConfigService

router = APIRouter(prefix="/tenants/{tenant_id}", tags=["SiteConfig"])
logger = logging.getLogger("wowhub.api.site_config")


def _get_tenant_or_404(db: Session, tenant_id: int) -> Tenant:
    t = db.get(Tenant, tenant_id)
    if not t:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Tenant no encontrado")
    return t


@router.get("/site-config", response_model=TenantSiteConfigOut)
def get_tenant_site_config(
    tenant_id: int,
    db: Session = Depends(get_db),
):
    """Obtiene la configuración pública del tenant.
    
    Si no existe registro, retorna defaults (crea bajo demanda).
    """
    _get_tenant_or_404(db, tenant_id)
    svc = TenantSiteConfigService(db)
    cfg = svc.get_or_create(tenant_id)
    return cfg


@router.patch("/site-config", response_model=TenantSiteConfigOut)
def update_tenant_site_config(
    tenant_id: int,
    data: TenantSiteConfigUpdate,
    db: Session = Depends(get_db),
):
    """Actualiza la configuración pública del tenant.
    
    Campos disponibles:
    - nombre_sitio, mensaje_principal, brand_color, logo_url
    - bookings_enabled, orders_enabled, loyalty_enabled, public_menu_enabled
    - web_booking_enabled
    """
    _get_tenant_or_404(db, tenant_id)
    svc = TenantSiteConfigService(db)
    cfg = svc.update(tenant_id, data.model_dump(exclude_unset=True))
    return cfg
