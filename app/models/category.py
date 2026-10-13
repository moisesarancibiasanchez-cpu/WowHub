"""Category: categoría de productos (jerárquica vía parent_id)."""
from typing import Optional

from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import GUID, BaseModel, TenantMixin


class Category(BaseModel, TenantMixin):
    __tablename__ = "categories"

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    slug: Mapped[str] = mapped_column(String(140), nullable=False, index=True)
    description: Mapped[str] = mapped_column(String(500), nullable=True)
    parent_id: Mapped[Optional[str]] = mapped_column(GUID(), nullable=True, index=True)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    icon: Mapped[str] = mapped_column(String(60), nullable=True)
    color: Mapped[str] = mapped_column(String(20), nullable=True)
