"""MockProvider — implementación de `PaymentProvider` para desarrollo y tests.

NO requiere API key ni SDKs externos. Devuelve SIEMPRE un intent
"succeeded" para que el flujo end-to-end pueda probarse sin tocar un
proveedor real.

Pensado para:
- Tests unitarios.
- Entornos de desarrollo sin credenciales.
- Fallback automático cuando `STRIPE_SECRET_KEY` no está configurado.
"""
from __future__ import annotations

import secrets
from typing import Any, Dict, Optional

from app.services.payments.base import PaymentIntentResult, PaymentProvider


class MockProvider(PaymentProvider):
    """Provider mock: no hace red, no requiere secretos."""

    name = "mock"

    # ── overrides requeridos por ABC ─────────────────────────
    def create_payment_intent(
        self,
        amount_cents: int,
        currency: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> PaymentIntentResult:
        token = secrets.token_urlsafe(12)
        intent_id = f"mock_pi_{token}"
        meta = dict(metadata or {})
        return PaymentIntentResult(
            provider=self.name,
            intent_id=intent_id,
            client_secret=f"{intent_id}_secret_{secrets.token_urlsafe(8)}",
            init_point=None,
            amount_cents=int(amount_cents),
            currency=(currency or "usd").lower(),
            status="succeeded",  # mock: siempre "ok" para tests E2E
            raw={"mock": True, "metadata": meta},
        )

    def confirm_payment(self, payment_intent_id: str) -> PaymentIntentResult:
        return PaymentIntentResult(
            provider=self.name,
            intent_id=payment_intent_id,
            client_secret=None,
            init_point=None,
            amount_cents=0,
            currency="usd",
            status="succeeded",
            raw={"mock": True},
        )

    def refund(
        self,
        payment_intent_id: str,
        amount_cents: Optional[int] = None,
    ) -> Dict[str, Any]:
        return {
            "ok": True,
            "refund_id": f"mock_re_{secrets.token_urlsafe(10)}",
            "status": "succeeded",
            "raw": {"mock": True, "intent_id": payment_intent_id, "amount_cents": amount_cents},
        }

    def handle_webhook(self, payload: bytes, signature: str) -> Dict[str, Any]:
        # Mock: ignora la firma. Si el caller quiere testear 400/503,
        # debe ejercitar el webhook de un provider real.
        return {
            "type": "mock.event",
            "intent_id": None,
            "status": "succeeded",
            "raw": payload.decode("utf-8", errors="replace")[:1024],
        }