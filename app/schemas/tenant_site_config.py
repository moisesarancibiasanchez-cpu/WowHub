"""Schemas de TenantSiteConfig (configuración del sitio por tenant)."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


# ── Sub-schemas ────────────────────────────────────────────────────────
class SocialLink(BaseModel):
    """Link a una red social del tenant."""
    platform: str = Field(..., max_length=30, description="Plataforma: facebook, instagram, twitter, tiktok, whatsapp, web.")
    url: str = Field(..., max_length=500)
    label: Optional[str] = Field(None, max_length=60)


class SiteBlock(BaseModel):
    """Bloque custom del sitio (drag&drop section).

    Cada bloque representa una sección en la landing pública. El orden
    se controla con ``position`` (entero no-negativo). El frontend debe
    ordenar por ``position`` ASC y renderizar secuencialmente.
    """
    id: Optional[str] = Field(None, max_length=40, description="ID opcional (UUID-like); autogenerado si falta.")
    type: str = Field(..., max_length=30, description="Tipo: hero, features, menu, gallery, cta, testimonials, custom_html, divider.")
    title: str = Field("", max_length=120)
    content: str = Field("", max_length=8000, description="Contenido HTML/Markdown/texto según el tipo.")
    image_url: Optional[str] = Field(None, max_length=500)
    position: int = Field(0, ge=0, description="Orden en la página (menor = primero).")
    enabled: bool = Field(True)
    config: dict = Field(default_factory=dict, description="Config adicional por tipo (e.g. {\"columns\": 3}).")


# ── Out / Update ───────────────────────────────────────────────────────
class TenantSiteConfigOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    tenant_id: str
    nombre_sitio: str
    eslogan: str
    logo_url: str
    brand_color: str
    mensaje_principal: str
    imagen_hero_url: str
    bookings_enabled: bool
    orders_enabled: bool
    loyalty_enabled: bool
    public_menu_enabled: bool
    web_booking_enabled: bool
    # NUEVO (HU_42 drag&drop):
    social_links: list[SocialLink] = Field(default_factory=list)
    blocks: list[SiteBlock] = Field(default_factory=list)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class TenantSiteConfigUpdate(BaseModel):
    """Actualización parcial de la configuración del sitio. Todos opcionales."""

    nombre_sitio: Optional[str] = Field(None, max_length=120)
    eslogan: Optional[str] = Field(None, max_length=200)
    logo_url: Optional[str] = Field(None, max_length=500)
    brand_color: Optional[str] = Field(None, max_length=20)
    mensaje_principal: Optional[str] = None
    imagen_hero_url: Optional[str] = Field(None, max_length=500)
    bookings_enabled: Optional[bool] = None
    orders_enabled: Optional[bool] = None
    loyalty_enabled: Optional[bool] = None
    public_menu_enabled: Optional[bool] = None
    web_booking_enabled: Optional[bool] = None
    # NUEVO (HU_42 drag&drop):
    social_links: Optional[list[SocialLink]] = None
    blocks: Optional[list[SiteBlock]] = None