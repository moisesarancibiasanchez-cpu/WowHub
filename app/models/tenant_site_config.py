"""TenantSiteConfig: configuración pública por tenant (V134.2).
 
Cada tenant tiene su propio registro en site_configs (one-to-one).
Controla branding, módulos visibles y toggles de la página pública.
"""
from datetime import datetime

from sqlalchemy import Boolean, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class TenantSiteConfig(Base):
    """Configuración pública por tenant.
 
    Un registro por tenant (unique constraint en tenant_id).
    Se crea bajo demanda cuando el tenant accede a su site_config.
    """
    __tablename__ = "site_configs"
    __table_args__ = (
        Index("ix_site_configs_tenant_id", "tenant_id", unique=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(unique=True, nullable=False, index=True)

    # Branding
    nombre_sitio: Mapped[str | None] = mapped_column(String(255), nullable=True)
    mensaje_principal: Mapped[str | None] = mapped_column(Text, nullable=True)
    brand_color: Mapped[str | None] = mapped_column(String(7), nullable=True)   # hex: "#7c5cff"
    logo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Módulos visibles en landing pública
    bookings_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    orders_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    loyalty_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    public_menu_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Toggle fino: permite reservas online (independiente de bookings_enabled)
    web_booking_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    def __repr__(self) -> str:
        return f"<TenantSiteConfig tenant_id={self.tenant_id} nombre={self.nombre_sitio!r}>"
