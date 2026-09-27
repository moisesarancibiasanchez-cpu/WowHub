"""Schemas de TenantSiteConfig (V134.2)."""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class TenantSiteConfigBase(BaseModel):
    nombre_sitio: Optional[str] = Field(None, max_length=255)
    mensaje_principal: Optional[str] = None
    brand_color: Optional[str] = Field(None, pattern=r"^#[0-9a-fA-F]{6}$")
    logo_url: Optional[str] = Field(None, max_length=500)
    bookings_enabled: bool = True
    orders_enabled: bool = True
    loyalty_enabled: bool = True
    public_menu_enabled: bool = True
    web_booking_enabled: bool = True


class TenantSiteConfigUpdate(TenantSiteConfigBase):
    """Campos opcionales para PATCH — todos opcionales."""
    model_config = ConfigDict(extra="ignore")


class TenantSiteConfigOut(TenantSiteConfigBase):
    """Respuesta completa de site_config — incluye derivados."""
    model_config = ConfigDict(from_attributes=True)
    id: int
    tenant_id: int
    created_at: datetime
    updated_at: datetime
