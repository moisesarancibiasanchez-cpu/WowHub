"""Regresión Bug 1 (2026-10-21) — schema drift: `products.product_type`.

Contexto
--------
En producción (Railway / PostgreSQL) ``GET /api/v1/tenants/{id}/products``
devolvía 500::

    psycopg.errors.UndefinedColumn: column products.product_type does not exist

La DB nació de ``Base.metadata.create_all()`` (no de Alembic). El bootstrap
detectaba ese estado como ``legacy`` y calculaba la revisión objetivo
ignorando las columnas agregadas con ``op.add_column``, por lo que sellaba la
DB en ``head`` sin ejecutar los 15 ``ADD COLUMN`` de HU_50–HU_65.
``create_all()`` no puede repararlo: sólo crea tablas inexistentes.

Estos tests fijan el comportamiento correcto:
  1. ``scripts.reconcile_schema`` agrega las columnas faltantes.
  2. Es idempotente (una segunda pasada no cambia nada).
  3. Crea los índices declarados en los modelos.
  4. No borra datos ni columnas existentes.
  5. La migración correctiva ``2026_10_21_fix_drift`` es idempotente.
  6. El bootstrap ya NO considera aplicada una migración cuyas columnas
     ``add_column`` faltan en la DB (el defecto de origen).
  7. La cadena Alembic tiene una sola head.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.database import Base  # noqa: E402
import app.models  # noqa: F401,E402

from scripts.bootstrap_migrate import (  # noqa: E402
    _columns_added_by_migration,
    _highest_fully_applied_revision,
    _load_migrations,
    _migrations_in_dependency_order,
)
from scripts.reconcile_schema import reconcile  # noqa: E402


HU50_65 = "2026_10_16_hu50_65"
FIX_DRIFT = "2026_10_21_fix_drift"

# Columnas declaradas por la migración HU_50–HU_65 (add_column).
HU50_65_COLUMNS = {
    "products": ["product_type", "template_type", "m2_price_cents"],
    "customers": [
        "customer_type",
        "marketing_email_status",
        "marketing_whatsapp_status",
        "current_debt_cents",
    ],
    "quote_items": [
        "template_type",
        "width_cm",
        "height_cm",
        "faces",
        "suggested_price_cents",
        "cost_unit_cents",
        "pack_qty",
        "pack_size",
    ],
}


def _columns(engine, table):
    insp = inspect(engine)
    if not insp.has_table(table):
        return set()
    return {c["name"] for c in insp.get_columns(table)}


def _build_legacy_schema(engine):
    """Crea el esquema completo del modelo y le QUITA las columnas de HU_50–HU_65.

    Esto reproduce exactamente el estado de producción: las tablas existen
    con todas las columnas del modelo salvo las 15 que declaraba la
    migración ``2026_10_16_hu50_65`` (que nunca llegó a ejecutarse).
    """
    from sqlalchemy.schema import CreateTable

    with engine.begin() as conn:
        for table_name, drop_cols in HU50_65_COLUMNS.items():
            tbl = Base.metadata.tables[table_name]
            # Recrear la tabla sin sus índices (los índices que referencian
            # una columna a eliminar impiden el DROP COLUMN en SQLite).
            conn.execute(text(f'DROP TABLE IF EXISTS "{table_name}"'))
            conn.execute(CreateTable(tbl))
            for col in drop_cols:
                conn.execute(text(f'ALTER TABLE "{table_name}" DROP COLUMN "{col}"'))


@pytest.fixture()
def drift_db(tmp_path):
    """DB con el esquema de producción: tablas existentes SIN las columnas HU."""
    url = f"sqlite:///{(tmp_path / 'drift.db').as_posix()}"
    engine = create_engine(url, future=True)
    try:
        Base.metadata.create_all(bind=engine, checkfirst=True)
        _build_legacy_schema(engine)
    finally:
        engine.dispose()
    return url


# ═══════════════════════════════════════════════════════════════════════
# 1-4. reconcile_schema
# ═══════════════════════════════════════════════════════════════════════
def test_reconcile_adds_missing_hu50_65_columns(drift_db):
    """Las 15 columnas de HU_50–HU_65 deben agregarse a las tablas existentes."""
    engine = create_engine(drift_db, future=True)
    try:
        report = reconcile(engine)
    finally:
        engine.dispose()

    engine = create_engine(drift_db, future=True)
    try:
        for table, wanted in HU50_65_COLUMNS.items():
            have = _columns(engine, table)
            for col in wanted:
                assert col in have, f"falta {table}.{col}"
    finally:
        engine.dispose()

    added = set(report["columns_added"])
    assert "products.product_type" in added
    assert "customers.customer_type" in added
    assert "quote_items.faces" in added
    assert not report["errors"], report["errors"]


def test_reconcile_is_idempotent(drift_db):
    """Una segunda pasada no debe modificar nada."""
    engine = create_engine(drift_db, future=True)
    try:
        reconcile(engine)
    finally:
        engine.dispose()

    engine = create_engine(drift_db, future=True)
    try:
        report = reconcile(engine)
    finally:
        engine.dispose()

    assert report["columns_added"] == []
    assert report["tables_created"] == []
    assert report["indexes_created"] == []
    assert not report["errors"], report["errors"]


def test_reconcile_creates_missing_indexes(drift_db):
    """Los índices declarados en los modelos deben crearse si faltan."""
    engine = create_engine(drift_db, future=True)
    try:
        report = reconcile(engine)
    finally:
        engine.dispose()

    engine = create_engine(drift_db, future=True)
    try:
        indexes = {i["name"] for i in inspect(engine).get_indexes("products")}
    finally:
        engine.dispose()

    assert "ix_products_product_type" in indexes
    assert "ix_products_product_type" in report["indexes_created"]


def test_reconcile_never_drops_anything(drift_db):
    """El reconciliador es aditivo: no borra columnas existentes."""
    engine = create_engine(drift_db, future=True)
    try:
        before = {t: _columns(engine, t) for t in HU50_65_COLUMNS}
        reconcile(engine)
        after = {t: _columns(engine, t) for t in HU50_65_COLUMNS}
    finally:
        engine.dispose()

    for table, cols in before.items():
        missing = cols - after[table]
        assert not missing, f"el reconciliador eliminó columnas de {table}: {missing}"
        # Y además las agregó (crecimiento esperado).
        assert len(after[table]) > len(cols)


# ═══════════════════════════════════════════════════════════════════════
# 5. El defecto de origen: bootstrap no debe sellar migraciones con
#    add_column sin aplicar.
# ═══════════════════════════════════════════════════════════════════════
def test_bootstrap_detects_add_column_operations():
    """Guarda de regresión: el parser debe ver los add_column de HU_50–HU_65."""
    mig_dir = str(ROOT / "alembic" / "versions")
    pairs = _columns_added_by_migration(mig_dir, HU50_65)
    found = {f"{t}.{c}" for t, c in pairs}

    assert "products.product_type" in found
    assert "customers.customer_type" in found
    assert "quote_items.pack_size" in found
    assert len(found) == 15


def test_highest_fully_applied_rejects_missing_columns(drift_db):
    """Con las columnas ausentes, HU_50–HU_65 NO es una revisión aplicable."""
    mig_dir = str(ROOT / "alembic" / "versions")
    migs = _load_migrations()
    assert HU50_65 in migs

    engine = create_engine(drift_db, future=True)
    try:
        target = _highest_fully_applied_revision(
            engine, migs, mig_dir, set(Base.metadata.tables.keys())
        )
    finally:
        engine.dispose()

    assert target != HU50_65, (
        "el bootstrap volvió a considerar aplicada una migración cuyas "
        "columnas add_column faltan en la DB"
    )


def test_highest_fully_applied_accepts_complete_schema(tmp_path):
    """Con las columnas presentes, HU_50–HU_65 sí es aplicable."""
    url = f"sqlite:///{(tmp_path / 'full.db').as_posix()}"
    engine = create_engine(url, future=True)
    try:
        # Esquema completo del modelo (incluye las columnas HU_50–HU_65).
        Base.metadata.create_all(bind=engine, checkfirst=True)

        mig_dir = str(ROOT / "alembic" / "versions")
        migs = _load_migrations()
        target = _highest_fully_applied_revision(
            engine, migs, mig_dir, set(Base.metadata.tables.keys())
        )
    finally:
        engine.dispose()

    assert target == HU50_65


# ═══════════════════════════════════════════════════════════════════════
# 6. La migración correctiva es idempotente.
# ═══════════════════════════════════════════════════════════════════════
def _load_migration_module(filename: str):
    """Carga un archivo de ``alembic/versions`` por ruta.

    El paquete ``alembic`` instalado en el venv tapa el directorio local
    ``alembic/`` del repo, así que ``import alembic.versions...`` no funciona:
    hay que cargarlo por ``spec_from_file_location``.
    """
    import importlib.util

    path = ROOT / "alembic" / "versions" / filename
    spec = importlib.util.spec_from_file_location(f"_mig_{path.stem}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_fix_drift_migration_is_idempotent(tmp_path):
    """``2026_10_21_fix_drift`` se puede aplicar dos veces sin fallar."""
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    mod = _load_migration_module("2026_10_21_fix_schema_drift.py")

    url = f"sqlite:///{(tmp_path / 'fix.db').as_posix()}"
    engine = create_engine(url, future=True)
    try:
        with engine.begin() as conn:
            conn.execute(text(
                "CREATE TABLE products (id VARCHAR(36) PRIMARY KEY, sku VARCHAR(50))"
            ))
            conn.execute(text(
                "CREATE TABLE customers (id VARCHAR(36) PRIMARY KEY, email VARCHAR(200))"
            ))
            conn.execute(text(
                "CREATE TABLE quote_items (id VARCHAR(36) PRIMARY KEY, quote_id VARCHAR(36))"
            ))

        with engine.begin() as conn:
            ctx = MigrationContext.configure(conn)
            original_op = mod.op
            mod.op = Operations(ctx)
            try:
                mod.upgrade()
                mod.upgrade()  # segunda pasada: no debe fallar
            finally:
                mod.op = original_op

        for table, wanted in HU50_65_COLUMNS.items():
            have = _columns(engine, table)
            for col in wanted:
                assert col in have, f"falta {table}.{col}"

        indexes = {i["name"] for i in inspect(engine).get_indexes("products")}
        assert "ix_products_product_type" in indexes
    finally:
        engine.dispose()


# ═══════════════════════════════════════════════════════════════════════
# 7. Estructura de la cadena Alembic
# ═══════════════════════════════════════════════════════════════════════
def test_single_alembic_head():
    """La cadena Alembic debe tener una sola head (``2026_10_21_fix_drift``)."""
    mig_dir = str(ROOT / "alembic" / "versions")
    migs = _load_migrations()
    referenced = {m["down"] for m in migs.values() if m["down"] in migs}
    heads = [rev for rev in migs if rev not in referenced]

    assert len(heads) == 1, f"heads múltiples: {heads}"
    assert heads[0] == FIX_DRIFT


def test_migration_chain_is_ordered():
    """La nueva migración debe ser descendiente de HU_50–HU_65."""
    mig_dir = str(ROOT / "alembic" / "versions")
    migs = _load_migrations()
    order = _migrations_in_dependency_order(migs)

    assert order.index(FIX_DRIFT) == len(order) - 1
    assert order.index(HU50_65) < order.index(FIX_DRIFT)
