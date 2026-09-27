"""Schemas de TenantSiteConfig (configuración del sitio por tenant)."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


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
