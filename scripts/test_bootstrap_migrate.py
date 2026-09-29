"""Test del bootstrap de migracion en los 3 estados posibles de una DB."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Tablas nuevas que la migracion 2026_09_27_0001 introduce y que NO existian
# en la version previa de WowHub (pre-commit 9163349). En produccion la DB fue
# poblada por esa version anterior via `Base.metadata.create_all`, asi que
# estas 3 tablas no existen en la DB legacy de Railway. El TEST E simula
# exactamente ese escenario.
NEW_TABLES_2026_09_27_0001 = (
    "tenant_site_configs",
    "marketplace_plugins",
    "plugin_subscriptions",
)


def setup_env(db_url: str) -> None:
    os.environ["DATABASE_URL"] = db_url
    os.environ["APP_ENV"] = "development"
    os.environ["SECRET_KEY"] = "test-secret-key-min-32-chars-long-ok!!x"
    os.environ["JWT_SECRET"] = "test-jwt-secret-key-min-32-chars-ok!!!!"
    os.environ["WEBHOOK_SECRET"] = "test-webhook-secret-min-32-chars-ok!"


def run_bootstrap() -> int:
    return subprocess.call(
        [sys.executable, "-m", "scripts.bootstrap_migrate"],
        cwd=str(ROOT),
    )


def table_count(db_url: str) -> int:
    from sqlalchemy import create_engine, inspect
    eng = create_engine(db_url)
    try:
        return len(inspect(eng).get_table_names())
    finally:
        eng.dispose()


def has_alembic_version(db_url: str) -> bool:
    from sqlalchemy import create_engine, inspect
    eng = create_engine(db_url)
    try:
        return "alembic_version" in inspect(eng).get_table_names()
    finally:
        eng.dispose()


print("=" * 72)
print("TEST A: DB vacia -> 'alembic upgrade head'")
print("=" * 72)
db_a = ROOT / "test_a.db"
db_a.unlink(missing_ok=True)
setup_env(f"sqlite:///{db_a}")
rc_a = run_bootstrap()
n_a = table_count(f"sqlite:///{db_a}")
v_a = has_alembic_version(f"sqlite:///{db_a}")
print(f"   exit={rc_a}  tablas={n_a}  alembic_version={v_a}")
ok_a = rc_a == 0 and n_a > 0 and v_a
print(f"   {'[OK  ]' if ok_a else '[FAIL]'} TEST A")

print()
print("=" * 72)
print("TEST B: DB legacy (solo create_all, sin alembic_version) -> stamp + upgrade")
print("=" * 72)
db_b = ROOT / "test_b.db"
db_b.unlink(missing_ok=True)
setup_env(f"sqlite:///{db_b}")
# crear todas las tablas con Base.metadata.create_all
subprocess.run(
    [sys.executable, "-c",
     "from app.database import Base, engine\n"
     "import app.models  # noqa\n"
     "Base.metadata.create_all(bind=engine)\n"],
    cwd=str(ROOT), check=True,
)
n_b_pre = table_count(f"sqlite:///{db_b}")
v_b_pre = has_alembic_version(f"sqlite:///{db_b}")
print(f"   antes de bootstrap: tablas={n_b_pre}  alembic_version={v_b_pre}")
rc_b = run_bootstrap()
n_b = table_count(f"sqlite:///{db_b}")
v_b = has_alembic_version(f"sqlite:///{db_b}")
print(f"   exit={rc_b}  tablas={n_b}  alembic_version={v_b}")
# Tras el stamp la única tabla nueva es `alembic_version` (la crea Alembic).
# Ninguna tabla de aplicacion se duplica: ese era el bug que arreglamos.
ok_b = rc_b == 0 and n_b == n_b_pre + 1 and v_b and not v_b_pre
print(f"   {'[OK  ]' if ok_b else '[FAIL]'} TEST B (legacy: stamp crea solo alembic_version)")

print()
print("=" * 72)
print("TEST C: DB gestionada por Alembic -> upgrade head (no-op)")
print("=" * 72)
db_c = ROOT / "test_c.db"
db_c.unlink(missing_ok=True)
setup_env(f"sqlite:///{db_c}")
rc_c1 = run_bootstrap()
rc_c2 = run_bootstrap()
n_c = table_count(f"sqlite:///{db_c}")
v_c = has_alembic_version(f"sqlite:///{db_c}")
print(f"   primera corrida exit={rc_c1}  segunda corrida exit={rc_c2}")
print(f"   tablas={n_c}  alembic_version={v_c}")
ok_c = rc_c1 == 0 and rc_c2 == 0 and n_c > 0 and v_c
print(f"   {'[OK  ]' if ok_c else '[FAIL]'} TEST C (idempotente: dos corridas consecutivas OK)")

print()
print("=" * 72)
print("TEST D: DB legacy (Base.metadata.create_all + boostrap en 2 corridas)")
print("=" * 72)
db_d = ROOT / "test_d.db"
db_d.unlink(missing_ok=True)
setup_env(f"sqlite:///{db_d}")
# crear todas las tablas con Base.metadata.create_all
subprocess.run(
    [sys.executable, "-c",
     "from app.database import Base, engine\n"
     "import app.models  # noqa\n"
     "Base.metadata.create_all(bind=engine)\n"],
    cwd=str(ROOT), check=True,
)
n_d_pre = table_count(f"sqlite:///{db_d}")
v_d_pre = has_alembic_version(f"sqlite:///{db_d}")
print(f"   antes de bootstrap: tablas={n_d_pre}  alembic_version={v_d_pre}")
rc_d1 = run_bootstrap()
n_d_after = table_count(f"sqlite:///{db_d}")
v_d_after = has_alembic_version(f"sqlite:///{db_d}")
# Segunda corrida: debe ser idempotente.
rc_d2 = run_bootstrap()
n_d_final = table_count(f"sqlite:///{db_d}")
v_d_final = has_alembic_version(f"sqlite:///{db_d}")
print(
    f"   corrida1 exit={rc_d1}  tablas={n_d_after}  alembic_version={v_d_after}"
)
print(
    f"   corrida2 exit={rc_d2}  tablas={n_d_final}  alembic_version={v_d_final}"
)
ok_d = (
    rc_d1 == 0
    and rc_d2 == 0
    and n_d_after == n_d_pre + 1
    and v_d_after
    and not v_d_pre
    and n_d_final == n_d_after
    and v_d_final
)
print(
    f"   {'[OK  ]' if ok_d else '[FAIL]'} TEST D (legacy: stamp en corrida1, no-op en corrida2)"
)

print()
print("=" * 72)
print("TEST E: DB legacy parcial (caso real Railway — sin las 3 tablas nuevas)")
print("=" * 72)
print(
    "   Simula: WowHub pre-9163349 poblo la DB con create_all() cuando\n"
    "   tenant_site_configs / marketplace_plugins / plugin_subscriptions\n"
    "   NO eran modelos. La DB tiene la base (initial_schema) aplicada\n"
    "   pero NO las 3 tablas nuevas."
)
db_e = ROOT / "test_e.db"
db_e.unlink(missing_ok=True)
setup_env(f"sqlite:///{db_e}")
# crear todas las tablas con Base.metadata.create_all
subprocess.run(
    [sys.executable, "-c",
     "from app.database import Base, engine\n"
     "import app.models  # noqa\n"
     "Base.metadata.create_all(bind=engine)\n"],
    cwd=str(ROOT), check=True,
)
# Borrar las 3 tablas nuevas para simular el estado real de la DB legacy de
# Railway. DROP las crea el bootstrap via `alembic upgrade head`.
subprocess.run(
    [sys.executable, "-c",
     "from sqlalchemy import create_engine, text\n"
     "eng = create_engine('sqlite:///" + str(db_e).replace("\\", "\\\\") + "')\n"
     "with eng.begin() as conn:\n"
     "    for t in ('tenant_site_configs', 'marketplace_plugins', 'plugin_subscriptions'):\n"
     "        conn.execute(text(f'DROP TABLE IF EXISTS {t}'))\n"
     "eng.dispose()\n"],
    cwd=str(ROOT), check=True,
)
n_e_pre = table_count(f"sqlite:///{db_e}")
v_e_pre = has_alembic_version(f"sqlite:///{db_e}")
print(f"   antes de bootstrap: tablas={n_e_pre}  alembic_version={v_e_pre}")
rc_e = run_bootstrap()
n_e = table_count(f"sqlite:///{db_e}")
v_e = has_alembic_version(f"sqlite:///{db_e}")
print(f"   exit={rc_e}  tablas={n_e}  alembic_version={v_e}")
# Tras el bootstrap la DB debe tener:
#   - todas las tablas de Base.metadata (incluidas las 3 nuevas)
#   - alembic_version presente
#   - ninguna tabla duplicada (el bug que estamos arreglando)
def all_new_present(db_url: str) -> bool:
    from sqlalchemy import create_engine, inspect
    eng = create_engine(db_url)
    try:
        names = set(inspect(eng).get_table_names())
        return all(t in names for t in NEW_TABLES_2026_09_27_0001)
    finally:
        eng.dispose()
new_present = all_new_present(f"sqlite:///{db_e}")
ok_e = (
    rc_e == 0
    and v_e
    and not v_e_pre
    and new_present
    and n_e >= n_e_pre + 1  # +1 alembic_version + 3 tablas nuevas = +4
    and n_e == n_e_pre + 4
)
print(
    f"   {'[OK  ]' if ok_e else '[FAIL]'} TEST E "
    "(legacy parcial: stamp base + upgrade crea las 3 tablas nuevas)"
)

print()
print("=" * 72)
print("RESUMEN")
print("=" * 72)
total = 5
passed = sum([ok_a, ok_b, ok_c, ok_d, ok_e])
print(f"   Pasaron: {passed}/{total}")
print(f"   {'EXIT OK' if passed == total else 'EXIT FAIL'}")
for db in (db_a, db_b, db_c, db_d, db_e):
    db.unlink(missing_ok=True)
sys.exit(0 if passed == total else 1)
