"""SiteConfigService: gestiona la configuración global del sitio (singleton)."""
import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.models.site_config import SITE_CONFIG_ID, SiteConfig

logger = logging.getLogger("wowhub.site_config")


# Temas permitidos para la portada
VALID_THEMES = ("dark", "pro")
DEFAULT_THEME = "dark"


def _normalize_theme(value: Optional[str]) -> str:
    """Devuelve un theme válido o el default si el valor no es reconocido."""
    if not value:
        return DEFAULT_THEME
    v = value.strip().lower()
    return v if v in VALID_THEMES else DEFAULT_THEME


class SiteConfigService:
    """Capa de servicio para SiteConfig (singleton)."""

    def __init__(self, db: Session):
        self.db = db

    def get(self) -> SiteConfig:
        """Obtiene el singleton. Si no existe, lo crea con valores por defecto."""
        cfg = self.db.get(SiteConfig, SITE_CONFIG_ID)
        if not cfg:
            logger.info("Creando SiteConfig singleton (id=%s)", SITE_CONFIG_ID)
            cfg = SiteConfig(id=SITE_CONFIG_ID, home_theme=DEFAULT_THEME)
            self.db.add(cfg)
            self.db.commit()
            self.db.refresh(cfg)
        return cfg

    def get_or_create(self) -> SiteConfig:
        return self.get()

    def get_theme(self) -> str:
        return self.get().home_theme

    def set_theme(self, theme: str) -> SiteConfig:
        """Cambia el tema de la portada. Devuelve la entidad actualizada."""
        cfg = self.get()
        cfg.home_theme = _normalize_theme(theme)
        self.db.commit()
        self.db.refresh(cfg)
        logger.info("Home theme cambiado a: %s", cfg.home_theme)
        return cfg

    def set_maintenance(self, enabled: bool, message: str = "") -> SiteConfig:
        cfg = self.get()
        cfg.maintenance_mode = bool(enabled)
        cfg.maintenance_message = (message or "").strip()[:500]
        self.db.commit()
        self.db.refresh(cfg)
        return cfg
