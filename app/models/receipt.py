"""HU_33 — Receipt: resultado de OCR de un comprobante (ticket/factura).

Cada Receipt representa el resultado de procesar una imagen vía OCR.
Almacena el texto crudo detectado y los items parseados, junto con
metadata del proceso (proveedor OCR, confianza, estado).

Estados:
- ``pending``: en cola o procesando.
- ``processed``: OCR exitoso, items parseados.
- ``failed``: error durante el OCR (ver ``error_message``).
"""
from __future__ import annotations

from typing import Any, Optional
from uuid import UUID, uuid4

from sqlalchemy import JSON, Enum as SQLEnum, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel, TenantMixin


class ReceiptStatus:
    """Estados posibles de un Receipt (HU_33)."""
    PENDING = "pending"
    PROCESSED = "processed"
    FAILED = "failed"


class Receipt(BaseModel, TenantMixin):
    """Resultado de OCR de un comprobante para un tenant.

    Attributes:
        tenant_id: FK a ``tenants.id``.
        image_url: URL de la imagen fuente (S3, /storage, etc).
        status: pending/processed/failed.
        provider: nombre del proveedor OCR ("mock", "tesseract", ...).
        raw_text: texto crudo devuelto por el OCR.
        items_json: array de items parseados [{name, qty, unit_cents, total_cents}].
        total_cents: monto total detectado.
        currency: código de moneda (CLP, ARS, MXN, USD, ...).
        confidence: 0.0-1.0, confianza del proveedor OCR.
        error_message: si ``status=failed``, detalle del error.
        entity_type: tipo de entidad relacionada ("order", "expense", None).
        entity_id: ID de la entidad relacionada.
    """
    __tablename__ = "receipts"
    __table_args__ = (
        Index("ix_receipts_tenant_status", "tenant_id", "status"),
    )

    image_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=ReceiptStatus.PENDING,
    )
    provider: Mapped[str] = mapped_column(String(40), nullable=False, default="mock")
    raw_text: Mapped[Optional[str]] = mapped_column(String(8000), nullable=True)
    items_json: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    total_cents: Mapped[int] = mapped_column(default=0, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="CLP")
    confidence: Mapped[float] = mapped_column(default=0.0, nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(String(2000), nullable=True)
    entity_type: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    entity_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        n = len(self.items_json or [])
        return f"<Receipt tenant={self.tenant_id} status={self.status} items={n} total={self.total_cents}>"

    @property
    def items(self) -> list[dict[str, Any]]:
        """Helper: devuelve ``items_json`` como lista de dicts."""
        return list(self.items_json or [])
