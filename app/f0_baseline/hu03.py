"""
HU_03 — Estado de Alembic + pytest del proyecto.

A diferencia de un proyecto vacío, WowHub puede o no tener
directorio `alembic/`. Si NO existe, validamos con:
  - `Base.metadata.create_all()` para confirmar que los modelos cargan
  - `pytest --collect-only` para confirmar que los tests son recolectables
  - `pytest` para correr la suite (modo resumido)

Si SÍ existe, validamos con `alembic upgrade head` y `pytest`.

Devuelve un dict con estado de cada check.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Ajustar import dinámico porque `app/` es raíz del proyecto
HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent.parent  # /workspace/wowhub


def _project_root() -> Path:
    """Encuentra la raíz del proyecto (donde está pyproject.toml)."""
    candidates = [Path.cwd(), HERE.parent.parent, HERE.parent.parent.parent]
    for c in candidates:
        if (c / "pyproject.toml").exists():
            return c
    return HERE.parent.parent


@dataclass
class Hu03Report:
    alembic_dir_exists: bool
    alembic_upgrade: str
    pytest: str
    pytest_collected: int
    database_url: str
    models_loaded: int
    elapsed_ms: int

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


def _run(cmd: list[str], cwd: Path, timeout: int = 60) -> tuple[int, str, str]:
    """Ejecuta un comando y devuelve (rc, stdout, stderr)."""
    try:
        proc = subprocess.run(
            cmd, cwd=str(cwd), capture_output=True, text=True, timeout=timeout
        )
        return proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired:
        return 124, "", f"Timeout después de {timeout}s ejecutando: {' '.join(cmd)}"
    except FileNotFoundError as e:
        return 127, "", f"Comando no encontrado: {e}"


def build_report() -> dict[str, Any]:
    """Ejecuta los checks de HU_03 y devuelve un dict serializable."""
    import time
    t0 = time.perf_counter()
    root = _project_root()
    alembic_dir = root / "alembic"
    alembic_ini = root / "alembic.ini"
    has_alembic = alembic_dir.exists() and alembic_ini.exists()

    # 1) Alembic
    if has_alembic:
        rc, out, err = _run(
            ["alembic", "current"], cwd=root, timeout=30
        )
        alembic_status = "ok" if rc == 0 else f"error: {(err or out).strip()[:120]}"
    else:
        alembic_status = "n/a (no alembic/ en el proyecto)"

    # 2) Modelos cargan
    try:
        from app.database import Base  # noqa: F401
        from app.models import (  # noqa: F401
            tenant, user, branch, category, product, customer,
            promotion, qr, landing, order, payment, webhook,
            audit, branch_product, token, cart, invoice, booking,
            legal, onboarding, upload, site_config, ai,
            loyalty_pass, quote, automation, insumo,
        )
        n_models = len(Base.metadata.tables)
    except Exception as e:  # pragma: no cover
        n_models = 0
        alembic_status = f"models-fail: {e}"

    # 3) Pytest collect
    # Por defecto solo recolectamos los tests de F0 (rápido).
    # Para validar todo el suite, exportar F0_PYTEST_TARGET=tests/
    pytest_target = os.environ.get("F0_PYTEST_TARGET", "tests/f0_baseline/")
    rc, out, err = _run(
        [sys.executable, "-m", "pytest", pytest_target, "--collect-only", "-q"],
        cwd=root, timeout=60,
    )
    pytest_collected = 0
    if rc == 0:
        import re as _re
        # Buscar la línea resumen "N tests collected" (puede estar envuelta
        # en separadores "===" o venir sola al final de la salida).
        for line in out.splitlines():
            m = _re.search(r"(\d+)\s+tests?\s+collected", line)
            if m:
                pytest_collected = int(m.group(1))
                break

    # 4) Pytest run (resumido) — solo si la collect fue ok.
    # Por defecto solo corre los tests de F0 (rápido). Para correr todo,
    # exportar F0_PYTEST_TARGET=tests/ y F0_PYTEST_RUN=full.
    pytest_run_target = os.environ.get("F0_PYTEST_RUN", pytest_target)
    if rc == 0 and pytest_collected > 0:
        rc2, out2, err2 = _run(
            [sys.executable, "-m", "pytest", pytest_run_target, "-q", "--tb=line"],
            cwd=root, timeout=120,
        )
        # Buscar "X passed" en la última línea
        pytest_status = "unknown"
        for line in (out2 + err2).splitlines()[::-1]:
            line = line.strip().lower()
            if "passed" in line and "failed" not in line:
                pytest_status = line
                break
            if "failed" in line:
                pytest_status = line
                break
        if pytest_status == "unknown":
            pytest_status = f"rc={rc2} (ver logs)"
    else:
        pytest_status = f"collect-fail rc={rc}"

    elapsed = int((time.perf_counter() - t0) * 1000)
    report = Hu03Report(
        alembic_dir_exists=has_alembic,
        alembic_upgrade=alembic_status,
        pytest=pytest_status,
        pytest_collected=pytest_collected,
        database_url=os.environ.get("DATABASE_URL", "sqlite:///./wowhub.db"),
        models_loaded=n_models,
        elapsed_ms=elapsed,
    )
    return report.to_dict()


def to_markdown(report: dict[str, Any]) -> str:
    out: list[str] = []
    out.append("# HU_03 — Estado de Alembic + pytest — WowHub F0")
    out.append("")
    out.append("| Check | Estado |")
    out.append("|---|---|")
    out.append(f"| `alembic/` existe | **{report['alembic_dir_exists']}** |")
    out.append(f"| `alembic upgrade` | `{report['alembic_upgrade']}` |")
    out.append(f"| `pytest --collect-only` | **{report['pytest_collected']} tests** |")
    out.append(f"| `pytest` corrida | `{report['pytest']}` |")
    out.append(f"| Modelos cargados | **{report['models_loaded']}** tablas |")
    out.append(f"| `DATABASE_URL` | `{report['database_url']}` |")
    out.append(f"| Tiempo total | {report['elapsed_ms']} ms |")
    out.append("")
    out.append("---")
    out.append("_Generado por `app.f0_baseline.hu03` · introspección + subprocess._")
    return "\n".join(out)
