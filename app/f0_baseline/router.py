"""
Router FastAPI del paquete F0.

Endpoints:
  GET /f0/hu01     → HU_01 — Inventario de funciones window.*
  GET /f0/hu02     → HU_02 — Mapeo localStorage ↔ modelos
  GET /f0/hu03     → HU_03 — Estado de Alembic + pytest
  GET /f0/health   → Healthcheck del paquete F0
  GET /f0/         → Índice con info del paquete
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from app.f0_baseline import __version__, __phase__, __story_points__, __hu_covered__

router = APIRouter(
    prefix="/f0",
    tags=["F0 — Baseline & Auditoría"],
    responses={404: {"description": "Reporte no generado aún"}},
)


REPORTS_DIR = Path(__file__).resolve().parent.parent.parent / "reports" / "f0_baseline"


def _read_json(name: str) -> dict[str, Any]:
    p = REPORTS_DIR / name
    if not p.exists():
        raise HTTPException(
            status_code=404,
            detail=(
                f"Reporte '{name}' no encontrado. "
                f"Ejecuta: python -m scripts.f0_baseline.validate_all"
            ),
        )
    return json.loads(p.read_text(encoding="utf-8"))


@router.get("/", response_model=dict)
async def index() -> dict[str, Any]:
    """Índice del paquete F0."""
    return {
        "package": "app.f0_baseline",
        "version": __version__,
        "phase": __phase__,
        "story_points": __story_points__,
        "hu_covered": __hu_covered__,
        "endpoints": {
            "GET /f0/":        "este índice",
            "GET /f0/health":  "healthcheck del paquete",
            "GET /f0/hu01":    "HU_01 — Inventario window.* (3 SP)",
            "GET /f0/hu02":    "HU_02 — Mapeo localStorage ↔ modelos (3 SP)",
            "GET /f0/hu03":    "HU_03 — Estado Alembic + pytest (2 SP)",
        },
    }


@router.get("/health", response_model=dict)
async def health() -> dict[str, Any]:
    """Healthcheck del paquete F0."""
    return {
        "status": "ok",
        "package": "app.f0_baseline",
        "version": __version__,
        "hu_covered": __hu_covered__,
    }


@router.get("/hu01", response_model=dict)
async def hu01_inventory() -> JSONResponse:
    """HU_01 — Devuelve el inventario de funciones `window.*` del prototipo."""
    data = _read_json("window-functions.json")
    rows = data.get("rows", [])
    return JSONResponse(content={
        "hu": "HU_01",
        "title": "Inventariar funciones del prototipo V134.1",
        "story_points": 3,
        "priority": "Must",
        "result": {
            "total_functions": data.get("total", 0),
            "elapsed_ms": data.get("elapsed_ms", 0),
            "modules": sorted({r["module"] for r in rows}),
        },
        "report": {
            "markdown": "/reports/f0_baseline/window-functions.md",
            "json":     "/reports/f0_baseline/window-functions.json",
        },
    })


@router.get("/hu02", response_model=dict)
async def hu02_mapping() -> JSONResponse:
    """HU_02 — Devuelve el mapeo localStorage ↔ modelos SQLAlchemy."""
    data = _read_json("mapping.json")
    stats = data.get("stats", {})
    return JSONResponse(content={
        "hu": "HU_02",
        "title": "Mapear localStorage a modelos SQLAlchemy multi-tenant",
        "story_points": 3,
        "priority": "Must",
        "result": {
            "keys_in_html":         stats.get("keys_in_html", 0),
            "models":               stats.get("models", 0),
            "models_with_tenant_id": stats.get("models_with_tenant_id", 0),
            "cross_foreign_keys":   stats.get("cross_foreign_keys", 0),
            "coverage_pct":         stats.get("coverage_pct", 0.0),
        },
        "mapping_sample": data.get("mapping", [])[:5],
        "report": {
            "markdown": "/reports/f0_baseline/mapping.md",
            "json":     "/reports/f0_baseline/mapping.json",
        },
    })


@router.get("/hu03", response_model=dict)
async def hu03_migrations(live: bool = Query(False, description="Si True, corre pytest + alembic en vivo en lugar de leer el cache.")) -> JSONResponse:
    """HU_03 — Estado de Alembic + última corrida de pytest.

    Por defecto devuelve el reporte cacheado generado por
    `python -m scripts.f0_baseline.validate_all`. Si el cache no existe
    o si se pasa ``?live=1``, corre los checks en vivo (sólo recomendado
    fuera de tests porque puede tardar 30-120 s).
    """
    if live:
        from app.f0_baseline.hu03 import build_report as _build
        try:
            report = _build()
        except Exception as e:  # pragma: no cover — defensivo
            report = {"error": f"live build failed: {e}"}
    else:
        try:
            data = _read_json("migrations.json")
            report = data.get("result", data)
        except HTTPException:
            report = {"note": "Ejecuta `python -m scripts.f0_baseline.validate_all` para generar el reporte."}
    return JSONResponse(content={
        "hu": "HU_03",
        "title": "Configurar Alembic como sistema de migraciones",
        "story_points": 2,
        "priority": "Must",
        "result": report,
        "tests": "/tests/",
    })
