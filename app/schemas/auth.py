"""Schemas de auth: registro, login, tokens, user."""
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models.user import UserRole


class UserBase(BaseModel):
    email: EmailStr
    full_name: str = Field(..., min_length=2, max_length=120)
    phone: Optional[str] = Field(None, max_length=40)


class UserCreate(UserBase):
    """Registro de un nuevo user (puede incluir tenant inicial o no)."""
    password: str = Field(..., min_length=8, max_length=128)
    # Si se quiere crear un tenant al mismo tiempo:
    create_tenant: bool = False
    tenant_legal_name: Optional[str] = Field(None, max_length=200)
    tenant_slug: Optional[str] = Field(None, max_length=60, pattern=r"^[a-z0-9-]+$")
    tenant_industry: Optional[str] = None

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("La contraseña debe tener al menos 8 caracteres")
        if v.isdigit() or v.isalpha():
            raise ValueError("La contraseña debe combinar letras y números")
        return v


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserUpdate(BaseModel):
    full_name: Optional[str] = Field(None, min_length=2, max_length=120)
    phone: Optional[str] = Field(None, max_length=40)
    avatar_url: Optional[str] = None
    default_role: Optional[UserRole] = None


class UserOut(UserBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    is_active: bool
    is_superuser: bool
    default_role: UserRole
    avatar_url: Optional[str] = None
    created_at: datetime


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds
    user: UserOut
    current_tenant: Optional["MembershipOut"] = None


class TokenRefresh(BaseModel):
    refresh_token: str


class MembershipOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    role: UserRole
    is_owner: bool
    is_active: bool
    last_login_at: Optional[str] = None
    tenant_slug: Optional[str] = None
    tenant_display_name: Optional[str] = None


# Resolver forward ref
TokenPair.model_rebuild()
