"""HU_38 — RBAC Granular con Casbin (rbac_policies + rbac_groupings)

Revision ID: 2026_09_30_0003
Revises: 2026_09_30_0002
Create Date: 2026-09-30

Crea dos tablas planas que actúan como backend del
``casbin.persist.Adapter`` definido en ``app/core/rbac_adapter.py``:

  * ``rbac_policies``  — reglas ``(sub, dom, obj, act)``.
  * ``rbac_groupings`` — relaciones de jerarquía ``(sub, role, dom)``.

Ambas usan columnas ``String`` portables (Postgres + SQLite) y NO
tienen FK cross-DB — RBAC puede crecer más rápido que el resto del
schema, y un ``DROP TABLE tenants`` no debe romper el módulo.

Idempotencia
------------
- ``CREATE TABLE IF NOT EXISTS`` — Postgres 9.1+, SQLite 3.3+.
- ``CREATE INDEX IF NOT EXISTS``.
- El bloque se ejecuta sin detección de dialecto: el SQL crudo es
  portable en ambos motores (sólo usamos tipos ``VARCHAR`` y
  constraints ``UNIQUE`` que existen en ambos).

Seed inicial
------------
Esta migración NO seedea policies por defecto — eso lo hace el
``lifespan`` de ``app/main.py`` llamando a
``seed_default_rbac_policies()`` (idempotente vía ``count == 0``).

Backfill
--------
N/A — son tablas nuevas.
"""
from __future__ import annotations

import logging

from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = "2026_09_30_0003"
down_revision = "2026_09_30_0002"
branch_labels = None
depends_on = None


logger = logging.getLogger("alembic.runtime.migration")


# ── DDL portable (Postgres + SQLite) ───────────────────────────────────
_DDL_RBAC_POLICIES = """
CREATE TABLE IF NOT EXISTS rbac_policies (
    id CHAR(32) NOT NULL PRIMARY KEY,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    sub VARCHAR(120) NOT NULL,
    dom VARCHAR(120) NOT NULL,
    obj VARCHAR(120) NOT NULL,
    act VARCHAR(60) NOT NULL,
    effect VARCHAR(16) NOT NULL DEFAULT 'allow',
    priority INTEGER NOT NULL DEFAULT 0,
    note VARCHAR(255) NOT NULL DEFAULT ''
)
"""

_DDL_RBAC_GROUPINGS = """
CREATE TABLE IF NOT EXISTS rbac_groupings (
    id CHAR(32) NOT NULL PRIMARY KEY,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    sub VARCHAR(120) NOT NULL,
    role VARCHAR(120) NOT NULL,
    dom VARCHAR(120) NOT NULL
)
"""


_IDX_RBAC_POLICY_SUB_DOM = (
    "CREATE INDEX IF NOT EXISTS ix_rbac_policy_sub_dom "
    "ON rbac_policies (sub, dom)"
)
_IDX_RBAC_POLICY_DOM = (
    "CREATE INDEX IF NOT EXISTS ix_rbac_policy_dom "
    "ON rbac_policies (dom)"
)
_IDX_RBAC_POLICY_RULE = (
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_rbac_policy_rule "
    "ON rbac_policies (sub, dom, obj, act)"
)

_IDX_RBAC_GROUP_SUB = (
    "CREATE INDEX IF NOT EXISTS ix_rbac_group_sub "
    "ON rbac_groupings (sub)"
)
_IDX_RBAC_GROUP_ROLE_DOM = (
    "CREATE INDEX IF NOT EXISTS ix_rbac_group_role_dom "
    "ON rbac_groupings (role, dom)"
)
_IDX_RBAC_GROUP_RULE = (
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_rbac_group_rule "
    "ON rbac_groupings (sub, role, dom)"
)


def upgrade() -> None:
    """Crea las 2 tablas y 6 índices (todos IF NOT EXISTS, idempotente)."""
    op.execute(text(_DDL_RBAC_POLICIES))
    op.execute(text(_DDL_RBAC_GROUPINGS))

    op.execute(text(_IDX_RBAC_POLICY_SUB_DOM))
    op.execute(text(_IDX_RBAC_POLICY_DOM))
    op.execute(text(_IDX_RBAC_POLICY_RULE))

    op.execute(text(_IDX_RBAC_GROUP_SUB))
    op.execute(text(_IDX_RBAC_GROUP_ROLE_DOM))
    op.execute(text(_IDX_RBAC_GROUP_RULE))

    logger.info("rbac_casbin: 2 tablas + 6 índices creados OK")


def downgrade() -> None:
    """Drop de las 2 tablas (no romper otros deployments)."""
    op.execute(text("DROP INDEX IF EXISTS uq_rbac_group_rule"))
    op.execute(text("DROP INDEX IF EXISTS ix_rbac_group_role_dom"))
    op.execute(text("DROP INDEX IF EXISTS ix_rbac_group_sub"))
    op.execute(text("DROP INDEX IF EXISTS uq_rbac_policy_rule"))
    op.execute(text("DROP INDEX IF EXISTS ix_rbac_policy_dom"))
    op.execute(text("DROP INDEX IF EXISTS ix_rbac_policy_sub_dom"))
    op.execute(text("DROP TABLE IF EXISTS rbac_groupings"))
    op.execute(text("DROP TABLE IF EXISTS rbac_policies"))