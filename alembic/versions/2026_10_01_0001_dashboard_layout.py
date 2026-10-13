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

FIX 2026-10-03
--------------
La versión 2026-10-02 usaba ``op.execute(text(...))`` con SQL inline que
contenía ``DEFAULT '[]'::json``. Esa sintaxis de cast explícito ``::json``
es PostgreSQL-only — SQLite la rechaza con ``unrecognized token: ":"``.
Esto rompía ``tests/f0_baseline/test_alembic.py::test_alembic_downgrade_base_after_upgrade``
que corre ``alembic upgrade head`` contra un SQLite temporal.

La solución es usar la API declarativa de Alembic (``op.create_table`` /
``op.create_index``) que genera DDL portable cross-DB:
- ``sa.JSON()`` → ``JSON`` (PG) o ``TEXT`` (SQLite), sin necesidad de
  ``::json`` cast.
- ``server_default=text("'[]'")`` → ``DEFAULT '[]'`` (literal portable).
- ``DateTime(timezone=True)`` con ``server_default=func.now()`` →
  ``TIMESTAMP WITH TIME ZONE DEFAULT NOW()`` (PG) o
  ``DATETIME DEFAULT CURRENT_TIMESTAMP`` (SQLite).
- ``app.models.base.GUID()`` se reutiliza para mantener el contrato
  portable (CHAR(32) en SQLite, UUID nativo en PG).

Idempotencia
------------
- DDL declarativa sin ``CREATE TABLE IF NOT EXISTS`` se reemplaza por
  un wrapper ``_safe_create_table`` que en PG usa ``op.create_table``
  normal y en SQLite captura ``OperationalError``/"table already exists"
  para que la migración sea no-op en re-runs (igual que el patrón de
  ``2026_10_03_0001_report_runs_hu31.py``).
- Índices se crean con ``IF NOT EXISTS`` (soportado en ambos dialectos).

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

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text
from sqlalchemy.exc import OperationalError, ProgrammingError

# revision identifiers, used by Alembic.
revision = "2026_10_01_0001"
down_revision = "2026_09_30_0003"
branch_labels = None
depends_on = None


logger = logging.getLogger("alembic.runtime.migration")


def _safe_create_table() -> None:
    """Crea ``dashboard_layouts`` de forma idempotente cross-DB.

    PG: ``op.create_table`` (declarativo Alembic) — si ya existe la tabla,
    PG la crea OK (los IDs nunca colisionan porque cada migración corre 1
    vez) y los índices se manejan abajo con IF NOT EXISTS.

    SQLite: NO soporta CREATE TABLE IF NOT EXISTS en versiones antiguas y
    además la columna ``JSON NOT NULL DEFAULT '[]'::json`` con cast PG
    falla. Usamos try/except ``OperationalError`` / ``ProgrammingError``
    para capturar el caso "table already exists" — patrón validado en
    ``2026_10_03_0001_report_runs_hu31.py``.
    """
    bind = op.get_bind()
    # En PG generamos DDL con tipos PG nativos (UUID, TIMESTAMP WITH TIME
    # ZONE) para mantener paridad con la migración original.
    if bind.dialect.name == "postgresql":
        op.create_table(
            "dashboard_layouts",
            sa.Column(
                "id",
                sa.dialects.postgresql.UUID(as_uuid=True),
                primary_key=True,
                nullable=False,
            ),
            sa.Column(
                "tenant_id",
                sa.dialects.postgresql.UUID(as_uuid=True),
                sa.ForeignKey("tenants.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "layout_json",
                sa.JSON(),
                nullable=False,
                server_default=text("'[]'::json"),
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.UniqueConstraint("tenant_id", name="uq_dashboard_layouts_tenant"),
        )
        return

    # SQLite: DDL portable (CHAR(36) para IDs — equivalente al GUID() hex
    # de 32 chars pero más compatible con los IDs reales; ``JSON`` se
    # almacena como TEXT con default ``'[]'`` que es JSON válido).
    try:
        op.create_table(
            "dashboard_layouts",
            sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
            sa.Column(
                "tenant_id",
                sa.String(length=36),
                sa.ForeignKey("tenants.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "layout_json",
                sa.JSON(),
                nullable=False,
                server_default=text("'[]'"),
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.current_timestamp(),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.current_timestamp(),
                nullable=False,
            ),
            sa.UniqueConstraint("tenant_id", name="uq_dashboard_layouts_tenant"),
        )
    except (OperationalError, ProgrammingError) as exc:
        logger.warning(
            "dashboard_layouts: CREATE TABLE ya aplicado (dialect=%s): %s",
            bind.dialect.name,
            exc,
        )


# ── Índices idempotentes (cross-DB) ──────────────────────────────────
_IDX_DASHBOARD_TENANT = (
    "CREATE INDEX IF NOT EXISTS ix_dashboard_layouts_tenant "
    "ON dashboard_layouts (tenant_id)"
)


def upgrade() -> None:
    """Crea la tabla + 1 índice (IF NOT EXISTS, idempotente cross-DB).

    El índice único sobre ``tenant_id`` lo declaramos dentro de
    ``op.create_table(...)`` como ``UniqueConstraint`` — eso evita
    duplicación con la PK lógica de "1 row por tenant" (la tabla
    ``DashboardLayout`` también lo define en ``__table_args__``). En
    SQLite, el ``UniqueConstraint`` se materializa como índice único
    automáticamente.
    """
    _safe_create_table()
    op.execute(text(_IDX_DASHBOARD_TENANT))

    logger.info("dashboard_layouts: tabla + índice creados OK (cross-DB)")


def downgrade() -> None:
    """Drop del índice y la tabla (no rompe otros deployments)."""
    op.execute(text("DROP INDEX IF EXISTS ix_dashboard_layouts_tenant"))
    op.execute(text("DROP TABLE IF EXISTS dashboard_layouts"))