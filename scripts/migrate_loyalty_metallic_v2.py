"""Migración idempotente para el sistema metálico V2 de fidelización.

Asegura que existan las 7 columnas nuevas en `loyalty_campaigns`:
  - metal_c1..metal_c5 (VARCHAR 7 NULL) — gradient stops
  - metal_angle       (INTEGER NULL)   — grados 0-360
  - sheen_opacity     (INTEGER NULL)   — 0-100

USO
  Como script:    python -m scripts.migrate_loyalty_metallic_v2
  Desde init_db:  from scripts.migrate_loyalty_metallic_v2 import ensure_metallic_columns
                  ensure_metallic_columns()
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
log = logging.getLogger("migrate.loyalty_metallic_v2")


# Catálogo de columnas V2 (7 columnas nuevas en loyalty_campaigns)
METALLIC_V2_COLUMNS: Tuple[Tuple[str, str, str, str], ...] = (
    # (tabla, columna, sql_type, comment)
    ("loyalty_campaigns", "metal_c1",      "VARCHAR(7)",  "V2: gradient stop 1 (color claro)"),
    ("loyalty_campaigns", "metal_c2",      "VARCHAR(7)",  "V2: gradient stop 2"),
    ("loyalty_campaigns", "metal_c3",      "VARCHAR(7)",  "V2: gradient stop 3 (highlight central)"),
    ("loyalty_campaigns", "metal_c4",      "VARCHAR(7)",  "V2: gradient stop 4"),
    ("loyalty_campaigns", "metal_c5",      "VARCHAR(7)",  "V2: gradient stop 5 (sombra)"),
    ("loyalty_campaigns", "metal_angle",   "INTEGER",     "V2: ángulo del gradiente en grados (0-360)"),
    ("loyalty_campaigns", "sheen_opacity", "INTEGER",     "V2: opacidad del sheen especular (0-100)"),
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


def ensure_metallic_columns() -> int:
    """Asegura las 7 columnas metálicas V2. Idempotente. Devuelve cuántas agregó."""
    from app.database import engine, Base
    from app.models import loyalty_pass  # noqa: F401
    Base.metadata.create_all(bind=engine)  # por si la tabla loyalty_campaigns no existe

    added_total = 0
    with engine.begin() as conn:
        if not _table_exists(conn, "loyalty_campaigns"):
            log.warning("Tabla loyalty_campaigns no existe — create_all la debería crear")
            return 0
        for table, col, sql_type, comment in METALLIC_V2_COLUMNS:
            result = _add_column_if_missing(conn, table, col, sql_type)
            if result == "added":
                log.info("%s.%s AGREGADA (%s) — %s", table, col, sql_type, comment)
                added_total += 1
            elif result == "exists":
                log.debug("%s.%s ya existe — OK", table, col)
    log.info(
        "ensure_metallic_columns OK — agregadas=%s db=%s",
        added_total,
        engine.dialect.name,
    )
    return added_total


def run() -> int:
    try:
        added = ensure_metallic_columns()
        if added:
            log.warning("⚠ %s columna(s) metálica(s) V2 fueron agregadas.", added)
        return 0
    except Exception as e:
        log.exception("migrate_loyalty_metallic_v2 falló: %s", e)
        return 1


if __name__ == "__main__":
    sys.exit(run())
