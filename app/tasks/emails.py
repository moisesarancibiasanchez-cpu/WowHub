"""Email background tasks (Celery).

HU_36 — Cola emails: campañas de marketing, notificaciones transaccionales,
recordatorios de reserva, etc.

Enviar un email en segundo plano desde la API:
    from app.tasks.emails import send_campaign
    send_campaign.delay(campaign_id=str(campaign.id), recipient_ids=[...])
"""
import logging
from typing import Optional

from celery import Task

from app.celery_app import celery_app

logger = logging.getLogger("wowhub.tasks.emails")


@celery_app.task(bind=True, name="emails.send_campaign", max_retries=3)
def send_campaign(
    self: Task,
    campaign_id: str,
    recipient_ids: list[str],
    subject: Optional[str] = None,
    body_html: Optional[str] = None,
) -> dict:
    """Send email campaign in background.

    Args:
        campaign_id: UUID del objeto Campaign en la DB.
        recipient_ids: Lista de IDs de clientes (Customer.id) a quienes enviar.
        subject: Override del asunto (opcional, se lee de la campaña si no se pasa).
        body_html: Override del cuerpo HTML (opcional).

    Returns:
        Dict con campaign_id, enviados, fallidos.
    """
    logger.info(
        "send_campaign started — campaign=%s, recipients=%d",
        campaign_id,
        len(recipient_ids),
    )
    try:
        # TODO: integrar con email_service.py real del tenant
        # 1. Leer campaña de la DB (campaign_id)
        # 2. Para cada recipient_id → resolver email
        # 3. Renderizar plantilla con datos del cliente
        # 4. Enviar vía el email provider configurado
        # 5. Registrar delivery en notifications
        sent = 0
        failed = 0

        # Placeholder — reemplazar con lógica real:
        for rid in recipient_ids:
            try:
                # _send_single_email(rid, campaign_id, subject, body_html)
                sent += 1
            except Exception:
                failed += 1

        result = {"campaign_id": campaign_id, "sent": sent, "failed": failed}
        logger.info("send_campaign done — campaign=%s, sent=%d, failed=%d", campaign_id, sent, failed)
        return result

    except Exception as exc:
        logger.error("send_campaign failed — campaign=%s, error=%s", campaign_id, exc)
        raise self.retry(exc=exc, countdown=60)


@celery_app.task(bind=True, name="emails.send_single", max_retries=3)
def send_single_email(
    self: Task,
    to_email: str,
    subject: str,
    body_html: str,
    body_text: Optional[str] = None,
    tenant_id: Optional[int] = None,
    from_name: Optional[str] = None,
) -> dict:
    """Send a single transactional email in background.

    FIX 2026-09-27: era un placeholder que sólo logueaba
    `"Email sent (placeholder)"` y devolvía `{"ok": True}` sin enviar nada.
    Ahora delega en `EmailService`, que selecciona el backend real
    (resend / smtp / log / console) según `EMAIL_BACKEND`.

    `tenant_id` y `from_name` se aceptan por compatibilidad con llamadas
    previas, pero ya no son obligatorios.

    Returns:
        {"ok": True} o {"ok": False, "error": "..."}.
    """
    logger.info("send_single_email — to=%s, subject=%s", to_email, subject)
    try:
        from app.services.email_service import EmailService

        svc = EmailService()
        ok = svc._backend_send_sync(  # envío real, sin re-encolar
            to=to_email,
            subject=subject,
            html=body_html,
            text=body_text,
        )
        if not ok:
            raise RuntimeError(f"backend no pudo enviar a {to_email}")
        return {"ok": True, "to": to_email, "subject": subject}
    except Exception as exc:
        logger.error("send_single_email failed — to=%s, error=%s", to_email, exc)
        raise self.retry(exc=exc, countdown=30)


@celery_app.task(name="emails.send_bulk_raw")
def send_bulk_raw(
    tenant_id: int,
    recipients: list[dict],
    subject: str,
    body_html: str,
) -> dict:
    """Send the same email to a list of recipients (raw version, no campaign tracking).

    Args:
        tenant_id: ID del tenant.
        recipients: Lista de dicts [{email, name, vars}, ...].
        subject: Asunto común.
        body_html: Cuerpo HTML (soporta {{variable}} Jinja2).

    Returns:
        {"sent": N, "failed": M}.
    """
    from jinja2 import Template

    logger.info("send_bulk_raw — tenant=%d, recipients=%d", tenant_id, len(recipients))
    sent = 0
    failed = 0
    tmpl = Template(body_html)

    for r in recipients:
        try:
            rendered = tmpl.render(**(r.get("vars", {})))
            # TODO: call real email service
            _ = rendered  # placeholder
            sent += 1
        except Exception:
            failed += 1

    logger.info("send_bulk_raw done — sent=%d, failed=%d", sent, failed)
    return {"tenant_id": tenant_id, "sent": sent, "failed": failed}
