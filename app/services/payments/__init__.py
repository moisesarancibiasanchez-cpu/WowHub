"""Subpaquete `app.services.payments` — HU_23 pasarela unificada.

Reglas (DoD Mínimo):
- NO mover `app/services/payment_service.py` (sigue siendo la integración
  legacy con MercadoPago / manual). Este subpaquete es ADICIONAL.
- La factory `get_provider(name)` selecciona el provider por nombre
  (`"mock"` o `"stripe"`).
- `get_provider` resuelve la configuración desde `app.config.settings`
  para mantener una única fuente de verdad.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from app.services.payments.base import PaymentIntentResult, PaymentProvider

__all__ = [
    "PaymentIntentResult",
    "PaymentProvider",
    "get_provider",
]


def get_provider(name: str) -> PaymentProvider:
    """Factory de `PaymentProvider`.

    Parameters
    ----------
    name : str
        `"mock"` | `"stripe"`. Cualquier otro valor → Mock con warning.

    Returns
    -------
    PaymentProvider
        Instancia del provider pedido. La instancia NO se cachea porque
        `StripeProvider` puede recibir configuración lazy y queremos
        poder re-leer `settings` en cada llamada (importante en tests).
    """
    key = (name or "").strip().lower()

    if key == "mock":
        from app.services.payments.mock_service import MockProvider
        return MockProvider()

    if key == "stripe":
        from app.config import settings
        from app.services.payments.stripe_service import StripeProvider
        return StripeProvider(
            secret_key=settings.stripe_secret_key,
            webhook_secret=settings.stripe_webhook_secret,
        )

    # Fallback seguro: cualquier nombre desconocido → Mock.
    import logging
    logging.getLogger("wowhub.payments").warning(
        "get_provider('%s') desconocido — fallback a MockProvider", name
    )
    from app.services.payments.mock_service import MockProvider
    return MockProvider()


# Import lazy helpers — sólo para type checkers (no se ejecuta en runtime).
if TYPE_CHECKING:  # pragma: no cover
    from app.services.payments.mock_service import MockProvider  # noqa: F401
    from app.services.payments.stripe_service import StripeProvider  # noqa: F401