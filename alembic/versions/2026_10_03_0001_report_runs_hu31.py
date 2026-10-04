"""report_runs (HU_31 follow-up)

Revision ID: 2026_10_03_0001
Revises: 2026_10_02_0004
Create Date: 2026-10-03

Contexto
--------
HU_31 implementÃ³ el endpoint ``GET /api/v1/tenants/{tid}/reports`` con
un catÃ¡logo hardcoded de 3 reportes (sales / customers / inventory) y
``last_run_at: null`` siempre â€” porque no habÃ­a tabla de historial.

Este follow-up persiste cada ejecuciÃ³n del endpoint en una nueva tabla
``report_runs`` para que ``last_run_at`` se hidrate con la fecha real
de la Ãºltima corrida desde la BD.

Schema
------
* ``id UUID PK`` (GUID portable â€” patrÃ³n validado en
  ``2026_09_30_0001_add_hu12_hu17_hu19_hu29.py``).
* ``tenant_id UUID NULLABLE`` FK a ``tenants(id) ON DELETE CASCADE``.
  PatrÃ³n idÃ©ntico a ``audit_logs.tenant_id`` (HU_40 v1.1) â€” permite
  reportes cross-tenant de plataforma ejecutados por superadmin.
* ``user_id UUID NULLABLE`` FK a ``users(id) ON DELETE SET NULL``.
  Permite ejecuciones del scheduler (sin usuario humano).
* ``report_key VARCHAR(64) NOT NULL`` â€” uno de
  ``"sales" | "customers" | "inventory"`` (HU_31).
* ``params_json TEXT NULLABLE`` â€” JSON con filtros/params del request.
* ``status VARCHAR(16) NOT NULL DEFAULT 'ok'`` â€” ``"ok" | "error"``.
* ``error TEXT NULLABLE`` â€” mensaje de error (sÃ³lo si status="error").
* ``started_at, finished_at TIMESTAMP WITH TIME ZONE NOT NULL`` â€”
  precisiÃ³n microsegundo desde Python (mismo patrÃ³n que
  ``AuditLog._utcnow_microsecond``).
* ``duration_ms INTEGER NULLABLE`` â€” calculado por el service.
* ``created_at, updated_at`` de ``TimestampMixin``.

Ãndices
-------
* ``(tenant_id, report_key, started_at)`` â€” query tÃ­pica
  "Ãºltimo run del reporte X del tenant Y".
* ``(started_at)`` â€” listado cronolÃ³gico global.
* ``(created_at)`` â€” orden de inserciÃ³n.

Los Ã­ndices simples ``(tenant_id)``, ``(user_id)`` y ``(report_key)``
los crea SQLAlchemy automÃ¡ticamente al sincronizar el schema del modelo
(``mapped_column(..., index=True)``), por lo que la migraciÃ³n NO los
declara aquÃ­ â€” serÃ­an DDL duplicado.

Idempotencia
------------
* ``CREATE TABLE IF NOT EXISTS`` (PG) + try/except ``OperationalError``
  (SQLite) â€” patrÃ³n validado en
  ``2026_10_02_0004_hu03_refresh_rotation_blacklist.py``.
* ``CREATE INDEX IF NOT EXISTS`` para los 3 Ã­ndices explÃ­citos.
"""
from __future__ import annotations

import logging

from alembic import op
from sqlalchemy import text
from sqlalchemy.exc import OperationalError, ProgrammingError

revision = "2026_10_03_0001"
down_revision = "2026_10_02_0004"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")


# â”€â”€ DDL validada contra PostgreSQL real de Railway â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# El dialecto del modelo es ``GUID()`` (CHAR(32) en SQLite, UUID nativo en
# PG). En la migraciÃ³n usamos DDL explÃ­cito para no acoplarnos al ``GUID``
# portable â€” el dialecto de Railway es siempre PG.
_DDL_REPORT_RUNS = """
CREATE TABLE IF NOT EXISTS report_runs (
    id UUID NOT NULL PRIMARY KEY,
    tenant_id UUID,
    user_id UUID,
    report_key VARCHAR(64) NOT NULL,
    params_json TEXT,
    status VARCHAR(16) NOT NULL DEFAULT 'ok',
    error TEXT,
    started_at TIMESTAMP WITH TIME ZONE NOT NULL,
    finished_at TIMESTAMP WITH TIME ZONE NOT NULL,
    duration_ms INTEGER,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_report_runs_tenant
        FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE,
    CONSTRAINT fk_report_runs_user
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
)
"""

_IDX_REPORT_RUNS_TENANT = (
    "CREATE INDEX IF NOT EXISTS ix_report_runs_tenant "
    "ON report_runs (tenant_id)"
)
_IDX_REPORT_RUNS_USER = (
    "CREATE INDEX IF NOT EXISTS ix_report_runs_user "
    "ON report_runs (user_id)"
)
_IDX_REPORT_RUNS_REPORT_KEY = (
    "CREATE INDEX IF NOT EXISTS ix_report_runs_report_key "
    "ON report_runs (report_key)"
)
_IDX_REPORT_RUNS_TENANT_KEY_STARTED = (
    "CREATE INDEX IF NOT EXISTS ix_report_runs_tenant_key_started "
    "ON report_runs (tenant_id, report_key, started_at)"
)
_IDX_REPORT_RUNS_STARTED_AT = (
    "CREATE INDEX IF NOT EXISTS ix_report_runs_started_at "
    "ON report_runs (started_at)"
)
_IDX_REPORT_RUNS_CREATED_AT = (
    "CREATE INDEX IF NOT EXISTS ix_report_runs_created_at "
    "ON report_runs (created_at)"
)


def _safe_create_table(ddl: str) -> None:
    """Crea una tabla idempotente cross-DB.

    PG: ``CREATE TABLE IF NOT EXISTS`` resuelve la idempotencia.
    SQLite: NO soporta ``IF NOT EXISTS`` en CREATE TABLE en versiones
    antiguas â€” usamos try/except ``OperationalError`` /
    ``ProgrammingError``. Si la tabla ya existe, ambos errores
    capturan el caso y la migraciÃ³n es no-op silencioso (igual que el
    helper ``_add_column_if_not_exists`` de
    ``2026_10_02_0002_site_blocks_hu42.py``).
    """
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(text(ddl))
        return
    try:
        op.execute(text(ddl))
    except (OperationalError, ProgrammingError) as exc:
        logger.warning(
            "report_runs: CREATE TABLE ya aplicado (dialect=%s): %s",
            bind.dialect.name,
            exc,
        )


def upgrade() -> None:
    """Crea la tabla ``report_runs`` + 3 Ã­ndices explÃ­citos (todos IF NOT EXISTS).

    Los Ã­ndices simples ``ix_report_runs_tenant_id``, ``ix_report_runs_user``
    y ``ix_report_runs_report_key`` los crea SQLAlchemy automÃ¡ticamente
    porque las columnas tienen ``index=True`` en el modelo Python
    (``mapped_column(..., index=True)``). AquÃ­ sÃ³lo declaramos los 3 que
    NO estÃ¡n cubiertos: el Ã­ndice compuesto por tenant/key/started_at, y
    los Ã­ndices simples por ``started_at`` y ``created_at``.
    """
    _safe_create_table(_DDL_REPORT_RUNS)
    op.execute(text(_IDX_REPORT_RUNS_TENANT_KEY_STARTED))
    op.execute(text(_IDX_REPORT_RUNS_STARTED_AT))
    op.execute(text(_IDX_REPORT_RUNS_CREATED_AT))
    logger.info("report_runs: tabla + 3 Ã­ndices explÃ­citos creados OK")


def downgrade() -> None:
    """Drop de los Ã­ndices y la tabla (orden importa por FK)."""
    op.execute(text("DROP INDEX IF EXISTS ix_report_runs_created_at"))
    op.execute(text("DROP INDEX IF EXISTS ix_report_runs_started_at"))
    op.execute(text("DROP INDEX IF EXISTS ix_report_runs_tenant_key_started"))
    op.execute(text("DROP TABLE IF EXISTS report_runs"))
    logger.info("report_runs: tabla + Ã­ndices eliminados OK")