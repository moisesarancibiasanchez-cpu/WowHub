"""add audit_logs hash chain columns + indexes + immutability trigger

Revision ID: 2026_09_30_0002
Revises: 2026_09_30_0001
Create Date: 2026-09-30

HU_40 — Audit log hash chain (SHA-256) + PostgreSQL immutability.

Esta migración añade 3 piezas al esquema de ``audit_logs``:

  1. Columnas ``prev_hash`` y ``current_hash`` (ambas ``VARCHAR(64)``,
     ``NULLABLE``).
  2. 3 índices:
       - ``ix_audit_tenant_created_id`` — walk cronológico para verify-chain.
       - ``ix_audit_prev_hash``
       - ``ix_audit_current_hash``
  3. Trigger PG ``BEFORE UPDATE OR DELETE`` que rechaza la operación con
     ``RAISE EXCEPTION``. Sólo se crea si el dialecto es PostgreSQL;
     en SQLite (tests) se omite silenciosamente.

Idempotencia
------------
- ``ALTER TABLE ... ADD COLUMN IF NOT EXISTS`` — PostgreSQL ≥ 9.6,
  SQLite ≥ 3.35.0.
- ``CREATE INDEX IF NOT EXISTS``.
- Trigger y función: ``DROP TRIGGER IF EXISTS`` + ``CREATE OR REPLACE
  FUNCTION`` para re-ejecución segura.
- El bloque PG va envuelto en ``try/except``: si el rol de la app no tiene
  permisos para ``CREATE FUNCTION``/``CREATE TRIGGER`` (caso real en
  managed Postgres donde los privilegios son limitados), se loguea un
  warning pero la migración continúa sin romper el deploy. El fallback es
  defensivo: la cadena de hashes se calcula y verifica por aplicación, el
  trigger es una segunda línea de defensa.

Backfill
--------
Esta migración NO hace backfill de hashes. El cálculo se hace desde la
app en ``AuditService.log()`` (para registros nuevos) y vía
``POST /api/v1/audit/backfill-chain`` (para los registros pre-existentes).
Esto evita que la migración escanee millones de filas en el deploy.
"""
from __future__ import annotations

import logging

from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = "2026_09_30_0002"
down_revision = "2026_09_30_0001"
branch_labels = None
depends_on = None


logger = logging.getLogger("alembic.runtime.migration")


# ── DDL idempotente ──────────────────────────────────────────────
_DDL_ADD_PREV_HASH = (
    "ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS prev_hash VARCHAR(64)"
)
_DDL_ADD_CURRENT_HASH = (
    "ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS current_hash VARCHAR(64)"
)

_IDX_TENANT_WALK = (
    "CREATE INDEX IF NOT EXISTS ix_audit_tenant_created_id "
    "ON audit_logs (tenant_id, created_at, id)"
)
_IDX_PREV_HASH = (
    "CREATE INDEX IF NOT EXISTS ix_audit_prev_hash "
    "ON audit_logs (prev_hash)"
)
_IDX_CURRENT_HASH = (
    "CREATE INDEX IF NOT EXISTS ix_audit_current_hash "
    "ON audit_logs (current_hash)"
)


# ── Trigger PostgreSQL (best-effort) ────────────────────────────
_PG_FUNCTION_DDL = """
CREATE OR REPLACE FUNCTION audit_logs_immutable() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'audit_logs is append-only: % is forbidden', TG_OP
        USING ERRCODE = 'P0001';
END;
$$ LANGUAGE plpgsql;
"""

_PG_DROP_TRIGGERS = (
    "DROP TRIGGER IF EXISTS audit_logs_no_update ON audit_logs;"
    "DROP TRIGGER IF EXISTS audit_logs_no_delete ON audit_logs;"
)

_PG_CREATE_TRIGGERS = """
CREATE TRIGGER audit_logs_no_update
    BEFORE UPDATE ON audit_logs
    FOR EACH ROW EXECUTE FUNCTION audit_logs_immutable();

CREATE TRIGGER audit_logs_no_delete
    BEFORE DELETE ON audit_logs
    FOR EACH ROW EXECUTE FUNCTION audit_logs_immutable();
"""


def upgrade() -> None:
    # 1) columnas (idempotente, cross-DB).
    # FIX 2026-10-02: SQLite NO soporta ``ADD COLUMN IF NOT EXISTS``
    # (sólo PostgreSQL 9.6+). Usamos try/except con OperationalError
    # para que la migración sea idempotente en ambos motores.
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(text(_DDL_ADD_PREV_HASH))
        op.execute(text(_DDL_ADD_CURRENT_HASH))
    else:
        from sqlalchemy.exc import OperationalError
        for ddl in (_DDL_ADD_PREV_HASH, _DDL_ADD_CURRENT_HASH):
            try:
                op.execute(text(ddl.replace("ADD COLUMN IF NOT EXISTS", "ADD COLUMN")))
            except OperationalError as exc:
                logger.warning(
                    "audit_hash_chain: columna ya existe (SQLite idempotente): %s",
                    exc,
                )

    # 2) índices (idempotente, cross-DB).
    op.execute(text(_IDX_TENANT_WALK))
    op.execute(text(_IDX_PREV_HASH))
    op.execute(text(_IDX_CURRENT_HASH))

    # 3) trigger PG (best-effort, sólo si el dialecto es PostgreSQL).
    if bind.dialect.name != "postgresql":
        logger.info(
            "audit_hash_chain: dialect=%s — se omite el trigger "
            "(sólo PostgreSQL lo soporta)",
            bind.dialect.name,
        )
        return

    try:
        op.execute(text(_PG_FUNCTION_DDL))
        op.execute(text(_PG_DROP_TRIGGERS))
        op.execute(text(_PG_CREATE_TRIGGERS))
        logger.info("audit_hash_chain: trigger PG instalado OK")
    except Exception as exc:
        # No rompemos la migración: el rol puede no tener CREATE FUNCTION.
        # La cadena de hashes sigue funcionando vía aplicación; el trigger
        # es una segunda línea de defensa.
        logger.warning(
            "audit_hash_chain: no se pudo instalar el trigger PG "
            "(continuando sin él): %s",
            exc,
        )


def downgrade() -> None:
    bind = op.get_bind()

    # 1) trigger PG (best-effort).
    if bind.dialect.name == "postgresql":
        try:
            op.execute(text(_PG_DROP_TRIGGERS))
            op.execute(text("DROP FUNCTION IF EXISTS audit_logs_immutable()"))
        except Exception as exc:
            logger.warning(
                "audit_hash_chain.downgrade: trigger drop falló: %s", exc
            )

    # 2) índices.
    op.execute(text("DROP INDEX IF EXISTS ix_audit_current_hash"))
    op.execute(text("DROP INDEX IF EXISTS ix_audit_prev_hash"))
    op.execute(text("DROP INDEX IF EXISTS ix_audit_tenant_created_id"))

    # 3) columnas.
    op.execute(text("ALTER TABLE audit_logs DROP COLUMN IF EXISTS current_hash"))
    op.execute(text("ALTER TABLE audit_logs DROP COLUMN IF EXISTS prev_hash"))
