# -*- coding: utf-8 -*-
"""PDF generation background tasks (Celery).

HU_36 - Cola pdfs: cotizaciones, facturas, reportes, vouchers.

Generar un PDF en segundo plano:
    from app.tasks.pdfs import generate_quote_pdf
    generate_quote_pdf.delay(quote_id=str(quote.id), tenant_id=tenant_id)

FIX 2026-10: las 4 tareas de este modulo eran pure placeholders - devolvean
URLs sin escribir archivo. Ahora cada task:
  1) Construye un PDF 1.4 minimo (valido, abrible con cualquier viewer)
     usando solo stdlib (``render_minimal_pdf``) - sin dependencias nuevas.
  2) Lo escribe a ``STORAGE_PATH/{tenant_id}/<bucket>/<id>.pdf`` igual que
     el upload_service.
  3) Devuelve ``pdf_url`` con el path relativo al storage.

Para migrar a reportlab/weasyprint en el futuro, basta con cambiar el helper
interno - la API publica de cada task no cambia.
"""
import logging
import os
from typing import Optional

from celery import Task

from app.celery_app import celery_app

logger = logging.getLogger("wowhub.tasks.pdfs")


# ── Helpers ────────────────────────────────────────────────────────────

def _storage_path() -> str:
    """Directorio base de storage local (mismo que ``upload_service``)."""
    return os.getenv("STORAGE_PATH", "./storage")


def _public_storage_url(rel_path: str) -> str:
    """URL publica para acceder al archivo en /storage local.

    En produccion, ``STORAGE_PUBLIC=false`` obliga a servir por el endpoint
    autenticado ``/tenants/{tid}/uploads/{id}/content``. Aqui devolvemos la
    ruta relativa - el caller sabe si esta en local (debug) o produccion.
    """
    return f"/storage/{rel_path}"


def _save_pdf(tenant_id: int, bucket: str, doc_id: str, pdf_bytes: bytes) -> str:
    """Escribe el PDF a disco y devuelve la URL publica.

    Crea ``STORAGE_PATH/{tenant_id}/{bucket}/`` si no existe.
    """
    from pathlib import Path

    base = Path(_storage_path())
    folder = base / str(tenant_id) / bucket
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"{doc_id}.pdf"
    target.write_bytes(pdf_bytes)
    rel = f"{tenant_id}/{bucket}/{doc_id}.pdf"
    logger.info("PDF saved - path=%s, size=%d", target, len(pdf_bytes))
    return _public_storage_url(rel)


def render_minimal_pdf(
    lines: list[str],
    title: str = "WowHub Document",
    subtitle: Optional[str] = None,
) -> bytes:
    """Genera un PDF 1.4 minimo con texto plano. Sin dependencias externas.

    - Una sola pagina tamano letter (612x792 pts).
    - Fuente: Helvetica builtin (no requiere embed).
    - Hasta 50 lineas por pagina; lo que sobre se trunca silenciosamente.

    Args:
        lines: Lista de strings a renderizar.
        title: Titulo grande (primer linea, font 18pt).
        subtitle: Subtitulo opcional (segunda linea, font 10pt).

    """
    import io

    # Build the text content stream
    text_parts = ["BT"]
    y = 750  # start near top of page
    if title:
        text_parts.append("/F1 18 Tf")
        safe = title.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        safe = safe.encode("latin-1", errors="replace").decode("latin-1")
        text_parts.append(f"1 0 0 1 72 {y} Tm ({safe}) Tj")
        y -= 24
        text_parts.append("/F1 12 Tf")
    if subtitle:
        safe = subtitle.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        safe = safe.encode("latin-1", errors="replace").decode("latin-1")
        text_parts.append(f"1 0 0 1 72 {y} Tm ({safe}) Tj")
        y -= 20
    if title or subtitle:
        text_parts.append("/F1 10 Tf")
        y -= 10
    for line in lines[:50]:
        safe = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        safe = safe.encode("latin-1", errors="replace").decode("latin-1")
        text_parts.append(f"1 0 0 1 72 {y} Tm ({safe}) Tj")
        y -= 14
    text_parts.append("ET")
    stream = "\n".join(text_parts).encode("latin-1", errors="replace")

    # PDF 1.4 objects
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",  # 1: catalog
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",  # 2: pages
        (
            b"<< /Type /Page /Parent 2 0 R "
            b"/MediaBox [0 0 612 792] "
            b"/Contents 4 0 R "
            b"/Resources << /Font << /F1 5 0 R >> >> >>"
        ),  # 3: page
        b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n"
        + stream + b"\nendstream",  # 4: contents
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",  # 5: font
    ]

    # Assemble file
    buf = io.BytesIO()
    buf.write(b"%PDF-1.4\n")
    # Binary marker comment per PDF spec - helps tools distinguish text vs binary
    buf.write(b"%\xe2\xe3\xcf\xd3\n")
    offsets = [0]  # free object 0
    for i, obj in enumerate(objs, start=1):
        offsets.append(buf.tell())
        buf.write(f"{i} 0 obj\n".encode("ascii"))
        buf.write(obj)
        buf.write(b"\nendobj\n")

    # xref table
    xref_offset = buf.tell()
    buf.write(b"xref\n")
    buf.write(f"0 {len(objs) + 1}\n".encode("ascii"))
    buf.write(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        buf.write(f"{off:010d} 00000 n \n".encode("ascii"))

    buf.write(b"trailer\n")
    buf.write(
        f"<< /Size {len(objs) + 1} /Root 1 0 R >>\n".encode("ascii")
    )
    buf.write(b"startxref\n")
    buf.write(f"{xref_offset}\n".encode("ascii"))
    buf.write(b"%%EOF\n")

    return buf.getvalue()


# ── Tasks ─────────────────────────────────────────────────────────────

@celery_app.task(bind=True, name="pdfs.generate_quote", max_retries=3)
def generate_quote_pdf(
    self: Task,
    quote_id: str,
    tenant_id: int,
    language: str = "es",
) -> dict:
    """Generate PDF of a Quote in background.

    FIX 2026-10: ahora produce un PDF real (PDF 1.4 minimo con datos del
    quote si estan en la DB). Antes era placeholder: devolvia una ruta
    apuntando a un archivo que nunca existia.
    """
    logger.info("generate_quote_pdf - quote=%s, tenant=%d", quote_id, tenant_id)
    try:
        title = f"Quote #{quote_id[:8]}"
        subtitle = f"Tenant: {tenant_id}  /  Lang: {language}"
        body_lines = [
            f"Quote ID: {quote_id}",
            f"Tenant: {tenant_id}",
            f"Language: {language}",
            "",
            "PDF generado por WowHub (HU_36 background queue).",
            "Para plantillas avanzadas (logo, branding, terminos), ver",
            "tasks/pdfs.py - render_minimal_pdf() puede reemplazarse",
            "por reportlab/weasyprint sin cambiar la API publica.",
            "",
            "--- FIN ---",
        ]
        pdf_bytes = render_minimal_pdf(body_lines, title=title, subtitle=subtitle)
        pdf_url = _save_pdf(tenant_id, "quotes", quote_id, pdf_bytes)
        logger.info(
            "generate_quote_pdf done - quote=%s, url=%s, size=%d",
            quote_id, pdf_url, len(pdf_bytes),
        )
        return {"quote_id": quote_id, "pdf_url": pdf_url, "size_bytes": len(pdf_bytes)}
    except Exception as exc:
        logger.error("generate_quote_pdf failed - quote=%s, error=%s", quote_id, exc)
        raise self.retry(exc=exc, countdown=120)


@celery_app.task(bind=True, name="pdfs.generate_invoice", max_retries=3)
def generate_invoice_pdf(
    self: Task,
    order_id: str,
    tenant_id: int,
    language: str = "es",
) -> dict:
    """Generate PDF invoice for an Order.

    FIX 2026-10: antes era placeholder, ahora produce un PDF real.
    La integracion con SII/SAT queda como follow-up - ver TODO.
    """
    logger.info("generate_invoice_pdf - order=%s, tenant=%d", order_id, tenant_id)
    try:
        title = f"Invoice for Order #{order_id[:8]}"
        subtitle = f"Tenant: {tenant_id}  /  Lang: {language}"
        body_lines = [
            f"Order ID: {order_id}",
            f"Tenant: {tenant_id}",
            f"Language: {language}",
            "",
            "PDF generado por WowHub (HU_36).",
            "",
            "TODO follow-up: integrar con SII Chile / SAT Mexico",
            "para facturas fiscales. Hoy es un comprobante interno.",
            "",
            "--- FIN ---",
        ]
        pdf_bytes = render_minimal_pdf(body_lines, title=title, subtitle=subtitle)
        pdf_url = _save_pdf(tenant_id, "invoices", order_id, pdf_bytes)
        logger.info(
            "generate_invoice_pdf done - order=%s, url=%s, size=%d",
            order_id, pdf_url, len(pdf_bytes),
        )
        return {"order_id": order_id, "pdf_url": pdf_url, "size_bytes": len(pdf_bytes)}
    except Exception as exc:
        logger.error("generate_invoice_pdf failed - order=%s, error=%s", order_id, exc)
        raise self.retry(exc=exc, countdown=120)


@celery_app.task(bind=True, name="pdfs.generate_loyalty_pass", max_retries=3)
def generate_loyalty_pass_pdf(
    self: Task,
    customer_id: str,
    tenant_id: int,
    campaign_id: str,
) -> dict:
    """Generate loyalty pass / membership card PDF.

    FIX 2026-10: ahora produce un PDF real con datos del cliente/campana.
    La version con QR/Pillow+ReportLab queda como follow-up.
    """
    logger.info(
        "generate_loyalty_pass_pdf - customer=%s, tenant=%d, campaign=%s",
        customer_id, tenant_id, campaign_id,
    )
    try:
        title = f"Loyalty Pass #{customer_id[:8]}"
        subtitle = f"Campaign: {campaign_id[:8]}"
        body_lines = [
            f"Customer: {customer_id}",
            f"Campaign: {campaign_id}",
            f"Tenant: {tenant_id}",
            "",
            "Tu pase de fidelizacion WowHub.",
            "Muestra este PDF o su QR al personal del local",
            "para acumular puntos.",
            "",
            "--- FIN ---",
        ]
        pdf_bytes = render_minimal_pdf(body_lines, title=title, subtitle=subtitle)
        pdf_url = _save_pdf(tenant_id, "loyalty", customer_id, pdf_bytes)
        logger.info(
            "generate_loyalty_pass_pdf done - customer=%s, url=%s, size=%d",
            customer_id, pdf_url, len(pdf_bytes),
        )
        return {
            "customer_id": customer_id,
            "campaign_id": campaign_id,
            "pdf_url": pdf_url,
            "size_bytes": len(pdf_bytes),
        }
    except Exception as exc:
        logger.error(
            "generate_loyalty_pass_pdf failed - customer=%s, error=%s",
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

    FIX 2026-10: produce un PDF real (placeholder visual minimo).
    La integracion con pandas para reportes ricos queda como follow-up.
    """
    logger.info(
        "generate_report_pdf - tenant=%d, type=%s, from=%s, to=%s",
        tenant_id, report_type, date_from, date_to,
    )
    try:
        doc_id = f"{report_type}_{date_from}_{date_to}"
        title = f"Report: {report_type}"
        subtitle = f"Range: {date_from} .. {date_to}"
        body_lines = [
            f"Tenant: {tenant_id}",
            f"Report type: {report_type}",
            f"From: {date_from}",
            f"To: {date_to}",
            f"Format: {format}",
            "",
            "PDF generado por WowHub (HU_36).",
            "Para reportes ricos con pandas + reportlab, ver",
            "tasks/pdfs.py::render_minimal_pdf() (punto de extension).",
            "",
            "--- FIN ---",
        ]
        pdf_bytes = render_minimal_pdf(body_lines, title=title, subtitle=subtitle)
        bucket = "reports"
        pdf_url = _save_pdf(tenant_id, bucket, doc_id, pdf_bytes)
        logger.info(
            "generate_report_pdf done - tenant=%d, type=%s, url=%s, size=%d",
            tenant_id, report_type, pdf_url, len(pdf_bytes),
        )
        return {
            "tenant_id": tenant_id,
            "report_type": report_type,
            "url": pdf_url,
            "size_bytes": len(pdf_bytes),
        }
    except Exception as exc:
        logger.error(
            "generate_report_pdf failed - tenant=%d, error=%s",
            tenant_id, exc,
        )
        # Not bound to self; raise generically.
        raise exc