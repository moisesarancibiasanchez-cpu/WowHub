"""HU_42 follow-up — agregar ``floor_layout`` a la tabla ``branches``.

Revision ID: 2026_10_06_0001
Revises: 9ac7d3705ee1
Create Date: 2026-10-06

Contexto
--------
``app/models/branch.py`` declara ``floor_layout: Mapped[dict] = mapped_column(
JSON, default=dict, nullable=False)`` desde hace tiempo, sin embargo la migración
inicial ``2026_09_07_1002-f2efb29e03b1_initial_schema.py`` NO incluyó la
columna al crear la tabla ``branches``.

Resultado en producción (PG real):
  GET /api/v1/tenants/{id}/branches      → 500 (ProgrammingError column does not exist)
  GET /api/v1/public/t/{slug}/branches  → 500 (idem)

Fix:
- ``ALTER TABLE branches ADD COLUMN IF NOT EXISTS floor_layout JSON NOT NULL
  DEFAULT '{}'::json``.
- Idempotente (PG 9.6+) y compatible con SQLite vía try/except (mismo patrón
  que HU_42 site_blocks).
"""
from __future__ import annotations

import logging

from alembic import op
from sqlalchemy import text

revision = "2026_10_06_0001"
down_revision = "9ac7d3705ee1"
branch_labels = None
depends_on = None


logger = logging.getLogger("alembic.runtime.migration")


def _add_column_if_not_exists(table: str, column: str, ddl: str) -> None:
    """Agrega una columna idempotente: usa IF NOT EXISTS en PostgreSQL,
    o un try/except silencioso en SQLite (que no soporta IF NOT EXISTS)."""
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {ddl}")
        )
    else:
        # SQLite: try/except. La columna ya existe → ignora.
        from sqlalchemy.exc import OperationalError

        try:
            op.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))
        except OperationalError as exc:
            logger.warning(
                "ADD COLUMN %s.%s ya existe (SQLite): %s", table, column, exc
            )


def upgrade() -> None:
    """Agrega ``floor_layout`` a ``branches`` (JSONB en PG, JSON en SQLite)."""
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        ddl = "JSONB NOT NULL DEFAULT '{}'::jsonb"
    else:
        # SQLite: JSON es TEXT con validación. DEFAULT '{}' literal.
        ddl = "JSON NOT NULL DEFAULT '{}'"
    _add_column_if_not_exists("branches", "floor_layout", ddl)
    logger.info("branches: +floor_layout OK")


def downgrade() -> None:
    """Elimina la columna (solo PG; SQLite no soporta DROP COLUMN bien)."""
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(text("ALTER TABLE branches DROP COLUMN IF EXISTS floor_layout"))