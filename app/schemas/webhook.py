"""Schemas para Webhook."""
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, HttpUrl


class WebhookCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    url: HttpUrl
    events: list[str] = Field(default_factory=lambda: ["*"])


class WebhookUpdate(BaseModel):
    name: Optional[str] = None
    url: Optional[HttpUrl] = None
    events: Optional[list[str]] = None
    is_active: Optional[bool] = None


class WebhookOut(BaseModel):
    id: UUID
    tenant_id: UUID
    name: str
    url: str
    events: list[str]
    is_active: bool
    total_deliveries: int
    successful_deliveries: int
    failed_deliveries: int
    last_triggered_at: Optional[str] = None
    last_status_code: Optional[int] = None
    created_at: datetime

    class Config:
        from_attributes = True


class WebhookDeliveryOut(BaseModel):
    id: UUID
    webhook_id: str
    event: str
    success: bool
    status_code: Optional[int] = None
    error: Optional[str] = None
    attempts: int
    created_at: datetime

    class Config:
        from_attributes = True
