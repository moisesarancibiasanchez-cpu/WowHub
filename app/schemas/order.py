"""Schemas de Order."""
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.order import OrderStatus


class OrderItemIn(BaseModel):
    product_id: UUID
    quantity: int = Field(1, ge=1, le=999)
    options: dict = Field(default_factory=dict)


class OrderCreate(BaseModel):
    customer_id: Optional[UUID] = None
    branch_id: Optional[UUID] = None
    customer_name: Optional[str] = Field(None, max_length=200)
    customer_phone: Optional[str] = Field(None, max_length=40)
    customer_email: Optional[str] = None
    shipping_address: Optional[str] = Field(None, max_length=500)
    notes: Optional[str] = None
    source: str = Field("web", max_length=40)
    qr_code_id: Optional[UUID] = None
    promotion_codes: list[str] = Field(default_factory=list)
    items: list[OrderItemIn] = Field(..., min_length=1)

    @field_validator("items")
    @classmethod
    def items_not_empty(cls, v):
        if not v:
            raise ValueError("El pedido debe tener al menos un item")
        return v


class OrderTransition(BaseModel):
    new_status: OrderStatus
    notes: Optional[str] = None


class OrderItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    product_id: Optional[UUID] = None
    product_name: str
    product_sku: Optional[str] = None
    product_image: Optional[str] = None
    quantity: int
    unit_price_cents: int
    total_cents: int
    options: dict


class OrderListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    number: str
    status: OrderStatus
    customer_name: Optional[str] = None
    customer_email: Optional[str] = None
    total_cents: int
    currency: str
    item_count: int = 0
    source: str
    created_at: datetime


class OrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    number: str
    status: OrderStatus
    customer_id: Optional[UUID] = None
    branch_id: Optional[UUID] = None
    subtotal_cents: int
    discount_cents: int
    shipping_cents: int
    tax_cents: int
    total_cents: int
    currency: str
    promotion_ids: list[str] = Field(default_factory=list)
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    customer_email: Optional[str] = None
    shipping_address: Optional[str] = None
    notes: Optional[str] = None
    source: str
    qr_code_id: Optional[UUID] = None
    items: list[OrderItemOut]
    created_at: datetime
    updated_at: datetime
