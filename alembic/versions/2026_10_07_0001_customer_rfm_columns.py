"""HU_26 — agregar columnas RFM persistentes a ``customers``.

Revision ID: 2026_10_07_0001
Revises: 2026_10_06_0004
Create Date: 2026-10-07

Contexto
--------
La tarea ``app.tasks.rfm.run_rfm_analysis`` ya calcula scores RFM
quintiles (1-5) y nombre de segmento para los clientes del tenant,
pero solo los retornaba en la respuesta de Celery — NO los persistía
(ver TODO histórico línea 121 de ``app/tasks/rfm.py``).

Esta migración agrega 6 columnas idempotentes a la tabla ``customers``:

- ``rfm_segment VARCHAR(40) NULL``            — nombre del segmento
  (``champions``, ``loyal``, ``potential``, ``new``, ``about_to_sleep``,
  ``at_risk``, ``hibernating``, ``lost``).
- ``r_score INTEGER NULL``                    — quintil recency 1-5.
- ``f_score INTEGER NULL``                    — quintil frequency 1-5.
- ``m_score INTEGER NULL``                    — quintil monetary 1-5.
- ``rfm_cell VARCHAR(8) NULL``                — concatenado ``"RFM"``
  (ej. ``"555"``, ``"111"``).
- ``"rfm_updated_at" VARCHAR(40) NULL``        — timestamp ISO de la
  última corrida RFM que escribió los valores.

Todas las columnas se crean ``NULL`` (sin default) porque el cálculo
RFM es opcional: los tenants que aún no han corrido el análisis no
deben quedar con valores falsos (un ``0`` o ``""`` se confundiría con
un quintil válido en la UI). Los endpoints exponen estos campos como
``Optional`` y la UI los trata como "sin clasificar" hasta la primera
corrida.

Idempotencia cross-DB
---------------------
Mismo patrón que ``2026_10_02_0002_site_blocks_hu42.py``:

- PostgreSQL (producción Railway): ``ALTER TABLE … ADD COLUMN IF NOT
  EXISTS`` (PG 9.6+).
- SQLite (tests/CI): try/except silencioso porque ``ALTER TABLE ADD
  COLUMN`` NO soporta ``IF NOT EXISTS``.

Tipos validados contra ``app/models/customer.py``:

- ``String(40)`` para ``rfm_segment`` y ``rfm_updated_at`` (alineado
  con ``segmento`` y ``last_order_at`` ya existentes en la tabla).
- ``String(8)`` para ``rfm_cell`` — alcanza holgadamente para ``"555"``.
- ``Integer`` para los scores (quintiles 1-5).
"""
from __future__ import annotations

import logging

from alembic import op
from sqlalchemy import text

revision = "2026_10_07_0001"
down_revision = "2026_10_06_0004"
branch_labels = None
depends_on = None


logger = logging.getLogger("alembic.runtime.migration")


# DDL por columna. Mantener alineado 1-a-1 con ``app/models/customer.py``.
# ``rfm_updated_at`` lleva comillas porque es palabra reservada en algunos
# dialectos (PG trata ``UPDATE`` como keyword pero acepta ``rfm_updated_at``
# sin comillas; lo entrecomillamos igual por portabilidad máxima).
_DDL_RFM_SEGMENT = "VARCHAR(40)"
_DDL_R_SCORE = "INTEGER"
_DDL_F_SCORE = "INTEGER"
_DDL_M_SCORE = "INTEGER"
_DDL_RFM_CELL = "VARCHAR(8)"
_DDL_RFM_UPDATED_AT = "VARCHAR(40)"


def _add_column_if_not_exists(table: str, column: str, ddl: str, quoted: bool = False) -> None:
    """Agrega una columna idempotente: usa IF NOT EXISTS en PostgreSQL,
    o un try/except silencioso en SQLite (que no soporta IF NOT EXISTS).

    ``quoted=True`` entrecomilla el identificador de columna (necesario
    cuando coincide con una palabra reservada del dialecto).
    """
    bind = op.get_bind()
    col_ident = f'"{column}"' if quoted else column
    if bind.dialect.name == "postgresql":
        op.execute(
            text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col_ident} {ddl}")
        )
    else:
        # SQLite: try/except. La columna ya existe → ignora.
        from sqlalchemy.exc import OperationalError
        try:
            op.execute(text(f"ALTER TABLE {table} ADD COLUMN {col_ident} {ddl}"))
        except OperationalError as exc:
            logger.warning(
                "ADD COLUMN %s.%s ya existe (SQLite): %s", table, column, exc,
            )


def upgrade() -> None:
    """Agrega las 6 columnas RFM a la tabla ``customers`` (todas NULL)."""
    bind = op.get_bind()
    table = "customers"
    _add_column_if_not_exists(table, "rfm_segment", _DDL_RFM_SEGMENT)
    _add_column_if_not_exists(table, "r_score", _DDL_R_SCORE)
    _add_column_if_not_exists(table, "f_score", _DDL_F_SCORE)
    _add_column_if_not_exists(table, "m_score", _DDL_M_SCORE)
    _add_column_if_not_exists(table, "rfm_cell", _DDL_RFM_CELL)
    # rfm_updated_at: quoted porque en algunos dialectos ``updated_at``
    # se trata como palabra reservada — el prefijo ``rfm_`` no alcanza
    # a resguardarnos si el driver aplica quoting automático distinto.
    _add_column_if_not_exists(table, "rfm_updated_at", _DDL_RFM_UPDATED_AT)

    # Índices idempotentes (uno por columna indexada según el modelo).
    # ``rfm_segment`` y ``rfm_cell`` son los filtros del dashboard RFM.
    if bind.dialect.name == "postgresql":
        op.execute(
            text("CREATE INDEX IF NOT EXISTS ix_customers_rfm_segment ON customers (rfm_segment)")
        )
        op.execute(
            text("CREATE INDEX IF NOT EXISTS ix_customers_rfm_cell ON customers (rfm_cell)")
        )
    else:
        # SQLite: CREATE INDEX IF NOT EXISTS sí está soportado (>= 3.8.0).
        op.execute(
            text("CREATE INDEX IF NOT EXISTS ix_customers_rfm_segment ON customers (rfm_segment)")
        )
        op.execute(
            text("CREATE INDEX IF NOT EXISTS ix_customers_rfm_cell ON customers (rfm_cell)")
        )

    logger.info("HU_26 — customers: +rfm_segment, +r_score, +f_score, +m_score, +rfm_cell, +rfm_updated_at")


def downgrade() -> None:
    """Elimina las columnas y los índices.

    Compatible PG (DROP COLUMN IF EXISTS). SQLite no soporta DROP COLUMN
    en versiones < 3.35.0; el downgrade puede fallar ahí, igual que en
    migraciones HU_33/HU_42 anteriores — sólo se invoca manualmente.
    """
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(text("DROP INDEX IF EXISTS ix_customers_rfm_cell"))
        op.execute(text("DROP INDEX IF EXISTS ix_customers_rfm_segment"))
        op.execute(text('ALTER TABLE customers DROP COLUMN IF EXISTS "rfm_updated_at"'))
        op.execute(text("ALTER TABLE customers DROP COLUMN IF EXISTS rfm_cell"))
        op.execute(text("ALTER TABLE customers DROP COLUMN IF EXISTS m_score"))
        op.execute(text("ALTER TABLE customers DROP COLUMN IF EXISTS f_score"))
        op.execute(text("ALTER TABLE customers DROP COLUMN IF EXISTS r_score"))
        op.execute(text("ALTER TABLE customers DROP COLUMN IF EXISTS rfm_segment"))
    else:
        logger.warning(
            "downgrade SQLite no soportado en <3.35.0; "
            "considere recrear la tabla para revertir."
        )