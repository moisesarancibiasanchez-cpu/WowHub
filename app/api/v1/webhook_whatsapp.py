"""WhatsApp Business webhook handler — `POST /api/v1/webhooks/whatsapp` (público, sin auth).

HU_16 — Pedidos multi-canal (WhatsApp) + QR menu. Soporta DOS formatos:

1. WhatsApp Cloud API (JSON): body JSON, header ``X-WhatsApp-Signature`` con
   HMAC-SHA256(whatsapp_business_token, body). Por compatibilidad se mantiene
   el comportamiento del stub original.

2. Twilio-compatible (form-encoded): ``Content-Type: application/x-www-form-
   urlencoded``, campos ``From``, ``Body``, ``MessageSid``. Header
   ``X-Twilio-Signature`` con HMAC-SHA1(whatsapp_webhook_secret, url+body).

Reglas de seguridad (CRÍTICAS — lección CVSS 9.1):
- **Fail-closed en producción**: si el secret aplicable al formato detectado
  NO está configurado Y ``APP_ENV=production``, devolvemos 503. Devolver 200
  OK sin verificar firma sería fail-open → aceptaríamos cualquier evento.
- Si la firma está mal o falta → 400 Bad Request.
- Si está OK → procesamos + 200 OK (TwiML XML si es Twilio, JSON si es WA).

Comandos soportados en el path Twilio:
- ``menu`` → responde con TwiML listando los productos activos del tenant
  resuelto por el número de teléfono del remitente. Si el número no está
  vinculado a ningún tenant, responde con mensaje de ayuda.
- ``pedir <item_id>`` → crea un pedido en estado RECIBIDO con source=whatsapp
  vinculado al cliente (o crea uno implícito por teléfono) y devuelve TwiML
  con el número de pedido.
- Cualquier otra cosa → eco con ayuda.

NO modifica el flujo existente de webhooks (Stripe, MercadoPago u otros).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import re
from typing import Any, Optional
from urllib.parse import quote, urlparse

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy import select

from app.config import settings
from app.database import SessionLocal
from app.models.order import Order, OrderItem, OrderSource, OrderStatus
from app.models.product import Product, ProductStatus
from app.services.order_service import OrderService

logger = logging.getLogger("wowhub.webhook_whatsapp")

router = APIRouter(tags=["orders", "webhooks"])


# ── Helpers de seguridad ──────────────────────────────────────────────────
def _fail_closed_if_production(reason: str, code: str) -> Optional[JSONResponse]:
    """Devuelve 503 si APP_ENV=production, None en dev (warning log)."""
    if settings.is_production:
        logger.error(
            "POST /webhooks/whatsapp FAIL-CLOSED: %s — APP_ENV=production", reason
        )
        return JSONResponse(
            status_code=503,
            content={"detail": reason, "code": code},
        )
    logger.warning(
        "POST /webhooks/whatsapp dev-mode: %s (en producción sería 503)", reason
    )
    return None


# ── Twilio-compatible: parseo de firma ─────────────────────────────────────
def _verify_twilio_signature(
    full_url: str, body: bytes, params: dict[str, str], signature: str
) -> bool:
    """Verifica X-Twilio-Signature según el algoritmo oficial de Twilio.

    StringToSign = full_url + concat(sorted(p) + "=" + params[p])
    Signature    = Base64(HMAC-SHA1(auth_token, StringToSign))

    La ``full_url`` debe coincidir con la que recibió Twilio. La usamos tal
    cual llega al handler (``request.url_for``) — incluyendo query string.
    """
    secret = (settings.whatsapp_webhook_secret or "").strip()
    if not secret:
        return False
    # Twilio concatena URL + pares ordenados alfabéticamente. Sólo incluye
    # los que tienen valor; los vacíos se omiten.
    sorted_keys = sorted(k for k, v in params.items() if v is not None and v != "")
    message = full_url
    for k in sorted_keys:
        message += k + params[k]
    digest = hmac.new(secret.encode("utf-8"), message.encode("utf-8"), hashlib.sha1).digest()
    expected = base64.b64encode(digest).decode("ascii")
    return hmac.compare_digest(expected, signature or "")


# ── WhatsApp Cloud API: HMAC-SHA256 ─────────────────────────────────────────
def _verify_whatsapp_cloud_signature(body: bytes, signature: str) -> bool:
    secret = (settings.whatsapp_business_token or "").strip()
    if not secret:
        return False
    expected = hmac.new(
        secret.encode("utf-8"), body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature or "")


# ── Helpers de comandos (Twilio path) ───────────────────────────────────────
_MENU_RE = re.compile(r"^\s*menu\s*$", re.IGNORECASE)
_ORDER_RE = re.compile(r"^\s*pedir\s+([0-9a-fA-F\-]{32,36})\s*$", re.IGNORECASE)


def _resolve_tenant_for_phone(db, phone: str):
    """Devuelve el (tenant, customer) más probable para un número E.164.

    Estrategia: matchear el sufijo del phone contra cualquier
    TenantMembership.customer.phone en el mismo tenant. Como fallback,
    devolvemos el PRIMER tenant activo (útil en dev mono-tenant).
    """
    from app.models.customer import Customer
    from app.models.tenant import Tenant

    if not phone:
        return None, None
    phone_norm = phone.strip()
    # Búsqueda exacta por phone
    cust = db.execute(
        select(Customer).where(Customer.phone == phone_norm).limit(1)
    ).scalar_one_or_none()
    if cust:
        tenant = db.get(Tenant, cust.tenant_id)
        if tenant and tenant.is_active:
            return tenant, cust
    # Búsqueda por sufijo (últimos 8 dígitos) — útil para variantes
    # +56 9 ... vs 569... que Twilio a veces entrega distinto.
    suffix = phone_norm.replace("+", "")[-8:]
    if len(suffix) >= 6:
        cust = db.execute(
            select(Customer).where(Customer.phone.like(f"%{suffix}%")).limit(1)
        ).scalar_one_or_none()
        if cust:
            tenant = db.get(Tenant, cust.tenant_id)
            if tenant and tenant.is_active:
                return tenant, cust
    # Fallback mono-tenant (dev convenience). NO usar en multi-tenant prod
    # sin gate explícito.
    tenants = db.execute(select(Tenant).where(Tenant.is_active == True)).scalars().all()  # noqa: E712
    if len(tenants) == 1:
        return tenants[0], None
    return None, None


def _twiml_response(message: str) -> str:
    safe = (
        message.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<Response>"
        f"<Message>{safe}</Message>"
        "</Response>"
    )


def _handle_twilio_command(db, tenant, customer, from_phone: str, body: str) -> str:
    """Procesa el cuerpo del mensaje y devuelve TwiML."""
    text = (body or "").strip()

    # MENU
    if _MENU_RE.match(text):
        if not tenant:
            return _twiml_response(
                "👋 Hola. Aún no estás vinculado a un negocio. "
                "Pide a tu local que escanee el QR de la mesa para empezar."
            )
        products = list(db.execute(
            select(Product)
            .where(Product.tenant_id == str(tenant.id), Product.status == ProductStatus.ACTIVE)
            .order_by(Product.name)
            .limit(20)
        ).scalars())
        if not products:
            return _twiml_response(
                "📋 El menú aún no tiene productos activos. Vuelve pronto."
            )
        lines = ["📋 Menú:"]
        for p in products:
            price_pesos = (p.price_cents or 0) // 100
            lines.append(f"• {p.name} — ${price_pesos}")
        lines.append("")
        lines.append("Para pedir responde: pedir <id>")
        if products:
            lines.append(f"Ej: pedir {products[0].id}")
        return _twiml_response("\n".join(lines))

    # PEDIR <id>
    m = _ORDER_RE.match(text)
    if m:
        if not tenant:
            return _twiml_response(
                "❌ No pude identificar tu negocio. Pide al local que te vincule."
            )
        product_id = m.group(1)
        product = db.get(Product, product_id)
        if not product or product.tenant_id != tenant.id:
            return _twiml_response(
                f"❌ Producto {product_id} no encontrado en este menú."
            )
        if product.status != ProductStatus.ACTIVE:
            return _twiml_response(
                f"❌ {product.name} no está disponible ahora."
            )
        # Crear pedido (source=whatsapp)
        try:
            order = OrderService(db).create(
                tenant,
                items=[{"product_id": product.id, "quantity": 1, "options": {}}],
                customer_id=customer.id if customer else None,
                customer_name=customer.full_name if customer else None,
                customer_phone=from_phone,
                source=OrderSource.WHATSAPP.value,
            )
            db.commit()
            return _twiml_response(
                f"✅ Pedido recibido: #{order.number}\n"
                f"{product.name} — ${(product.price_cents or 0) // 100}\n"
                "Te avisaremos cuando esté listo."
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Error creando pedido WhatsApp")
            db.rollback()
            return _twiml_response(
                f"❌ No pude crear el pedido: {exc}"
            )

    # Default: ayuda
    return _twiml_response(
        "👋 Hola! Responde:\n"
        "• menu — ver el menú\n"
        "• pedir <id> — hacer un pedido"
    )


# ── Endpoint principal ──────────────────────────────────────────────────────
@router.post("/webhooks/whatsapp")
async def whatsapp_webhook(
    request: Request,
    x_whatsapp_signature: str | None = Header(default=None, alias="X-WhatsApp-Signature"),
    x_twilio_signature: str | None = Header(default=None, alias="X-Twilio-Signature"),
):
    """Recibe webhooks de WhatsApp Business / Twilio.

    Detecta el formato por el ``Content-Type``:
    - ``application/x-www-form-urlencoded`` → path Twilio.
    - otro (o JSON) → path WhatsApp Cloud API.
    """
    raw = await request.body()
    if not raw:
        return JSONResponse(status_code=400, content={"detail": "Empty payload"})

    content_type = (request.headers.get("content-type") or "").lower()
    is_twilio = "application/x-www-form-urlencoded" in content_type

    # ── Path 1: Twilio ────────────────────────────────────────────────
    if is_twilio:
        # Defensa 1: secret configurado? Si no, fail-closed en prod.
        if not settings.whatsapp_webhook_secret:
            blocked = _fail_closed_if_production(
                "WHATSAPP_WEBHOOK_SECRET no configurado",
                "whatsapp_webhook_disabled",
            )
            if blocked is not None:
                return blocked
            # Dev-mode: aceptamos sin firma (warning ya loggeado).
            signature_ok = True
        else:
            # Defensa 2: validar header.
            if not x_twilio_signature:
                return JSONResponse(
                    status_code=400,
                    content={"detail": "X-Twilio-Signature header requerido"},
                )
            # Parsear form-encoded params.
            from urllib.parse import parse_qsl
            params = dict(parse_qsl(raw.decode("utf-8"), keep_blank_values=True))
            full_url = str(request.url)
            signature_ok = _verify_twilio_signature(
                full_url, raw, params, x_twilio_signature
            )
        if not signature_ok:
            logger.warning(
                "POST /webhooks/whatsapp (Twilio) firma inválida — descartando"
            )
            return JSONResponse(
                status_code=400, content={"detail": "Invalid signature"}
            )

        from_phone = (request.headers.get("X-Twilio-From") or "").strip()
        body_text = ""
        message_sid = ""
        try:
            from urllib.parse import parse_qsl as _parse_qsl
            params = dict(_parse_qsl(raw.decode("utf-8"), keep_blank_values=True))
            from_phone = params.get("From", from_phone)
            body_text = params.get("Body", "")
            message_sid = params.get("MessageSid", "")
        except Exception:
            pass

        # Log estructurado (no DB table — el user spec lo deja opcional).
        logger.info(
            "WhatsApp/Twilio msg from=%s sid=%s body=%r",
            from_phone, message_sid, body_text[:200],
        )

        # Procesar comandos en su propia sesión (evita mezclar con la del handler).
        with SessionLocal() as db:
            try:
                tenant, customer = _resolve_tenant_for_phone(db, from_phone)
                twiml = _handle_twilio_command(db, tenant, customer, from_phone, body_text)
            except Exception as exc:  # noqa: BLE001
                # Si la BD está en mal estado (schema drift, DB caída) NO
                # debemos hacer 5xx — Twilio lo reintentaría y DoS. Caemos a
                # un mensaje genérico en TwiML.
                logger.exception("Error procesando comando WhatsApp Twilio")
                twiml = _twiml_response(
                    "👋 Recibimos tu mensaje. Estamos actualizando el sistema; "
                    "intenta nuevamente en breve."
                )

        return PlainTextResponse(content=twiml, media_type="application/xml")

    # ── Path 2: WhatsApp Cloud API (JSON, HMAC-SHA256) ────────────────
    if not settings.whatsapp_business_token:
        blocked = _fail_closed_if_production(
            "WHATSAPP_BUSINESS_TOKEN no configurado",
            "whatsapp_webhook_disabled",
        )
        if blocked is not None:
            return blocked
        # Dev-mode: aceptamos sin verificar. Aún así logueamos el payload.
        logger.warning(
            "POST /webhooks/whatsapp WA Cloud: sin secret en dev, aceptando"
        )
    else:
        if not x_whatsapp_signature:
            from fastapi import HTTPException
            raise HTTPException(
                status_code=400,
                detail="X-WhatsApp-Signature header requerido",
            )
        if not _verify_whatsapp_cloud_signature(raw, x_whatsapp_signature):
            logger.warning(
                "POST /webhooks/whatsapp firma inválida — descartando request"
            )
            from fastapi import HTTPException
            raise HTTPException(status_code=400, detail="Invalid signature")

    logger.info(
        "WhatsApp Cloud webhook OK: signature=%s… payload_bytes=%d",
        (x_whatsapp_signature or "")[:12],
        len(raw),
    )
    return {"received": True, "processed": False}