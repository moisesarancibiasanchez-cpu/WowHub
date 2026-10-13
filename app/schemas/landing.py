"""Schemas de LandingConfig."""
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class LandingConfigUpdate(BaseModel):
    hero_title: Optional[str] = Field(None, max_length=200)
    hero_subtitle: Optional[str] = Field(None, max_length=400)
    hero_image_url: Optional[str] = None
    hero_cta_text: Optional[str] = Field(None, max_length=60)
    hero_cta_url: Optional[str] = None
    brand_color: Optional[str] = None
    accent_color: Optional[str] = None
    logo_url: Optional[str] = None
    favicon_url: Optional[str] = None
    contact_whatsapp: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_email: Optional[str] = None
    contact_address: Optional[str] = None
    social_instagram: Optional[str] = None
    social_facebook: Optional[str] = None
    social_tiktok: Optional[str] = None
    show_categories: Optional[bool] = None
    show_featured_products: Optional[bool] = None
    show_promotions: Optional[bool] = None
    show_branches: Optional[bool] = None
    show_contact: Optional[bool] = None
    seo_title: Optional[str] = None
    seo_description: Optional[str] = None
    seo_image_url: Optional[str] = None
    custom_css: Optional[str] = None
    extra_blocks: Optional[list] = None


class LandingConfigOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    hero_title: str
    hero_subtitle: Optional[str] = None
    hero_image_url: Optional[str] = None
    hero_cta_text: str
    hero_cta_url: Optional[str] = None
    brand_color: str
    accent_color: str
    logo_url: Optional[str] = None
    favicon_url: Optional[str] = None
    contact_whatsapp: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_email: Optional[str] = None
    contact_address: Optional[str] = None
    social_instagram: Optional[str] = None
    social_facebook: Optional[str] = None
    social_tiktok: Optional[str] = None
    show_categories: bool
    show_featured_products: bool
    show_promotions: bool
    show_branches: bool
    show_contact: bool
    seo_title: Optional[str] = None
    seo_description: Optional[str] = None
    seo_image_url: Optional[str] = None
    custom_css: Optional[str] = None
    extra_blocks: list
    updated_at: datetime
