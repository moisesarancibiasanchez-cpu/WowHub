"""
Schemas Pydantic v2 para los endpoints del paquete F0.

Estos modelos dan:
  - Validación de request (params / query / body)
  - Contrato explícito de response (tipos estrictos en OpenAPI)
  - Ejemplos para `/docs` y validación automática en tests

Convención de nombres:
  - `*Request`  → query/path/body params que acepta el endpoint
  - `*Response` → shape JSON que devuelve
  - `*Report`   → un sub-dict reusable (HU_03 result, etc.)

Si añades un campo nuevo al response de un endpoint, **primero** actualizá
el schema acá. FastAPI detecta el mismatch en runtime y devuelve 500
explícito, no un JSON silencioso con tipos rotos.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


# ── Compartido ─────────────────────────────────────────────────────

class PackageInfo(BaseModel):
    """Metadata del paquete F0 — aparece en /, /health, /metrics, etc."""
    name: str
    version: str
    phase: str
    story_points: int
    hu_covered: list[str]


class ReportLink(BaseModel):
    """Path a un artefacto (markdown + json)."""
    markdown: str = Field(..., description="Ruta al .md bajo reports/f0_baseline/")
    json: str = Field(..., description="Ruta al .json bajo reports/f0_baseline/")


# ── /f0/ — índice ────────────────────────────────────────────────

class IndexResponse(BaseModel):
    package: str
    version: str
    phase: str
    story_points: int
    hu_covered: list[str]
    endpoints: dict[str, str]


# ── /f0/health ────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    status: Literal["ok"]
    package: str
    version: str
    hu_covered: list[str]


# ── /f0/metrics ───────────────────────────────────────────────────

class MetricsCounts(BaseModel):
    """Conteos crudos — todos >= 0 (un conteo negativo no tiene sentido)."""
    models_in_metadata: int = Field(..., ge=0)
    models_in_catalog: int = Field(..., ge=0)
    keys_localstorage: int = Field(..., ge=0)
    tenant_scoped_models: int = Field(..., ge=0)
    cross_foreign_keys: int = Field(..., ge=0)
    tests_collected: int = Field(..., ge=0)
    window_functions: int = Field(..., ge=0)


class MetricsRatios(BaseModel):
    catalog_coverage_pct: float = Field(..., ge=0.0, le=100.0)


class MetricsFlags(BaseModel):
    alembic_dir_exists: bool


class MetricsPackage(BaseModel):
    name: str
    version: str
    phase: str
    story_points: int
    hu_covered: list[str]


class MetricsResponse(BaseModel):
    counts: MetricsCounts
    ratios: MetricsRatios
    flags: MetricsFlags
    package: MetricsPackage


# ── /f0/catalog ───────────────────────────────────────────────────

class CatalogDiffResponse(BaseModel):
    in_catalog_count: int
    in_metadata_count: int
    in_allowlist_count: int
    orphan_models: list[str]
    orphan_models_count: int
    catalog_only: list[str]
    catalog_only_count: int
    metadata_table_map: dict[str, str]


# ── /f0/hu01 ──────────────────────────────────────────────────────

class Hu01Result(BaseModel):
    total_functions: int
    elapsed_ms: int
    modules: list[str]


class Hu01Response(BaseModel):
    hu: Literal["HU_01"]
    title: str
    story_points: int
    priority: str
    result: Hu01Result
    report: ReportLink


# ── /f0/hu02 ──────────────────────────────────────────────────────

class Hu02MappingSampleItem(BaseModel):
    model_config = ConfigDict(extra="allow")  # mapping es libre, aceptamos extras
    key: str | None = None
    model: str | None = None
    storage_kind: str | None = None
    module: str | None = None
    description: str | None = None


class Hu02Result(BaseModel):
    keys_in_html: int
    models: int
    models_with_tenant_id: int
    cross_foreign_keys: int
    coverage_pct: float


class Hu02Response(BaseModel):
    hu: Literal["HU_02"]
    title: str
    story_points: int
    priority: str
    result: Hu02Result
    mapping_sample: list[dict[str, Any]]
    report: ReportLink


# ── /f0/hu03 ──────────────────────────────────────────────────────

class Hu03Query(BaseModel):
    """Query params de /f0/hu03 (se valida con Query() en el router)."""
    live: bool = Field(
        False,
        description=(
            "Si True, corre pytest + alembic en vivo en lugar de leer el cache. "
            "Limitado a F0_HU03_LIVE_TIMEOUT segundos (default 30s)."
        ),
    )


class Hu03Result(BaseModel):
    """Sub-dict `result` del response — modela el cache (migrations.json)."""
    model_config = ConfigDict(extra="allow")
    alembic_dir_exists: bool | None = None
    alembic_upgrade: str | None = None
    pytest: str | None = None
    pytest_collected: int | None = None
    database_url: str | None = None
    models_loaded: int | None = None
    elapsed_ms: int | None = None
    # Slots en vivo o cache miss
    note: str | None = None
    error: str | None = None


class Hu03Response(BaseModel):
    hu: Literal["HU_03"]
    title: str
    story_points: int
    priority: str
    result: dict[str, Any] = Field(
        ...,
        description=(
            "Payload del reporte. En modo cache, viene de migrations.json. "
            "En live, viene de build_report() con circuit breaker."
        ),
    )
    tests: str | None = Field(
        None,
        description="Path a la suite de tests (referencia)",
    )


class Hu03TimeoutResponse(BaseModel):
    """Response específico del 503 — circuit breaker."""
    hu: Literal["HU_03"]
    title: str
    story_points: int
    priority: str
    error: Literal["live_timeout"]
    detail: str
    timeout_s: int


# ── Error envelope (mismo shape que el resto de la API) ──────────

class ErrorResponse(BaseModel):
    detail: str
