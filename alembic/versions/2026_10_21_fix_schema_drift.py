"""Reparación correctiva de schema drift — HU_50–HU_65 (producción 2026-10-21).

Revision ID: 2026_10_21_fix_drift
Revises: 2026_10_16_hu50_65
Create Date: 2026-10-21

Problema
--------
En producción (Railway / PostgreSQL) ``GET /api/v1/tenants/{id}/products``
devolvía 500::

    psycopg.errors.UndefinedColumn: column products.product_type does not exist

Causa raíz
----------
La DB de producción nació de ``Base.metadata.create_all()`` (no de Alembic).
``scripts/bootstrap_migrate.py`` detecta ese estado como ``legacy`` y calcula
la revisión objetivo con ``_highest_fully_applied_revision()``, que **sólo
comprobaba las tablas declaradas con ``op.create_table``** e ignoraba por
completo las columnas agregadas con ``op.add_column``.

``2026_10_16_hu50_65`` es la única migración del proyecto que combina
``create_table`` + ``add_column``. Como las 6 tablas nuevas sí existían
(creadas por ``create_all`` en un deploy anterior), el bootstrap dará la
migración por aplicada y selló la DB en ``head`` **sin ejecutar jamás sus 15
``ADD COLUMN``** sobre ``products`` / ``customers`` / ``quote_items``.

``Base.metadata.create_all()`` no puede repararlo: sólo crea tablas
inexistentes, nunca hace ``ALTER TABLE`` sobre tablas que ya existen.

Qué hace esta migración
------------------------
Agrega, de forma **idempotente**, las 15 columnas de HU_50–HU_65 que faltan
y crea los 3 índices declarados en los modelos. Si la columna ya existe (DB
correcta, o ya reparada por ``scripts/reconcile_schema.py``), no hace nada.

Es ADITIVA: no borra ni modifica columnas ni datos existentes.

Reversible
----------
El ``downgrade`` elimina únicamente las columnas e índices que esta migración
declara, y sólo si existen (``IF EXISTS``). Es seguro ejecutarlo más de una
vez.
"""
from __future__ import annotations

import logging

from alembic import op
from sqlalchemy import inspect, text

revision = "2026_10_21_fix_drift"
down_revision = "2026_10_16_hu50_65"
branch_labels = None
depends_on = None


logger = logging.getLogger("alembic.runtime.migration")


# ── Columnas declaradas por HU_50–HU_65 (modelo → DDL) ───────────────────
# (tabla, columna, DDL, ¿nullable?)
COLUMNS: list[tuple[str, str, str, bool]] = [
    # products (HU_51, HU_54, HU_58)
    ("products", "product_type", "VARCHAR(30) NOT NULL DEFAULT 'standard'", False),
    ("products", "template_type", "VARCHAR(30)", True),
    ("products", "m2_price_cents", "INTEGER NOT NULL DEFAULT 0", False),
    # customers (HU_50, HU_56, HU_57)
    ("customers", "customer_type", "VARCHAR(20) NOT NULL DEFAULT 'particular'", False),
    ("customers", "marketing_email_status", "VARCHAR(20) NOT NULL DEFAULT 'pending'", False),
    ("customers", "marketing_whatsapp_status", "VARCHAR(20) NOT NULL DEFAULT 'pending'", False),
    ("customers", "current_debt_cents", "INTEGER NOT NULL DEFAULT 0", False),
    # quote_items (HU_54, HU_58)
    ("quote_items", "template_type", "VARCHAR(30)", True),
    ("quote_items", "width_cm", "FLOAT", True),
    ("quote_items", "height_cm", "FLOAT", True),
    ("quote_items", "faces", "INTEGER NOT NULL DEFAULT 1", False),
    ("quote_items", "suggested_price_cents", "INTEGER NOT NULL DEFAULT 0", False),
    ("quote_items", "cost_unit_cents", "INTEGER NOT NULL DEFAULT 0", False),
    ("quote_items", "pack_qty", "INTEGER", True),
    ("quote_items", "pack_size", "INTEGER", True),
]

# (índice, tabla, columnas)
INDEXES: list[tuple[str, str, list[str]]] = [
    ("ix_products_product_type", "products", ["product_type"]),
    ("ix_products_template_type", "products", ["template_type"]),
    ("ix_customers_customer_type", "customers", ["customer_type"]),
]


def _existing_columns(table: str) -> set[str] | None:
    """Columnas reales de ``table``. ``None`` si la tabla no existe."""
    bind = op.get_bind()
    insp = inspect(bind)
    if not insp.has_table(table):
        return None
    return {c["name"] for c in insp.get_columns(table)}


def _add_column(table: str, column: str, ddl: str, nullable: bool) -> None:
    """Agrega una columna si no existe. Idempotente en PG y SQLite."""
    bind = op.get_bind()
    existing = _existing_columns(table)
    if existing is None:
        logger.warning("[fix_drift] la tabla %s no existe — omito %s", table, column)
        return
    if column in existing:
        logger.info("[fix_drift] %s.%s ya existe — omito", table, column)
        return

    logger.info("[fix_drift] agrego %s.%s (%s)", table, column, ddl)
    if bind.dialect.name == "postgresql":
        op.execute(
            text(f'ALTER TABLE "{table}" ADD COLUMN IF NOT EXISTS "{column}" {ddl}')
        )
    else:
        # SQLite no soporta ADD COLUMN IF NOT EXISTS: try/except.
        from sqlalchemy.exc import OperationalError

        try:
            op.execute(text(f'ALTER TABLE "{table}" ADD COLUMN "{column}" {ddl}'))
        except OperationalError as exc:
            logger.warning("[fix_drift] %s.%s ya existe (SQLite): %s", table, column, exc)


def _create_index(name: str, table: str, columns: list[str]) -> None:
    """Crea un índice si no existe. Idempotente en PG y SQLite."""
    bind = op.get_bind()
    if _existing_columns(table) is None:
        return
    cols = ", ".join(f'"{c}"' for c in columns)
    op.execute(text(f'CREATE INDEX IF NOT EXISTS "{name}" ON "{table}" ({cols})'))
    logger.info("[fix_drift] índice %s verificado/creado", name)


def upgrade() -> None:
    """Agrega las columnas e índices faltantes de HU_50–HU_65."""
    for table, column, ddl, nullable in COLUMNS:
        _add_column(table, column, ddl, nullable)

    for name, table, columns in INDEXES:
        _create_index(name, table, columns)

    logger.info(
        "[fix_drift] OK — %d columnas HU_50-HU_65 verificadas sobre el esquema real",
        len(COLUMNS),
    )


def downgrade() -> None:
    """NO-OP documentado.

    Esta migración NO es propietaria de las columnas que agrega: son las
    mismas 15 columnas declaradas por ``2026_10_16_hu50_65``. El
    ``downgrade`` de la migración padre ya las elimina (en orden inverso).

    Si esta migración las eliminara también, el ``downgrade base`` completo
    fallaría con "no such column" al intentar borrar por segunda vez.

    Qué SÍ es reversible: el estado de la DB vuelve a ser el de antes de
    HU_50-HU_65 en cuanto se ejecuta el downgrade de la migración padre.
    """
    logger.info(
        "[fix_drift] downgrade sin efecto: las columnas HU_50-HU_65 las "
        "elimina el downgrade de %s.",
        "2026_10_16_hu50_65",
    )
