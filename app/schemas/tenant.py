"""Schemas de Tenant y Membership."""
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator
import re

from app.models.tenant import Industry, TenantPlan, TenantStatus
from app.models.user import UserRole


class TenantBase(BaseModel):
    legal_name: str = Field(..., min_length=2, max_length=200)
    display_name: str = Field(..., min_length=2, max_length=120)
    industry: Industry = Industry.OTHER
    country: str = Field("CL", min_length=2, max_length=2)
    locale: str = "es-CL"
    currency: str = "CLP"
    timezone: str = "America/Santiago"


class TenantCreate(TenantBase):
    slug: str = Field(..., min_length=3, max_length=60)

    @field_validator("slug")
    @classmethod
    def slug_format(cls, v: str) -> str:
        v = v.strip()
        if not re.match(r"^[a-z0-9](?:[a-z0-9-]{1,58}[a-z0-9])?$", v):
            raise ValueError("slug debe ser kebab-case (a-z, 0-9, -); no se permiten mayúsculas")
        return v


class TenantUpdate(BaseModel):
    legal_name: Optional[str] = Field(None, min_length=2, max_length=200)
    display_name: Optional[str] = Field(None, min_length=2, max_length=120)
    industry: Optional[Industry] = None
    plan: Optional[TenantPlan] = None
    status: Optional[TenantStatus] = None
    country: Optional[str] = None
    locale: Optional[str] = None
    currency: Optional[str] = None
    timezone: Optional[str] = None
    settings: Optional[dict] = None
    is_active: Optional[bool] = None


class TenantOut(TenantBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    slug: str
    plan: TenantPlan
    status: TenantStatus
    wow_score: int
    health_score: int
    active_branches: int
    is_active: bool
    settings: dict
    created_at: datetime


class TenantMembershipCreate(BaseModel):
    email: Optional[EmailStr] = None
    user_id: Optional[UUID] = None
    role: UserRole = UserRole.STAFF

    @field_validator("role")
    @classmethod
    def validate_role_for_invite(cls, v: UserRole) -> UserRole:
        if v == UserRole.OWNER:
            raise ValueError("No se puede asignar OWNER por invitación (usar transfer-ownership)")
        return v


class TenantMembershipUpdate(BaseModel):
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None


class TenantMembershipOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    tenant_id: UUID
    role: UserRole
    is_owner: bool
    is_active: bool
    last_login_at: Optional[str] = None
    user: Optional["UserMini"] = None


class UserMini(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    full_name: str


TenantMembershipOut.model_rebuild()
