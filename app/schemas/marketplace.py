"""Pydantic schemas for Marketplace API (HU_45)."""
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class MarketplacePluginBase(BaseModel):
    name: str = Field(..., max_length=100)
    slug: str = Field(..., max_length=100, pattern=r"^[a-z0-9-]+$")
    description: Optional[str] = None
    version: str = "1.0.0"
    category: str = Field(..., max_length=50)
    pip_package: Optional[str] = Field(None, max_length=255)
    git_url: Optional[str] = Field(None, max_length=500)
    install_script: Optional[str] = None
    config_schema: Optional[str] = None
    is_active: bool = True
    is_featured: bool = False
    is_paid: bool = False
    price_monthly_usd: int = 0


class MarketplacePluginCreate(MarketplacePluginBase):
    pass


class MarketplacePluginUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = None
    version: Optional[str] = Field(None, max_length=20)
    category: Optional[str] = Field(None, max_length=50)
    pip_package: Optional[str] = Field(None, max_length=255)
    git_url: Optional[str] = Field(None, max_length=500)
    install_script: Optional[str] = None
    config_schema: Optional[str] = None
    is_active: Optional[bool] = None
    is_featured: Optional[bool] = None
    is_paid: Optional[bool] = None
    price_monthly_usd: Optional[int] = None


class MarketplacePluginResponse(MarketplacePluginBase):
    id: UUID
    installs: int
    rating: int
    published_by: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PluginSubscriptionBase(BaseModel):
    config: Optional[str] = None


class PluginSubscriptionCreate(PluginSubscriptionBase):
    pass


class PluginSubscriptionUpdate(BaseModel):
    config: Optional[str] = None
    status: Optional[str] = None


class PluginSubscriptionResponse(PluginSubscriptionBase):
    id: UUID
    tenant_id: UUID
    plugin_id: UUID
    status: str
    installed_at: datetime
    canceled_at: Optional[datetime] = None
    revenue_share_70_to_developer: bool
    plugin: Optional[MarketplacePluginResponse] = None

    model_config = {"from_attributes": True}


class MarketplaceListResponse(BaseModel):
    items: list[MarketplacePluginResponse]
    total: int
    page: int
    per_page: int
    pages: int
