"""Tests F1.3 — Alembic setup (≈ HU_06).

Verifica que el setup de Alembic esté completo y funcional:

  1. Estructura de directorios (``alembic/``, ``alembic.ini``, ``versions/``).
  2. ``alembic/env.py`` importa ``Base.metadata`` y los modelos necesarios.
  3. ``alembic.ini`` no hardcodea URL — usa env var o settings.
  4. La migración inicial existe, importa ``app.models.base`` (para GUID)
     y se aplica limpia en una DB vacía (upgrade + downgrade).

Los tests 1-3 son estáticos (leen archivos). El test 4 es dinámico
(spawn ``alembic`` CLI contra un SQLite temporal) y está marcado como
``@pytest.mark.slow`` para no ejecutarse en el flujo default de CI.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


# ── Rutas del proyecto ───────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
ALEMBIC_INI = PROJECT_ROOT / "alembic.ini"
ALEMBIC_DIR = PROJECT_ROOT / "alembic"
ENV_PY = ALEMBIC_DIR / "env.py"
VERSIONS_DIR = ALEMBIC_DIR / "versions"


# ── 1. Estructura de directorios ──────────────────────────────────────────


def test_alembic_directory_exists() -> None:
    assert ALEMBIC_DIR.exists(), f"Directorio {ALEMBIC_DIR} no existe"
    assert ALEMBIC_DIR.is_dir()


def test_alembic_ini_exists() -> None:
    assert ALEMBIC_INI.exists(), f"{ALEMBIC_INI} no existe"


def test_alembic_versions_dir_exists() -> None:
    assert VERSIONS_DIR.exists(), f"Directorio {VERSIONS_DIR} no existe"
    assert VERSIONS_DIR.is_dir()


def test_alembic_env_py_exists() -> None:
    assert ENV_PY.exists(), f"{ENV_PY} no existe"


def test_alembic_script_py_mako_exists() -> None:
    """El template Mako que genera las migraciones nuevas debe existir."""
    mako = ALEMBIC_DIR / "script.py.mako"
    assert mako.exists()


def test_at_least_one_migration_exists() -> None:
    """La migración inicial (autogenerada) debe estar en versions/."""
    migrations = list(VERSIONS_DIR.glob("*.py"))
    assert len(migrations) >= 1, (
        f"No hay migraciones en {VERSIONS_DIR}. "
        "Ejecutá: alembic revision --autogenerate -m 'initial_schema'"
    )


# ── 2. Contenido de alembic/env.py ───────────────────────────────────────


def test_env_py_imports_base_metadata() -> None:
    text = ENV_PY.read_text(encoding="utf-8")
    assert "from app.database import Base" in text
    assert "target_metadata = Base.metadata" in text


def test_env_py_imports_models() -> None:
    """env.py debe importar los modelos para que se registren en Base.metadata."""
    text = ENV_PY.read_text(encoding="utf-8")
    # Debe importar el paquete ``app.models`` (lazy loading)
    assert "import app.models" in text
    # Y al menos los modelos principales explícitamente
    assert "from app.models import" in text
    # Verificamos que están los modelos clave
    for model_module in ("user", "tenant", "product", "order", "customer"):
        assert model_module in text, f"Falta importar modelo {model_module}"


def test_env_py_resolves_database_url_from_settings() -> None:
    """env.py debe tomar la URL de settings o env var (no hardcoded)."""
    text = ENV_PY.read_text(encoding="utf-8")
    assert "DATABASE_URL" in text, "env.py debe leer la env var DATABASE_URL"
    assert "from app.config import settings" in text
    assert "settings.database_url" in text


def test_env_py_sets_sqlalchemy_url() -> None:
    """env.py debe inyectar la URL en config antes de correr migraciones."""
    text = ENV_PY.read_text(encoding="utf-8")
    assert 'config.set_main_option("sqlalchemy.url"' in text


# ── 3. Contenido de alembic.ini ──────────────────────────────────────────


def test_alembic_ini_has_script_location() -> None:
    text = ALEMBIC_INI.read_text(encoding="utf-8")
    assert "script_location = %(here)s/alembic" in text


def test_alembic_ini_url_is_placeholder() -> None:
    """La URL en alembic.ini debe ser un placeholder (la real viene de env.py)."""
    text = ALEMBIC_INI.read_text(encoding="utf-8")
    # El comentario debe explicar que es un placeholder
    assert "F1.3" in text or "placeholder" in text.lower(), (
        "alembic.ini debe documentar que la URL es ignorada en favor de env.py"
    )
    # El valor literal debe ser el placeholder default
    assert "driver://user:pass@localhost/dbname" in text


def test_alembic_ini_has_chronological_file_template() -> None:
    """El file_template debe incluir timestamp para que ``ls`` ordene cronológicamente."""
    text = ALEMBIC_INI.read_text(encoding="utf-8")
    # Debe haber una línea file_template con year/month/day/hour/minute
    assert "file_template = %%(year)d_%%(month).2d_%%(day).2d" in text, (
        "F1.3: file_template debe incluir timestamp para orden cronológico"
    )


# ── 4. La migración inicial tiene el import de GUID ──────────────────────


def test_initial_migration_imports_app_models_base() -> None:
    """La migración autogenerada usa ``app.models.base.GUID()`` y debe importarlo."""
    migrations = list(VERSIONS_DIR.glob("*initial*.py"))
    if not migrations:
        pytest.skip("No hay migración inicial — saltamos este test")
    text = migrations[0].read_text(encoding="utf-8")
    assert "import app.models.base" in text, (
        f"La migración {migrations[0].name} debe importar app.models.base "
        "para que ``app.models.base.GUID()`` esté disponible en upgrade()."
    )


def test_initial_migration_has_upgrade_and_downgrade() -> None:
    migrations = list(VERSIONS_DIR.glob("*initial*.py"))
    if not migrations:
        pytest.skip("No hay migración inicial — saltamos este test")
    text = migrations[0].read_text(encoding="utf-8")
    assert "def upgrade() -> None:" in text
    assert "def downgrade() -> None:" in text


# ── 5. Test dinámico: alembic upgrade + downgrade contra SQLite temporal ──


@pytest.mark.slow
def test_alembic_upgrade_head_on_empty_db(tmp_path: Path) -> None:
    """Levanta una DB SQLite vacía, corre ``alembic upgrade head`` y
    verifica que la tabla ``alembic_version`` se creó con la revisión.
    """
    db_path = tmp_path / "alembic_smoke.db"
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{db_path}"

    # Usamos el Python del venv actual (no el system) para tener alembic instalado
    cmd = [
        sys.executable, "-m", "alembic",
        "-c", str(ALEMBIC_INI),
        "upgrade", "head",
    ]
    result = subprocess.run(
        cmd, cwd=str(PROJECT_ROOT), env=env,
        capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 0, (
        f"alembic upgrade head falló:\n"
        f"STDOUT:\n{result.stdout}\n"
        f"STDERR:\n{result.stderr}"
    )

    # Verificar que la DB existe y tiene la tabla alembic_version
    assert db_path.exists()
    import sqlite3
    con = sqlite3.connect(str(db_path))
    try:
        cur = con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='alembic_version'"
        )
        assert cur.fetchone() is not None, "No se creó la tabla alembic_version"
        # Verificar que tiene una revisión
        cur = con.execute("SELECT version_num FROM alembic_version")
        row = cur.fetchone()
        assert row is not None and row[0], "alembic_version está vacía"
    finally:
        con.close()


@pytest.mark.slow
def test_alembic_downgrade_base_after_upgrade(tmp_path: Path) -> None:
    """Upgrade → Downgrade base debe dejar la DB vacía (sin tablas de modelos)."""
    db_path = tmp_path / "alembic_smoke2.db"
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{db_path}"

    def _run(args: list[str]) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, "-m", "alembic", "-c", str(ALEMBIC_INI)] + args,
            cwd=str(PROJECT_ROOT), env=env,
            capture_output=True, text=True, timeout=120,
        )

    # Upgrade
    r1 = _run(["upgrade", "head"])
    assert r1.returncode == 0, f"upgrade falló: {r1.stderr}"

    # Downgrade
    r2 = _run(["downgrade", "base"])
    assert r2.returncode == 0, f"downgrade falló: {r2.stderr}"

    # La DB debe existir pero NO tener tablas del proyecto
    import sqlite3
    con = sqlite3.connect(str(db_path))
    try:
        cur = con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name != 'alembic_version'"
        )
        project_tables = [r[0] for r in cur.fetchall()]
        assert project_tables == [], (
            f"Quedan tablas del proyecto tras downgrade base: {project_tables}"
        )
    finally:
        con.close()
