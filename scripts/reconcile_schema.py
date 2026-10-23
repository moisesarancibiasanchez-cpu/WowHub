"""Reconciliación idempotente de esquema contra la DB real.

Problema (Bug 1 — producción, 2026-10-21)
-----------------------------------------
``GET /api/v1/tenants/{id}/products`` devolvía 500::

    psycopg.errors.UndefinedColumn: column products.product_type does not exist

Causa raíz: la DB de Railway nació de ``Base.metadata.create_all()`` (no de
Alembic). El bootstrap (``scripts/bootstrap_migrate.py``) detecta ese estado
como ``legacy`` y, como ``_highest_fully_applied_revision()`` sólo comprobaba
las tablas declaradas con ``op.create_table``, **ignoraba por completo las
columnas agregadas con ``op.add_column``**. Resultado: la revisión HU_50–HU_65
(única migración del proyecto que combina ``create_table`` + ``add_column``)
se daba por aplicada y el bootstrap sellaba la DB en ``head`` sin haber
ejecutado jamás sus 15 ``ADD COLUMN`` sobre ``products`` / ``customers`` /
``quote_items``.

``Base.metadata.create_all()`` no puede reparar esto: sólo crea tablas
inexistentes, nunca ALTER TABLE sobre tablas que ya existen.

Qué hace este script
--------------------
Compara ``Base.metadata`` (modelos activos) contra el esquema real de la DB y
repara la diferencia, de forma **idempotente** y **agnóstica del estado de
Alembic**:

1. Crea las tablas que falten (mismo criterio que ``create_all``).
2. Agrega las columnas que falten, derivando el tipo del modelo y un valor
   por defecto seguro.
3. Crea los índices declarados en los modelos que no existan.

Es idempotente: correrlo N veces produce el mismo esquema. Es seguro: nunca
hace ``DROP``, nunca modifica datos, nunca altera columnas existentes.

Se invoca desde ``scripts/entrypoint.sh`` DESPUÉS de ``create_all`` y antes
de arrancar uvicorn, de modo que el esquema queda consistente aunque Alembic
esté en cualquier estado (``legacy``, ``stamped``, ``alembic`` o ``failed``).

Uso manual (diagnóstico)::

    DATABASE_URL=postgresql://... python -m scripts.reconcile_schema
    DATABASE_URL=postgresql://... python -m scripts.reconcile_schema --dry-run
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from typing import Any

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine

logger = logging.getLogger("wowhub.reconcile_schema")

# ── Tipos que NO sabemos crear de forma segura ───────────────────────────
# Los ENUM de PostgreSQL requieren crear el TYPE en la DB antes de usarlo.
# Crearlo aquí es destructivo si el TYPE existe con otra forma, así que se
# omiten y se reportan para revisión manual.
UNSAFE_TYPES = ("Enum", "ARRAY", "HSTORE", "JSONBPath")


def _engine() -> Engine:
    """Engine sincrónico desde ``DATABASE_URL``."""
    raw = os.environ.get("DATABASE_URL", "").strip()
    if not raw:
        raise SystemExit("DATABASE_URL no configurada")
    return create_engine(raw, future=True)


def _type_ddl(col: Any, dialect: Any) -> str | None:
    """DDL del tipo de la columna, o ``None`` si el tipo no es seguro de crear."""
    type_name = type(col.type).__name__
    if type_name in UNSAFE_TYPES:
        return None
    try:
        return col.type.compile(dialect=dialect)
    except Exception as exc:  # noqa: BLE001
        logger.warning("No se pudo compilar el tipo de %s: %s", col.name, exc)
        return None


def _server_default_sql(col: Any, dialect: Any) -> str | None:
    """Literal SQL del default del modelo, o ``None`` si no hay uno usable."""
    sd = col.server_default
    if sd is not None:
        arg = getattr(sd, "arg", None)
        if isinstance(arg, str):
            # ``server_default="standard"`` → literal de texto.
            return repr(arg)
        try:
            return str(arg.compile(dialect=dialect))
        except Exception:  # noqa: BLE001
            return None

    # Default a nivel Python: sólo sirve si es un escalar literal.
    default = col.default
    if default is not None:
        arg = getattr(default, "arg", None)
        if isinstance(arg, bool):
            return "true" if arg else "false"
        if isinstance(arg, (int, float)):
            return str(arg)
        if isinstance(arg, str):
            return repr(arg)
    return None


def _fallback_default_sql(col: Any) -> str | None:
    """Default de último recurso según el tipo, para columnas NOT NULL."""
    type_name = type(col.type).__name__
    if type_name in ("Boolean",):
        return "false"
    if type_name in ("Integer", "BigInteger", "SmallInteger", "Float", "Numeric"):
        return "0"
    if type_name in ("JSON",):
        return "'{}'"
    if type_name in ("String", "Text"):
        return "''"
    if type_name in ("DateTime", "Date", "TIMESTAMP"):
        return None  # se deja NULL
    return None


def _quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def reconcile(engine: Engine, dry_run: bool = False) -> dict[str, Any]:
    """Compara modelos contra el esquema real y repara la diferencia.

    Devuelve un reporte con las acciones aplicadas (o que se aplicarían si
    ``dry_run`` es True).
    """
    from app.database import Base  # noqa: WPS433 (import local: evita ciclo)
    import app.models  # noqa: F401,WPS433

    dialect = engine.dialect
    insp = inspect(engine)
    existing_tables = set(insp.get_table_names())

    report: dict[str, Any] = {
        "tables_created": [],
        "columns_added": [],
        "columns_skipped_unsafe_type": [],
        "indexes_created": [],
        "errors": [],
    }

    # ── 1. Tablas ─────────────────────────────────────────────────────────
    for table in Base.metadata.sorted_tables:
        if table.name in existing_tables:
            continue
        logger.info("[reconcile] falta la tabla %s — creando", table.name)
        report["tables_created"].append(table.name)
        if not dry_run:
            try:
                table.create(bind=engine, checkfirst=True)
                existing_tables.add(table.name)
            except Exception as exc:  # noqa: BLE001
                report["errors"].append(f"create table {table.name}: {exc}")
                logger.error("[reconcile] no se pudo crear %s: %s", table.name, exc)

    # ── 2. Columnas ───────────────────────────────────────────────────────
    for table in Base.metadata.sorted_tables:
        if table.name not in existing_tables:
            continue
        try:
            live_cols = {c["name"] for c in insp.get_columns(table.name)}
        except Exception as exc:  # noqa: BLE001
            report["errors"].append(f"inspect columns {table.name}: {exc}")
            continue

        for col in table.columns:
            if col.name in live_cols:
                continue

            ddl_type = _type_ddl(col, dialect)
            if ddl_type is None:
                report["columns_skipped_unsafe_type"].append(
                    f"{table.name}.{col.name} ({type(col.type).__name__})"
                )
                logger.warning(
                    "[reconcile] NO se agrega %s.%s (tipo %s no seguro de crear)",
                    table.name, col.name, type(col.type).__name__,
                )
                continue

            default_sql = _server_default_sql(col, dialect)
            nullable = bool(col.nullable)

            if not nullable and default_sql is None:
                default_sql = _fallback_default_sql(col)
                if default_sql is None:
                    # Sin default no podemos cumplir NOT NULL sobre una tabla
                    # que ya tiene filas: se agrega nullable y se avisa.
                    nullable = True
                    report["columns_skipped_unsafe_type"].append(
                        f"{table.name}.{col.name} (NOT NULL sin default seguro)"
                    )

            parts = [f"ADD COLUMN {_quote_ident(col.name)} {ddl_type}"]
            if not nullable:
                parts.append("NOT NULL")
            if default_sql is not None:
                parts.append(f"DEFAULT {default_sql}")

            ddl = f"ALTER TABLE {_quote_ident(table.name)} " + " ".join(parts)
            logger.info("[reconcile] %s", ddl)
            report["columns_added"].append(f"{table.name}.{col.name}")
            if dry_run:
                continue

            try:
                with engine.begin() as conn:
                    if dialect.name == "postgresql":
                        conn.execute(
                            text(
                                f"ALTER TABLE {_quote_ident(table.name)} "
                                f"ADD COLUMN IF NOT EXISTS {_quote_ident(col.name)} "
                                f"{ddl_type}"
                                + ("" if nullable else " NOT NULL")
                                + (f" DEFAULT {default_sql}" if default_sql else "")
                            )
                        )
                    else:
                        conn.execute(text(ddl))
            except Exception as exc:  # noqa: BLE001
                report["errors"].append(f"add column {table.name}.{col.name}: {exc}")
                logger.error(
                    "[reconcile] no se pudo agregar %s.%s: %s",
                    table.name, col.name, exc,
                )

    # ── 3. Índices ────────────────────────────────────────────────────────
    for table in Base.metadata.sorted_tables:
        if table.name not in existing_tables:
            continue
        try:
            live_indexes = {i["name"] for i in insp.get_indexes(table.name)}
        except Exception as exc:  # noqa: BLE001
            report["errors"].append(f"inspect indexes {table.name}: {exc}")
            continue

        for index in table.indexes:
            if index.name in live_indexes:
                continue
            logger.info("[reconcile] falta el índice %s — creando", index.name)
            report["indexes_created"].append(index.name)
            if dry_run:
                continue
            try:
                index.create(bind=engine, checkfirst=True)
            except Exception as exc:  # noqa: BLE001
                report["errors"].append(f"create index {index.name}: {exc}")
                logger.error("[reconcile] no se pudo crear el índice %s: %s", index.name, exc)

    return report


def main() -> int:
    """Punto de entrada CLI."""
    parser = argparse.ArgumentParser(description="Reconcilia el esquema con los modelos.")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Sólo informa qué haría, sin modificar la DB.",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="[reconcile_schema] %(message)s",
        stream=sys.stdout,
    )

    eng = _engine()
    try:
        report = reconcile(eng, dry_run=args.dry_run)
    finally:
        eng.dispose()

    verb = "se agregaría" if args.dry_run else "se agregó"
    logger.info(
        "Resumen — tablas %s: %d | %s %d columnas | índices %s: %d | omitidas: %d | errores: %d",
        "a crear" if args.dry_run else "creadas",
        len(report["tables_created"]),
        verb, len(report["columns_added"]),
        "a crear" if args.dry_run else "creados",
        len(report["indexes_created"]),
        len(report["columns_skipped_unsafe_type"]),
        len(report["errors"]),
    )
    for item in report["columns_added"]:
        logger.info("  + columna %s", item)
    for item in report["columns_skipped_unsafe_type"]:
        logger.warning("  ! omitida %s", item)
    for item in report["errors"]:
        logger.error("  x %s", item)

    if report["errors"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
