"""Migración idempotente: agrega columnas RFM a ``customers`` si no existen.

CONTEXTO
========
HU_26 agregó las columnas RFM al modelo ``Customer`` en
``app/models/customer.py`` (línea 42-49):

  - rfm_segment   VARCHAR(40)  NULL — nombre del segmento RFM
  - r_score      INTEGER      NULL — quintil recency  1-5
  - f_score      INTEGER      NULL — quintil frequency 1-5
  - m_score      INTEGER      NULL — quintil monetary  1-5
  - rfm_cell     VARCHAR(8)   NULL — celda "RFM" ej. "555"
  - rfm_updated_at VARCHAR(40) NULL — timestamp ISO última corrida

La migración Alembic ``2026_10_07_0001_customer_rfm_columns.py`` fue creada
pero NUNCA se ejecutó en producción (Railway no aplica Alembic automáticamente
en cada deploy; el entrypoint.sh original fue modificado para usar bootstrap_
migrate.py que tiene lógica especial para DBs vírgenes vs. existentes).

PATRÓN
======
Mismo patrón que ``migrate_product_v8_columns.py``:
  - ``ALTER TABLE ... ADD COLUMN IF NOT EXISTS`` (Postgres)
  - SQLite: try/except + chequeo con ``PRAGMA table_info``
  - Idempotente: correr N veces no rompe nada

Desde ``init_db()`` en ``app/database.py``:
    from scripts.migrate_rfm_columns import ensure_rfm_columns
    ensure_rfm_columns()
"""
from __future__ import annotations

import logging
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("migrate.rfm_columns")

# Catálogo de columnas RFM — alineado 1-a-1 con app/models/customer.py
# Todas son NULL porque el cálculo RFM es opcional.
RFM_COLUMNS = (
    # (column, sql_type_with_default, comment)
    ("rfm_segment",    "VARCHAR(40)",  "HU_26: nombre del segmento RFM"),
    ("r_score",        "INTEGER",      "HU_26: quintil recency  1-5"),
    ("f_score",        "INTEGER",      "HU_26: quintil frequency 1-5"),
    ("m_score",        "INTEGER",      "HU_26: quintil monetary  1-5"),
    ("rfm_cell",       "VARCHAR(8)",   "HU_26: celda RFM ej. '555'"),
    # rfm_updated_at lleva comillas porque ``updated_at`` puede ser keyword
    # en algunos dialectos; el prefijo rfm_ no alcanza para todos los
    # drivers, lo entrecomillamos por portabilidad.
    ('"rfm_updated_at"', "VARCHAR(40)", "HU_26: timestamp ISO última corrida RFM"),
)

RFM_INDEXES = (
    # (index_name, table, column) — IF NOT EXISTS en ambos dialectos
    ("ix_customers_rfm_segment", "customers", "rfm_segment"),
    ("ix_customers_rfm_cell",    "customers", "rfm_cell"),
)


def _dialect_name(conn) -> str:
    d = getattr(conn, "dialect", None)
    if d is not None:
        return d.name
    engine = getattr(conn, "engine", None)
    if engine is not None:
        return engine.dialect.name
    return ""


def _table_exists(conn, table: str) -> bool:
    from sqlalchemy import text
    dialect = _dialect_name(conn)
    if dialect == "sqlite":
        row = conn.execute(
            text("SELECT 1 FROM sqlite_master WHERE type='table' AND name=:n"),
            {"n": table},
        ).first()
        return row is not None
    # Postgres
    row = conn.execute(
        text(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = current_schema() AND table_name = :n"
        ),
        {"n": table},
    ).first()
    return row is not None


def _column_exists(conn, table: str, column: str) -> bool:
    from sqlalchemy import text
    dialect = _dialect_name(conn)
    if dialect == "sqlite":
        rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
        return any(r[1] == column for r in rows)
    # Postgres
    row = conn.execute(
        text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_schema = current_schema() "
            "AND table_name = :t AND column_name = :c"
        ),
        {"t": table, "c": column},
    ).first()
    return row is not None


def _index_exists(conn, index_name: str) -> bool:
    from sqlalchemy import text
    dialect = _dialect_name(conn)
    if dialect == "sqlite":
        row = conn.execute(
            text(
                "SELECT 1 FROM sqlite_master "
                "WHERE type='index' AND name=:n"
            ),
            {"n": index_name},
        ).first()
        return row is not None
    # Postgres
    row = conn.execute(
        text(
            "SELECT 1 FROM pg_indexes "
            "WHERE indexname = :n"
        ),
        {"n": index_name},
    ).first()
    return row is not None


def _add_column_if_missing(conn, table: str, column: str, sql_type: str) -> str:
    """Agrega table.column con sql_type si no existe. Devuelve 'added'/'exists'/'error'."""
    from sqlalchemy import text

    if _column_exists(conn, table, column):
        return "exists"

    dialect = _dialect_name(conn)
    try:
        if dialect == "sqlite":
            conn.execute(text(f'ALTER TABLE "{table}" ADD COLUMN "{column}" {sql_type}'))
        else:
            conn.execute(
                text(f'ALTER TABLE "{table}" ADD COLUMN IF NOT EXISTS "{column}" {sql_type}')
            )
        return "added"
    except Exception as e:
        log.warning("No se pudo agregar %s.%s (%s): %s", table, column, sql_type, e)
        return "error"


def _create_index_if_missing(
    conn, index_name: str, table: str, column: str
) -> str:
    """Crea índice IF NOT EXISTS. Devuelve 'added'/'exists'/'error'/'skipped'."""
    from sqlalchemy import text

    if _index_exists(conn, index_name):
        return "exists"

    dialect = _dialect_name(conn)
    try:
        sql = f'CREATE INDEX IF NOT EXISTS "{index_name}" ON "{table}" ("{column}")'
        conn.execute(text(sql))
        return "added"
    except Exception as e:
        log.warning("No se pudo crear índice %s: %s", index_name, e)
        return "error"


def ensure_rfm_columns() -> int:
    """Asegura que las 6 columnas RFM y sus índices existan en customers.

    Idempotente. Se loguea cada cambio. Devuelve el número total de
    objetos (columnas + índices) agregados.
    """
    from app.database import engine

    added_total = 0

    with engine.begin() as conn:
        if not _table_exists(conn, "customers"):
            log.info("Tabla 'customers' no existe (se creará con create_all) — skip")
            return 0

        # Agregar columnas
        for col, sql_type, comment in RFM_COLUMNS:
            result = _add_column_if_missing(conn, "customers", col, sql_type)
            if result == "added":
                log.info("customers.%s AGREGADA (%s) — %s", col, sql_type, comment)
                added_total += 1
            elif result == "exists":
                log.debug("customers.%s ya existe — OK", col)

        # Crear índices
        for idx_name, tbl, col in RFM_INDEXES:
            result = _create_index_if_missing(conn, idx_name, tbl, col)
            if result == "added":
                log.info("Índice %s creado en customers(%s)", idx_name, col)
                added_total += 1
            elif result == "exists":
                log.debug("Índice %s ya existe — OK", idx_name)

    log.info(
        "ensure_rfm_columns OK — objetos agregados=%s db=%s",
        added_total,
        engine.dialect.name,
    )
    return added_total


def run() -> int:
    """Entry-point para ``python -m scripts.migrate_rfm_columns``."""
    try:
        added = ensure_rfm_columns()
        if added:
            log.warning(
                "⚠ %s objeto(s) RFM fueron agregados a la DB. "
                "Re-deploy recomendado si los endpoints siguen fallando.",
                added,
            )
        return 0
    except Exception as e:
        log.exception("migrate_rfm_columns falló: %s", e)
        return 1


if __name__ == "__main__":
    sys.exit(run())
