"""StripeProvider — implementación real de `PaymentProvider` con Stripe SDK.

HU_23: pasarela de pagos unificada — adapter de Stripe.

Reglas (DoD Mínimo):
- `import stripe` se hace DENTRO de cada método (no a nivel de módulo).
  Si el SDK no está instalado, sólo fallan las llamadas a Stripe; el resto
  de WowHub sigue funcionando.
- Si `STRIPE_SECRET_KEY` no está configurado, `create_payment_intent` /
  `confirm_payment` / `refund` fallan a `MockProvider` (fail-open para
  desarrollo). El webhook handler (`handle_webhook`) NO es fail-open:
  si falta el secret, lanza `ValueError` para que el endpoint devuelva
  503 (defensa explícita — un webhook sin verificación de firma es un
  riesgo de seguridad real).
- Maneja PaymentIntent, Refund y eventos firmados vía `Webhook.construct_event`.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from app.services.payments.base import PaymentIntentResult, PaymentProvider

logger = logging.getLogger("wowhub.payments.stripe")


class StripeProvider(PaymentProvider):
    """Provider Stripe — usa SDK oficial `stripe>=8.0` con import lazy."""

    name = "stripe"

    def __init__(
        self,
        *,
        secret_key: Optional[str] = None,
        webhook_secret: Optional[str] = None,
    ) -> None:
        self._secret_key = secret_key
        self._webhook_secret = webhook_secret

    # ── helpers ───────────────────────────────────────────────
    def _import_stripe(self):
        """Import lazy del SDK. Falla con RuntimeError claro si no está."""
        try:
            import stripe  # type: ignore
        except ImportError as e:
            raise RuntimeError(
                "El SDK `stripe` no está instalado. Agregá `stripe>=8.0` a "
                "requirements.txt para usar StripeProvider."
            ) from e
        return stripe

    def _ensure_configured(self) -> str:
        """Devuelve la secret_key o lanza RuntimeError (no es fail-open aquí)."""
        if not self._secret_key:
            raise RuntimeError(
                "STRIPE_SECRET_KEY no está configurado. "
                "Defina la variable de entorno o use get_provider('mock') en su lugar."
            )
        return self._secret_key

    # ── overrides de PaymentProvider ──────────────────────────
    def create_payment_intent(
        self,
        amount_cents: int,
        currency: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> PaymentIntentResult:
        # Fail-open a Mock si no hay secret_key (dev/test friendly)
        if not self._secret_key:
            logger.warning(
                "StripeProvider.create_payment_intent sin STRIPE_SECRET_KEY — "
                "fallback a MockProvider (dev)"
            )
            from app.services.payments.mock_service import MockProvider
            return MockProvider().create_payment_intent(amount_cents, currency, metadata)

        stripe = self._import_stripe()
        try:
            stripe.api_key = self._secret_key
            meta = dict(metadata or {})
            intent = stripe.PaymentIntent.create(
                amount=int(amount_cents),
                currency=(currency or "usd").lower(),
                metadata=meta,
                automatic_payment_methods={"enabled": True},
            )
            return PaymentIntentResult(
                provider=self.name,
                intent_id=intent["id"],
                client_secret=intent.get("client_secret"),
                init_point=None,
                amount_cents=int(amount_cents),
                currency=(currency or "usd").lower(),
                status=intent.get("status", "requires_payment_method"),
                raw=dict(intent),
            )
        except Exception as e:
            # No rompemos el flujo: el caller puede decidir qué hacer.
            # Devolvemos un PaymentIntentResult con status="error" para
            # mantener el contrato (siempre devolver el dataclass, no raise).
            logger.exception("Stripe create_payment_intent failed: %s", e)
            return PaymentIntentResult(
                provider=self.name,
                intent_id=f"err_{int(__import__('time').time())}",
                client_secret=None,
                init_point=None,
                amount_cents=int(amount_cents),
                currency=(currency or "usd").lower(),
                status="error",
                raw={"error": str(e)},
            )

    def confirm_payment(self, payment_intent_id: str) -> PaymentIntentResult:
        if not self._secret_key:
            logger.warning(
                "StripeProvider.confirm_payment sin STRIPE_SECRET_KEY — fallback a Mock"
            )
            from app.services.payments.mock_service import MockProvider
            return MockProvider().confirm_payment(payment_intent_id)

        stripe = self._import_stripe()
        try:
            stripe.api_key = self._secret_key
            intent = stripe.PaymentIntent.retrieve(payment_intent_id)
            amount = int(intent.get("amount") or 0)
            return PaymentIntentResult(
                provider=self.name,
                intent_id=payment_intent_id,
                client_secret=intent.get("client_secret"),
                init_point=None,
                amount_cents=amount,
                currency=str(intent.get("currency") or "usd"),
                status=str(intent.get("status") or "unknown"),
                raw=dict(intent),
            )
        except Exception as e:
            logger.exception("Stripe confirm_payment failed: %s", e)
            return PaymentIntentResult(
                provider=self.name,
                intent_id=payment_intent_id,
                status="error",
                raw={"error": str(e)},
            )

    def refund(
        self,
        payment_intent_id: str,
        amount_cents: Optional[int] = None,
    ) -> Dict[str, Any]:
        if not self._secret_key:
            logger.warning("StripeProvider.refund sin STRIPE_SECRET_KEY — fallback a Mock")
            from app.services.payments.mock_service import MockProvider
            return MockProvider().refund(payment_intent_id, amount_cents)

        stripe = self._import_stripe()
        try:
            stripe.api_key = self._secret_key
            params: Dict[str, Any] = {"payment_intent": payment_intent_id}
            if amount_cents is not None and int(amount_cents) > 0:
                params["amount"] = int(amount_cents)
            r = stripe.Refund.create(**params)
            return {
                "ok": True,
                "refund_id": str(r.get("id")),
                "status": str(r.get("status") or "pending"),
                "raw": dict(r),
            }
        except Exception as e:
            logger.exception("Stripe refund failed: %s", e)
            return {
                "ok": False,
                "refund_id": None,
                "status": "error",
                "raw": {"error": str(e)},
            }

    def handle_webhook(self, payload: bytes, signature: str) -> Dict[str, Any]:
        """Verifica firma y parsea el evento.

        Raises
        ------
        ValueError
            Si falta `stripe_webhook_secret` o la firma es inválida
            (deja que el endpoint devuelva 503 / 400 respectivamente).
        """
        if not self._webhook_secret:
            raise ValueError(
                "STRIPE_WEBHOOK_SECRET no está configurado — webhook rechazado. "
                "Defina la variable de entorno para habilitar webhooks."
            )
        if not signature:
            raise ValueError("Falta header Stripe-Signature")

        stripe = self._import_stripe()
        try:
            event = stripe.Webhook.construct_event(
                payload, signature, self._webhook_secret
            )
        except Exception as e:
            # `stripe.error.SignatureVerificationError` cae acá también.
            logger.warning("Stripe webhook signature inválida: %s", e)
            raise ValueError(f"Firma inválida: {e}") from e

        data: Dict[str, Any] = event.get("data", {}) or {}
        obj = data.get("object") or {}
        return {
            "type": str(event.get("type") or "unknown"),
            "intent_id": obj.get("id") if obj else event.get("id"),
            "status": obj.get("status") if obj else None,
            "amount": obj.get("amount") if obj else None,
            "currency": obj.get("currency") if obj else None,
            "raw": dict(event),
        }