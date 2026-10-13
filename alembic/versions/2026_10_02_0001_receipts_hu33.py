"""HU_33 — Receipt: tabla para resultados de OCR de comprobantes.

Revision ID: 2026_10_02_0001
Revises: 2026_10_01_0001
Create Date: 2026-10-02

Contexto
--------
Crea la tabla ``receipts`` que almacena el resultado de procesar
imágenes de tickets/facturas vía OCR. Cada fila contiene el texto
crudo detectado, los items parseados, el total y metadata del proceso
(proveedor, confianza, estado).

Fix cross-DB (replicando el patrón validado en 2026_09_30_0001 y
2026_10_01_0001_dashboard_layout):

- ``id UUID NOT NULL PRIMARY KEY`` — no CHAR(32) (que PostgreSQL
  rechaza con 42804 datatype_mismatch contra FK de tenants.id UUID).
- ``tenant_id UUID NOT NULL`` — FK a tenants.id (UUID nativo en PG).
- ``created_at``/``updated_at`` ``TIMESTAMP WITH TIME ZONE``.
- ``image_url VARCHAR(1000)`` y resto columnas con tipos portables.

Idempotencia:
- ``CREATE TABLE IF NOT EXISTS``.
- ``CREATE INDEX IF NOT EXISTS``.

HU_33 entrega:
- Servicio ``app/services/ocr_service.py`` (con MockProvider +
  TesseractProvider opcional).
- 3 Celery tasks reemplazadas (no más TODO).
- API endpoints en ``app/api/v1/ocr.py`` (Commit B).
"""
from __future__ import annotations

import logging

from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = "2026_10_02_0001"
down_revision = "2026_10_01_0001"
branch_labels = None
depends_on = None


logger = logging.getLogger("alembic.runtime.migration")


# ── DDL validada contra PostgreSQL real de Railway (2026-10-02) ─────────
_DDL_RECEIPTS = """
CREATE TABLE IF NOT EXISTS receipts (
    id UUID NOT NULL PRIMARY KEY,
    tenant_id UUID NOT NULL,
    image_url VARCHAR(1000) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    provider VARCHAR(40) NOT NULL DEFAULT 'mock',
    raw_text VARCHAR(8000),
    items_json JSON NOT NULL DEFAULT '[]',
    total_cents INTEGER NOT NULL DEFAULT 0,
    currency VARCHAR(8) NOT NULL DEFAULT 'CLP',
    confidence DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    error_message VARCHAR(2000),
    entity_type VARCHAR(40),
    entity_id VARCHAR(64),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_receipts_tenant
        FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE
)
"""


_IDX_RECEIPTS_TENANT_STATUS = (
    "CREATE INDEX IF NOT EXISTS ix_receipts_tenant_status "
    "ON receipts (tenant_id, status)"
)


def upgrade() -> None:
    """Crea la tabla + 1 índice (IF NOT EXISTS, idempotente)."""
    op.execute(text(_DDL_RECEIPTS))
    op.execute(text(_IDX_RECEIPTS_TENANT_STATUS))

    logger.info("receipts: tabla + 1 índice creados OK")


def downgrade() -> None:
    """Drop del índice y la tabla."""
    op.execute(text("DROP INDEX IF EXISTS ix_receipts_tenant_status"))
    op.execute(text("DROP TABLE IF EXISTS receipts"))