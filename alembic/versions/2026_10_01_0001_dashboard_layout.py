"""HU_34 — Dashboard personalizable (GridStack): tabla ``dashboard_layouts``

Revision ID: 2026_10_01_0001
Revises: 2026_09_30_0003
Create Date: 2026-10-02

Contexto
--------
Crea la tabla ``dashboard_layouts`` que almacena el layout personalizable
del dashboard de cada tenant (relación 1:1 con ``tenants``).

El layout es un array JSON de widgets (id, x, y, w, h, type) que el
frontend (GridStack) interpreta para renderizar los widgets (stats,
orders, products, ai, etc.) en una grilla drag&drop.

FIX 2026-10-02
--------------
La versión inicial (``333c486``) usaba ``CHAR(32)`` para ``id`` /
``tenant_id`` y ``TIMESTAMP`` sin timezone. Esos tipos NO funcionan en
PostgreSQL de Railway porque ``tenants.id`` es ``UUID`` nativo, no
``CHAR(32)`` (error: ``datatype_mismatch - character and uuid are
incompatible``). Esta migración corregida usa los tipos validados en
producción, replicando el patrón de ``2026_09_30_0001_add_hu12_hu17...``
que ya está aplicada con éxito en la DB real.

Diseño (versión corregida)
---------------------------
- ``tenant_id`` ``UUID`` — FK a ``tenants.id`` ON DELETE CASCADE.
  En PostgreSQL es UUID nativo, en SQLite el GUID portable se almacena
  como CHAR(32) (hex sin guiones) gracias al tipo ``GUID()`` de
  ``app/models/base.py``. Aquí usamos ``UUID`` literal — Alembic lo
  traduce al tipo CHAR(32) en SQLite (ver ``_UUID`` en migraciones
  previas).
- ``id`` ``UUID`` PRIMARY KEY (BaseModel + uuid4).
- ``created_at`` / ``updated_at`` ``TIMESTAMP WITH TIME ZONE``.
- ``layout_json`` ``JSON NOT NULL DEFAULT '[]'::json``.

Idempotencia
------------
- ``CREATE TABLE IF NOT EXISTS``.
- ``CREATE INDEX IF NOT EXISTS`` + ``CREATE UNIQUE INDEX IF NOT EXISTS``.

Cross-DB
--------
La migración funciona en PostgreSQL (producción) y SQLite (tests).
NO droppea tablas existentes.

NOTA: La hipótesis "DEFAULT '[]' sin cast ::json causa 42804" era
incorrecta — el DEFAULT sí funciona. El verdadero culpable era la
declaración de ``tenant_id CHAR(32)`` cuando ``tenants.id`` es ``UUID``.
"""
from __future__ import annotations

import logging

from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = "2026_10_01_0001"
down_revision = "2026_09_30_0003"
branch_labels = None
depends_on = None


logger = logging.getLogger("alembic.runtime.migration")


# ── DDL corregida ──────────────────────────────────────────────────────
# Tipos validados contra PostgreSQL real de Railway (2026-10-02):
#   - tenants.id   = UUID
#   - tenants.created_at / updated_at = TIMESTAMP WITH TIME ZONE
# Verificado con diag_db2.py + diag_tenant_type.py.
_DDL_DASHBOARD_LAYOUTS = """
CREATE TABLE IF NOT EXISTS dashboard_layouts (
    id UUID NOT NULL PRIMARY KEY,
    tenant_id UUID NOT NULL,
    layout_json JSON NOT NULL DEFAULT '[]'::json,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_dashboard_layouts_tenant
        FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE
)
"""


# ── Índices idempotentes ──────────────────────────────────────────────
_IDX_DASHBOARD_TENANT = (
    "CREATE INDEX IF NOT EXISTS ix_dashboard_layouts_tenant "
    "ON dashboard_layouts (tenant_id)"
)
_UNIQ_DASHBOARD_TENANT = (
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_dashboard_layouts_tenant "
    "ON dashboard_layouts (tenant_id)"
)


def upgrade() -> None:
    """Crea la tabla + 2 índices (IF NOT EXISTS, idempotente)."""
    op.execute(text(_DDL_DASHBOARD_LAYOUTS))
    op.execute(text(_IDX_DASHBOARD_TENANT))
    op.execute(text(_UNIQ_DASHBOARD_TENANT))

    logger.info("dashboard_layouts: tabla + 2 índices creados OK")


def downgrade() -> None:
    """Drop del índice y la tabla (no rompe otros deployments)."""
    op.execute(text("DROP INDEX IF EXISTS uq_dashboard_layouts_tenant"))
    op.execute(text("DROP INDEX IF EXISTS ix_dashboard_layouts_tenant"))
    op.execute(text("DROP TABLE IF EXISTS dashboard_layouts"))