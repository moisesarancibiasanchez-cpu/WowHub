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


# ═══════════════════════════════════════════════════════════════════════
# ENUM de PostgreSQL: labels y datos legacy
# ═══════════════════════════════════════════════════════════════════════
# Los TYPE ENUM de PG no admiten DROP VALUE, y el modelo puede usar labels
# distintos de los con los que la migración original creó el TYPE (típico:
# migración en MAYÚSCULAS + modelo en minúsculas con ``values_callable``).
#
# Casos reales en este proyecto (2026-10-23):
#   product_status  migración: DRAFT/ACTIVE/OUT_OF_STOCK/ARCHIVED
#                  modelo   : draft/active/out_of_stock/archived
#   quote_status    migración: DRAFT/SENT/VIEWED/ACCEPTED/REJECTED/EXPIRED
#                  modelo   : draft/sent/viewed/accepted/rejected/expired
#
# Consecuencia: PG rechaza el bind y SQLAlchemy rechaza la lectura:
#   DataError: invalid input value for enum product_status: "active"
#   LookupError: 'ACTIVE' is not among the defined enum values
#
# Se reparan aquí (capa agnóstica del estado de Alembic) porque el
# reconciliador se ejecuta SIEMPRE en el entrypoint, haya funcionado o no
# ``alembic upgrade head``.


def _pg_enum_labels(engine: Engine, type_name: str) -> set[str] | None:
    """Labels actuales del TYPE ENUM en PostgreSQL. ``None`` si no existe."""
    sql = text(
        "SELECT e.enumlabel FROM pg_type t "
        "JOIN pg_enum e ON e.enumtypid = t.oid "
        "WHERE t.typname = :name"
    )
    with engine.connect() as conn:
        rows = conn.execute(sql, {"name": type_name}).fetchall()
    if not rows:
        # El TYPE no existe o no tiene labels (no es un ENUM).
        with engine.connect() as conn:
            exists = conn.execute(
                text("SELECT 1 FROM pg_type WHERE typname = :name"),
                {"name": type_name},
            ).fetchone()
        return None if exists is None else set()
    return {r[0] for r in rows}


def _model_enum_labels() -> dict[str, set[str]]:
    """labels declarados por los modelos, por nombre de TYPE."""
    from sqlalchemy import Enum as SAEnum

    from app.database import Base  # noqa: WPS433 (import local: evita ciclo)
    import app.models  # noqa: F401,WPS433

    out: dict[str, set[str]] = {}
    for table in Base.metadata.sorted_tables:
        for col in table.columns:
            t = col.type
            if not isinstance(t, SAEnum) or not t.name:
                continue
            if t.enums:
                labels = set(t.enums)
            elif t.enum_class:
                labels = {str(e.value) for e in t.enum_class}
            else:
                labels = set()
            out.setdefault(t.name, set()).update(labels)
    return out


def _enum_columns() -> dict[str, list[tuple[str, str]]]:
    """Columnas de la metadata que usan cada TYPE ENUM: {tipo: [(tabla, col)]}."""
    from sqlalchemy import Enum as SAEnum

    from app.database import Base  # noqa: WPS433 (import local: evita ciclo)
    import app.models  # noqa: F401,WPS433

    out: dict[str, list[tuple[str, str]]] = {}
    for table in Base.metadata.sorted_tables:
        for col in table.columns:
            t = col.type
            if isinstance(t, SAEnum) and t.name:
                out.setdefault(t.name, []).append((table.name, col.name))
    return out


def _ensure_enum_labels(engine: Engine, dry_run: bool) -> tuple[list[str], list[str]]:
    """Agrega a cada TYPE ENUM los labels que el modelo declara.

    Usa ``ALTER TYPE ... ADD VALUE IF NOT EXISTS`` (aditivo, idempotente) y
    lo ejecuta en AUTOCOMMIT: PostgreSQL restricts ``ALTER TYPE ... ADD
    VALUE`` dentro de un bloque transaccional en versiones antiguas, y de
    todos modos no queremos que un fallo en un label contamine la sesión.
    """
    added: list[str] = []
    errors: list[str] = []
    model_labels = _model_enum_labels()

    for type_name, labels in sorted(model_labels.items()):
        current = _pg_enum_labels(engine, type_name)
        if current is None:
            logger.info(
                "[reconcile] el TYPE ENUM %s no existe en PostgreSQL — se omite "
                "(lo crea create_all si la columna depende de él)",
                type_name,
            )
            continue

        faltan = sorted(labels - current)
        if not faltan:
            continue

        for label in faltan:
            logger.info(
                "[reconcile] ALTER TYPE %s ADD VALUE IF NOT EXISTS '%s'",
                type_name, label,
            )
            added.append(f"{type_name}.{label}")
            if dry_run:
                continue
            try:
                with engine.connect().execution_options(
                    isolation_level="AUTOCOMMIT"
                ) as conn:
                    conn.execute(
                        text(f'ALTER TYPE "{type_name}" ADD VALUE IF NOT EXISTS \'{label}\'')
                    )
            except Exception as exc:  # noqa: BLE001
                errors.append(f"add enum value {type_name}.{label}: {exc}")
                logger.error(
                    "[reconcile] no se pudo agregar %s.%s: %s", type_name, label, exc
                )
    return added, errors


def _enum_label_mapping(
    current_labels: set[str], model_labels: set[str]
) -> dict[str, str]:
    """Mapeo legacy->model: {'ACTIVE': 'active', ...}.

    Sólo incluye pares donde el equivalente en minúsculas (lower) EXISTE en
    los labels del modelo. Es un mapeo 1:1 verificable: si el legacy
    'CANCELED' no tiene equivalente en el modelo (que usa 'cancelado'), no se
    toca la fila.
    """
    mapping: dict[str, str] = {}
    for label in current_labels:
        low = label.lower()
        if low in model_labels and label != low:
            mapping[label] = low
    return mapping


def _normalize_enum_data(engine: Engine, dry_run: bool) -> tuple[list[str], list[str]]:
    """Normaliza filas con labels legacy en MAYÚSCULAS a los del modelo.

    El modelo usa ``values_callable`` (minúsculas). Filas escritas por
    versiones anteriores del código pueden tener el NOMBRE del miembro
    ('ACTIVE'), que SQLAlchemy no sabe mapear:

        LookupError: 'ACTIVE' is not among the defined enum values

    Sólo se actualizan los valores cuyo equivalente en minúsculas (lower)
    EXISTE en el modelo: es un mapeo 1:1 verificable. Los labels legacy sin
    equivalente (p.ej. 'CANCELED' de order_status, cuyo valor en el modelo
    es 'cancelado') se dejan intactos y se reportan.
    """
    updated: list[str] = []
    errors: list[str] = []
    model_labels = _model_enum_labels()
    enum_cols = _enum_columns()

    for type_name, cols in sorted(enum_cols.items()):
        labels = model_labels.get(type_name, set())
        if not labels:
            continue
        current = _pg_enum_labels(engine, type_name)
        if not current:
            continue

        # Mapeo verificable: MAYÚSCULA -> minúscula presente en el modelo.
        mapping = _enum_label_mapping(current, labels)
        if not mapping:
            continue

        for table_name, col_name in cols:
            for old, new in sorted(mapping.items()):
                where = f'"{table_name}"."{col_name}" = :old'
                sql = (
                    f'UPDATE "{table_name}" SET "{col_name}" = :new '
                    f"WHERE {where}"
                )
                logger.info(
                    "[reconcile] UPDATE %s.%s: '%s' -> '%s'",
                    table_name, col_name, old, new,
                )
                updated.append(f"{table_name}.{col_name}:{old}->{new}")
                if dry_run:
                    continue
                try:
                    with engine.begin() as conn:
                        result = conn.execute(
                            text(sql), {"old": old, "new": new}
                        )
                        if result.rowcount:
                            logger.info(
                                "[reconcile] %s.%s: %d fila(s) normalizadas",
                                table_name, col_name, result.rowcount,
                            )
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"normalize {table_name}.{col_name}: {exc}")
                    logger.error(
                        "[reconcile] no se pudo normalizar %s.%s: %s",
                        table_name, col_name, exc,
                    )
    return updated, errors


def _alembic_version(engine: Engine) -> str | None:
    """Revisión actual de ``alembic_version`` (si la tabla existe).

    Se reporta porque la cadena de migraciones puede no estar avanzando (una
    migración de datos que falla en datos reales, por ejemplo). El
    reconciliador es la capa que repara el esquema sea cual sea el estado de
    Alembic, pero conviene dejar la evidencia visible en el log del deploy.
    """
    try:
        insp = inspect(engine)
        if not insp.has_table("alembic_version"):
            return None
        with engine.connect() as conn:
            row = conn.execute(text("SELECT version_num FROM alembic_version")).first()
        return row[0] if row else None
    except Exception as exc:  # noqa: BLE001
        logger.warning("[reconcile] no se pudo leer alembic_version: %s", exc)
        return None


def _model_is_uuid(col: Any) -> bool:
    """True si la columna del modelo es un UUID (GUID/TypeDecorator o Uuid)."""
    tname = type(col.type).__name__
    if tname in ("GUID", "Uuid", "UUID"):
        return True
    # Un Enum de un solo valor "uuid" también cuenta.
    return str(col.type).upper() == "UUID"


def _live_is_char32(type_obj: Any) -> bool:
    """True si el tipo real de la columna es un CHAR/VARCHAR de 32 chars."""
    t = str(type_obj).upper().replace(" ", "")
    return t in ("CHAR(32)", "CHARACTER(32)", "VARCHAR(32)", "CHARACTERVARYING(32)")


def _repair_column_types(
    engine: Engine,
    insp: Any,
    tables: list[Any],
    existing_tables: set[str],
    dry_run: bool,
    report: dict[str, Any],
) -> None:
    """Repara el TIPO y el DEFAULT de columnas ya existentes.

    Drift de tipo (Bug 4 — permisos, 2026-10-23)
    --------------------------------------------
    ``alembic/versions/2026_09_30_0003_rbac_casbin.py`` creó las tablas
    ``rbac_policies`` y ``rbac_groupings`` con DDL crudo:

        id CHAR(32) NOT NULL PRIMARY KEY,
        created_at TIMESTAMP NOT NULL,

    Pero el ORM (``app/models/base.py``) usa el TypeDecorator ``GUID``, que
    en PostgreSQL es un **UUID nativo**, y ``TimestampMixin`` con
    ``server_default=func.now()``.

    Resultado: el seed de políticas fallaba en PostgreSQL (UUID contra
    char(32), y created_at NOT NULL sin DEFAULT), la transacción entera se
    revertía, la tabla quedaba VACÍA y Casbin denegaba todas las
    operaciones a todos los roles → HTTP 403 en 26 endpoints.

    Sólo se reparan dos casos, acotados y verificables:

    1. Columna ``CHAR(32)``/``VARCHAR(32)`` en la DB cuyo modelo es UUID:
       se convierte a ``uuid``. La conversión usa el cast de entrada de
       PostgreSQL, que acepta tanto la forma con guiones como los 32 hex
       sin guiones (``rtrim`` quita el relleno de ``CHAR``).
    2. Columna NOT NULL sin DEFAULT en la DB cuyo modelo declara
       ``server_default``: se le pone el DEFAULT del modelo. Sin esto, un
       INSERT que omita la columna (que es lo que hace SQLAlchemy) viola
       NOT NULL.

    Es idempotente: si el tipo ya es ``uuid`` o el default ya existe, no
    hace nada. Nunca hace DROP ni borra datos.
    """
    dialect = engine.dialect
    if dialect.name != "postgresql":
        # En SQLite el propio ORM usa CHAR(32) para GUID: no hay drift.
        return

    for table in tables:
        if table.name not in existing_tables:
            continue
        try:
            live_cols = {c["name"]: c for c in insp.get_columns(table.name)}
        except Exception as exc:  # noqa: BLE001
            report["errors"].append(f"inspect columns {table.name}: {exc}")
            continue

        for col in table.columns:
            live = live_cols.get(col.name)
            if live is None:
                continue  # la columna no existe: la crea el pase de columnas

            # ── 1. Tipo CHAR(32) → uuid ──────────────────────────────────
            if _model_is_uuid(col) and _live_is_char32(live.get("type")):
                ddl = (
                    f"ALTER TABLE {_quote_ident(table.name)} "
                    f"ALTER COLUMN {_quote_ident(col.name)} TYPE uuid "
                    f"USING rtrim({_quote_ident(col.name)})::uuid"
                )
                logger.info("[reconcile] %s", ddl)
                report["column_types_fixed"].append(f"{table.name}.{col.name}")
                if dry_run:
                    continue
                try:
                    with engine.begin() as conn:
                        conn.execute(text(ddl))
                except Exception as exc:  # noqa: BLE001
                    report["errors"].append(
                        f"fix type {table.name}.{col.name}: {exc}"
                    )
                    logger.error(
                        "[reconcile] no se pudo corregir el tipo de %s.%s: %s",
                        table.name, col.name, exc,
                    )
                continue

            # ── 2. DEFAULT faltante en columna NOT NULL ───────────────────
            if live.get("default") is not None:
                continue
            if live.get("nullable", True):
                continue
            default_sql = _server_default_sql(col, dialect)
            if default_sql is None:
                continue
            ddl = (
                f"ALTER TABLE {_quote_ident(table.name)} "
                f"ALTER COLUMN {_quote_ident(col.name)} SET DEFAULT {default_sql}"
            )
            logger.info("[reconcile] %s", ddl)
            report["column_defaults_fixed"].append(f"{table.name}.{col.name}")
            if dry_run:
                continue
            try:
                with engine.begin() as conn:
                    conn.execute(text(ddl))
            except Exception as exc:  # noqa: BLE001
                report["errors"].append(
                    f"fix default {table.name}.{col.name}: {exc}"
                )
                logger.error(
                    "[reconcile] no se pudo agregar el default de %s.%s: %s",
                    table.name, col.name, exc,
                )


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
        "column_types_fixed": [],
        "column_defaults_fixed": [],
        "indexes_created": [],
        "enum_values_added": [],
        "enum_rows_normalized": [],
        "alembic_version": None,
        "errors": [],
    }

    # Estado de Alembic: evidencia visible en el log del deploy.
    report["alembic_version"] = _alembic_version(engine)
    logger.info(
        "[reconcile] alembic_version actual: %s",
        report["alembic_version"] or "(sin tabla alembic_version)",
    )

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

    # ── 2b. Tipos y DEFAULTs de columnas ya existentes ───────────────────
    # Un columna puede existir pero con el TIPO equivocado (CHAR(32) donde
    # el modelo pide UUID) o sin el DEFAULT que el modelo declara. Eso
    # rompe los INSERT del ORM aunque la columna "exista". Ver
    # _repair_column_types() para el caso concreto de rbac_policies.
    try:
        _repair_column_types(
            engine, insp, list(Base.metadata.sorted_tables),
            existing_tables, dry_run, report,
        )
    except Exception as exc:  # noqa: BLE001
        report["errors"].append(f"repair column types: {exc}")
        logger.error("[reconcile] no se pudo reparar tipos de columna: %s", exc)

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

    # ── 4. ENUM de PostgreSQL: labels ─────────────────────────────────────
    # Primero los labels (para que PG acepte el bind del modelo) y después
    # la normalización de las filas legacy en mayúsculas (para que
    # SQLAlchemy pueda mapearlas).
    if dialect.name == "postgresql":
        enum_added, enum_errors = _ensure_enum_labels(engine, dry_run)
        report["enum_values_added"].extend(enum_added)
        report["errors"].extend(enum_errors)

        normalized, norm_errors = _normalize_enum_data(engine, dry_run)
        report["enum_rows_normalized"].extend(normalized)
        report["errors"].extend(norm_errors)
    else:
        logger.info("[reconcile] dialecto %s: sin ENUM de PostgreSQL", dialect.name)

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
        "Resumen — alembic_version: %s | tablas %s: %d | %s %d columnas | "
        "%s %d tipos corregidos | %s %d defaults agregados | "
        "índices %s: %d | enum labels %s: %d | filas enum normalizadas: %d | "
        "omitidas: %d | errores: %d",
        report["alembic_version"] or "(sin tabla)",
        "a crear" if args.dry_run else "creadas",
        len(report["tables_created"]),
        verb, len(report["columns_added"]),
        "tipos a corregir" if args.dry_run else "tipos corregidos",
        len(report["column_types_fixed"]),
        "defaults a agregar" if args.dry_run else "defaults agregados",
        len(report["column_defaults_fixed"]),
        "a crear" if args.dry_run else "creados",
        len(report["indexes_created"]),
        "a agregar" if args.dry_run else "agregados",
        len(report["enum_values_added"]),
        len(report["enum_rows_normalized"]),
        len(report["columns_skipped_unsafe_type"]),
        len(report["errors"]),
    )
    for item in report["columns_added"]:
        logger.info("  + columna %s", item)
    for item in report["column_types_fixed"]:
        logger.info("  ~ tipo corregido %s", item)
    for item in report["column_defaults_fixed"]:
        logger.info("  ~ default agregado %s", item)
    for item in report["enum_values_added"]:
        logger.info("  + enum %s", item)
    for item in report["enum_rows_normalized"]:
        logger.info("  ~ enum fila %s", item)
    for item in report["columns_skipped_unsafe_type"]:
        logger.warning("  ! omitida %s", item)
    for item in report["errors"]:
        logger.error("  x %s", item)

    if report["errors"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
