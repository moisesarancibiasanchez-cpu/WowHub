"""LoyaltyService — sistema de puntos para clientes.

Reglas por defecto (configurables por tenant vía Tenant.settings):
- earn_rate: 1 punto por cada 100 cents gastados (default)
- redeem_rate: 100 puntos = 1000 cents de descuento (default)
"""
import logging
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.customer import Customer
from app.models.order import Order
from app.models.tenant import Tenant

logger = logging.getLogger("wowhub.loyalty")

DEFAULT_EARN_RATE = 1 / 100  # 1 punto por cada 100 cents
DEFAULT_REDEEM_RATE = 1000 / 100  # 1000 cents descuento por cada 100 puntos


class LoyaltyService:
    def __init__(self, db: Session):
        self.db = db

    def _rates(self, tenant: Tenant) -> tuple[float, float]:
        settings = tenant.settings or {}
        earn = float(settings.get("loyalty_earn_rate", DEFAULT_EARN_RATE))
        redeem = float(settings.get("loyalty_redeem_rate", DEFAULT_REDEEM_RATE))
        return earn, redeem

    def earn_points(self, customer: Customer, order: Order) -> int:
        """Otorga puntos al cliente por una orden pagada.

        Retorna los puntos otorgados.
        """
        tenant = self.db.get(Tenant, UUID(customer.tenant_id) if isinstance(customer.tenant_id, str) else customer.tenant_id)
        if not tenant:
            return 0
        earn_rate, _ = self._rates(tenant)
        points = int(order.total_cents * earn_rate)
        if points > 0:
            customer.points = (customer.points or 0) + points
            logger.info("Cliente %s ganó %d puntos (orden %s)", customer.id, points, order.number)
        return points

    def redeem_points(self, customer: Customer, points: int) -> int:
        """Canjea puntos por descuento. Retorna el descuento en centavos."""
        if points <= 0:
            return 0
        if (customer.points or 0) < points:
            raise ValueError("Puntos insuficientes")
        tenant = self.db.get(Tenant, UUID(customer.tenant_id) if isinstance(customer.tenant_id, str) else customer.tenant_id)
        if not tenant:
            return 0
        _, redeem_rate = self._rates(tenant)
        discount_cents = int(points * redeem_rate)
        customer.points = (customer.points or 0) - points
        return discount_cents

    def preview_redeem(self, customer: Customer, points: int) -> dict:
        """Preview de un canje sin aplicarlo."""
        if points <= 0 or (customer.points or 0) < points:
            return {"valid": False, "discount_cents": 0, "error": "Puntos insuficientes"}
        tenant = self.db.get(Tenant, UUID(customer.tenant_id) if isinstance(customer.tenant_id, str) else customer.tenant_id)
        if not tenant:
            return {"valid": False, "discount_cents": 0, "error": "Tenant no encontrado"}
        _, redeem_rate = self._rates(tenant)
        return {
            "valid": True,
            "discount_cents": int(points * redeem_rate),
            "remaining_points": (customer.points or 0) - points,
        }
