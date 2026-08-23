"""Migración idempotente para los P0 del audit V8.

Asegura que existan las columnas/tablas nuevas:
  - customers.segmento (VARCHAR 40 NULL) — segmentación manual
  - Tablas `insumos` y `recetas` (V8 P0.1) — el create_all las crea
    si no existen, pero si la DB ya tiene productos/pedidos y nunca se
    importaron los modelos, faltarían. La función es defensiva.

USO
  Como script:    python -m scripts.migrate_v8_p0_columns
  Desde init_db:  from scripts.migrate_v8_p0_columns import ensure_v8_p0_objects
                  ensure_v8_p0_objects()
"""
from __future__ import annotations
import logging
import os
import sys
from typing import Tuple

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("migrate.v8_p0")


# Catálogo de columnas a asegurar (V8 P0 audit)
V8_P0_COLUMNS: Tuple[Tuple[str, str, str, str, str], ...] = (
    # (tabla, columna, sql_type, default_sql, comment)
    # customers.segmento (V8 P0.3): segmentación manual opcional.
    (
        "customers",
        "segmento",
        "VARCHAR(40)",
        "NULL",
        "V8 P0.3: segmento manual (nuevo, regular, recurrente, vip, inactivo). NULL = auto.",
    ),
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
    d = _dialect_name(conn)
    if d == "sqlite":
        row = conn.execute(
            text("SELECT 1 FROM sqlite_master WHERE type='table' AND name=:n"),
            {"n": table},
        ).first()
        return row is not None
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
    d = _dialect_name(conn)
    if d == "sqlite":
        rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
        return any(r[1] == column for r in rows)
    row = conn.execute(
        text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_schema = current_schema() "
            "AND table_name = :t AND column_name = :c"
        ),
        {"t": table, "c": column},
    ).first()
    return row is not None


def _add_column_if_missing(conn, table: str, column: str, sql_type: str) -> str:
    from sqlalchemy import text
    if _column_exists(conn, table, column):
        return "exists"
    d = _dialect_name(conn)
    try:
        if d == "sqlite":
            conn.execute(text(f'ALTER TABLE "{table}" ADD COLUMN "{column}" {sql_type}'))
        else:
            conn.execute(text(f'ALTER TABLE "{table}" ADD COLUMN IF NOT EXISTS "{column}" {sql_type}'))
        return "added"
    except Exception as e:  # pragma: no cover
        log.warning("No se pudo agregar %s.%s (%s): %s", table, column, sql_type, e)
        return "error"


def ensure_v8_p0_objects() -> int:
    """Asegura columnas V8 P0. Idempotente. Devuelve cuántas agregó."""
    from app.database import engine, Base
    # Importar modelos para que SQLAlchemy los registre en Base.metadata.
    # `insumos` y `recetas` se crearán automáticamente con create_all si
    # no existen. Aquí sólo agregamos columnas faltantes en tablas previas.
    from app.models import customer  # noqa: F401
    from app.models import insumo  # noqa: F401
    Base.metadata.create_all(bind=engine)  # crea tablas faltantes sin tocar las existentes

    added_total = 0
    with engine.begin() as conn:
        for table, col, sql_type, _default, comment in V8_P0_COLUMNS:
            if not _table_exists(conn, table):
                log.info("Tabla %s no existe (la creará create_all) — skip", table)
                continue
            result = _add_column_if_missing(conn, table, col, sql_type)
            if result == "added":
                log.info("%s.%s AGREGADA (%s) — %s", table, col, sql_type, comment)
                added_total += 1
            elif result == "exists":
                log.debug("%s.%s ya existe — OK", table, col)
    log.info(
        "ensure_v8_p0_objects OK — agregadas=%s db=%s",
        added_total,
        engine.dialect.name,
    )
    return added_total


def run() -> int:
    try:
        added = ensure_v8_p0_objects()
        if added:
            log.warning("⚠ %s objeto(s) V8 P0 fueron agregados.", added)
        return 0
    except Exception as e:
        log.exception("migrate_v8_p0_columns falló: %s", e)
        return 1


if __name__ == "__main__":
    sys.exit(run())
