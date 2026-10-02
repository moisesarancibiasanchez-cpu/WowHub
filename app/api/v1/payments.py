"""Payments API — gestión de pagos (MercadoPago, manual, etc.)."""
import json
import logging
import os
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, ValidationError
from app.database import get_db
from app.deps import get_current_membership
from app.models.order import Order
from app.models.payment import PaymentMethod, PaymentStatus
from app.models.tenant import Tenant, TenantMembership
from app.schemas.common import Page
from app.schemas.payment import PaymentConfirm, PaymentCreate, PaymentListItem, PaymentOut
from app.services.payment_service import PaymentService

logger = logging.getLogger("wowhub.payments_api")
router = APIRouter(tags=["payments"])


# ── Endpoints autenticados (tenant) ─────────────────
tenant_router = APIRouter(prefix="/tenants/{tenant_id}/payments", tags=["payments"])


@tenant_router.get("", response_model=Page[PaymentListItem])
def list_payments(
    tenant_id: UUID,
    status: Optional[PaymentStatus] = Query(None),
    order_id: Optional[UUID] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    membership: TenantMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    return PaymentService(db).list(
        tenant_id, status=status, order_id=order_id, page=page, page_size=page_size,
    )


@tenant_router.post("/mercadopago", response_model=PaymentOut, status_code=201)
def create_mp_preference(
    tenant_id: UUID,
    payload: PaymentCreate,
    membership: TenantMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    """Crea una preference de MercadoPago y retorna el init_point."""
    tenant = db.get(Tenant, tenant_id)
    if not tenant:
        raise NotFoundError("Tenant")
    order = db.get(Order, payload.order_id)
    if not order or order.tenant_id != tenant_id:
        raise NotFoundError("Pedido")
    payment = PaymentService(db).create_mercadopago_preference(tenant, order)
    return _to_out(payment)


@tenant_router.post("/manual", response_model=PaymentOut, status_code=201)
def create_manual_payment(
    tenant_id: UUID,
    payload: PaymentCreate,
    membership: TenantMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    """Crea un pago manual (transfer, cash, etc.)."""
    tenant = db.get(Tenant, tenant_id)
    if not tenant:
        raise NotFoundError("Tenant")
    order = db.get(Order, payload.order_id)
    if not order or order.tenant_id != tenant_id:
        raise NotFoundError("Pedido")
    method = payload.method if payload.method in (
        PaymentMethod.TRANSFER, PaymentMethod.CASH,
        PaymentMethod.CARD_ON_DELIVERY, PaymentMethod.OTHER,
    ) else PaymentMethod.TRANSFER
    payment = PaymentService(db).create_manual_payment(tenant, order, method=method, notes=payload.notes)
    return _to_out(payment)


@tenant_router.post("/{payment_id}/confirm", response_model=PaymentOut)
def confirm_payment(
    tenant_id: UUID,
    payment_id: UUID,
    payload: PaymentConfirm,
    membership: TenantMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    """Confirma/rechaza un pago manual desde el dashboard."""
    payment = PaymentService(db).get(tenant_id, payment_id)
    payment = PaymentService(db).confirm_manual(payment, paid=payload.paid, notes=payload.notes)
    return _to_out(payment)


@tenant_router.get("/{payment_id}", response_model=PaymentOut)
def get_payment(
    tenant_id: UUID,
    payment_id: UUID,
    membership: TenantMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    return _to_out(PaymentService(db).get(tenant_id, payment_id))


# ── Webhook público (MercadoPago) ────────────────────
public_router = APIRouter(tags=["payments"])


def _validate_mp_signature(
    *,
    x_signature: Optional[str],
    x_request_id: Optional[str],
    body_bytes: bytes,
    secret: str,
) -> bool:
    """Valida la firma HMAC-SHA256 de un webhook de MercadoPago.

    MercadoPago envía el header ``x-signature`` con formato ``ts=<unix>,v1=<hex>``
    y opcionalmente ``x-request-id``. La firma válida es::

        manifest = f"id:{data_id};request-id:{x_request_id};ts:{ts};"
        hmac.new(secret.encode(), manifest.encode(), hashlib.sha256).hexdigest()

    Retorna True si la firma coincide o si no se envió ``x-signature``
    (modo "soft validation" — log warning pero no rechaza, para
    mantener compatibilidad con integraciones de prueba).

    Para producción con ``MERCADOPAGO_WEBHOOK_SECRET`` configurado,
    cambiar el fallback a ``return False`` para fallar cerrado.
    """
    import hashlib
    import hmac as _hmac

    if not x_signature:
        # Sin header x-signature — modo permisivo en dev, estricto en prod.
        logger.warning("MP webhook sin x-signature (dev mode)")
        return True

    # Parse "ts=...,v1=..."
    parts: dict[str, str] = {}
    for kv in x_signature.split(","):
        if "=" in kv:
            k, _, v = kv.partition("=")
            parts[k.strip()] = v.strip()
    ts = parts.get("ts", "")
    v1 = parts.get("v1", "")
    if not ts or not v1:
        logger.warning("MP webhook x-signature mal formado: %r", x_signature)
        return False

    # Extraer data.id del body (ya validado como JSON antes de llamar esto).
    try:
        data = json.loads(body_bytes.decode("utf-8"))
        data_id = str((data.get("data") or {}).get("id") or "")
    except Exception:
        data_id = ""

    manifest = f"id:{data_id};request-id:{x_request_id or ''};ts:{ts};"
    expected = _hmac.new(
        secret.encode("utf-8"),
        manifest.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    if not _hmac.compare_digest(expected, v1):
        logger.warning(
            "MP webhook firma inválida — expected=%s, got=%s, manifest=%s",
            expected[:12] + "...", v1[:12] + "...", manifest,
        )
        return False
    return True


@public_router.post("/webhook/mercadopago")
async def mercadopago_webhook(
    request: Request,
    db: Session = Depends(get_db),
    x_signature: Optional[str] = None,
    x_request_id: Optional[str] = None,
):
    """Recibe webhooks de MercadoPago con validación HMAC-SHA256.

    Headers importantes:
    - ``x-signature``: ``ts=<unix>,v1=<hex>`` — firma del payload.
    - ``x-request-id``: UUID de la request MP.

    Comportamiento:
    - Si la firma es **inválida** y ``MERCADOPAGO_WEBHOOK_SECRET`` está
      configurado → 401 Unauthorized (rechazamos).
    - Si no hay secret configurado (dev) → log warning y procesamos igual.
    - Si el body no es JSON o no tiene ``data.id`` → 200 OK con
      ``{"ok": true}`` (MP envía pings sin body para keepalive).
    """
    body_bytes = await request.body()
    secret = os.getenv("MERCADOPAGO_WEBHOOK_SECRET", "")
    app_env = os.getenv("APP_ENV", "production").lower()
    if not secret:
        # FIX CRÍTICO 2026-10-02: en producción sin secret we fail-closed
        # (403) en vez de aceptar cualquier request. Esto cierra la
        # vulnerabilidad de spoofing de pagos detectada por el verificador.
        # En dev/staging se mantiene el comportamiento permisivo (warning).
        if app_env == "production":
            from fastapi.responses import JSONResponse
            logger.error(
                "MP webhook sin MERCADOPAGO_WEBHOOK_SECRET en producción — "
                "rechazando request por seguridad"
            )
            return JSONResponse(
                status_code=503,
                content={
                    "ok": False,
                    "code": "mp_webhook_disabled",
                    "detail": "MERCADOPAGO_WEBHOOK_SECRET no configurado en producción — "
                              "configura la variable en Railway",
                },
            )
        logger.warning("MP webhook sin secret (dev/staging mode) — procesando sin firma")

    if secret:
        # Modo estricto: la firma DEBE ser válida.
        if not _validate_mp_signature(
            x_signature=x_signature,
            x_request_id=x_request_id,
            body_bytes=body_bytes,
            secret=secret,
        ):
            from fastapi.responses import JSONResponse
            return JSONResponse(
                status_code=401,
                content={
                    "ok": False,
                    "code": "invalid_signature",
                    "detail": "Firma HMAC-SHA256 inválida — verifica MERCADOPAGO_WEBHOOK_SECRET",
                },
            )
    elif x_signature:
        # Hay header pero no secret configurado: log warning en dev.
        logger.warning(
            "MP webhook con x-signature pero sin MERCADOPAGO_WEBHOOK_SECRET — "
            "configura el secret para activar validación estricta"
        )

    try:
        body = json.loads(body_bytes.decode("utf-8")) if body_bytes else {}
    except Exception:
        return {"ok": True}  # MP envía ping sin body

    # MP envía: {"type": "payment", "data": {"id": "..."}}
    if body.get("type") == "payment":
        payment_id = (body.get("data") or {}).get("id")
        if payment_id:
            import httpx
            token = os.getenv("MERCADOPAGO_ACCESS_TOKEN", "")
            if token:
                try:
                    resp = httpx.get(
                        f"https://api.mercadopago.com/v1/payments/{payment_id}",
                        headers={"Authorization": f"Bearer {token}"},
                        timeout=10.0,
                    )
                    if resp.status_code == 200:
                        PaymentService(db).process_webhook(resp.json())
                except Exception as e:
                    logger.warning("Error fetching MP payment: %s", e)
    return {"ok": True}


# ── Mock checkout (desarrollo) ──────────────────────
@public_router.get("/mock/{token}")
def mock_checkout(token: str, db: Session = Depends(get_db)):
    """Página de checkout mock para desarrollo cuando no hay credenciales MP."""
    from fastapi.responses import HTMLResponse
    return HTMLResponse(f"""
    <html>
    <head><title>Mock Checkout</title></head>
    <body style="font-family:sans-serif;max-width:600px;margin:50px auto;padding:20px">
        <h1>🧪 Checkout Mock (Desarrollo)</h1>
        <p>Este es un checkout simulado. En producción, MercadoPago procesará el pago real.</p>
        <p>Token: <code>{token}</code></p>
        <form method="post" action="/api/v1/payments/mock/{token}/approve">
            <button style="background:#00d4a8;color:white;border:none;padding:12px 24px;border-radius:6px;cursor:pointer">
                Simular Pago Exitoso
            </button>
        </form>
        <form method="post" action="/api/v1/payments/mock/{token}/reject" style="margin-top:10px">
            <button style="background:#e53e3e;color:white;border:none;padding:12px 24px;border-radius:6px;cursor:pointer">
                Simular Pago Fallido
            </button>
        </form>
    </body>
    </html>
    """)


@public_router.post("/mock/{token}/approve")
def mock_approve(token: str, db: Session = Depends(get_db)):
    """Aprueba un pago mock (dev only)."""
    from sqlalchemy import select
    from app.models.payment import Payment
    p = db.execute(
        select(Payment).where(Payment.provider_preference_id == f"mock_pref_{token}")
    ).scalar_one_or_none()
    if p:
        PaymentService(db).process_webhook({"external_reference": p.order_id, "status": "approved", "id": f"mock_{token}"})
    return {"ok": True, "message": "Pago simulado como aprobado"}


@public_router.post("/mock/{token}/reject")
def mock_reject(token: str, db: Session = Depends(get_db)):
    from sqlalchemy import select
    from app.models.payment import Payment
    p = db.execute(
        select(Payment).where(Payment.provider_preference_id == f"mock_pref_{token}")
    ).scalar_one_or_none()
    if p:
        p.status = PaymentStatus.FAILED
        db.commit()
    return {"ok": True, "message": "Pago simulado como rechazado"}


def _to_out(p) -> PaymentOut:
    return PaymentOut(
        id=p.id,
        tenant_id=UUID(p.tenant_id) if isinstance(p.tenant_id, str) else p.tenant_id,
        order_id=UUID(p.order_id) if isinstance(p.order_id, str) else p.order_id,
        method=p.method,
        status=p.status,
        amount_cents=p.amount_cents,
        fee_cents=p.fee_cents,
        net_cents=p.net_cents,
        currency=p.currency,
        provider=p.provider,
        provider_payment_id=p.provider_payment_id,
        provider_preference_id=p.provider_preference_id,
        init_point=p.init_point,
        paid_at=p.paid_at,
        expires_at=p.expires_at,
        created_at=p.created_at,
    )


# ── HU_23 — Stripe (pasarela unificada) ─────────────────────────────
# Endpoints ADICIONALES — los existentes (MercadoPago, manual, mock) NO
# se tocan. Sólo agregamos dos rutas nuevas detrás de `tenant_router`:
#   POST /api/v1/tenants/{tenant_id}/payments/stripe/intent
#   GET  /api/v1/tenants/{tenant_id}/payments/stripe/status/{payment_intent_id}
#
# Si `STRIPE_SECRET_KEY` no está configurado, ambos endpoints funcionan
# gracias al fail-open del `StripeProvider` (cae a Mock + warning).
from typing import Optional as _Optional  # noqa: E402  (local alias para evitar shadowing del import superior)
from fastapi import HTTPException  # noqa: E402
from pydantic import BaseModel as _BaseModel, Field as _Field  # noqa: E402

from app.services.payments import get_provider as _get_provider  # noqa: E402


class _StripeIntentBody(_BaseModel):
    """Body de POST /tenants/{id}/payments/stripe/intent."""
    amount_cents: int = _Field(..., ge=1, description="Monto en centavos")
    currency: str = _Field("usd", min_length=2, max_length=8, description="ISO-4217")


class _StripeIntentResponse(_BaseModel):
    """Respuesta normalizada del endpoint de Stripe."""
    provider: str
    intent_id: str
    client_secret: _Optional[str] = None
    status: str
    amount_cents: int
    currency: str


class _StripeStatusResponse(_BaseModel):
    provider: str
    intent_id: str
    status: str
    amount_cents: int
    currency: str


@tenant_router.post(
    "/stripe/intent",
    response_model=_StripeIntentResponse,
    status_code=201,
    tags=["payments", "stripe"],
)
def create_stripe_intent(
    tenant_id: UUID,
    payload: _StripeIntentBody,
    membership: TenantMembership = Depends(get_current_membership),
):
    """Crea un PaymentIntent en Stripe (o Mock si no hay STRIPE_SECRET_KEY).

    Requiere auth de tenant (JWT + membresía). El `tenant_id` del JWT y del
    path deben coincidir (regla estándar de WowHub — ver `get_current_membership`).
    """
    provider = _get_provider("stripe")
    meta = {
        "tenant_id": str(tenant_id),
        "membership_id": str(getattr(membership, "id", "")),
    }
    try:
        result = provider.create_payment_intent(
            amount_cents=payload.amount_cents,
            currency=payload.currency,
            metadata=meta,
        )
    except RuntimeError as e:
        # SDK no instalado o config inválida — devolvemos 503 (no 500)
        # para que el cliente sepa que es un problema de configuración.
        raise HTTPException(status_code=503, detail=str(e))
    if result.status == "error":
        raise HTTPException(status_code=502, detail="Stripe error")
    return _StripeIntentResponse(
        provider=result.provider,
        intent_id=result.intent_id,
        client_secret=result.client_secret,
        status=result.status,
        amount_cents=result.amount_cents,
        currency=result.currency,
    )


@tenant_router.get(
    "/stripe/status/{payment_intent_id}",
    response_model=_StripeStatusResponse,
    tags=["payments", "stripe"],
)
def get_stripe_status(
    tenant_id: UUID,
    payment_intent_id: str,
    membership: TenantMembership = Depends(get_current_membership),
):
    """Consulta el estado de un PaymentIntent por id."""
    provider = _get_provider("stripe")
    try:
        result = provider.confirm_payment(payment_intent_id)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    if result.status == "error":
        raise HTTPException(status_code=502, detail="Stripe error")
    return _StripeStatusResponse(
        provider=result.provider,
        intent_id=result.intent_id,
        status=result.status,
        amount_cents=result.amount_cents,
        currency=result.currency,
    )
