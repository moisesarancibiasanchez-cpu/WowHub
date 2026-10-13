"""PromotionEngine — aplica promociones a un carrito/orden.

Soporta:
- PERCENT (% descuento)
- FIXED (monto fijo)
- BUY_X_GET_Y (2x1, 3x2)
- FREE_SHIPPING
- BUNDLE (placeholder, lógica custom)
"""
import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, ValidationError
from app.models.order import Order
from app.models.product import Product
from app.models.promotion import DiscountType, Promotion, PromotionType

logger = logging.getLogger("wowhub.promotion")


class AppliedDiscount:
    def __init__(self, promotion_id: UUID, name: str, amount_cents: int, kind: str):
        self.promotion_id = promotion_id
        self.name = name
        self.amount_cents = amount_cents
        self.kind = kind  # percent, fixed, bogo, free_shipping

    def to_dict(self):
        return {
            "promotion_id": str(self.promotion_id),
            "name": self.name,
            "amount_cents": self.amount_cents,
            "kind": self.kind,
        }


class PromotionEngine:
    def __init__(self, db: Session):
        self.db = db

    def list_active(self, tenant_id: UUID, *, public_only: bool = True) -> list[Promotion]:
        now = datetime.now(timezone.utc)
        q = select(Promotion).where(
            Promotion.tenant_id == str(tenant_id),
            Promotion.is_active == True,  # noqa: E712
        )
        if public_only:
            q = q.where(Promotion.is_public == True)  # noqa: E712
        promos = list(self.db.execute(q).scalars())
        # Filtrar por vigencia
        return [p for p in promos if self._is_valid_now(p, now)]

    def _is_valid_now(self, p: Promotion, now: datetime) -> bool:
        if p.starts_at and p.starts_at.replace(tzinfo=timezone.utc) > now:
            return False
        if p.ends_at and p.ends_at.replace(tzinfo=timezone.utc) < now:
            return False
        if p.usage_limit and p.used_count >= p.usage_limit:
            return False
        return True

    def validate_code(self, tenant_id: UUID, code: str) -> Promotion:
        p = self.db.execute(
            select(Promotion).where(
                Promotion.tenant_id == str(tenant_id),
                Promotion.code == code.upper(),
                Promotion.is_active == True,  # noqa: E712
            )
        ).scalar_one_or_none()
        if not p:
            raise NotFoundError("Cupón no válido")
        if not self._is_valid_now(p, datetime.now(timezone.utc)):
            raise ValidationError("Cupón expirado o agotado")
        return p

    def apply_to_order(self, order: Order, codes: list[str]) -> int:
        """Aplica una lista de códigos de promoción a una orden.

        Retorna el total de descuento en centavos.
        """
        if not codes:
            return 0
        total_discount = 0
        applied_ids: list[str] = []
        for code in codes:
            try:
                promo = self.validate_code(UUID(order.tenant_id) if isinstance(order.tenant_id, str) else order.tenant_id, code)
            except (NotFoundError, ValidationError) as e:
                logger.info("Cupón %s rechazado: %s", code, e)
                continue
            discount = self._compute_discount(promo, order)
            if discount > 0:
                total_discount += discount
                applied_ids.append(str(promo.id))
                promo.used_count += 1
        order.promotion_ids = applied_ids
        return total_discount

    def preview(self, tenant_id: UUID, items: list[dict], code: Optional[str] = None) -> dict:
        """Calcula un preview del descuento sin persistir.

        `items` = [{"product_id": UUID, "quantity": int, "unit_price_cents": int}, ...]
        """
        subtotal = sum(i["quantity"] * i["unit_price_cents"] for i in items)
        applied: list[dict] = []
        discount_total = 0
        if code:
            try:
                promo = self.validate_code(tenant_id, code)
            except Exception as e:
                return {"subtotal_cents": subtotal, "discount_cents": 0, "total_cents": subtotal, "applied": [], "error": str(e)}
            # Para preview construimos una "orden virtual"
            virtual = type("V", (), {
                "tenant_id": str(tenant_id),
                "subtotal_cents": subtotal,
                "promotion_ids": [],
                "items": [type("I", (), {
                    "product_id": str(i["product_id"]),
                    "quantity": i["quantity"],
                    "unit_price_cents": i["unit_price_cents"],
                    "total_cents": i["quantity"] * i["unit_price_cents"],
                })() for i in items],
            })()
            d = self._compute_discount(promo, virtual)
            applied.append({"code": code, "name": promo.name, "amount_cents": d})
            discount_total = d
        return {
            "subtotal_cents": subtotal,
            "discount_cents": discount_total,
            "total_cents": max(0, subtotal - discount_total),
            "applied": applied,
        }

    def _compute_discount(self, promo: Promotion, order) -> int:
        """Calcula el descuento (en centavos) que aplica esta promoción a la orden."""
        items = order.items if hasattr(order, "items") else []
        if not items:
            return 0

        # Verificar compra mínima
        if order.subtotal_cents < promo.min_purchase_cents:
            return 0

        # Filtrar items aplicables
        if not promo.applies_to_all:
            applicable_items = [it for it in items if str(it.product_id) in [str(pid) for pid in (promo.product_ids or [])]]
            if not applicable_items:
                return 0
        else:
            applicable_items = items

        applicable_subtotal = sum(it.total_cents for it in applicable_items)

        if promo.promo_type == PromotionType.PERCENT:
            discount = int(applicable_subtotal * (promo.discount_value / 100.0))
        elif promo.promo_type == PromotionType.FIXED:
            discount = min(promo.discount_value, applicable_subtotal)
        elif promo.promo_type == PromotionType.BUY_X_GET_Y:
            # Lógica simple: discount_value = X (comprar X), valor fijo = Y
            # Se interpreta como: por cada X unidades, 1 gratis a precio promedio
            x = max(2, promo.discount_value or 2)
            discount = self._compute_bogo(applicable_items, x)
        elif promo.promo_type == PromotionType.FREE_SHIPPING:
            # El descuento es el shipping (lo descuenta el order si tiene)
            discount = getattr(order, "shipping_cents", 0) or 0
        else:
            discount = 0

        # Cap por max_discount
        if promo.max_discount_cents and discount > promo.max_discount_cents:
            discount = promo.max_discount_cents

        return max(0, discount)

    def _compute_bogo(self, items: list, x: int) -> int:
        """Para buy_x_get_y: agrupa items por producto, cada X unidades paga X-1.
        El descuento es el precio del item más barato de cada grupo.
        """
        discount = 0
        for it in items:
            groups = it.quantity // x
            if groups > 0:
                discount += groups * it.unit_price_cents
        return discount
