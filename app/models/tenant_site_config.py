"""TenantSiteConfig: configuración del sitio pública por tenant.

Cada tenant tiene su propia configuración (nombre, marca, colores, toggles de
visibilidad). Es una tabla DISTINTA de `site_config`, que es el singleton global
controlado por el equipo de WowHub (tema de portada, mantenimiento).

El nombre de tabla es `tenant_site_configs` (plural) a propósito: la tabla
global es `site_config` (singular). Una versión anterior de este modelo usó
`site_configs` y colisionó con el índice de la global.
"""
from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel, GUID


class TenantSiteConfig(BaseModel):
    """Configuración pública/sitio de un tenant (branding + feature toggles).

    No usa `TenantMixin` a propósito: la relación es 1:1 con el tenant y
    necesitamos `unique=True`, mientras `TenantMixin.tenant_id` es un
    `@declared_attr` compartido por entidades 1:N. Redeclararlo aquí
    entraría en conflicto con el mixin.
    """

    __tablename__ = "tenant_site_configs"

    tenant_id: Mapped[str] = mapped_column(
        GUID(),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    # Identidad del sitio
    nombre_sitio: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    eslogan: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    logo_url: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    brand_color: Mapped[str] = mapped_column(String(20), default="#0f172a", nullable=False)

    # Contenido
    mensaje_principal: Mapped[str] = mapped_column(Text, default="", nullable=False)
    imagen_hero_url: Mapped[str] = mapped_column(String(500), default="", nullable=False)

    # Toggles de visibilidad por sección
    bookings_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    orders_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    loyalty_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    public_menu_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    web_booking_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<TenantSiteConfig tenant_id={self.tenant_id} nombre={self.nombre_sitio!r}>"
