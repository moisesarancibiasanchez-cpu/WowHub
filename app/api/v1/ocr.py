"""HU_33 — API REST para OCR de comprobantes.

Endpoints:
- POST /api/v1/tenants/{tid}/ocr/receipt         → enqueue OCR (process_receipt_image)
- POST /api/v1/tenants/{tid}/ocr/payment-proof   → enqueue OCR + verify (process_payment_proof)
- GET  /api/v1/tenants/{tid}/ocr/receipts        → lista los receipts del tenant
- GET  /api/v1/tenants/{tid}/ocr/receipts/{rid}  → devuelve un receipt específico

NOTA: El procesamiento es **asíncrono** vía Celery (HU_36). El endpoint
POST devuelve ``task_id`` y ``receipt_id`` (pending). El cliente puede
hacer GET /receipts/{rid} después para ver el resultado (status cambia
a 'processed' o 'failed').
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field, HttpUrl
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_tenant_for_membership
from app.models.dashboard import DashboardLayout  # noqa: F401  (template dependency, ensure imports work)
from app.models.receipt import Receipt, ReceiptStatus
from app.models.tenant import Tenant


router = APIRouter(
    prefix="/tenants/{tenant_id}/ocr",
    tags=["ocr"],
)


# ── Schemas ────────────────────────────────────────────────────────────
class ReceiptOut(BaseModel):
    """Response con datos de un Receipt."""
    id: str
    tenant_id: str
    image_url: str
    status: str
    provider: str
    items: list[dict]
    total_cents: int
    currency: str
    confidence: float
    error_message: Optional[str] = None
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    @classmethod
    def from_receipt(cls, r: Receipt) -> "ReceiptOut":
        return cls(
            id=str(r.id),
            tenant_id=str(r.tenant_id),
            image_url=r.image_url,
            status=r.status,
            provider=r.provider,
            items=list(r.items_json or []),
            total_cents=r.total_cents,
            currency=r.currency,
            confidence=r.confidence,
            error_message=r.error_message,
            entity_type=r.entity_type,
            entity_id=r.entity_id,
            created_at=r.created_at.isoformat() if r.created_at else None,
            updated_at=r.updated_at.isoformat() if r.updated_at else None,
        )


class ReceiptProcessIn(BaseModel):
    """Body para POST /ocr/receipt."""
    image_url: HttpUrl = Field(..., description="URL pública de la imagen.")
    branch_id: Optional[str] = Field(None, description="ID de branch (opcional).")
    entity_type: Optional[str] = Field(None, max_length=40)
    entity_id: Optional[str] = Field(None, max_length=64)
    # Si True, procesa SINCRONICAMENTE en lugar de encolar Celery (útil para
    # debug o cuando el worker no está disponible).
    sync: bool = Field(False, description="Si True, procesa en línea en lugar de encolar Celery.")


class ReceiptProcessOut(BaseModel):
    receipt_id: str
    task_id: Optional[str] = None  # None cuando sync=True
    status: str
    provider: str
    items: list[dict]
    total_cents: int
    currency: str
    confidence: float
    processed_synchronously: bool


class PaymentProofIn(BaseModel):
    """Body para POST /ocr/payment-proof."""
    image_url: HttpUrl
    order_id: str = Field(..., min_length=1, max_length=64)
    expected_amount_cents: int = Field(0, ge=0, description="Monto esperado (centavos).")
    tolerance_cents: int = Field(500, ge=0, le=100_000, description="Tolerancia (centavos).")
    # Si True, procesa SINCRONICAMENTE en lugar de encolar Celery (útil para
    # debug o cuando el worker no está disponible).
    sync: bool = Field(False, description="Si True, procesa en línea en lugar de encolar Celery.")


class PaymentProofOut(BaseModel):
    receipt_id: str
    task_id: Optional[str] = None
    verified: bool
    confidence: float
    detected_total_cents: int
    expected_amount_cents: int
    delta_cents: int
    currency: str
    provider: str
    processed_synchronously: bool


# ── Endpoints ──────────────────────────────────────────────────────────
@router.post(
    "/receipt",
    response_model=ReceiptProcessOut,
    status_code=202,
    summary="Encolar OCR de un comprobante (HU_33)",
)
def process_receipt(
    payload: ReceiptProcessIn = Body(...),
    tenant: Tenant = Depends(get_tenant_for_membership),
    db: Session = Depends(get_db),
):
    """Encola el procesamiento OCR de un comprobante.

    Por default, el procesamiento es **asíncrono** vía Celery (worker
    de la cola ``ocr``). Si ``sync=true``, se procesa en línea (útil
    para debug; en producción siempre async).

    Devuelve:
    - ``receipt_id`` (creado con status=pending al encolar, o
      status=processed/failed si sync).
    - ``task_id`` de Celery (None si sync).
    - El resultado del OCR (items + total + currency + confidence).
    """
    from app.tasks.ocr import process_receipt_image

    image_url = str(payload.image_url)
    if payload.sync:
        # Procesar en línea (síncrono)
        result = process_receipt_image.run(
            image_url=image_url,
            tenant_id=str(tenant.id),
            branch_id=payload.branch_id,
            entity_type=payload.entity_type,
            entity_id=payload.entity_id,
        )
        # Leer el receipt recién creado
        receipt = db.query(Receipt).filter(
            Receipt.id == result["receipt_id"]
        ).one_or_none()
        if not receipt:
            raise HTTPException(status_code=500, detail="Receipt no encontrado tras OCR")
        return ReceiptProcessOut(
            receipt_id=str(receipt.id),
            task_id=None,
            status=receipt.status,
            provider=receipt.provider,
            items=list(receipt.items_json or []),
            total_cents=receipt.total_cents,
            currency=receipt.currency,
            confidence=receipt.confidence,
            processed_synchronously=True,
        )
    # Modo async: encolar Celery task
    async_result = process_receipt_image.delay(
        image_url=image_url,
        tenant_id=str(tenant.id),
        branch_id=payload.branch_id,
        entity_type=payload.entity_type,
        entity_id=payload.entity_id,
    )
    # Crear fila Receipt en estado pending para tracking
    receipt = Receipt(
        tenant_id=str(tenant.id),
        image_url=image_url,
        status=ReceiptStatus.PENDING,
        provider="pending",
        entity_type=payload.entity_type,
        entity_id=payload.entity_id,
    )
    db.add(receipt)
    db.commit()
    db.refresh(receipt)
    return ReceiptProcessOut(
        receipt_id=str(receipt.id),
        task_id=str(async_result.id),
        status=receipt.status,
        provider=receipt.provider,
        items=[],
        total_cents=0,
        currency="CLP",
        confidence=0.0,
        processed_synchronously=False,
    )


@router.post(
    "/payment-proof",
    response_model=PaymentProofOut,
    status_code=202,
    summary="Verificar comprobante de pago contra monto esperado (HU_33)",
)
def verify_payment_proof(
    payload: PaymentProofIn = Body(...),
    tenant: Tenant = Depends(get_tenant_for_membership),
    db: Session = Depends(get_db),
):
    """Encola verificación de un comprobante de pago."""
    from app.tasks.ocr import process_payment_proof

    image_url = str(payload.image_url)
    if payload.sync:
        result = process_payment_proof.run(
            image_url=image_url,
            tenant_id=str(tenant.id),
            order_id=payload.order_id,
            expected_amount_cents=payload.expected_amount_cents,
            tolerance_cents=payload.tolerance_cents,
        )
        receipt = db.query(Receipt).filter(
            Receipt.id == result["receipt_id"]
        ).one_or_none()
        if not receipt:
            raise HTTPException(status_code=500, detail="Receipt no encontrado tras OCR")
        return PaymentProofOut(
            receipt_id=str(receipt.id),
            task_id=None,
            verified=result["verified"],
            confidence=result["confidence"],
            detected_total_cents=result["detected_total_cents"],
            expected_amount_cents=result["expected_amount_cents"],
            delta_cents=result["delta_cents"],
            currency=receipt.currency,
            provider=receipt.provider,
            processed_synchronously=True,
        )
    async_result = process_payment_proof.delay(
        image_url=image_url,
        tenant_id=str(tenant.id),
        order_id=payload.order_id,
        expected_amount_cents=payload.expected_amount_cents,
        tolerance_cents=payload.tolerance_cents,
    )
    receipt = Receipt(
        tenant_id=str(tenant.id),
        image_url=image_url,
        status=ReceiptStatus.PENDING,
        provider="pending",
        entity_type="order",
        entity_id=payload.order_id,
    )
    db.add(receipt)
    db.commit()
    db.refresh(receipt)
    return PaymentProofOut(
        receipt_id=str(receipt.id),
        task_id=str(async_result.id),
        verified=False,
        confidence=0.0,
        detected_total_cents=0,
        expected_amount_cents=payload.expected_amount_cents,
        delta_cents=-payload.expected_amount_cents,
        currency="CLP",
        provider="pending",
        processed_synchronously=False,
    )


@router.get(
    "/receipts",
    response_model=list[ReceiptOut],
    summary="Lista los receipts del tenant (HU_33)",
)
def list_receipts(
    tenant: Tenant = Depends(get_tenant_for_membership),
    db: Session = Depends(get_db),
    status_filter: Optional[str] = Query(None, description="Filtrar por status: pending/processed/failed."),
    entity_type: Optional[str] = Query(None, description="Filtrar por entity_type."),
    entity_id: Optional[str] = Query(None, description="Filtrar por entity_id."),
    limit: int = Query(50, ge=1, le=200),
):
    """Devuelve los receipts del tenant, ordenados por fecha descendente."""
    q = db.query(Receipt).filter(Receipt.tenant_id == str(tenant.id))
    if status_filter:
        q = q.filter(Receipt.status == status_filter)
    if entity_type:
        q = q.filter(Receipt.entity_type == entity_type)
    if entity_id:
        q = q.filter(Receipt.entity_id == entity_id)
    q = q.order_by(Receipt.created_at.desc()).limit(limit)
    return [ReceiptOut.from_receipt(r) for r in q.all()]


@router.get(
    "/receipts/{receipt_id}",
    response_model=ReceiptOut,
    summary="Devuelve un receipt específico (HU_33)",
)
def get_receipt(
    receipt_id: UUID,
    tenant: Tenant = Depends(get_tenant_for_membership),
    db: Session = Depends(get_db),
):
    """Devuelve el detalle de un receipt por ID."""
    receipt = db.query(Receipt).filter(
        Receipt.id == str(receipt_id),
        Receipt.tenant_id == str(tenant.id),
    ).one_or_none()
    if not receipt:
        raise HTTPException(status_code=404, detail="Receipt no encontrado")
    return ReceiptOut.from_receipt(receipt)