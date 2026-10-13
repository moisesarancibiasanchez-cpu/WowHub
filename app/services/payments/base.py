"""PaymentProvider — interface base (Adapter pattern).

HU_23: pasarela de pagos unificada. Esta ABC define el contrato que
toda implementación concreta (Mock, Stripe, ...) debe cumplir. La
selección del provider se hace vía `app.services.payments.get_provider(name)`.

NO importar SDKs externos en este módulo — la importación se hace dentro
de cada provider (lazy) para que un fallo de un SDK (p.ej. `stripe`) no
rompa el resto de la app.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class PaymentIntentResult:
    """Resultado normalizado de `create_payment_intent`.

    Cada provider mapea su respuesta nativa (Stripe PaymentIntent,
    MercadoPago preference, etc.) a esta estructura común.
    """

    provider: str                       # "mock" | "stripe" | ...
    intent_id: str                      # id externo (pi_xxx / preference_id / uuid mock)
    client_secret: Optional[str] = None  # para Stripe Elements / SDKs cliente
    init_point: Optional[str] = None      # URL para redirect (si aplica)
    amount_cents: int = 0
    currency: str = "usd"
    status: str = "pending"
    raw: Dict[str, Any] = field(default_factory=dict)


class PaymentProvider(ABC):
    """Interfaz base para todos los proveedores de pago.

    Las implementaciones deben:
    - No importar SDKs a nivel de módulo (sólo dentro de los métodos).
    - Ser `fail-open` a Mock si la configuración crítica falta (excepto
      webhooks, que deben rechazar con error claro).
    - Devolver SIEMPRE un `PaymentIntentResult` o lanzar una excepción
      tipada (no devolver strings mágicos).
    """

    #: Nombre corto del provider (lo usa `get_provider`).
    name: str = "abstract"

    @abstractmethod
    def create_payment_intent(
        self,
        amount_cents: int,
        currency: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> PaymentIntentResult:
        """Crea un intent/preference de pago.

        Parameters
        ----------
        amount_cents : int
            Monto en centavos (o unidad mínima). Stripe acepta centavos.
        currency : str
            Código ISO-4217 lowercase ("usd", "eur", "mxn", "clp", ...).
        metadata : dict, opcional
            Metadatos arbitrarios para round-trip en el webhook
            (p.ej. {"tenant_id": "...", "order_id": "..."}).
        """

    @abstractmethod
    def confirm_payment(self, payment_intent_id: str) -> PaymentIntentResult:
        """Confirma/consulta un intent existente y devuelve su estado."""

    @abstractmethod
    def refund(
        self,
        payment_intent_id: str,
        amount_cents: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Emite un refund (total o parcial).

        Devuelve un dict con al menos: ``{"ok": bool, "refund_id": str|None,
        "status": str, "raw": dict}``.
        """

    @abstractmethod
    def handle_webhook(self, payload: bytes, signature: str) -> Dict[str, Any]:
        """Procesa un webhook firmado.

        Parameters
        ----------
        payload : bytes
            Cuerpo crudo del request (NO JSON parseado).
        signature : str
            Header de firma (`Stripe-Signature`, etc.).

        Returns
        -------
        dict
            Estructura normalizada con al menos
            ``{"type": str, "intent_id": str|None, "status": str|None}``.

        Raises
        ------
        ValueError
            Si la firma es inválida o falta el secret configurado.
        """