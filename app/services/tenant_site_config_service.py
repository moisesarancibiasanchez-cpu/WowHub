"""TenantSiteConfigService — usa el modelo existente SiteConfig (V134.2).

El modelo SiteConfig ya existe en app.models.site_config.
Esta servicio lo usa para gestión per-tenant del site_config público.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.site_config import SiteConfig  # noqa: F401


def get_site_config_for_tenant(db: Session, tenant_id: int) -> dict:
    """Retorna un dict con los valores de site_config para un tenant.

    Si no existe registro, retorna defaults.
    Usa la tabla existente site_configs — no crea tabla nueva.
    """
    cfg = db.execute(
        select(SiteConfig).where(SiteConfig.tenant_id == tenant_id)
    ).scalar_one_or_none()

    if not cfg:
        return {
            "nombre_sitio": None,
            "mensaje_principal": None,
            "brand_color": "#7c5cff",
            "logo_url": None,
            "bookings_enabled": True,
            "orders_enabled": True,
            "loyalty_enabled": True,
            "public_menu_enabled": True,
            "web_booking_enabled": True,
        }

    return {
        "nombre_sitio": cfg.nombre_sitio,
        "mensaje_principal": cfg.mensaje_principal,
        "brand_color": cfg.brand_color or "#7c5cff",
        "logo_url": cfg.logo_url,
        "bookings_enabled": cfg.bookings_enabled,
        "orders_enabled": cfg.orders_enabled,
        "loyalty_enabled": cfg.loyalty_enabled,
        "public_menu_enabled": cfg.public_menu_enabled,
        "web_booking_enabled": cfg.web_booking_enabled,
    }


def update_site_config_for_tenant(db: Session, tenant_id: int, data: dict) -> SiteConfig:
    """Crea o actualiza el site_config de un tenant."""
    cfg = db.execute(
        select(SiteConfig).where(SiteConfig.tenant_id == tenant_id)
    ).scalar_one_or_none()

    if not cfg:
        cfg = SiteConfig(tenant_id=tenant_id)
        db.add(cfg)

    for key, value in data.items():
        if hasattr(cfg, key):
            setattr(cfg, key, value)

    db.commit()
    db.refresh(cfg)
    return cfg
