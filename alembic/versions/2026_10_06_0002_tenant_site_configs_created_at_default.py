"""FIX — tenant_site_configs.created_at sin DEFAULT en PG.

Revision ID: 2026_10_06_0002
Revises: 2026_10_06_0001
Create Date: 2026-10-06

Contexto
--------
La migración ``2026_09_27_0001_add_tenant_site_configs_and_marketplace.py``
creó la tabla ``tenant_site_configs`` con::

  created_at TIMESTAMP WITH TIME ZONE NOT NULL
  updated_at TIMESTAMP WITH TIME ZONE NOT NULL

SIN ``DEFAULT NOW()``. El modelo ORM (``TimestampMixin``) sí declara
``server_default=func.now()``, pero ese DEFAULT solo aplica cuando SQLAlchemy
genera el DDL (``create_all``); NO se refleja en la migración manual
ejecutada contra PG real.

Resultado en producción: ``get_or_create`` ejecuta ``INSERT INTO
tenant_site_configs (tenant_id) VALUES (...)`` → PG rechaza con
``null value in column "created_at" violates not-null constraint`` (HTTP 500).

Aplica a GET/PATCH ``/api/v1/tenants/{id}/site-config``.

Fix:
- ``ALTER COLUMN ... SET DEFAULT now()`` (idempotente en PG).
- Backfill ``updated_at`` y ``created_at`` para filas pre-existentes que
  tengan NULL (defensivo; el modelo dice NOT NULL pero queremos ser robustos).
- SQLite: la columna ya tiene DEFAULT vía SQLAlchemy, así que no tocamos
  nada (no-op).
"""
from __future__ import annotations

import logging

from alembic import op
from sqlalchemy import text

revision = "2026_10_06_0002"
down_revision = "2026_10_06_0001"
branch_labels = None
depends_on = None


logger = logging.getLogger("alembic.runtime.migration")


def upgrade() -> None:
    """Aplica DEFAULT now() a created_at/updated_at (PG) + backfill defensivo."""
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        logger.info("SQLite: DEFAULT ya viene del modelo; no-op")
        return

    # 1) Set server defaults (idempotente en PG).
    op.execute(
        text(
            "ALTER TABLE tenant_site_configs "
            "ALTER COLUMN created_at SET DEFAULT now()"
        )
    )
    op.execute(
        text(
            "ALTER TABLE tenant_site_configs "
            "ALTER COLUMN updated_at SET DEFAULT now()"
        )
    )

    # 2) Backfill defensivo (idempotente): filas existentes sin timestamp.
    op.execute(
        text(
            "UPDATE tenant_site_configs "
            "SET created_at = COALESCE(created_at, now()), "
            "    updated_at = COALESCE(updated_at, now())"
        )
    )

    logger.info("tenant_site_configs: DEFAULT now() aplicado en created_at/updated_at")


def downgrade() -> None:
    """Quita el server default (solo PG)."""
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute(
        text(
            "ALTER TABLE tenant_site_configs "
            "ALTER COLUMN created_at DROP DEFAULT"
        )
    )
    op.execute(
        text(
            "ALTER TABLE tenant_site_configs "
            "ALTER COLUMN updated_at DROP DEFAULT"
        )
    )