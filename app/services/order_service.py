"""OrderService — gestión de pedidos: state machine, items, totales."""
from __future__ import annotations
import secrets
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.models.customer import Customer
from app.models.order import Order, OrderItem, OrderStatus
from app.models.product import Product
from app.models.tenant import Tenant


# State machine de OrderStatus
TRANSITIONS = {
    OrderStatus.PENDING: {OrderStatus.CONFIRMED, OrderStatus.CANCELED},
    OrderStatus.CONFIRMED: {OrderStatus.PREPARING, OrderStatus.CANCELED},
    OrderStatus.PREPARING: {OrderStatus.READY, OrderStatus.CANCELED},
    OrderStatus.READY: {OrderStatus.DELIVERED, OrderStatus.CANCELED},
    OrderStatus.DELIVERED: set(),  # terminal
    OrderStatus.CANCELED: set(),   # terminal
}


def generate_order_number(tenant: Tenant) -> str:
    """Genera número amigable por tenant: ORD-YYYYMMDD-XXXX."""
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    suffix = secrets.token_hex(2).upper()
    return f"ORD-{today}-{tenant.slug[:4].upper()}-{suffix}"


class OrderService:
    def __init__(self, db: Session):
        self.db = db

    def list(
        self, tenant_id: UUID, *, status: Optional[OrderStatus] = None,
        page: int = 1, page_size: int = 20,
    ):
        from app.schemas.common import Page
        from app.schemas.order import OrderListItem

        page, page_size = max(1, page), max(1, min(200, page_size))
        offset = (page - 1) * page_size

        q = select(Order).where(Order.tenant_id == str(tenant_id))
        if status:
            q = q.where(Order.status == status)
        q = q.order_by(Order.created_at.desc())

        # total
        from sqlalchemy import func
        total = self.db.execute(
            select(func.count()).select_from(q.subquery())
        ).scalar() or 0
        q = q.offset(offset).limit(page_size)

        orders = list(self.db.execute(q).scalars())
        items = [self._to_list_item(o) for o in orders]
        return Page.build(items, total, page, page_size)

    def get(self, tenant_id: UUID, order_id: UUID) -> Order:
        o = self.db.get(Order, order_id)
        if not o or o.tenant_id != tenant_id:
            raise NotFoundError("Pedido")
        return o

    def get_by_number(self, tenant_id: UUID, number: str) -> Order:
        o = self.db.execute(
            select(Order).where(
                Order.tenant_id == str(tenant_id),
                Order.number == number,
            )
        ).scalar_one_or_none()
        if not o:
            raise NotFoundError("Pedido")
        return o

    def create(
        self, tenant: Tenant, *,
        items: list[dict],
        customer_id: Optional[UUID] = None,
        customer_name: Optional[str] = None,
        customer_phone: Optional[str] = None,
        customer_email: Optional[str] = None,
        shipping_address: Optional[str] = None,
        notes: Optional[str] = None,
        source: str = "web",
        qr_code_id: Optional[UUID] = None,
        promotion_codes: Optional[list[str]] = None,
    ) -> Order:
        """Crea una orden con snapshot de productos.

        `items` = [{"product_id": UUID, "quantity": int, "options": dict?}, ...]
        """
        if not items:
            raise ValidationError("El pedido debe tener al menos un item")

        # Resolver/crear customer
        customer = None
        if customer_id:
            customer = self.db.get(Customer, customer_id)
            if not customer or customer.tenant_id != tenant.id:
                raise NotFoundError("Cliente")
        elif customer_email or customer_phone:
            # buscar o crear customer implícito
            q = select(Customer).where(Customer.tenant_id == str(tenant.id))
            if customer_email:
                q = q.where(Customer.email == customer_email.lower())
            elif customer_phone:
                q = q.where(Customer.phone == customer_phone)
            customer = self.db.execute(q).scalar_one_or_none()
            if not customer and (customer_name and (customer_email or customer_phone)):
                customer = Customer(
                    tenant_id=str(tenant.id),
                    full_name=customer_name,
                    email=customer_email.lower() if customer_email else None,
                    phone=customer_phone,
                )
                self.db.add(customer)
                self.db.flush()

        # Calcular totales
        order_items: list[OrderItem] = []
        subtotal = 0
        for it in items:
            pid = it["product_id"]
            qty = int(it.get("quantity", 1))
            if qty < 1:
                raise ValidationError(f"Cantidad inválida: {qty}")
            p = self.db.get(Product, pid)
            if not p or p.tenant_id != tenant.id:
                raise NotFoundError(f"Producto {pid}")
            if p.status.value not in ("active", "out_of_stock"):
                raise ValidationError(f"Producto {p.name} no disponible")
            line_total = p.price_cents * qty
            order_items.append(OrderItem(
                product_id=str(p.id),
                product_name=p.name,
                product_sku=p.sku,
                product_image=p.image_url,
                quantity=qty,
                unit_price_cents=p.price_cents,
                total_cents=line_total,
                options=it.get("options", {}),
            ))
            subtotal += line_total

        # Crear orden
        order = Order(
            tenant_id=str(tenant.id),
            number=generate_order_number(tenant),
            status=OrderStatus.PENDING,
            customer_id=str(customer.id) if customer else None,
            branch_id=None,
            subtotal_cents=subtotal,
            discount_cents=0,
            shipping_cents=0,
            tax_cents=0,
            total_cents=subtotal,
            currency=tenant.currency,
            customer_name=customer_name or (customer.full_name if customer else None),
            customer_phone=customer_phone or (customer.phone if customer else None),
            customer_email=customer_email or (customer.email if customer else None),
            shipping_address=shipping_address,
            notes=notes,
            source=source,
            qr_code_id=str(qr_code_id) if qr_code_id else None,
            items=order_items,
        )
        self.db.add(order)
        self.db.flush()

        # Aplicar promociones
        if promotion_codes:
            from app.services.promotion_engine import PromotionEngine
            engine = PromotionEngine(self.db)
            discount_cents = engine.apply_to_order(order, promotion_codes)
            order.discount_cents = discount_cents
            order.total_cents = max(0, subtotal + order.shipping_cents + order.tax_cents - discount_cents)

        # Descontar stock
        for oi in order_items:
            p = self.db.get(Product, UUID(oi.product_id))
            if p and p.track_inventory:
                p.stock = max(0, p.stock - oi.quantity)
                if p.stock == 0:
                    p.status = type(p.status).OUT_OF_STOCK if p.stock == 0 else p.status

        # Actualizar métricas del customer
        if customer:
            customer.total_orders += 1
            customer.total_spent_cents += order.total_cents
            customer.last_order_at = datetime.now(timezone.utc).isoformat()

            # Loyalty: 1 punto por cada 1000 cents gastados (configurable)
            try:
                from app.services.loyalty_service import LoyaltyService
                loyalty = LoyaltyService(self.db)
                loyalty.earn_points(customer, order)
            except Exception:
                pass

        # Métricas de productos
        for oi in order_items:
            p = self.db.get(Product, UUID(oi.product_id))
            if p:
                p.sold_count += oi.quantity

        self.db.commit()
        self.db.refresh(order)
        return order

    def transition(self, order: Order, new_status: OrderStatus) -> Order:
        allowed = TRANSITIONS.get(order.status, set())
        if new_status not in allowed:
            raise ConflictError(
                f"Transición inválida: {order.status.value} → {new_status.value}. "
                f"Estados permitidos: {[s.value for s in allowed]}"
            )
        order.status = new_status
        if new_status == OrderStatus.DELIVERED:
            order.updated_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(order)
        return order

    def cancel(self, order: Order, reason: Optional[str] = None) -> Order:
        if order.status in (OrderStatus.DELIVERED, OrderStatus.CANCELED):
            raise ConflictError(f"No se puede cancelar un pedido {order.status.value}")
        # Devolver stock
        for oi in order.items:
            p = self.db.get(Product, UUID(oi.product_id))
            if p and p.track_inventory:
                p.stock += oi.quantity
                if p.status.value == "out_of_stock" and p.stock > 0:
                    p.status = type(p.status).ACTIVE
        order.status = OrderStatus.CANCELED
        if reason:
            order.notes = (order.notes or "") + f"\n[CANCELADO: {reason}]"
        self.db.commit()
        self.db.refresh(order)
        return order

    @staticmethod
    def _to_list_item(o: Order):
        from app.schemas.order import OrderListItem
        return OrderListItem(
            id=o.id,
            tenant_id=UUID(o.tenant_id) if isinstance(o.tenant_id, str) else o.tenant_id,
            number=o.number,
            status=o.status,
            customer_name=o.customer_name,
            customer_email=o.customer_email,
            total_cents=o.total_cents,
            currency=o.currency,
            item_count=len(o.items or []),
            source=o.source,
            created_at=o.created_at,
        )
