"""Schemas de Promotion."""
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.promotion import DiscountType, PromotionType


class PromotionBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=160)
    description: Optional[str] = None
    code: Optional[str] = Field(None, max_length=40)
    promo_type: PromotionType = PromotionType.PERCENT
    discount_type: DiscountType = DiscountType.PERCENT
    discount_value: int = Field(0, ge=0)
    min_purchase_cents: int = Field(0, ge=0)
    max_discount_cents: Optional[int] = Field(None, ge=0)
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    usage_limit: Optional[int] = Field(None, ge=1)
    usage_limit_per_customer: Optional[int] = Field(None, ge=1)
    applies_to_all: bool = True
    product_ids: list[UUID] = Field(default_factory=list)
    category_ids: list[UUID] = Field(default_factory=list)
    is_active: bool = True
    is_public: bool = True
    priority: int = 0
    badge_text: Optional[str] = Field(None, max_length=40)
    color: Optional[str] = None
    image_url: Optional[str] = None


class PromotionCreate(PromotionBase):
    pass


class PromotionUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    code: Optional[str] = None
    promo_type: Optional[PromotionType] = None
    discount_type: Optional[DiscountType] = None
    discount_value: Optional[int] = Field(None, ge=0)
    min_purchase_cents: Optional[int] = Field(None, ge=0)
    max_discount_cents: Optional[int] = Field(None, ge=0)
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    usage_limit: Optional[int] = None
    usage_limit_per_customer: Optional[int] = None
    used_count: Optional[int] = Field(None, ge=0)
    applies_to_all: Optional[bool] = None
    product_ids: Optional[list[UUID]] = None
    category_ids: Optional[list[UUID]] = None
    is_active: Optional[bool] = None
    is_public: Optional[bool] = None
    priority: Optional[int] = None
    badge_text: Optional[str] = None
    color: Optional[str] = None
    image_url: Optional[str] = None


class PromotionOut(PromotionBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    used_count: int
    created_at: datetime
    is_valid_now: bool = True
