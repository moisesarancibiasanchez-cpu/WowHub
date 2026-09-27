"""TenantSiteConfigService: configuración del sitio pública por tenant.

A diferencia de `SiteConfigService` (singleton global), este servicio opera
sobre un registro por tenant. Aísla el acceso por `tenant_id` y expone
`get_site_config_for_tenant` como helper de módulo, que es la firma que
consumen las páginas renderizadas en `app/main.py`.
"""
import logging
from typing import Any, Dict, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.tenant_site_config import TenantSiteConfig

logger = logging.getLogger("wowhub.tenant_site_config")

# Campos que el cliente puede modificar vía PATCH
_UPDATABLE_FIELDS = frozenset(
    {
        "nombre_sitio",
        "eslogan",
        "logo_url",
        "brand_color",
        "mensaje_principal",
        "imagen_hero_url",
        "bookings_enabled",
        "orders_enabled",
        "loyalty_enabled",
        "public_menu_enabled",
        "web_booking_enabled",
    }
)


class TenantSiteConfigService:
    """Capa de servicio para TenantSiteConfig (uno por tenant)."""

    def __init__(self, db: Session):
        self.db = db

    def _query(self, tenant_id: Any):
        return select(TenantSiteConfig).where(TenantSiteConfig.tenant_id == tenant_id)

    def get(self, tenant_id: Any) -> Optional[TenantSiteConfig]:
        """Devuelve la config del tenant o None si aún no existe."""
        return self.db.execute(self._query(tenant_id)).scalar_one_or_none()

    def get_or_create(self, tenant_id: Any) -> TenantSiteConfig:
        """Devuelve la config del tenant, creándola bajo demanda."""
        cfg = self.get(tenant_id)
        if cfg is not None:
            return cfg
        logger.info("Creando TenantSiteConfig para tenant=%s", tenant_id)
        cfg = TenantSiteConfig(tenant_id=tenant_id)
        self.db.add(cfg)
        self.db.commit()
        self.db.refresh(cfg)
        return cfg

    def update(self, tenant_id: Any, data: Dict[str, Any]) -> TenantSiteConfig:
        """Actualiza sólo los campos permitidos. Ignora el resto silenciosamente."""
        cfg = self.get_or_create(tenant_id)
        applied = {k: v for k, v in (data or {}).items() if k in _UPDATABLE_FIELDS}
        ignored = set(data or {}) - _UPDATABLE_FIELDS
        if ignored:
            logger.warning(
                "TenantSiteConfig.update ignoró campos no permitidos: %s", sorted(ignored)
            )
        for key, value in applied.items():
            setattr(cfg, key, value)
        self.db.commit()
        self.db.refresh(cfg)
        return cfg


def get_site_config_for_tenant(db: Session, tenant_id: Any) -> Optional[Dict[str, Any]]:
    """Helper de módulo para las páginas renderizadas en `app/main.py`.

    Devuelve un dict serializable o None. NUNCA propaga excepciones: una config
    ausente no debe impedir que se renderice la página pública.
    """
    try:
        cfg = TenantSiteConfigService(db).get(tenant_id)
        if cfg is None:
            return None
        return {
            "nombre_sitio": cfg.nombre_sitio,
            "eslogan": cfg.eslogan,
            "logo_url": cfg.logo_url,
            "brand_color": cfg.brand_color,
            "mensaje_principal": cfg.mensaje_principal,
            "imagen_hero_url": cfg.imagen_hero_url,
            "bookings_enabled": cfg.bookings_enabled,
            "orders_enabled": cfg.orders_enabled,
            "loyalty_enabled": cfg.loyalty_enabled,
            "public_menu_enabled": cfg.public_menu_enabled,
            "web_booking_enabled": cfg.web_booking_enabled,
        }
    except Exception:  # noqa: BLE001 - una config ausente no debe romper el render
        logger.exception("get_site_config_for_tenant falló para tenant=%s", tenant_id)
        return None
