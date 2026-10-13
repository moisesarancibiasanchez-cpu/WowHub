"""Webhooks API — gestión de webhooks salientes."""
import secrets
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.database import get_db
from app.deps import get_current_membership
from app.models.tenant import TenantMembership
from app.models.webhook import Webhook, WebhookDelivery
from app.schemas.common import Page
from app.schemas.webhook import WebhookCreate, WebhookDeliveryOut, WebhookOut, WebhookUpdate
from app.services.webhook_service import WebhookDispatcher

router = APIRouter(prefix="/tenants/{tenant_id}/webhooks", tags=["webhooks"])


@router.get("", response_model=list[WebhookOut])
def list_webhooks(
    tenant_id: UUID,
    membership: TenantMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    return [WebhookOut.model_validate(w) for w in WebhookDispatcher(db).list(str(tenant_id))]


@router.post("", response_model=WebhookOut, status_code=201)
def create_webhook(
    tenant_id: UUID,
    payload: WebhookCreate,
    membership: TenantMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    """Crea un nuevo webhook. El secret se genera automáticamente."""
    secret = secrets.token_urlsafe(32)
    wh = Webhook(
        tenant_id=str(tenant_id),
        name=payload.name,
        url=str(payload.url),
        secret=secret,
        events=payload.events,
        is_active=True,
    )
    db.add(wh)
    db.commit()
    db.refresh(wh)
    return WebhookOut.model_validate(wh)


@router.patch("/{webhook_id}", response_model=WebhookOut)
def update_webhook(
    tenant_id: UUID,
    webhook_id: UUID,
    payload: WebhookUpdate,
    membership: TenantMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    wh = db.get(Webhook, webhook_id)
    if not wh or wh.tenant_id != tenant_id:
        raise NotFoundError("Webhook")
    data = payload.model_dump(exclude_unset=True)
    if "url" in data and data["url"]:
        data["url"] = str(data["url"])
    for k, v in data.items():
        setattr(wh, k, v)
    db.commit()
    db.refresh(wh)
    return WebhookOut.model_validate(wh)


@router.delete("/{webhook_id}", status_code=204)
def delete_webhook(
    tenant_id: UUID,
    webhook_id: UUID,
    membership: TenantMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    wh = db.get(Webhook, webhook_id)
    if not wh or wh.tenant_id != tenant_id:
        raise NotFoundError("Webhook")
    db.delete(wh)
    db.commit()


@router.get("/{webhook_id}/deliveries", response_model=list[WebhookDeliveryOut])
def list_deliveries(
    tenant_id: UUID,
    webhook_id: UUID,
    limit: int = Query(50, ge=1, le=200),
    membership: TenantMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    deliveries = WebhookDispatcher(db).list_deliveries(str(tenant_id), webhook_id=str(webhook_id), limit=limit)
    return [WebhookDeliveryOut.model_validate(d) for d in deliveries]
