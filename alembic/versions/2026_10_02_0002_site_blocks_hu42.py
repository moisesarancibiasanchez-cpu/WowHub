"""HU_42 — Site constructor drag&drop: agregar ``social_links`` y ``blocks``.

Revision ID: 2026_10_02_0002
Revises: 2026_10_02_0001
Create Date: 2026-10-02

Contexto
--------
Extiende ``tenant_site_configs`` con dos columnas JSON para soportar el
constructor de sitio drag&drop:

- ``social_links JSON NOT NULL DEFAULT '[]'::json``: lista de
  ``{platform, url, label}`` para Facebook/Instagram/Twitter/etc.
- ``blocks JSON NOT NULL DEFAULT '[]'::json``: lista de bloques
  ``{id, type, title, content, image_url, position, enabled, config}``.
  El frontend ordena por ``position`` ASC.

Idempotencia:
- ``ADD COLUMN IF NOT EXISTS`` (PostgreSQL 9.6+).
- En SQLite, ``ALTER TABLE ADD COLUMN`` NO soporta IF NOT EXISTS,
  por lo que la migración envuelve cada ADD en un try/except y
  registra warnings si la columna ya existe. Esto preserva el
  cross-DB sin romper SQLite (que se usa en tests).

Tipos validados (mismo patrón que HU_33/HU_34):
- ``JSON`` con DEFAULT ``'[]'::json`` (PG requiere cast explícito).
"""
from __future__ import annotations

import logging

from alembic import op
from sqlalchemy import text

revision = "2026_10_02_0002"
down_revision = "2026_10_02_0001"
branch_labels = None
depends_on = None


logger = logging.getLogger("alembic.runtime.migration")


def _add_column_if_not_exists(table: str, column: str, ddl: str) -> None:
    """Agrega una columna idempotente: usa IF NOT EXISTS en PostgreSQL,
    o un try/except silencioso en SQLite (que no soporta IF NOT EXISTS)."""
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {ddl}"))
    else:
        # SQLite: try/except. La columna ya existe → ignora.
        from sqlalchemy.exc import OperationalError
        try:
            op.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))
        except OperationalError as exc:
            logger.warning("ADD COLUMN %s.%s ya existe (SQLite): %s", table, column, exc)


def upgrade() -> None:
    """Agrega las 2 columnas a tenant_site_configs."""
    _add_column_if_not_exists(
        "tenant_site_configs",
        "social_links",
        "JSON NOT NULL DEFAULT '[]'",
    )
    _add_column_if_not_exists(
        "tenant_site_configs",
        "blocks",
        "JSON NOT NULL DEFAULT '[]'",
    )
    logger.info("HU_42 — tenant_site_configs: +social_links, +blocks")


def downgrade() -> None:
    """Elimina las columnas (downgrade solo PG — SQLite no soporta DROP COLUMN bien)."""
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(text("ALTER TABLE tenant_site_configs DROP COLUMN IF EXISTS blocks"))
        op.execute(text("ALTER TABLE tenant_site_configs DROP COLUMN IF EXISTS social_links"))