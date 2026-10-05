"""Sites API — HU_42.

GET  /api/v1/sites  — devuelve la site-config del tenant autenticado.
PUT  /api/v1/sites  — actualiza la site-config del tenant autenticado.

El tenant se resuelve desde el JWT vía get_current_membership (deps.py),
no desde un path param. Esto permite la ruta plana /sites sin嵌.
"""
import logging
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_membership
from app.models.tenant import TenantMembership
from app.schemas.tenant_site_config import (
    TenantSiteConfigOut,
    TenantSiteConfigUpdate,
)
from app.services.tenant_site_config_service import TenantSiteConfigService

router = APIRouter(prefix="/sites", tags=["Sites"])
logger = logging.getLogger("wowhub.api.sites")


@router.get("", response_model=TenantSiteConfigOut)
def get_my_site_config(
    membership: TenantMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    """Devuelve la configuración del sitio público del tenant autenticado.

    Crea el registro bajo demanda si no existe (nunca retorna 404).
    Requiere: token JWT con membresía activa.
    """
    tenant_id = UUID(str(membership.tenant_id))
    svc = TenantSiteConfigService(db)
    cfg = svc.get_or_create(tenant_id)
    return cfg


@router.put("", response_model=TenantSiteConfigOut)
def update_my_site_config(
    data: TenantSiteConfigUpdate,
    membership: TenantMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    """Actualiza la configuración del sitio público del tenant autenticado.

    Campos disponibles:
    - nombre_sitio, eslogan, logo_url, brand_color
    - mensaje_principal, imagen_hero_url
    - bookings_enabled, orders_enabled, loyalty_enabled
    - public_menu_enabled, web_booking_enabled
    - social_links, blocks (HU_42 — drag&drop section builder)

    Requiere: token JWT con membresía activa.
    """
    tenant_id = UUID(str(membership.tenant_id))
    svc = TenantSiteConfigService(db)
    cfg = svc.update(tenant_id, data.model_dump(exclude_unset=True))
    return cfg
