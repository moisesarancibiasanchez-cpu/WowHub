"""Schemas de Product."""
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.product import ProductStatus


class ProductBase(BaseModel):
    sku: str = Field(..., min_length=1, max_length=60)
    name: str = Field(..., min_length=2, max_length=200)
    slug: str = Field(..., min_length=2, max_length=220)
    short_description: Optional[str] = Field(None, max_length=300)
    description: Optional[str] = None
    category_id: Optional[UUID] = None
    price_cents: int = Field(..., ge=0)
    compare_at_cents: Optional[int] = Field(None, ge=0)
    cost_cents: Optional[int] = Field(None, ge=0)
    track_inventory: bool = False
    stock: int = Field(0, ge=0)
    low_stock_threshold: int = Field(5, ge=0)
    image_url: Optional[str] = None
    gallery: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    status: ProductStatus = ProductStatus.DRAFT
    is_featured: bool = False
    position: int = 0

    @field_validator("compare_at_cents")
    @classmethod
    def compare_gt_price(cls, v, info):
        price = info.data.get("price_cents")
        if v is not None and price is not None and v > 0 and v < price:
            raise ValueError("compare_at_cents debe ser >= price_cents (es un 'precio tachado')")
        return v


class ProductCreate(ProductBase):
    pass


class ProductUpdate(BaseModel):
    sku: Optional[str] = None
    name: Optional[str] = None
    slug: Optional[str] = None
    short_description: Optional[str] = None
    description: Optional[str] = None
    category_id: Optional[UUID] = None
    price_cents: Optional[int] = Field(None, ge=0)
    compare_at_cents: Optional[int] = Field(None, ge=0)
    cost_cents: Optional[int] = Field(None, ge=0)
    track_inventory: Optional[bool] = None
    stock: Optional[int] = Field(None, ge=0)
    low_stock_threshold: Optional[int] = Field(None, ge=0)
    image_url: Optional[str] = None
    gallery: Optional[list[str]] = None
    tags: Optional[list[str]] = None
    status: Optional[ProductStatus] = None
    is_featured: Optional[bool] = None
    position: Optional[int] = None


class ProductOut(ProductBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    view_count: int
    sold_count: int
    created_at: datetime
    updated_at: datetime
    # Helpers de presentación
    on_sale: bool = False
    discount_pct: Optional[int] = None


class ProductListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    sku: str
    name: str
    slug: str
    short_description: Optional[str] = None
    category_id: Optional[UUID] = None
    price_cents: int
    compare_at_cents: Optional[int] = None
    image_url: Optional[str] = None
    status: ProductStatus
    is_featured: bool
    position: int
    stock: int
    track_inventory: bool
    on_sale: bool = False
    discount_pct: Optional[int] = None
