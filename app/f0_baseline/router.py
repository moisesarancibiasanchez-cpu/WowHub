"""
Router FastAPI del paquete F0.

Endpoints:
  GET /f0/             → Índice con info del paquete
  GET /f0/health       → Healthcheck del paquete F0
  GET /f0/metrics      → Métricas estilo Prometheus (counts de modelos/tests/keys)
  GET /f0/catalog      → Diff KEY_TO_MODEL ↔ Base.metadata (auditoría de catálogo)
  GET /f0/hu01         → HU_01 — Inventario de funciones window.*
  GET /f0/hu02         → HU_02 — Mapeo localStorage ↔ modelos
  GET /f0/hu03[?live=] → HU_03 — Estado de Alembic + pytest
"""
from __future__ import annotations

import json
import os
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


# Modelos del dominio que NO necesitan entrada en KEY_TO_MODEL.
# Son objetos "raíz multi-tenant" o entidades de plataforma que el
# frontend referencia indirectamente vía API y nunca siembra en localStorage.
# (Auditoría — actualizar al añadir/quitar modelos de `app.models`.)
INTERNAL_MODELS_ALLOWLIST: frozenset[str] = frozenset({
    "Tenant",            # raíz SaaS — el tenant es la base de la jerarquía
    "User",              # usuario global, no por tenant
    "AuthToken",         # sesión, no persistida en localStorage del cliente
    "AuditLog",          # log de plataforma, solo escritura server-side
    "LegalConsent",      # consentimiento legal, no es objeto de UI
    "SiteConfig",        # config global, leída vía /config no localStorage
    "OnboardingState",   # estado efímero de wizard
    # Modelos API-served (frontend usa /api/v1/... no localStorage)
    "BusinessCosts",     # fuente de verdad de costos por tenant;
                         #   el form V8_Costos_Onboarding.html escribe
                         #   vía PUT /api/v1/costs/, no localStorage.
})


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


def _catalog_diff() -> dict[str, Any]:
    """Calcula el diff entre KEY_TO_MODEL y los modelos en Base.metadata.

    Devuelve un dict con:
      - in_catalog:        modelos del catálogo
      - in_metadata:       modelos de Base.metadata
      - orphan_models:     modelos de app.models sin entrada en catálogo
                           (excluyendo INTERNAL_MODELS_ALLOWLIST)
      - catalog_only:      entradas del catálogo sin modelo en metadata
      - metadata_table_map: nombre de tabla por modelo (solo los catalogados)
    """
    from app.f0_baseline.mapping import KEY_TO_MODEL, LocalStorageMapping
    from app.database import Base

    m = LocalStorageMapping()
    rows = m.build_rows()

    in_catalog = {meta["model"] for meta in KEY_TO_MODEL.values()}
    in_metadata: set[str] = set()
    metadata_table_map: dict[str, str] = {}

    registry = getattr(Base, "registry", None)
    if registry is not None and hasattr(registry, "mappers"):
        for mapper in registry.mappers:
            cls = getattr(mapper, "class_", None)
            if cls is None:
                continue
            name = cls.__name__
            in_metadata.add(name)
            local_table = getattr(mapper, "local_table", None)
            if local_table is not None and name in in_catalog:
                metadata_table_map[name] = local_table.name

    orphan_models = sorted(
        (in_metadata - in_catalog) - INTERNAL_MODELS_ALLOWLIST
    )
    catalog_only = sorted(in_catalog - in_metadata)

    return {
        "in_catalog_count": len(in_catalog),
        "in_metadata_count": len(in_metadata),
        "in_allowlist_count": len(
            (in_metadata - in_catalog) & INTERNAL_MODELS_ALLOWLIST
        ),
        "orphan_models": orphan_models,
        "orphan_models_count": len(orphan_models),
        "catalog_only": catalog_only,
        "catalog_only_count": len(catalog_only),
        "metadata_table_map": metadata_table_map,
    }


def _metrics_payload() -> dict[str, Any]:
    """Genera métricas estilo Prometheus en formato JSON.

    Contrato:
      - counts:    enteros simples (modelos, tests, keys, FKs)
      - ratios:    proporciones 0-1 (coverage_pct / 100)
      - timing_ms: tiempos medidos
      - flags:     booleanos de estado (alembic_dir_exists, etc.)
    """
    from app.f0_baseline.mapping import KEY_TO_MODEL, LocalStorageMapping
    from app.database import Base

    # 1) Conteos de modelos / catálogo / FKs
    m = LocalStorageMapping()
    rows = m.build_rows()
    in_metadata = {
        cls.__name__
        for mapper in getattr(Base, "registry", None).mappers
        for cls in [getattr(mapper, "class_", None)]
        if cls is not None
    } if getattr(Base, "registry", None) is not None else set()

    in_catalog = {meta["model"] for meta in KEY_TO_MODEL.values()}
    fk_count = sum(len(r.fks) for r in rows)
    tenant_id_count = sum(1 for r in rows if r.has_tenant_id)

    # 2) Conteos de tests (lee del cache si existe, sino recount manual)
    tests_collected = 0
    cache = REPORTS_DIR / "migrations.json"
    if cache.exists():
        try:
            data = json.loads(cache.read_text(encoding="utf-8"))
            tests_collected = int(data.get("result", {}).get("pytest_collected", 0) or 0)
        except (json.JSONDecodeError, ValueError, KeyError):
            tests_collected = 0

    # 3) Inventario (lee del cache si existe)
    total_window_functions = 0
    inv_cache = REPORTS_DIR / "window-functions.json"
    if inv_cache.exists():
        try:
            inv_data = json.loads(inv_cache.read_text(encoding="utf-8"))
            total_window_functions = int(inv_data.get("total", 0) or 0)
        except (json.JSONDecodeError, ValueError, KeyError):
            total_window_functions = 0

    # 4) Cobertura
    catalog_total = len(KEY_TO_MODEL)
    coverage_pct = (catalog_total / max(len(in_metadata), 1)) * 100

    return {
        "counts": {
            "models_in_metadata": len(in_metadata),
            "models_in_catalog": catalog_total,
            "keys_localstorage": catalog_total,
            "tenant_scoped_models": tenant_id_count,
            "cross_foreign_keys": fk_count,
            "tests_collected": tests_collected,
            "window_functions": total_window_functions,
        },
        "ratios": {
            "catalog_coverage_pct": round(coverage_pct, 2),
        },
        "flags": {
            "alembic_dir_exists": (Path(__file__).parent.parent.parent / "alembic").exists()
            and (Path(__file__).parent.parent.parent / "alembic.ini").exists(),
        },
        "package": {
            "name": "app.f0_baseline",
            "version": __version__,
            "phase": __phase__,
            "story_points": __story_points__,
            "hu_covered": list(__hu_covered__),
        },
    }


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
            "GET /f0/":           "este índice",
            "GET /f0/health":     "healthcheck del paquete",
            "GET /f0/metrics":    "métricas (modelos, tests, FKs, coverage)",
            "GET /f0/catalog":    "diff KEY_TO_MODEL ↔ Base.metadata",
            "GET /f0/hu01":       "HU_01 — Inventario window.* (3 SP)",
            "GET /f0/hu02":       "HU_02 — Mapeo localStorage ↔ modelos (3 SP)",
            "GET /f0/hu03?live=": "HU_03 — Estado Alembic + pytest (2 SP)",
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


@router.get("/metrics", response_model=dict)
async def metrics() -> dict[str, Any]:
    """Métricas del paquete F0 (estilo Prometheus en JSON).

    Útil para integrar con Grafana / Datadog / scrapers de Prometheus.
    """
    return _metrics_payload()


@router.get("/catalog", response_model=dict)
async def catalog_diff() -> dict[str, Any]:
    """Diff entre ``KEY_TO_MODEL`` y ``Base.metadata``.

    Detecta:
      - ``orphan_models``: modelos en ``app.models`` que NO están en el
        catálogo y no son "internos" (allowlist).
      - ``catalog_only``: entradas del catálogo sin modelo físico
        (sería un bug — la key apunta a un modelo inexistente).
    """
    return _catalog_diff()


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
async def hu03_migrations(
    live: bool = Query(
        False,
        description=(
            "Si True, corre pytest + alembic en vivo en lugar de leer el cache. "
            "Limitado a F0_HU03_LIVE_TIMEOUT segundos (default 30s) — devuelve 503 si excede."
        ),
    ),
) -> JSONResponse:
    """HU_03 — Estado de Alembic + última corrida de pytest.

    Por defecto devuelve el reporte cacheado generado por
    ``python -m scripts.f0_baseline.validate_all``. Si el cache no existe
    o si se pasa ``?live=true``, corre los checks en vivo.

    En modo ``live`` se aplica un **circuit breaker**: si la corrida
    excede ``F0_HU03_LIVE_TIMEOUT`` (default 30 s) se devuelve ``503``
    con el detalle del timeout, en vez de esperar el timeout completo
    del subproceso (que sería de hasta 120 s).
    """
    if live:
        from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutTimeout

        from app.f0_baseline.hu03 import build_report as _build

        timeout_s = int(os.environ.get("F0_HU03_LIVE_TIMEOUT", "30"))
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(_build)
            try:
                report = future.result(timeout=timeout_s)
            except FutTimeout:
                # 503: circuit breaker — no dejar al cliente esperando
                # hasta 120 s si pytest/alembic se quedan colgados.
                return JSONResponse(
                    status_code=503,
                    content={
                        "hu": "HU_03",
                        "title": "Configurar Alembic como sistema de migraciones",
                        "story_points": 2,
                        "priority": "Must",
                        "error": "live_timeout",
                        "detail": (
                            f"hu03 live build excedió {timeout_s}s. "
                            "Aumenta F0_HU03_LIVE_TIMEOUT o usa el cache."
                        ),
                        "timeout_s": timeout_s,
                    },
                )
            except Exception as e:  # pragma: no cover — defensivo
                report = {"error": f"live build failed: {e}"}
    else:
        try:
            data = _read_json("migrations.json")
            report = data.get("result", data)
        except HTTPException:
            report = {
                "note": (
                    "Ejecuta `python -m scripts.f0_baseline.validate_all` "
                    "para generar el reporte."
                )
            }
    return JSONResponse(content={
        "hu": "HU_03",
        "title": "Configurar Alembic como sistema de migraciones",
        "story_points": 2,
        "priority": "Must",
        "result": report,
        "tests": "/tests/",
    })
