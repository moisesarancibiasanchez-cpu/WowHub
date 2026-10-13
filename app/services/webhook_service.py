"""WebhookService — gestión y dispatch de webhooks salientes."""
import hashlib
import hmac
import json
import logging
from datetime import datetime, timezone
from typing import Optional

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.webhook import Webhook, WebhookDelivery, WebhookEvent

logger = logging.getLogger("wowhub.webhook")


class WebhookDispatcher:
    """Envía webhooks a URLs registradas para los tenants."""

    def __init__(self, db: Session):
        self.db = db
        self.timeout = 10.0

    def dispatch(self, *, tenant_id: str, event: str, payload: dict) -> int:
        """Envía un evento a todos los webhooks activos que escuchan ese evento.

        Retorna el número de webhooks a los que se encoló.
        """
        webhooks = list(self.db.execute(
            select(Webhook).where(
                Webhook.tenant_id == tenant_id,
                Webhook.is_active == True,  # noqa: E712
            )
        ).scalars())

        count = 0
        for wh in webhooks:
            if not self._subscribes_to(wh, event):
                continue
            delivery = WebhookDelivery(
                tenant_id=tenant_id,
                webhook_id=str(wh.id),
                event=event,
                payload=payload,
                success=False,
                attempts=0,
                max_attempts=5,
            )
            self.db.add(delivery)
            self.db.flush()
            # Intentar entrega inmediata
            self._try_deliver(wh, delivery, payload)
            count += 1

        if count:
            self.db.commit()
        return count

    def _subscribes_to(self, wh: Webhook, event: str) -> bool:
        events = wh.events or []
        if "*" in events or "all" in events:
            return True
        return event in events

    def _try_deliver(self, wh: Webhook, delivery: WebhookDelivery, payload: dict) -> None:
        body = json.dumps(payload, default=str)
        signature = hmac.new(
            wh.secret.encode("utf-8"),
            body.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        headers = {
            "Content-Type": "application/json",
            "X-WowHub-Event": delivery.event,
            "X-WowHub-Signature": f"sha256={signature}",
            "X-WowHub-Delivery": str(delivery.id),
        }
        delivery.attempts += 1
        try:
            resp = httpx.post(wh.url, content=body, headers=headers, timeout=self.timeout)
            delivery.status_code = resp.status_code
            delivery.response_body = (resp.text or "")[:2000]
            delivery.success = 200 <= resp.status_code < 300
            wh.last_status_code = resp.status_code
        except Exception as e:
            delivery.error = str(e)[:500]
            delivery.success = False
        wh.total_deliveries += 1
        wh.last_triggered_at = datetime.now(timezone.utc).isoformat()
        if delivery.success:
            wh.successful_deliveries += 1
        else:
            wh.failed_deliveries += 1
            # Programar reintento con backoff exponencial
            from datetime import timedelta
            backoff = min(60 * 60, 2 ** delivery.attempts * 10)  # máx 1h
            delivery.next_retry_at = (datetime.now(timezone.utc) + timedelta(seconds=backoff)).isoformat()

    def list(self, tenant_id: str):
        return list(self.db.execute(
            select(Webhook).where(Webhook.tenant_id == tenant_id)
        ).scalars())

    def list_deliveries(self, tenant_id: str, webhook_id: Optional[str] = None, limit: int = 50):
        q = select(WebhookDelivery).where(WebhookDelivery.tenant_id == tenant_id)
        if webhook_id:
            q = q.where(WebhookDelivery.webhook_id == webhook_id)
        q = q.order_by(WebhookDelivery.created_at.desc()).limit(limit)
        return list(self.db.execute(q).scalars())
