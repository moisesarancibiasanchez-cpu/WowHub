"""SiteConfig: configuración global del sitio (singleton).

Sólo existe un registro en la tabla `site_config` con `id=1`.
Esto permite que el equipo de WowHub controle aspectos globales
(portada/tema, banners, feature flags) desde la API.
"""
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


# ID fijo para el singleton (PK entera para evitar overhead de UUID)
SITE_CONFIG_ID = 1


class SiteConfig(Base, TimestampMixin):
    __tablename__ = "site_config"

    id: Mapped[int] = mapped_column(primary_key=True, default=SITE_CONFIG_ID)

    # Tema de la portada: "dark" (actual) o "pro" (prototipo claro/limpio)
    home_theme: Mapped[str] = mapped_column(
        String(20), default="dark", nullable=False
    )

    # Flag de mantenimiento (opcional, para futuro uso)
    maintenance_mode: Mapped[bool] = mapped_column(default=False, nullable=False)
    maintenance_message: Mapped[str] = mapped_column(
        String(500), default="", nullable=False
    )

    def __repr__(self) -> str:
        return f"<SiteConfig id={self.id} theme={self.home_theme}>"
