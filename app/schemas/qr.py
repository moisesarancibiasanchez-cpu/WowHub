"""Schemas de QR."""
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.qr import QrTarget


class QrCodeBase(BaseModel):
    label: str = Field(..., min_length=1, max_length=120)
    target_type: QrTarget = QrTarget.CATALOG
    target_id: Optional[UUID] = None
    external_url: Optional[str] = None
    branch_id: Optional[UUID] = None
    is_active: bool = True
    expires_at: Optional[str] = None


class QrCodeCreate(QrCodeBase):
    pass


class QrCodeUpdate(BaseModel):
    label: Optional[str] = None
    target_type: Optional[QrTarget] = None
    target_id: Optional[UUID] = None
    external_url: Optional[str] = None
    branch_id: Optional[UUID] = None
    is_active: Optional[bool] = None
    expires_at: Optional[str] = None


class QrCodeOut(QrCodeBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    short_code: str
    scan_count: int
    unique_scans: int
    conversion_count: int
    created_at: datetime
    full_url: Optional[str] = None
    qr_image_data_url: Optional[str] = None
