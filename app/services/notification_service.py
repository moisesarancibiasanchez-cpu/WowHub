"""NotificationService — envía notificaciones por múltiples canales (email, WhatsApp, push)."""
import logging
from typing import Optional
from uuid import UUID

from app.models.customer import Customer
from app.models.order import Order
from app.models.tenant import Tenant
from app.services.email_service import email_service

logger = logging.getLogger("wowhub.notification")


class NotificationService:
    """Facade para enviar notificaciones por email / WhatsApp / push."""

    def __init__(self, db=None):
        self.db = db

    def notify_order_created(self, tenant: Tenant, order: Order, customer: Optional[Customer] = None):
        """Notifica al tenant y al cliente que se creó una orden."""
        # Email al cliente
        if order.customer_email:
            total = f"{order.total_cents / 100:,.0f}" if order.currency == "CLP" else f"{order.total_cents / 100:,.2f}"
            try:
                email_service.send_order_confirmation(
                    to=order.customer_email,
                    order_number=order.number,
                    total=total,
                    currency=order.currency,
                )
            except Exception as e:
                logger.warning("No se pudo enviar email de confirmación: %s", e)
        # WhatsApp al tenant (vía wa.me link generado)
        # En producción, integrar con WhatsApp Business API
        logger.info("Orden %s creada, notificacion enviada", order.number)

    def notify_order_paid(self, tenant: Tenant, order: Order, customer: Optional[Customer] = None):
        if order.customer_email:
            total = f"{order.total_cents / 100:,.0f}" if order.currency == "CLP" else f"{order.total_cents / 100:,.2f}"
            try:
                email_service.send_order_paid(
                    to=order.customer_email,
                    order_number=order.number,
                    total=total,
                    currency=order.currency,
                )
            except Exception as e:
                logger.warning("No se pudo enviar email de pago: %s", e)

    def notify_booking_confirmed(self, customer_email: str, booking_id: str, when: str, where: str):
        try:
            email_service.send_booking_confirmation(
                to=customer_email, booking_id=booking_id, when=when, where=where,
            )
        except Exception as e:
            logger.warning("No se pudo enviar email de booking: %s", e)

    @staticmethod
    def build_whatsapp_url(phone: str, message: str) -> str:
        """Genera URL wa.me con mensaje pre-armado.

        phone: en formato internacional SIN '+' (ej: 56912345678)
        message: texto a enviar
        """
        # Limpiar phone
        digits = "".join(c for c in phone if c.isdigit())
        import urllib.parse
        return f"https://wa.me/{digits}?text={urllib.parse.quote(message)}"
