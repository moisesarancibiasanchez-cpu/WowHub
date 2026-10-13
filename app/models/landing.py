"""LandingConfig: configuración de la página pública de un tenant (su "Hub")."""
from sqlalchemy import JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel, TenantMixin


class LandingConfig(BaseModel, TenantMixin):
    __tablename__ = "landing_configs"

    # Hero
    hero_title: Mapped[str] = mapped_column(String(200), default="Bienvenido", nullable=False)
    hero_subtitle: Mapped[str] = mapped_column(String(400), nullable=True)
    hero_image_url: Mapped[str] = mapped_column(String(500), nullable=True)
    hero_cta_text: Mapped[str] = mapped_column(String(60), default="Ver catálogo", nullable=False)
    hero_cta_url: Mapped[str] = mapped_column(String(500), nullable=True)

    # Marca
    brand_color: Mapped[str] = mapped_column(String(20), default="#7c5cff", nullable=False)
    accent_color: Mapped[str] = mapped_column(String(20), default="#00d4a8", nullable=False)
    logo_url: Mapped[str] = mapped_column(String(500), nullable=True)
    favicon_url: Mapped[str] = mapped_column(String(500), nullable=True)

    # Contacto
    contact_whatsapp: Mapped[str] = mapped_column(String(40), nullable=True)
    contact_phone: Mapped[str] = mapped_column(String(40), nullable=True)
    contact_email: Mapped[str] = mapped_column(String(255), nullable=True)
    contact_address: Mapped[str] = mapped_column(String(500), nullable=True)
    social_instagram: Mapped[str] = mapped_column(String(80), nullable=True)
    social_facebook: Mapped[str] = mapped_column(String(80), nullable=True)
    social_tiktok: Mapped[str] = mapped_column(String(80), nullable=True)

    # Bloques/secciones habilitadas
    show_categories: Mapped[bool] = mapped_column(default=True, nullable=False)
    show_featured_products: Mapped[bool] = mapped_column(default=True, nullable=False)
    show_promotions: Mapped[bool] = mapped_column(default=True, nullable=False)
    show_branches: Mapped[bool] = mapped_column(default=True, nullable=False)
    show_contact: Mapped[bool] = mapped_column(default=True, nullable=False)

    # SEO
    seo_title: Mapped[str] = mapped_column(String(200), nullable=True)
    seo_description: Mapped[str] = mapped_column(String(400), nullable=True)
    seo_image_url: Mapped[str] = mapped_column(String(500), nullable=True)

    # Custom code (avanzado, sanitizado en backend)
    custom_css: Mapped[str] = mapped_column(Text, nullable=True)

    # JSON para bloques custom
    extra_blocks: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
