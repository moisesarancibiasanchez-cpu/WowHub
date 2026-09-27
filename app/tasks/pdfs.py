"""PDF generation background tasks (Celery).

HU_36 — Cola pdfs: cotizaciones, facturas, reportes, vouchers.

Generar un PDF en segundo plano:
    from app.tasks.pdfs import generate_quote_pdf
    generate_quote_pdf.delay(quote_id=str(quote.id), tenant_id=tenant_id)
"""
import logging
from typing import Optional

from celery import Task

from app.celery_app import celery_app

logger = logging.getLogger("wowhub.tasks.pdfs")


@celery_app.task(bind=True, name="pdfs.generate_quote", max_retries=3)
def generate_quote_pdf(
    self: Task,
    quote_id: str,
    tenant_id: int,
    language: str = "es",
) -> dict:
    """Generate PDF of a Quote in background.

    Args:
        quote_id: UUID de la cotización.
        tenant_id: ID del tenant (para branding, logo, colores).
        language: Idioma de la plantilla ("es", "en", "pt").

    Returns:
        {"quote_id": ..., "pdf_url": "..."} o {"error": "..."}.
    """
    import tempfile
    from pathlib import Path

    logger.info("generate_quote_pdf — quote=%s, tenant=%d", quote_id, tenant_id)
    try:
        # TODO: implementar con reportlab o weasyprint
        # 1. Leer Quote de la DB
        # 2. Renderizar plantilla HTML con datos de la quote + tenant
        # 3. Convertir HTML → PDF (weasyprint o pdfkit)
        # 4. Subir a storage (S3 o local) → devolver URL pública
        #
        # Placeholder — crea un PDF mínimo temporal:
        # from reportlab.pdfgen import canvas
        # tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
        # p = canvas.Canvas(tmp.name)
        # p.drawString(100, 800, f"Quote: {quote_id}")
        # p.showPage()
        # p.save()
        # url = _upload_pdf(tenant_id, quote_id, Path(tmp.name))

        pdf_url = f"/storage/{tenant_id}/quotes/{quote_id}.pdf"
        logger.info("generate_quote_pdf done — quote=%s, url=%s", quote_id, pdf_url)
        return {"quote_id": quote_id, "pdf_url": pdf_url}

    except Exception as exc:
        logger.error("generate_quote_pdf failed — quote=%s, error=%s", quote_id, exc)
        raise self.retry(exc=exc, countdown=120)


@celery_app.task(bind=True, name="pdfs.generate_invoice", max_retries=3)
def generate_invoice_pdf(
    self: Task,
    order_id: str,
    tenant_id: int,
    language: str = "es",
) -> dict:
    """Generate PDF invoice for an Order.

    Args:
        order_id: UUID del pedido.
        tenant_id: ID del tenant.
        language: Idioma de la plantilla.

    Returns:
        {"order_id": ..., "pdf_url": "..."}.
    """
    logger.info("generate_invoice_pdf — order=%s, tenant=%d", order_id, tenant_id)
    try:
        # TODO: integrar con servicio de facturación (SII Chile, SAT México, etc.)
        # 1. Leer Order + OrderItems de la DB
        # 2. Renderizar plantilla HTML de factura
        # 3. HTML → PDF
        # 4. Subir a storage → devolver URL
        pdf_url = f"/storage/{tenant_id}/invoices/{order_id}.pdf"
        return {"order_id": order_id, "pdf_url": pdf_url}
    except Exception as exc:
        logger.error("generate_invoice_pdf failed — order=%s, error=%s", order_id, exc)
        raise self.retry(exc=exc, countdown=120)


@celery_app.task(bind=True, name="pdfs.generate_loyalty_pass", max_retries=3)
def generate_loyalty_pass_pdf(
    self: Task,
    customer_id: str,
    tenant_id: int,
    campaign_id: str,
) -> dict:
    """Generate loyalty pass / membership card PDF.

    Args:
        customer_id: UUID del cliente.
        tenant_id: ID del tenant.
        campaign_id: UUID de la campaña de fidelización.

    Returns:
        {"customer_id": ..., "pdf_url": "..."}.
    """
    logger.info(
        "generate_loyalty_pass_pdf — customer=%s, tenant=%d, campaign=%s",
        customer_id, tenant_id, campaign_id,
    )
    try:
        # TODO: usar Pillow + ReportLab para crear una tarjeta tipo "sello"
        # con logo del negocio, nombre del cliente, campaña, y código QR.
        pdf_url = f"/storage/{tenant_id}/loyalty/{customer_id}.pdf"
        return {"customer_id": customer_id, "pdf_url": pdf_url}
    except Exception as exc:
        logger.error(
            "generate_loyalty_pass_pdf failed — customer=%s, error=%s",
            customer_id, exc,
        )
        raise self.retry(exc=exc, countdown=60)


@celery_app.task(name="pdfs.generate_report")
def generate_report_pdf(
    tenant_id: int,
    report_type: str,
    date_from: str,
    date_to: str,
    format: str = "pdf",
) -> dict:
    """Generate a business report PDF in background.

    Args:
        tenant_id: ID del tenant.
        report_type: "sales", "inventory", "customers", "rfm".
        date_from / date_to: Rango de fechas ISO.
        format: "pdf" o "xlsx".

    Returns:
        {"report_id": ..., "url": "..."}.
    """
    logger.info(
        "generate_report_pdf — tenant=%d, type=%s, from=%s, to=%s",
        tenant_id, report_type, date_from, date_to,
    )
    # TODO: implementar con pandas + reportlab / openpyxl
    url = f"/storage/{tenant_id}/reports/{report_type}_{date_from}_{date_to}.{format}"
    return {
        "tenant_id": tenant_id,
        "report_type": report_type,
        "url": url,
    }
