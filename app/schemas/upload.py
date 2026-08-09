"""Schemas para Upload."""
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class UploadOut(BaseModel):
    id: UUID
    tenant_id: UUID
    filename: str
    url: str
    content_type: str
    size_bytes: int
    width: Optional[int] = None
    height: Optional[int] = None
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None
    purpose: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True
