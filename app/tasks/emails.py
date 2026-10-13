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

    FIX 2026-10: antes era un bucle que solo incrementaba ``sent`` sin
    enviar nada. Ahora:
      1) Abre sesion de DB y carga Customer por id
      3) Llama ``send_single_email.send()`` por recipient_id
      4) Devuelve sent/failed contadores reales

    Para leer el objeto Campaign y renderizar la plantilla Jinja2 desde la
    DB, ver follow-up. Aqui asumimos subject/body_html ya resueltos.

    Args:
        campaign_id: UUID del objeto Campaign en la DB.
        recipient_ids: Lista de IDs de clientes (Customer.id) a enviar.
        subject: Override del asunto (opcional).
        body_html: Override del cuerpo HTML (opcional).

    Returns:
        Dict con campaign_id, enviados, fallidos.
    """
    logger.info(
        "send_campaign started - campaign=%s, recipients=%d",
        campaign_id,
        len(recipient_ids),
    )
    try:
        from app.database import SessionLocal
        from app.models.customer import Customer

        sent = 0
        failed = 0

        eff_subject = subject or ("WowHub - Campana " + campaign_id[:8])
        eff_body = body_html or "<p>Hola! Gracias por ser parte de WowHub.</p>"

        with SessionLocal() as db:
            for rid in recipient_ids:
                try:
                    customer = db.get(Customer, rid)
                    if not customer or not getattr(customer, "email", None):
                        failed += 1
                        continue
                    send_single_email.send(
                        to_email=customer.email,
                        subject=eff_subject,
                        body_html=eff_body,
                        body_text=None,
                        tenant_id=getattr(customer, "tenant_id", None),
                    )
                    sent += 1
                except Exception as exc:  # noqa: BLE001 - defensivo
                    logger.warning(
                        "send_campaign - fallo envio a customer=%s: %s",
                        rid, exc,
                    )
                    failed += 1

        result = {"campaign_id": campaign_id, "sent": sent, "failed": failed}
        logger.info(
            "send_campaign done - campaign=%s, sent=%d, failed=%d",
            campaign_id, sent, failed,
        )
        return result

    except Exception as exc:
        logger.error(
            "send_campaign failed - campaign=%s, error=%s",
            campaign_id, exc,
        )
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

    FIX 2026-10: antes era placeholder que solo renderizaba el template y
    descartaba el resultado. Ahora envia via ``EmailService`` por cada
    recipient (mismo backend que ``send_single_email``).

    Args:
        tenant_id: ID del tenant.
        recipients: Lista de dicts [{email, name, vars}, ...].
        subject: Asunto comun.
        body_html: Cuerpo HTML (soporta {{variable}} Jinja2).

    Returns:
        {"sent": N, "failed": M}.
    """
    from jinja2 import Template

    logger.info(
        "send_bulk_raw - tenant=%d, recipients=%d",
        tenant_id, len(recipients),
    )

    sent = 0
    failed = 0
    tmpl = Template(body_html)

    # Lazy import: EmailService carga SMTP/Resend/etc. que pueden no estar
    # disponibles en CI. Se importa una sola vez.
    from app.services.email_service import EmailService
    svc = EmailService()

    for r in recipients:
        to_email = r.get("email") if isinstance(r, dict) else None
        if not to_email:
            failed += 1
            continue
        try:
            rendered = tmpl.render(**(r.get("vars", {}) if isinstance(r, dict) else {}))
            ok = svc._backend_send_sync(
                to=to_email,
                subject=subject,
                html=rendered,
                text=None,
            )
            if ok:
                sent += 1
            else:
                failed += 1
        except Exception as exc:  # noqa: BLE001 - defensivo
            logger.warning(
                "send_bulk_raw - fallo envio a %s: %s",
                to_email, exc,
            )
            failed += 1

    logger.info(
        "send_bulk_raw done - tenant=%d, sent=%d, failed=%d",
        tenant_id, sent, failed,
    )
    return {"tenant_id": tenant_id, "sent": sent, "failed": failed}
