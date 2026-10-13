"""Migración idempotente: agrega columnas de V8 a la tabla `products` (y
defensivamente a `business_costs`) si no existen.

CONTEXTO
========
El commit ``c1e7a44 feat(products): Fase 3 V8 — calculadora margen/precio
sugerido`` agregó la columna ``products.production_time_min`` al modelo
SQLAlchemy. La "migración in-place" que ese commit describe sólo se aplicó
al SQLite local (``wowhub.db``); la base Postgres de producción en Railway
nunca recibió el ``ALTER TABLE``.

Resultado: ``GET /api/v1/tenants/{tid}/products?order_by=position`` corre
``SELECT ... production_time_min`` y Postgres lanza
``column "production_time_min" of relation "products" does not exist``
→ 500 al cliente.

El proyecto NO usa Alembic (no hay carpeta ``alembic/``) sino
``Base.metadata.create_all()`` + scripts puntuales (``cashier_pin``,
``ai_agent_kind``). Mantenemos el mismo patrón:

  - Lista explícita de columnas V8 a asegurar.
  - ``ALTER TABLE ... ADD COLUMN IF NOT EXISTS`` (Postgres).
  - Para SQLite: chequeo via ``pragma table_info`` y ``ALTER TABLE`` clásico.
  - Idempotente: correr N veces no rompe nada.

USO
===
Como script:
    python -m scripts.migrate_product_v8_columns

Desde ``entrypoint.sh`` (después de ``migrate_ai_help_enum``):
    python -m scripts.migrate_product_v8_columns || echo "warn ..."

Desde ``init_db()`` en ``app/database.py`` (auto-heal en cada arranque):
    from scripts.migrate_product_v8_columns import ensure_v8_columns
    ensure_v8_columns()
"""
from __future__ import annotations

import logging
import os
import sys
from typing import Iterable, Tuple

# Bootstrap: poder correr tanto ``python -m scripts.migrate_xxx`` como
# ``from scripts.migrate_xxx import ...``. Agrega el root al sys.path si
# hace falta.
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("migrate.v8_columns")


# ── Catálogo de columnas V8 a asegurar ──────────────────────────
# Formato: (tabla, columna, tipo_sql, default_sql, default_python)
#
# El default se aplica SÓLO a filas existentes. Si la columna es NOT NULL
# sin default, Postgres requiere un default explícito (o no aplicar NOT NULL).
# Mantenemos los defaults alineados con el modelo SQLAlchemy.
#
# Para ``products.production_time_min`` usamos ``NOT NULL DEFAULT 0`` igual
# que el modelo (``default=0, nullable=False``).
V8_PRODUCT_COLUMNS: Tuple[Tuple[str, str, str, str], ...] = (
    # (column, sql_type_with_default, python_default, comment)
    # production_time_min: agregado en c1e7a44 (V8 Fase 3)
    # mano de obra para cálculo de costo real + precio sugerido.
    (
        "production_time_min",
        "INTEGER NOT NULL DEFAULT 0",
        0,
        "V8 Fase 3: mano de obra en minutos",
    ),
)

# Por si la tabla `business_costs` quedó con schema parcial de un deploy
# previo. (Si nunca existió, create_all ya la crea completa — no hace
# nada acá.) Mantenemos la lista como defensa contra drift futuro.
V8_BUSINESS_COSTS_COLUMNS: Tuple[Tuple[str, str, str], ...] = (
    # Si en el futuro se agregan columnas a BusinessCosts que no estén en
    # este script, agregarlas acá con su default. Mientras tanto, la lista
    # está vacía porque el modelo se introdujo en 183faa7 ya completo.
)


def _is_postgres(engine) -> bool:
    return engine.dialect.name in ("postgresql", "postgres")


def _is_sqlite(engine) -> bool:
    return engine.dialect.name == "sqlite"


def _dialect_name(conn) -> str:
    """Devuelve el nombre del dialecto de la conexión de forma robusta.

    SQLAlchemy 2.0 deprecó ``Connection.bind``; usamos ``Connection.dialect``
    (siempre presente) que es la API canónica.
    """
    d = getattr(conn, "dialect", None)
    if d is not None:
        return d.name
    # Fallback extremo (no debería pasar en SA 2.0+)
    engine = getattr(conn, "engine", None)
    if engine is not None:
        return engine.dialect.name
    return ""


def _table_exists(conn, table: str) -> bool:
    """True si la tabla existe en el schema actual."""
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
    """True si la columna existe en la tabla."""
    from sqlalchemy import text
    dialect = _dialect_name(conn)

    if dialect == "sqlite":
        rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
        # PRAGMA table_info devuelve: cid, name, type, notnull, dflt_value, pk
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


def _add_column_if_missing(conn, table: str, column: str, sql_type: str) -> str:
    """Agrega ``table.column`` con ``sql_type`` si no existe.

    Devuelve 'added' / 'exists' / 'error' para logging.
    """
    from sqlalchemy import text

    if _column_exists(conn, table, column):
        return "exists"

    dialect = _dialect_name(conn)

    try:
        if dialect == "sqlite":
            # SQLite no soporta IF NOT EXISTS en ADD COLUMN, pero ya
            # chequeamos con pragma table_info arriba.
            conn.execute(text(f'ALTER TABLE "{table}" ADD COLUMN "{column}" {sql_type}'))
        else:
            # Postgres: IF NOT EXISTS nativo
            conn.execute(text(f'ALTER TABLE "{table}" ADD COLUMN IF NOT EXISTS "{column}" {sql_type}'))
        return "added"
    except Exception as e:  # pragma: no cover - defensivo
        log.warning("No se pudo agregar %s.%s (%s): %s", table, column, sql_type, e)
        return "error"


def ensure_v8_columns() -> int:
    """Asegura que las columnas V8 existan en products y business_costs.

    Idempotente. Se loguea cada cambio. Devuelve el número de columnas
    agregadas (0 si el schema ya estaba al día).
    """
    from app.database import engine

    added_total = 0
    inspected = 0

    with engine.begin() as conn:
        # ── products ──
        if _table_exists(conn, "products"):
            for col, sql_type, _py_default, comment in V8_PRODUCT_COLUMNS:
                inspected += 1
                result = _add_column_if_missing(conn, "products", col, sql_type)
                if result == "added":
                    log.info("products.%s AGREGADA (%s) — %s", col, sql_type, comment)
                    added_total += 1
                elif result == "exists":
                    log.debug("products.%s ya existe — OK", col)
        else:
            log.info("Tabla products no existe (se creará con create_all) — skip")

        # ── business_costs ──
        if _table_exists(conn, "business_costs"):
            for col, sql_type, _py_default in V8_BUSINESS_COSTS_COLUMNS:
                inspected += 1
                result = _add_column_if_missing(conn, "business_costs", col, sql_type)
                if result == "added":
                    log.info("business_costs.%s AGREGADA (%s)", col, sql_type)
                    added_total += 1
        else:
            log.info("Tabla business_costs no existe (se creará con create_all) — skip")

    log.info(
        "ensure_v8_columns OK — inspeccionadas=%s agregadas=%s db=%s",
        inspected,
        added_total,
        engine.dialect.name,
    )
    return added_total


def run() -> int:
    """Entry-point para ``python -m scripts.migrate_product_v8_columns``."""
    try:
        added = ensure_v8_columns()
        if added:
            log.warning("⚠ %s columna(s) V8 fueron agregadas. Re-deploy recomendado.", added)
        return 0
    except Exception as e:
        log.exception("migrate_product_v8_columns falló: %s", e)
        return 1


if __name__ == "__main__":
    sys.exit(run())
