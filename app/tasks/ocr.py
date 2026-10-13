"""OCR background tasks (Celery).

HU_36 — Cola ocr: extracción de datos de tickets, facturas,
comprobantes de pago, documentos.

HU_33 — Las tasks ahora usan el ``OCRService`` real (MockOCRProvider
por default; TesseractOCRProvider si está disponible) en lugar de
los placeholders previos. Persisten el resultado en la tabla
``receipts``.
"""
import logging
from typing import Optional
from uuid import UUID

from celery import Task
from app.celery_app import celery_app

logger = logging.getLogger("wowhub.tasks.ocr")


def _serialize_uuid(value) -> str:
    """Helper: convierte UUID|str|int → str uniforme."""
    return str(value) if value is not None else None


def _persist_receipt(
    db,
    tenant_id: str,
    image_url: str,
    status: str,
    provider: str,
    raw_text: Optional[str] = None,
    items: Optional[list] = None,
    total_cents: int = 0,
    currency: str = "CLP",
    confidence: float = 0.0,
    error_message: Optional[str] = None,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
) -> str:
    """Crea una fila Receipt y devuelve su ID."""
    from app.models.receipt import Receipt, ReceiptStatus as RS

    receipt = Receipt(
        tenant_id=tenant_id,
        image_url=image_url,
        status=status,
        provider=provider,
        raw_text=raw_text,
        items_json=items or [],
        total_cents=total_cents,
        currency=currency,
        confidence=confidence,
        error_message=error_message,
        entity_type=entity_type,
        entity_id=entity_id,
    )
    db.add(receipt)
    db.commit()
    db.refresh(receipt)
    logger.info(
        "OCR receipt persisted — id=%s, tenant=%s, status=%s, total=%d",
        receipt.id, tenant_id, status, total_cents,
    )
    return str(receipt.id)


@celery_app.task(bind=True, name="ocr.process_receipt", max_retries=3)
def process_receipt_image(
    self: Task,
    image_url: str,
    tenant_id: str,
    branch_id: Optional[str] = None,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
) -> dict:
    """Extract line items from a receipt/ticket image via OCR (HU_33).

    Args:
        image_url: URL de la imagen a procesar.
        tenant_id: ID del tenant (UUID string).
        branch_id: ID de la branch (opcional, para inventario).
        entity_type: tipo de entidad relacionada ("order", "expense", ...).
        entity_id: ID de la entidad relacionada (opcional).

    Returns:
        dict con ``receipt_id``, ``provider``, ``items``, ``total_cents``.
    """
    logger.info(
        "process_receipt_image — tenant=%s, branch=%s, url=%s",
        tenant_id, branch_id, image_url,
    )
    try:
        # 1. Procesar imagen con el OCRService real.
        from app.services.ocr_service import get_ocr_service
        result = get_ocr_service().process_receipt(image_url)

        # 2. Persistir en la DB.
        from app.database import SessionLocal
        with SessionLocal() as db:
            receipt_id = _persist_receipt(
                db,
                tenant_id=tenant_id,
                image_url=image_url,
                status="processed",
                provider=result.provider,
                raw_text=result.raw_text,
                items=result.items,
                total_cents=result.total_cents,
                currency=result.currency,
                confidence=result.confidence,
                entity_type=entity_type,
                entity_id=entity_id,
            )

        return {
            "success": True,
            "receipt_id": receipt_id,
            "tenant_id": tenant_id,
            "image_url": image_url,
            "provider": result.provider,
            "items": result.items,
            "total_cents": result.total_cents,
            "currency": result.currency,
            "raw_text": result.raw_text,
        }
    except Exception as exc:
        logger.error(
            "process_receipt_image failed — url=%s, error=%s",
            image_url, exc,
        )
        # Persistir como failed (best-effort) y reintentar la task.
        try:
            from app.database import SessionLocal
            with SessionLocal() as db:
                _persist_receipt(
                    db,
                    tenant_id=tenant_id,
                    image_url=image_url,
                    status="failed",
                    provider="unknown",
                    error_message=str(exc)[:2000],
                    entity_type=entity_type,
                    entity_id=entity_id,
                )
        except Exception:
            pass
        raise self.retry(exc=exc, countdown=60)


@celery_app.task(bind=True, name="ocr.process_payment_proof", max_retries=3)
def process_payment_proof(
    self: Task,
    image_url: str,
    tenant_id: str,
    order_id: str,
    expected_amount_cents: int = 0,
    tolerance_cents: int = 500,
) -> dict:
    """Verify a payment proof image (HU_33 + HU_23 reconciliation).

    Compara el monto detectado en el OCR con ``expected_amount_cents``.
    Si está dentro de la tolerancia (default 500 centavos), marca
    ``verified=True``.

    Args:
        image_url: URL del comprobante de pago.
        tenant_id: ID del tenant.
        order_id: ID de la orden asociada.
        expected_amount_cents: monto que esperábamos (opcional).
        tolerance_cents: tolerancia de diferencia permitida (centavos).

    Returns:
        dict con ``verified``, ``detected_total_cents``, ``delta_cents``,
        ``receipt_id``, ``provider``.
    """
    logger.info(
        "process_payment_proof — tenant=%s, order=%s, url=%s, tol=%d",
        tenant_id, order_id, image_url, tolerance_cents,
    )
    try:
        from app.services.ocr_service import get_ocr_service
        verification = get_ocr_service().verify_payment_proof(
            image_url=image_url,
            expected_amount_cents=expected_amount_cents,
            tolerance_cents=tolerance_cents,
        )

        # Persistir el resultado en receipts (entity_type='order', entity_id=order_id).
        from app.database import SessionLocal
        with SessionLocal() as db:
            receipt_id = _persist_receipt(
                db,
                tenant_id=tenant_id,
                image_url=image_url,
                status="processed",
                provider=verification["provider"],
                raw_text=verification.get("raw_text", ""),
                items=[],
                total_cents=verification["detected_total_cents"],
                currency=verification["currency"],
                confidence=verification["confidence"],
                entity_type="order",
                entity_id=str(order_id),
            )

        return {
            "success": True,
            "receipt_id": receipt_id,
            "tenant_id": tenant_id,
            "order_id": order_id,
            "image_url": image_url,
            "verified": verification["verified"],
            "confidence": verification["confidence"],
            "detected_total_cents": verification["detected_total_cents"],
            "expected_amount_cents": verification["expected_amount_cents"],
            "delta_cents": verification["delta_cents"],
            "provider": verification["provider"],
        }
    except Exception as exc:
        logger.error(
            "process_payment_proof failed — order=%s, error=%s",
            order_id, exc,
        )
        try:
            from app.database import SessionLocal
            with SessionLocal() as db:
                _persist_receipt(
                    db,
                    tenant_id=tenant_id,
                    image_url=image_url,
                    status="failed",
                    provider="unknown",
                    error_message=str(exc)[:2000],
                    entity_type="order",
                    entity_id=str(order_id),
                )
        except Exception:
            pass
        raise self.retry(exc=exc, countdown=60)


@celery_app.task(name="ocr.process_batch")
def process_ocr_batch(
    tenant_id: str,
    image_urls: list[str],
    task_type: str = "receipt",
) -> dict:
    """Process a batch of images sequentially."""
    logger.info(
        "process_ocr_batch — tenant=%s, type=%s, urls=%d",
        tenant_id, task_type, len(image_urls),
    )
    results = []
    failed = 0
    for url in image_urls:
        try:
            if task_type == "receipt":
                r = process_receipt_image(url=url, tenant_id=tenant_id)
            else:
                # payment_proof requires order_id — en este flujo batch
                # no tenemos orden, así que usamos string vacío.
                r = process_payment_proof(
                    image_url=url,
                    tenant_id=tenant_id,
                    order_id="",
                    expected_amount_cents=0,
                )
            results.append(r)
        except Exception as exc:
            logger.warning("OCR batch item failed — url=%s, err=%s", url, exc)
            failed += 1
    return {
        "tenant_id": tenant_id,
        "processed": len(results),
        "failed": failed,
        "results": results,
    }