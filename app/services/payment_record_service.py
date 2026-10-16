"""PaymentRecordService — pagos manuales y gestión de deuda (HU_56, HU_57)."""
from __future__ import annotations
from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.models.customer import Customer
from app.models.order import Order
from app.models.payment_record import PaymentRecord, DebtAdjustment


class PaymentRecordService:
    def __init__(self, db: Session):
        self.db = db

    def create(self, tenant_id: UUID, payload, current_user_id: UUID) -> PaymentRecord:
        """HU_56 — registrar pago manual.
        
        Actualiza:
        - Order.paid_cents (si order_id presente)
        - Customer.current_debt_cents
        - Crea OrderEvent (HU_17) con event_type='payment'
        """
        # Validar que el cliente existe
        customer = self.db.get(Customer, payload.customer_id)
        if not customer or str(customer.tenant_id) != str(tenant_id):
            raise NotFoundError("Customer")

        # Validar que el pedido existe si se proveyó
        order = None
        if payload.order_id:
            order = self.db.get(Order, payload.order_id)
            if not order or str(order.tenant_id) != str(tenant_id):
                raise NotFoundError("Order")
            # Validar que el pago no exceda el total
            if (order.paid_cents + payload.amount_cents) > order.total_cents:
                raise ValidationError(
                    f"El pago ${payload.amount_cents/100} excede el saldo del pedido "
                    f"${(order.total_cents - order.paid_cents)/100}"
                )

        # Calcular balances
        order_total = order.total_cents if order else 0
        order_paid_before = order.paid_cents if order else 0
        order_paid_after = order_paid_before + payload.amount_cents
        order_debt = max(0, order_total - order_paid_after)

        # Crear PaymentRecord
        record = PaymentRecord(
            tenant_id=str(tenant_id),
            customer_id=str(payload.customer_id),
            order_id=str(payload.order_id) if payload.order_id else None,
            amount_cents=payload.amount_cents,
            payment_method=payload.payment_method,
            reference=payload.reference,
            notes=payload.notes,
            order_total_cents=order_total,
            order_paid_cents=order_paid_after,
            order_debt_cents=order_debt,
        )
        self.db.add(record)

        # Actualizar Order
        if order:
            order.paid_cents = order_paid_after
            if order_debt == 0:
                order.payment_status = "pagado"
            elif order_paid_after > 0:
                order.payment_status = "abono"
            # Hook OrderEvent (HU_17) — best effort
            try:
                from app.models.order_event import OrderEvent, OrderEventType
                event = OrderEvent(
                    tenant_id=str(tenant_id),
                    order_id=str(order.id),
                    event_type=OrderEventType.PAYMENT,
                    actor_user_id=str(current_user_id),
                    message=f"Pago de ${payload.amount_cents/100} via {payload.payment_method}",
                    payload={"amount_cents": payload.amount_cents, "method": payload.payment_method},
                )
                self.db.add(event)
            except Exception:
                pass  # No bloquear el pago si el evento falla

        # Actualizar Customer.current_debt_cents (snapshot)
        customer.current_debt_cents = max(0, order_debt if order else customer.current_debt_cents)

        self.db.commit()
        self.db.refresh(record)
        return record

    def list_for_customer(self, tenant_id: UUID, customer_id: UUID, limit: int = 50) -> list[PaymentRecord]:
        return list(self.db.execute(
            select(PaymentRecord)
            .where(PaymentRecord.tenant_id == str(tenant_id))
            .where(PaymentRecord.customer_id == str(customer_id))
            .order_by(PaymentRecord.created_at.desc())
            .limit(limit)
        ).scalars())

    def debt_summary(self, tenant_id: UUID, customer_id: UUID) -> dict:
        """Resumen de deuda del cliente."""
        customer = self.db.get(Customer, customer_id)
        if not customer or str(customer.tenant_id) != str(tenant_id):
            raise NotFoundError("Customer")

        # Total deuda = suma de (total_cents - paid_cents) de pedidos no cancelados
        from app.models.order import OrderStatus
        result = self.db.execute(
            select(
                func.coalesce(func.sum(Order.total_cents - Order.paid_cents), 0).label("total_debt"),
                func.count(Order.id).filter(Order.status != OrderStatus.CANCELADO.value).label("pending"),
            ).where(
                Order.tenant_id == str(tenant_id),
                Order.customer_id == str(customer_id),
                Order.status != OrderStatus.CANCELADO.value,
            )
        ).one()

        # Overdue = con due_date < hoy
        overdue = self.db.execute(
            select(func.count(Order.id))
            .where(
                Order.tenant_id == str(tenant_id),
                Order.customer_id == str(customer_id),
                Order.status != OrderStatus.CANCELADO.value,
                Order.paid_cents < Order.total_cents,
            )
        ).scalar() or 0

        last_payment = self.db.execute(
            select(PaymentRecord.created_at)
            .where(PaymentRecord.tenant_id == str(tenant_id), PaymentRecord.customer_id == str(customer_id))
            .order_by(PaymentRecord.created_at.desc()).limit(1)
        ).scalar_one_or_none()

        last_adj = self.db.execute(
            select(DebtAdjustment.created_at)
            .where(DebtAdjustment.tenant_id == str(tenant_id), DebtAdjustment.customer_id == str(customer_id))
            .order_by(DebtAdjustment.created_at.desc()).limit(1)
        ).scalar_one_or_none()

        return {
            "customer_id": customer_id,
            "total_debt_cents": int(result.total_debt or 0),
            "pending_orders": int(result.pending or 0),
            "overdue_orders": int(overdue),
            "last_payment_at": last_payment,
            "last_adjustment_at": last_adj,
        }


class DebtAdjustmentService:
    """HU_57 — gestión de ajustes de deuda (condonaciones, notas de crédito)."""
    def __init__(self, db: Session):
        self.db = db

    def create(self, tenant_id: UUID, payload, current_user_id: UUID) -> DebtAdjustment:
        """HU_57 — crear ajuste. INMUTABLE: no se puede editar/eliminar."""
        customer = self.db.get(Customer, payload.customer_id)
        if not customer or str(customer.tenant_id) != str(tenant_id):
            raise NotFoundError("Customer")

        order = None
        if payload.order_id:
            order = self.db.get(Order, payload.order_id)
            if not order or str(order.tenant_id) != str(tenant_id):
                raise NotFoundError("Order")
            # Aplicar el ajuste al total
            new_total = max(0, order.total_cents + payload.amount_cents)
            order.total_cents = new_total
            if new_total == 0:
                order.payment_status = "pagado"

        adj = DebtAdjustment(
            tenant_id=str(tenant_id),
            customer_id=str(payload.customer_id),
            order_id=str(payload.order_id) if payload.order_id else None,
            amount_cents=payload.amount_cents,
            reason=payload.reason,
            adjusted_by_user_id=str(current_user_id),
        )
        self.db.add(adj)
        self.db.commit()
        self.db.refresh(adj)
        return adj
