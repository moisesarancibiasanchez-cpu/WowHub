"""TenantSiteConfigService: gestión de site_config por tenant (sync)."""
import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.tenant_site_config import TenantSiteConfig

logger = logging.getLogger("wowhub.site_config")


class TenantSiteConfigService:
    """Servicio para la configuración pública de cada tenant."""

    def __init__(self, db: Session):
        self.db = db

    def get_by_tenant(self, tenant_id: int) -> Optional[TenantSiteConfig]:
        """Obtiene el registro de un tenant o None si no existe."""
        return self.db.execute(
            select(TenantSiteConfig).where(TenantSiteConfig.tenant_id == tenant_id)
        ).scalar_one_or_none()

    def get_or_create(self, tenant_id: int) -> TenantSiteConfig:
        """Obtiene el registro del tenant o lo crea con defaults."""
        existing = self.get_by_tenant(tenant_id)
        if existing:
            return existing
        cfg = TenantSiteConfig(tenant_id=tenant_id)
        self.db.add(cfg)
        self.db.commit()
        self.db.refresh(cfg)
        logger.info("Created TenantSiteConfig for tenant %s", tenant_id)
        return cfg

    def update(self, tenant_id: int, data: dict) -> TenantSiteConfig:
        """Actualiza campos del site_config del tenant (exclude_unset=True semantics)."""
        cfg = self.get_or_create(tenant_id)
        for key, value in data.items():
            if hasattr(cfg, key):
                setattr(cfg, key, value)
        self.db.commit()
        self.db.refresh(cfg)
        logger.info("Updated TenantSiteConfig for tenant %s: %s", tenant_id, list(data.keys()))
        return cfg


# Función de conveniencia para usar en main.py (sin instanciar)
def get_site_config_for_tenant(db: Session, tenant_id: int) -> dict:
    """Retorna un dict con los valores de site_config para un tenant.
    
    Si no existe registro, retorna defaults.
    """
    svc = TenantSiteConfigService(db)
    cfg = svc.get_by_tenant(tenant_id)
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
