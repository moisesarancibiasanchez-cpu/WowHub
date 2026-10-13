"""Upload: registro de archivos subidos (imágenes de productos, logos, etc.)."""
from typing import Optional

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel, TenantMixin


class Upload(BaseModel, TenantMixin):
    __tablename__ = "uploads"

    # Identidad del archivo
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_filename: Mapped[str] = mapped_column(String(255), nullable=False)  # nombre en disco/bucket
    url: Mapped[str] = mapped_column(String(500), nullable=False)  # URL pública
    storage_backend: Mapped[str] = mapped_column(String(20), default="local", nullable=False)

    # Metadata
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    width: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    height: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Vinculación
    entity_type: Mapped[Optional[str]] = mapped_column(String(40), nullable=True, index=True)  # product, landing, customer
    entity_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    purpose: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)  # gallery, avatar, hero, logo
