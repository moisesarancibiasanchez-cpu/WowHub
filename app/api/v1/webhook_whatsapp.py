"""WhatsApp Business webhook handler — `POST /api/v1/webhooks/whatsapp` (público, sin auth).

HU_16 — Pedidos multi-canal (WhatsApp). Stub mínimo.

Reglas:
- Sin auth (WhatsApp Cloud API no puede autenticarse con JWT).
- Si `WHATSAPP_BUSINESS_TOKEN` no está seteado → 503 Service Unavailable
  (fail-closed, igual que el webhook de Stripe). Devolver 200 OK sería
  fail-open: aceptaríamos cualquier evento sin verificar firma.
- Si la firma (`X-WhatsApp-Signature`) falta o es inválida → 400 Bad Request.
- Si el token está configurado y la firma está OK → 200 OK con
  `{"received": true, "processed": false}` (stub — sólo logea, no crea
  pedido todavía).

NO modifica el flujo existente de webhooks (Stripe, MercadoPago u otros).
Es un endpoint adicional para HU_16.
"""
from __future__ import annotations

import hashlib
import hmac
import logging

from fastapi import APIRouter, Header, Request

from app.config import settings

logger = logging.getLogger("wowhub.webhook_whatsapp")

router = APIRouter(tags=["orders", "webhooks"])


@router.post("/webhooks/whatsapp")
async def whatsapp_webhook(
    request: Request,
    x_whatsapp_signature: str | None = Header(default=None, alias="X-WhatsApp-Signature"),
):
    """Recibe webhooks de WhatsApp Business y los loguea (stub de HU_16)."""
    # Defensa 1: si falta el secret configurado, NO procesamos nada.
    # Devolver 200 OK sería fail-open: aceptaríamos cualquier request.
    if not settings.whatsapp_business_token:
        logger.error(
            "POST /webhooks/whatsapp llamado pero WHATSAPP_BUSINESS_TOKEN "
            "no está configurado — devolviendo 503"
        )
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=503,
            content={
                "detail": "WHATSAPP_BUSINESS_TOKEN no configurado",
                "code": "whatsapp_webhook_disabled",
            },
        )

    # Defensa 2: validar header de firma. WhatsApp Cloud API envía el header
    # `X-WhatsApp-Signature` con el HMAC-SHA256 del body usando el app secret.
    if not x_whatsapp_signature:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=400,
            detail="X-WhatsApp-Signature header requerido",
        )

    payload = await request.body()
    if not payload:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Empty payload")

    # Verificación de firma: HMAC-SHA256(body, app_secret) y comparar con el
    # header recibido. Si no matchea → 400 (no es nuestro request).
    expected = hmac.new(
        settings.whatsapp_business_token.encode("utf-8"),
        payload,
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(expected, x_whatsapp_signature):
        logger.warning(
            "POST /webhooks/whatsapp firma inválida — descartando request"
        )
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Invalid signature")

    # Stub: por ahora solo logeamos el evento recibido. La conversión de
    # payload WhatsApp → Order real queda fuera de este commit mínimo.
    logger.info(
        "WhatsApp webhook OK: signature=%s… payload_bytes=%d",
        x_whatsapp_signature[:12],
        len(payload),
    )
    return {"received": True, "processed": False}