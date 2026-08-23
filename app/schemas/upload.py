"""Schemas para Upload."""
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class UploadOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

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
