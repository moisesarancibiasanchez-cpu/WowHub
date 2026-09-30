"""Stripe webhook handler — `POST /api/v1/webhook/stripe` (público, sin auth).

Reglas:
- Sin auth (Stripe no puede autenticarse con JWT).
- Si `STRIPE_WEBHOOK_SECRET` no está configurado → 503 Service Unavailable.
- Si la firma es inválida → 400 Bad Request.
- Si el evento es válido → 200 OK y devuelve un resumen normalizado
  (`{type, intent_id, status, ...}`).

NO modifica el flujo existente de webhooks (MercadoPago u otros). Es un
endpoint adicional para HU_23.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Header, Request

from app.config import settings
from app.services.payments import get_provider

logger = logging.getLogger("wowhub.webhook_stripe")

router = APIRouter(tags=["payments", "webhooks"])


@router.post("/webhook/stripe")
async def stripe_webhook(
    request: Request,
    stripe_signature: str | None = Header(default=None, alias="Stripe-Signature"),
):
    """Recibe webhooks firmados de Stripe y los despacha al provider."""
    # Defensa: si falta el secret configurado, NO procesamos nada.
    # Devolver 200 OK sería un riesgo: Stripe seguiría enviando eventos
    # que nadie puede verificar, hasta saturar el endpoint.
    if not settings.stripe_webhook_secret:
        logger.error(
            "POST /webhook/stripe llamado pero STRIPE_WEBHOOK_SECRET no está "
            "configurado — devolviendo 503"
        )
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=503,
            content={
                "detail": "STRIPE_WEBHOOK_SECRET no configurado",
                "code": "stripe_webhook_disabled",
            },
        )

    payload = await request.body()
    if not payload:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Empty payload")

    provider = get_provider("stripe")
    try:
        event = provider.handle_webhook(payload, stripe_signature or "")
    except ValueError as ve:
        # Firma inválida / secret faltante — el provider ya devolvió un
        # mensaje útil, lo propagamos al cliente como 400.
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:  # noqa: BLE001
        logger.exception("Error procesando webhook Stripe: %s", e)
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail="Internal webhook error")

    logger.info(
        "Stripe webhook OK: type=%s intent_id=%s status=%s",
        event.get("type"), event.get("intent_id"), event.get("status"),
    )
    # Devolvemos 200 SIEMPRE con un resumen para que Stripe considere
    # el evento entregado (Stripe reintenta si recibe non-2xx).
    return {
        "ok": True,
        "provider": "stripe",
        "type": event.get("type"),
        "intent_id": event.get("intent_id"),
        "status": event.get("status"),
    }