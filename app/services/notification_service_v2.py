"""NotificationService v2 — plantillas y envío multicanal (HU_62, HU_63)."""
from __future__ import annotations
from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import select, and_
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, ValidationError
from app.models.customer import Customer
from app.models.notification import (
    NotificationTemplate, NotificationLog, NotificationEvent,
    NotificationChannel, NotificationStatus,
)


# 7 templates por defecto (de WowPrint db.settings — Épica E9, HU_62)
DEFAULT_TEMPLATES = {
    (NotificationEvent.QUOTE_SENT, NotificationChannel.WHATSAPP): 
        "Hola {cliente} 👋\n\nTe enviamos la cotización {cotizacion} de {empresa}.\n\nTotal: {total}\nValidez: {validez}\n\nSaludos,\n{empresa}",
    (NotificationEvent.ORDER_CONFIRMED, NotificationChannel.WHATSAPP):
        "Hola {cliente} 👋\n\n{empresa} confirma tu pedido {pedido}.\n\nEstado: {estado}\nTotal: {total}\n\nSi tienes consultas, escríbenos por este medio.\n\n{empresa}",
    (NotificationEvent.ORDER_READY, NotificationChannel.WHATSAPP):
        "Hola {cliente} 👋\n\nTu pedido {pedido} de {empresa} ya está listo para retiro o envío.\n\nTotal: {total}\n\n{empresa}",
    (NotificationEvent.ORDER_DELIVERED, NotificationChannel.WHATSAPP):
        "Hola {cliente} 👋\n\nTu pedido {pedido} de {empresa} ha sido entregado.\n\nEstado: {estado}\nTotal: {total}\n\nGracias por preferirnos.\n{empresa}",
    (NotificationEvent.PAYMENT_RECEIVED, NotificationChannel.WHATSAPP):
        "Hola {cliente} 👋\n\nConfirmamos tu pago de {total} en {empresa}.\n\nSaldo pendiente: {deuda}\n\n{empresa}",
    (NotificationEvent.DEBT_ADJUSTED, NotificationChannel.WHATSAPP):
        "Hola {cliente} 👋\n\n{empresa} aplicó un ajuste a tu cuenta: {detalle}\n\nNuevo saldo: {deuda}\n\n{empresa}",
    (NotificationEvent.PRODUCTION_DELAYED, NotificationChannel.WHATSAPP):
        "Hola {cliente} 👋\n\nTu pedido {pedido} de {empresa} está tomando más tiempo del esperado.\n\nNuevo plazo: {fecha}\nDisculpa las molestias.\n\n{empresa}",
}


class NotificationService:
    def __init__(self, db: Session):
        self.db = db

    def ensure_default_templates(self, tenant_id: UUID) -> int:
        """Crea los 7 templates default si no existen para el tenant.
        Llamado en onboarding."""
        created = 0
        for (event, channel), body in DEFAULT_TEMPLATES.items():
            existing = self.db.execute(
                select(NotificationTemplate).where(
                    and_(
                        NotificationTemplate.tenant_id == str(tenant_id),
                        NotificationTemplate.event == event.value,
                        NotificationTemplate.channel == channel.value,
                    )
                )
            ).scalar_one_or_none()
            if not existing:
                tpl = NotificationTemplate(
                    tenant_id=str(tenant_id),
                    event=event.value,
                    channel=channel.value,
                    template_body=body,
                    is_active=True,
                )
                self.db.add(tpl)
                created += 1
        if created:
            self.db.commit()
        return created

    def render_template(self, template_body: str, context: dict) -> str:
        """Renderiza un template con placeholders {cliente}, {pedido}, etc."""
        result = template_body
        for key, value in context.items():
            result = result.replace("{" + key + "}", str(value or ""))
        return result

    def get_template(self, tenant_id: UUID, event: NotificationEvent, 
                     channel: NotificationChannel) -> Optional[NotificationTemplate]:
        return self.db.execute(
            select(NotificationTemplate).where(
                and_(
                    NotificationTemplate.tenant_id == str(tenant_id),
                    NotificationTemplate.event == event.value,
                    NotificationTemplate.channel == channel.value,
                )
            )
        ).scalar_one_or_none()

    def list_templates(self, tenant_id: UUID) -> list[NotificationTemplate]:
        return list(self.db.execute(
            select(NotificationTemplate)
            .where(NotificationTemplate.tenant_id == str(tenant_id))
            .order_by(NotificationTemplate.event, NotificationTemplate.channel)
        ).scalars())

    def upsert_template(self, tenant_id: UUID, payload) -> NotificationTemplate:
        existing = self.get_template(tenant_id, payload.event, payload.channel)
        if existing:
            existing.template_body = payload.template_body
            existing.is_active = payload.is_active
            self.db.commit()
            self.db.refresh(existing)
            return existing
        tpl = NotificationTemplate(
            tenant_id=str(tenant_id),
            event=payload.event.value,
            channel=payload.channel.value,
            template_body=payload.template_body,
            is_active=payload.is_active,
        )
        self.db.add(tpl)
        self.db.commit()
        self.db.refresh(tpl)
        return tpl

    def send(self, tenant_id: UUID, payload) -> NotificationLog:
        """HU_62 + HU_63 — envía una notificación usando el template.
        
        Soporta fallback: si WhatsApp no está disponible, registra en log con
        contenido listo para enviar manualmente.
        """
        customer = self.db.get(Customer, payload.customer_id)
        if not customer or str(customer.tenant_id) != str(tenant_id):
            raise NotFoundError("Customer")

        tpl = self.get_template(tenant_id, payload.event, payload.channel)
        rendered = ""
        if tpl:
            context = {
                "cliente": customer.full_name,
                "empresa": "WowHub",
                **payload.context,
            }
            rendered = self.render_template(tpl.template_body, context)

        # Crear log
        log = NotificationLog(
            tenant_id=str(tenant_id),
            customer_id=str(payload.customer_id),
            order_id=str(payload.order_id) if payload.order_id else None,
            channel=payload.channel.value,
            event=payload.event.value,
            status=NotificationStatus.PENDING.value,
            content_rendered=rendered,
        )
        self.db.add(log)

        # HU_62: en producción real, aquí iría el dispatch a WhatsApp/Email.
        # Por ahora, registramos como SENT con el contenido pre-renderizado.
        # El frontend usa el contenido_rendered para wa.me links o mailto:
        log.status = NotificationStatus.SENT.value
        log.sent_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(log)
        return log

    def list_logs(self, tenant_id: UUID, customer_id: Optional[UUID] = None,
                  status: Optional[str] = None, limit: int = 50) -> list[NotificationLog]:
        q = select(NotificationLog).where(NotificationLog.tenant_id == str(tenant_id))
        if customer_id:
            q = q.where(NotificationLog.customer_id == str(customer_id))
        if status:
            q = q.where(NotificationLog.status == status)
        q = q.order_by(NotificationLog.created_at.desc()).limit(limit)
        return list(self.db.execute(q).scalars())
