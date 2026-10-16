"""Schemas para NotificationTemplate y NotificationLog (HU_62, HU_63)."""
from __future__ import annotations
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.notification import (
    NotificationEvent, NotificationChannel, NotificationStatus
)


class NotificationTemplateCreate(BaseModel):
    """HU_62 — crear/actualizar plantilla de notificación."""
    event: NotificationEvent
    channel: NotificationChannel
    template_body: str = Field(..., min_length=10, max_length=4000)
    is_active: bool = True


class NotificationTemplateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    tenant_id: UUID
    event: NotificationEvent
    channel: NotificationChannel
    template_body: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class NotificationSendRequest(BaseModel):
    """HU_62 — enviar una notificación manualmente."""
    customer_id: UUID
    order_id: Optional[UUID] = None
    event: NotificationEvent
    channel: NotificationChannel
    context: dict = Field(default_factory=dict)


class NotificationLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    tenant_id: UUID
    customer_id: Optional[UUID] = None
    order_id: Optional[UUID] = None
    channel: NotificationChannel
    event: NotificationEvent
    status: NotificationStatus
    content_rendered: Optional[str] = None
    error_message: Optional[str] = None
    sent_at: Optional[datetime] = None
    created_at: datetime
