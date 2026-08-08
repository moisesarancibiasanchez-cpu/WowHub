"""Schemas de Customer."""
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class CustomerBase(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=160)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(None, max_length=40)
    address: Optional[str] = Field(None, max_length=500)
    city: Optional[str] = Field(None, max_length=80)
    notes: Optional[str] = Field(None, max_length=1000)
    tags: list[str] = Field(default_factory=list)
    accepts_marketing: bool = True
    is_active: bool = True


class CustomerCreate(CustomerBase):
    pass


class CustomerUpdate(BaseModel):
    full_name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    notes: Optional[str] = None
    tags: Optional[list[str]] = None
    accepts_marketing: Optional[bool] = None
    is_active: Optional[bool] = None


class CustomerOut(CustomerBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    total_orders: int
    total_spent_cents: int
    points: int
    last_order_at: Optional[str] = None
    created_at: datetime
