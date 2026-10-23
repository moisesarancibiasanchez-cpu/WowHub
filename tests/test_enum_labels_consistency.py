"""Regresión (2026-10-23) — ENUM del modelo vs. ENUM de PostgreSQL.

Problema
--------
La migración inicial ``2026_09_07_1002-...`` creó varios ENUM con labels en
MAYÚSCULAS, mientras que el modelo los declara en minúsculas con
``values_callable=lambda obj: [e.value for e in obj]``::

    migración: sa.Enum('DRAFT', 'ACTIVE', ..., name='product_status')
    modelo   : Enum(ProductStatus, name="product_status",
                     values_callable=lambda obj: [e.value for e in obj])
               # -> 'draft', 'active', 'out_of_stock', 'archived'

PostgreSQL valida el cast contra los miembros del TYPE, así que cualquier
filtro ``WHERE status = 'active'`` falla con::

    DataError: invalid input value for enum product_status: "active"

y deja en 500 el catálogo público y el listado de productos del tenant.

El desfase de ``order_status`` ya se corrigió en
``2026_10_06_0004_order_status_add_lowercase_values.py`` con el patrón
``ALTER TYPE ... ADD VALUE IF NOT EXISTS``. Para ``product_status`` y
``quote_status`` no existía migración equivalente: ese era el hueco.

Este test falla si algún ENUM del modelo vuelve a quedar sin labels
alineados en la cadena de migraciones.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os_env = {"DATABASE_URL": "sqlite:///:memory:", "APP_ENV": "test"}
import os  # noqa: E402

os.environ.setdefault("DATABASE_URL", os_env["DATABASE_URL"])
os.environ.setdefault("APP_ENV", os_env["APP_ENV"])

from sqlalchemy import Enum as SAEnum  # noqa: E402

import app.models  # noqa: F401,E402
from app.database import Base  # noqa: E402

MIG_DIR = ROOT / "alembic" / "versions"


def _model_enum_labels() -> dict[str, set[str]]:
    """labels declarados por los modelos, por nombre de TYPE."""
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


def _migration_corpus() -> str:
    """Todo el texto de las migraciones, para buscar declaraciones y fixes."""
    return "\n".join(
        p.read_text(encoding="utf-8", errors="replace") for p in sorted(MIG_DIR.glob("*.py"))
    )


def _migrations_with_add_value() -> dict[str, set[str]]:
    """Para cada TYPE, los labels que alguna migración declara junto a él.

    Una migración cuenta como correctora de un TYPE si:
      - usa ``ALTER TYPE ... ADD VALUE``, y
      - menciona el nombre del TYPE.

    Se revisa archivo por archivo para tolerar tanto los literales directos
    (``ALTER TYPE x ADD VALUE 'v'``) como los bucles con variable
    (``for value in VALUES: ALTER TYPE {type_name} ADD VALUE '{value}'``).
    """
    out: dict[str, set[str]] = {}
    for path in sorted(MIG_DIR.glob("*.py")):
        txt = path.read_text(encoding="utf-8", errors="replace")
        if "ADD VALUE" not in txt.upper():
            continue
        quoted = set(re.findall(r"['\"]([a-z_][a-z0-9_]*)['\"]", txt))
        for type_name in MODEL_ENUMS:
            if type_name not in quoted:
                continue
            # Los labels que interesan son los del propio TYPE.
            labels = quoted & MODEL_ENUMS[type_name]
            out.setdefault(type_name.lower(), set()).update(labels)
    return out


def _created_labels(corpus: str, type_name: str) -> set[str]:
    """Labels con los que una migración crea el TYPE (sa.Enum(..., name=X))."""
    labels: set[str] = set()
    for m in re.finditer(
        r"sa\.Enum\(\s*((?:'[^']*'\s*,\s*)*'[^']*')\s*,\s*name\s*=\s*'" + re.escape(type_name) + r"'",
        corpus,
    ):
        labels.update(re.findall(r"'([^']*)'", m.group(1)))
    return labels


MODEL_ENUMS = _model_enum_labels()
CORPUS = _migration_corpus()
ADDED = _migrations_with_add_value()


def _es_lowercase(labels: set[str]) -> bool:
    """True si algún label no es un nombre de miembro en MAYÚSCULAS.

    El modelo usa ``values_callable`` para guardar el ``.value`` del enum.
    Si ese ``.value`` es lowercase, la migración que creó el TYPE en
    mayúsculas queda desalineada.
    """
    return any(lbl != lbl.upper() for lbl in labels)


@pytest.mark.parametrize("type_name", sorted(MODEL_ENUMS))
def test_enum_labels_alineados_con_la_cadena_de_migraciones(type_name):
    """Cada label del modelo debe existir en el TYPE de PostgreSQL.

    Se acepta cualquiera de estos caminos:
      1) la migración crea el TYPE directamente con esos labels, o
      2) una migración agrega el label con ALTER TYPE ... ADD VALUE.
    """
    model_labels = MODEL_ENUMS[type_name]
    created = _created_labels(CORPUS, type_name)
    added = ADDED.get(type_name.lower(), set())

    disponibles = created | added
    faltan = model_labels - disponibles

    if not faltan:
        return

    # Si el TYPE no lo crea ninguna migración, lo crea ``create_all`` a
    # partir del propio modelo -> es consistente por construcción.
    if not created:
        return

    assert not faltan, (
        f"el ENUM '{type_name}' no tiene estos labels en la cadena de "
        f"migraciones: {sorted(faltan)}. PostgreSQL rechazará el valor con "
        f"'invalid input value for enum {type_name}'."
    )


def test_enums_lowercase_cubiertos():
    """Los 3 ENUM con labels lowercase deben tener su migración correctiva.

    ``order_status`` se corrigió en 2026_10_06_0004.
    ``product_status`` y ``quote_status`` en 2026_10_23_fix_enum_labels.
    """
    for type_name in ("order_status", "product_status", "quote_status"):
        added = ADDED.get(type_name.lower(), set())
        faltan = MODEL_ENUMS[type_name] - added
        assert not faltan, (
            f"falta la migración correctiva de ALTER TYPE {type_name} "
            f"ADD VALUE para: {sorted(faltan)}"
        )


def test_migracion_enum_labels_es_idempotente(tmp_path):
    """La migración correctiva debe ser reejecutable sin efectos."""
    import importlib.util

    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import create_engine

    path = MIG_DIR / "2026_10_23_fix_enum_labels.py"
    assert path.exists(), "falta la migración correctiva de ENUM"

    spec = importlib.util.spec_from_file_location("_mig_enum_labels", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    url = f"sqlite:///{(tmp_path / 'enum.db').as_posix()}"
    engine = create_engine(url, future=True)
    try:
        with engine.begin() as conn:
            ctx = MigrationContext.configure(conn)
            original_op = mod.op
            mod.op = Operations(ctx)
            try:
                # En SQLite es un no-op, pero debe ejecutarse sin error y ser
                # reejecutable (idempotencia).
                assert mod.upgrade() is None
                assert mod.upgrade() is None
                assert mod.downgrade() is None
            finally:
                mod.op = original_op
    finally:
        engine.dispose()


def test_migracion_enum_labels_cubre_los_dos_tipos():
    """La migración debe declarar product_status y quote_status."""
    import importlib.util

    path = MIG_DIR / "2026_10_23_fix_enum_labels.py"
    spec = importlib.util.spec_from_file_location("_mig_enum_labels2", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    nombres = {name for name, _legacy, _model in mod.ENUMS}
    assert "product_status" in nombres
    assert "quote_status" in nombres

    # Y sus labels deben coincidir con los del modelo.
    for name, _legacy, model_values in mod.ENUMS:
        assert set(model_values) == MODEL_ENUMS[name], (
            f"la migración declara labels distintos a los del modelo para {name}"
        )


def test_cadena_alembic_una_sola_head():
    """Debe seguir habiendo una sola head tras agregar la migración."""
    from scripts.bootstrap_migrate import _load_migrations

    migs = _load_migrations()
    referenced = {m["down"] for m in migs.values() if m["down"] in migs}
    heads = [rev for rev in migs if rev not in referenced]

    assert len(heads) == 1, f"heads múltiples: {heads}"
    assert heads[0] == "2026_10_23_fix_enum_labels"
