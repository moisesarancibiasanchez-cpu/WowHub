"""Schemas de Branch."""
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class BranchBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=120)
    code: str = Field(..., min_length=1, max_length=20)
    address: str = Field(..., min_length=2, max_length=300)
    city: str = Field(..., min_length=2, max_length=80)
    region: Optional[str] = Field(None, max_length=80)
    country: str = Field("CL", min_length=2, max_length=2)
    phone: Optional[str] = Field(None, max_length=40)
    email: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    hours: dict = Field(default_factory=dict)
    is_main: bool = False
    is_active: bool = True


class BranchCreate(BranchBase):
    pass


class BranchUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=120)
    code: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    region: Optional[str] = None
    country: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    hours: Optional[dict] = None
    is_main: Optional[bool] = None
    is_active: Optional[bool] = None


class BranchOut(BranchBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    created_at: datetime
