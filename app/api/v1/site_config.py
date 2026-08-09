"""Endpoints admin para SiteConfig (configuración global del sitio)."""
import logging

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.errors import ForbiddenError
from app.database import get_db
from app.deps import get_current_user
from app.models.user import User, UserRole
from app.schemas.site_config import HomeThemeUpdate, SiteConfigOut, SiteConfigUpdate
from app.services.site_config_service import SiteConfigService

logger = logging.getLogger("wowhub.api.site_config")
router = APIRouter(prefix="/admin/site-config", tags=["admin"])


def _require_platform_admin(user: User) -> None:
    """Sólo el rol OWNER/ADMIN puede tocar SiteConfig (es config global, no por tenant)."""
    role = getattr(user, "role", None) or getattr(user, "default_role", None)
    if role not in (UserRole.OWNER, UserRole.ADMIN):
        raise ForbiddenError(
            "SiteConfig requiere rol de plataforma (OWNER/ADMIN)"
        )


@router.get("", response_model=SiteConfigOut)
def get_site_config(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Devuelve la configuración global del sitio. Requiere OWNER/ADMIN."""
    _require_platform_admin(user)
    svc = SiteConfigService(db)
    return svc.get()


@router.patch("", response_model=SiteConfigOut)
def update_site_config(
    payload: SiteConfigUpdate,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Actualiza uno o varios campos de SiteConfig. Requiere OWNER/ADMIN."""
    _require_platform_admin(user)
    svc = SiteConfigService(db)
    cfg = svc.get()
    data = payload.model_dump(exclude_unset=True)
    if "home_theme" in data:
        cfg.home_theme = data["home_theme"]
    if "maintenance_mode" in data:
        cfg.maintenance_mode = bool(data["maintenance_mode"])
    if "maintenance_message" in data:
        cfg.maintenance_message = (data["maintenance_message"] or "").strip()[:500]
    db.commit()
    db.refresh(cfg)
    logger.info(
        "SiteConfig actualizado por %s — campos: %s",
        user.email, list(data.keys()),
    )
    return cfg


@router.put("/home-theme", response_model=SiteConfigOut)
def set_home_theme(
    payload: HomeThemeUpdate,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Atajo: cambia sólo el tema de la portada ("dark" | "pro")."""
    _require_platform_admin(user)
    svc = SiteConfigService(db)
    cfg = svc.set_theme(payload.theme)
    logger.info("Home theme cambiado a '%s' por %s", cfg.home_theme, user.email)
    return cfg
