"""HU_23 — Stripe pasarela de pagos unificada — tests mínimos.

Cobertura (DoD Mínimo):
1. `test_mock_provider_default`           — get_provider("mock") funciona
2. `test_stripe_provider_no_key`          — sin STRIPE_SECRET_KEY usa Mock
3. `test_endpoint_intent_no_auth`         — POST /payments/stripe/intent sin auth → 401
4. `test_webhook_no_secret`               — POST /webhook/stripe sin secret → 503

Reglas:
- NO tocar `tests/conftest.py` (fixture ya está preparado por el resto de
  la suite). `conftest` desactiva rate limit y audit, y resetea la DB.
- Estos tests son independientes: no requieren credenciales Stripe reales.
"""
from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.payments import get_provider
from app.services.payments.base import PaymentProvider
from app.services.payments.mock_service import MockProvider


# ── Test 1: get_provider("mock") devuelve MockProvider ───────────
def test_mock_provider_default():
    """`get_provider("mock")` debe devolver un MockProvider funcional."""
    provider = get_provider("mock")
    assert isinstance(provider, MockProvider)
    assert isinstance(provider, PaymentProvider)
    assert provider.name == "mock"

    # Smoke test: create_payment_intent devuelve un PaymentIntentResult válido
    result = provider.create_payment_intent(
        amount_cents=2599, currency="usd", metadata={"order_id": "test-1"}
    )
    assert result.provider == "mock"
    assert result.intent_id.startswith("mock_pi_")
    assert result.amount_cents == 2599
    assert result.currency == "usd"
    assert result.status == "succeeded"


# ── Test 2: get_provider("stripe") sin STRIPE_SECRET_KEY → Mock ───
def test_stripe_provider_no_key(monkeypatch):
    """Sin STRIPE_SECRET_KEY, StripeProvider cae transparente a Mock."""
    # Forzar entorno limpio: sin secret_key, sin webhook_secret
    monkeypatch.setattr(
        "app.config.settings.stripe_secret_key", None, raising=False
    )
    monkeypatch.setattr(
        "app.config.settings.stripe_webhook_secret", None, raising=False
    )

    provider = get_provider("stripe")
    # El factory devuelve SIEMPRE un StripeProvider (sin secretos seteados
    # no debe tocar Stripe SDK); el comportamiento fail-open ocurre DENTRO
    # de los métodos, no en la factory.
    from app.services.payments.stripe_service import StripeProvider
    assert isinstance(provider, StripeProvider)

    # create_payment_intent sin key → fallback a MockProvider
    result = provider.create_payment_intent(
        amount_cents=1000, currency="eur", metadata={"order_id": "abc"}
    )
    assert result.provider == "mock"  # ← el fail-open devuelve mock
    assert result.intent_id.startswith("mock_pi_")
    assert result.amount_cents == 1000
    assert result.currency == "eur"

    # refund sin key → fallback a Mock
    refund_resp = provider.refund(payment_intent_id=result.intent_id)
    assert refund_resp["ok"] is True
    assert refund_resp["status"] == "succeeded"

    # handle_webhook sin secret → ValueError explícito (no es fail-open)
    with pytest.raises(ValueError):
        provider.handle_webhook(b'{"type":"payment_intent.succeeded"}', signature="")


# ── Test 3: POST /payments/stripe/intent sin auth → 401 ───────────
def test_endpoint_intent_no_auth():
    """El endpoint nuevo debe exigir auth (igual que /mercadopago)."""
    # Forzar ausencia de secret key para que el provider sea Mock (no toca red)
    os.environ.pop("STRIPE_SECRET_KEY", None)

    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/tenants/00000000-0000-0000-0000-000000000001/payments/stripe/intent",
            json={"amount_cents": 1000, "currency": "usd"},
        )
        # Sin Authorization header → 401 Unauthorized (regla de get_current_user)
    assert resp.status_code == 401, f"esperado 401, obtenido {resp.status_code}: {resp.text}"


# ── Test 4: POST /webhook/stripe sin STRIPE_WEBHOOK_SECRET → 503 ──
def test_webhook_no_secret(monkeypatch):
    """Sin STRIPE_WEBHOOK_SECRET, el endpoint devuelve 503 explícito."""
    monkeypatch.setattr(
        "app.config.settings.stripe_webhook_secret", None, raising=False
    )

    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/webhook/stripe",
            content=b'{"type":"payment_intent.succeeded"}',
            headers={"Content-Type": "application/json", "Stripe-Signature": "t=1,v1=invalid"},
        )
    assert resp.status_code == 503, f"esperado 503, obtenido {resp.status_code}: {resp.text}"
    body = resp.json()
    assert body.get("code") == "stripe_webhook_disabled"
    assert "STRIPE_WEBHOOK_SECRET" in body.get("detail", "")