"""OCR background tasks (Celery).

HU_36 — Cola ocr: extracción de datos de tickets, facturas,
comprobantes de pago, documentos.
"""
import logging
from typing import Optional

from celery import Task
from app.celery_app import celery_app

logger = logging.getLogger("wowhub.tasks.ocr")


@celery_app.task(bind=True, name="ocr.process_receipt", max_retries=3)
def process_receipt_image(
    self: Task,
    image_url: str,
    tenant_id: int,
    branch_id: Optional[str] = None,
) -> dict:
    """Extract line items from a receipt/ticket image via OCR."""
    logger.info("process_receipt_image — tenant=%d, url=%s", tenant_id, image_url)
    try:
        # TODO: integrate with OCR provider (OCR.space / Google Vision / AWS Textract)
        # 1. Download image
        # 2. Send to OCR endpoint
        # 3. Parse raw_text → items with regex
        # 4. Save Receipt + InventorySnapshot to DB
        raw_text = f"[OCR placeholder] receipt from {image_url}"
        return {
            "success": True,
            "tenant_id": tenant_id,
            "image_url": image_url,
            "items": [],
            "total": 0,
            "raw_text": raw_text,
        }
    except Exception as exc:
        logger.error("process_receipt_image failed — url=%s, error=%s", image_url, exc)
        raise self.retry(exc=exc, countdown=60)


@celery_app.task(bind=True, name="ocr.process_payment_proof", max_retries=3)
def process_payment_proof(
    self: Task,
    image_url: str,
    tenant_id: int,
    order_id: str,
) -> dict:
    """Verify a payment proof image."""
    logger.info("process_payment_proof — tenant=%d, order=%s", tenant_id, order_id)
    try:
        return {
            "success": True,
            "verified": False,
            "confidence": 0.0,
            "raw_text": "[OCR placeholder]",
            "order_id": order_id,
        }
    except Exception as exc:
        logger.error("process_payment_proof failed — order=%s, error=%s", order_id, exc)
        raise self.retry(exc=exc, countdown=60)


@celery_app.task(name="ocr.process_batch")
def process_ocr_batch(
    tenant_id: int,
    image_urls: list[str],
    task_type: str = "receipt",
) -> dict:
    """Process a batch of images sequentially."""
    logger.info("process_ocr_batch — tenant=%d, type=%s, urls=%d", tenant_id, task_type, len(image_urls))
    results = []
    failed = 0
    for url in image_urls:
        try:
            if task_type == "receipt":
                r = process_receipt_image(url=url, tenant_id=tenant_id)
            else:
                r = process_payment_proof(image_url=url, tenant_id=tenant_id, order_id="")
            results.append(r)
        except Exception:
            failed += 1
    return {"tenant_id": tenant_id, "processed": len(results), "failed": failed, "results": results}
