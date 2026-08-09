"""PaymentService — procesamiento de pagos.

Soporta:
- MercadoPago (scaffold para integración real via SDK/API)
- Manual: transferencia, efectivo, tarjeta en entrega

El proveedor real se selecciona por env var PAYMENT_PROVIDER.
"""
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, ValidationError
from app.models.order import Order, OrderStatus
from app.models.payment import Payment, PaymentMethod, PaymentStatus
from app.models.tenant import Tenant

logger = logging.getLogger("wowhub.payment")


class PaymentService:
    def __init__(self, db: Session):
        self.db = db
        self.provider = os.getenv("PAYMENT_PROVIDER", "mercadopago")
        self.mp_access_token = os.getenv("MERCADOPAGO_ACCESS_TOKEN", "")
        self.mp_sandbox = os.getenv("MERCADOPAGO_SANDBOX", "true").lower() == "true"

    def list(self, tenant_id: UUID, *, status: Optional[PaymentStatus] = None,
             order_id: Optional[UUID] = None, page: int = 1, page_size: int = 20):
        from app.schemas.common import Page
        from app.schemas.payment import PaymentListItem
        from sqlalchemy import func

        page, page_size = max(1, page), max(1, min(200, page_size))
        offset = (page - 1) * page_size

        q = select(Payment).where(Payment.tenant_id == str(tenant_id))
        if status:
            q = q.where(Payment.status == status)
        if order_id:
            q = q.where(Payment.order_id == str(order_id))
        q = q.order_by(Payment.created_at.desc())

        total = self.db.execute(
            select(func.count()).select_from(q.subquery())
        ).scalar() or 0
        q = q.offset(offset).limit(page_size)

        items = list(self.db.execute(q).scalars())
        return Page.build(
            [PaymentListItem(
                id=p.id,
                order_id=UUID(p.order_id) if isinstance(p.order_id, str) else p.order_id,
                method=p.method,
                status=p.status,
                amount_cents=p.amount_cents,
                currency=p.currency,
                provider=p.provider,
                created_at=p.created_at,
            ) for p in items],
            total, page, page_size,
        )

    def get(self, tenant_id: UUID, payment_id: UUID) -> Payment:
        p = self.db.get(Payment, payment_id)
        if not p or p.tenant_id != tenant_id:
            raise NotFoundError("Pago")
        return p

    # ── Crear preferencia de pago (MercadoPago) ─────────
    def create_mercadopago_preference(self, tenant: Tenant, order: Order) -> Payment:
        """Crea una preference en MercadoPago y retorna el init_point para redirigir al cliente.

        En modo sandbox o sin token configurado, retorna un init_point mock para desarrollo.
        """
        if not self.mp_access_token:
            logger.warning("MERCADOPAGO_ACCESS_TOKEN no configurado — usando modo mock")
            return self._create_mock_payment(tenant, order, PaymentMethod.MERCADO_PAGO)

        try:
            base_url = "https://api.mercadopago.com"
            headers = {
                "Authorization": f"Bearer {self.mp_access_token}",
                "Content-Type": "application/json",
            }
            payload = {
                "items": [{
                    "title": f"Pedido {order.number}",
                    "quantity": 1,
                    "unit_price": order.total_cents / 100,
                    "currency_id": order.currency,
                }],
                "external_reference": str(order.id),
                "notification_url": f"{os.getenv('BASE_URL', 'http://localhost:8000')}/api/v1/payments/webhook/mercadopago",
                "back_urls": {
                    "success": f"{os.getenv('FRONT_URL', 'http://localhost:3000')}/orders/{order.number}?status=approved",
                    "failure": f"{os.getenv('FRONT_URL', 'http://localhost:3000')}/orders/{order.number}?status=rejected",
                    "pending": f"{os.getenv('FRONT_URL', 'http://localhost:3000')}/orders/{order.number}?status=pending",
                },
                "auto_return": "approved",
            }
            resp = httpx.post(
                f"{base_url}/checkout/preferences",
                json=payload, headers=headers, timeout=10.0,
            )
            if resp.status_code not in (200, 201):
                logger.error("MercadoPago error: %s %s", resp.status_code, resp.text)
                # Fallback a mock si falla
                return self._create_mock_payment(tenant, order, PaymentMethod.MERCADO_PAGO)

            data = resp.json()
            payment = Payment(
                tenant_id=str(tenant.id),
                order_id=str(order.id),
                method=PaymentMethod.MERCADO_PAGO,
                status=PaymentStatus.PENDING,
                amount_cents=order.total_cents,
                fee_cents=int(order.total_cents * 0.039),  # ~3.9% MP fee
                net_cents=order.total_cents - int(order.total_cents * 0.039),
                currency=order.currency,
                provider="mercadopago",
                provider_preference_id=data.get("id"),
                init_point=data.get("init_point"),
                sandbox_init_point=data.get("sandbox_init_point"),
                expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
                provider_response=data,
            )
            self.db.add(payment)
            self.db.commit()
            self.db.refresh(payment)
            return payment
        except Exception as e:
            logger.exception("Error creando preference MercadoPago: %s", e)
            return self._create_mock_payment(tenant, order, PaymentMethod.MERCADO_PAGO)

    def create_manual_payment(
        self, tenant: Tenant, order: Order,
        method: PaymentMethod = PaymentMethod.TRANSFER,
        notes: Optional[str] = None,
    ) -> Payment:
        """Crea un pago manual (transfer, cash, card_on_delivery).

        El tenant confirma el pago desde el dashboard (no hay webhooks).
        """
        if method not in (PaymentMethod.TRANSFER, PaymentMethod.CASH, PaymentMethod.CARD_ON_DELIVERY, PaymentMethod.OTHER):
            raise ValidationError(f"Método manual inválido: {method}")
        payment = Payment(
            tenant_id=str(tenant.id),
            order_id=str(order.id),
            method=method,
            status=PaymentStatus.PENDING,
            amount_cents=order.total_cents,
            currency=order.currency,
            provider="manual",
            notes=notes,
        )
        self.db.add(payment)
        self.db.commit()
        self.db.refresh(payment)
        return payment

    def confirm_manual(self, payment: Payment, *, paid: bool = True, notes: Optional[str] = None) -> Payment:
        """Confirma o rechaza un pago manual desde el dashboard."""
        if payment.status not in (PaymentStatus.PENDING,):
            raise ValidationError(f"Pago no está pendiente: {payment.status}")
        payment.status = PaymentStatus.PAID if paid else PaymentStatus.CANCELED
        if paid:
            payment.paid_at = datetime.now(timezone.utc)
            # Marcar orden como pagada
            order = self.db.get(Order, UUID(payment.order_id) if isinstance(payment.order_id, str) else payment.order_id)
            if order and order.status == OrderStatus.PENDING:
                order.status = OrderStatus.CONFIRMED
        if notes:
            payment.notes = (payment.notes or "") + f"\n[{('CONFIRMADO' if paid else 'RECHAZADO')}: {notes}]"
        self.db.commit()
        self.db.refresh(payment)
        return payment

    def _create_mock_payment(self, tenant: Tenant, order: Order, method: PaymentMethod) -> Payment:
        """Pago mock para desarrollo: no requiere API key real."""
        token = secrets.token_urlsafe(16)
        payment = Payment(
            tenant_id=str(tenant.id),
            order_id=str(order.id),
            method=method,
            status=PaymentStatus.PENDING,
            amount_cents=order.total_cents,
            fee_cents=0,
            net_cents=order.total_cents,
            currency=order.currency,
            provider="mercadopago_mock",
            provider_preference_id=f"mock_pref_{token}",
            init_point=f"{os.getenv('BASE_URL', 'http://localhost:8000')}/api/v1/payments/mock/{token}",
            sandbox_init_point=f"{os.getenv('BASE_URL', 'http://localhost:8000')}/api/v1/payments/mock/{token}",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
            provider_response={"mock": True, "note": "MERCADO_PAGO_ACCESS_TOKEN no configurado"},
        )
        self.db.add(payment)
        self.db.commit()
        self.db.refresh(payment)
        return payment

    def process_webhook(self, data: dict) -> bool:
        """Procesa webhook de MercadoPago. Retorna True si procesó un pago."""
        try:
            external_ref = data.get("external_reference")
            mp_status = data.get("status")
            payment_id = data.get("id")
            if not external_ref:
                logger.warning("Webhook MP sin external_reference: %s", data)
                return False

            payment = self.db.execute(
                select(Payment).where(
                    Payment.order_id == external_ref,
                    Payment.provider == "mercadopago",
                )
            ).scalars().first()
            if not payment:
                logger.warning("No se encontró Payment para order %s", external_ref)
                return False

            # Mapear status de MP
            status_map = {
                "approved": PaymentStatus.PAID,
                "authorized": PaymentStatus.AUTHORIZED,
                "pending": PaymentStatus.PENDING,
                "in_process": PaymentStatus.PENDING,
                "rejected": PaymentStatus.FAILED,
                "cancelled": PaymentStatus.CANCELED,
                "refunded": PaymentStatus.REFUNDED,
            }
            new_status = status_map.get(mp_status, PaymentStatus.PENDING)
            payment.status = new_status
            payment.provider_payment_id = str(payment_id) if payment_id else payment.provider_payment_id
            payment.provider_status_detail = data.get("status_detail")
            if data:
                payment.provider_response = {**payment.provider_response, **data}
            if new_status == PaymentStatus.PAID:
                payment.paid_at = datetime.now(timezone.utc)
                # Marcar orden como confirmada
                order = self.db.get(Order, UUID(payment.order_id) if isinstance(payment.order_id, str) else payment.order_id)
                if order and order.status == OrderStatus.PENDING:
                    order.status = OrderStatus.CONFIRMED
                    # Disparar webhook order.paid
                    try:
                        from app.services.webhook_service import WebhookDispatcher
                        WebhookDispatcher(self.db).dispatch(
                            tenant_id=payment.tenant_id,
                            event="order.paid",
                            payload={"order_id": str(order.id), "number": order.number, "total_cents": order.total_cents, "currency": order.currency},
                        )
                    except Exception as e:
                        logger.warning("Error disparando webhook: %s", e)
            self.db.commit()
            return True
        except Exception as e:
            logger.exception("Error procesando webhook MP: %s", e)
            return False
