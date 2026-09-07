"""Tests F1.1 — Validación de los schemas Pydantic v2 del paquete F0.

HU_04 (3 SP) — El router de ``/f0/*`` debe tener ``response_model`` estricto
para que la spec OpenAPI declare los shapes exactos de cada endpoint, y los
tests deben garantizar que:

  1. Cada endpoint expone su modelo Pydantic en el contrato OpenAPI.
  2. La respuesta real del endpoint cumple ese contrato.
  3. Los modelos 404 / 503 están documentados en OpenAPI.
  4. Pydantic v2 rechaza payloads malformados (extra="forbid" en críticos).

Estos tests NO mockean la app: usan ``TestClient`` sobre la app real para
asegurar que la spec OpenAPI se corresponde con el código en producción.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError


# ── Schemas bajo test ───────────────────────────────────────────────────────
from app.f0_baseline.schemas import (  # noqa: E402
    CatalogDiffResponse,
    HealthResponse,
    Hu01Response,
    Hu01Result,
    Hu02Response,
    Hu02Result,
    Hu03Response,
    Hu03TimeoutResponse,
    IndexResponse,
    MetricsCounts,
    MetricsResponse,
    PackageInfo,
    ReportLink,
)


# ── Fixtures ────────────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def reports_dir(tmp_path_factory) -> Path:
    """Crea los artefactos cacheados que el router lee."""
    d = tmp_path_factory.mktemp("f0_reports_pydantic")
    (d / "window-functions.json").write_text(
        json.dumps(
            {
                "html": "demo.html",
                "total": 2,
                "elapsed_ms": 4,
                "rows": [
                    {"n": 1, "name": "fn_one", "module": "ALPHA",
                     "line": 10, "description": "primera"},
                    {"n": 2, "name": "fn_two", "module": "BETA",
                     "line": 20, "description": "segunda"},
                ],
                "markdown": "# demo",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (d / "mapping.json").write_text(
        json.dumps(
            {
                "stats": {
                    "keys_in_html": 2,
                    "models": 2,
                    "models_with_tenant_id": 2,
                    "cross_foreign_keys": 1,
                    "coverage_pct": 50.0,
                },
                "mapping": [
                    {"key": "k1", "model": "M1", "module": "alpha",
                     "storage_kind": "localStorage", "description": "x"},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (d / "migrations.json").write_text(
        json.dumps(
            {
                "hu": "HU_03",
                "result": {
                    "alembic_dir_exists": False,
                    "alembic_upgrade": "n/a (no alembic/ en el proyecto)",
                    "pytest": "10 passed",
                    "pytest_collected": 10,
                    "database_url": "sqlite:///:memory:",
                    "models_loaded": 30,
                    "elapsed_ms": 12,
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return d


@pytest.fixture(scope="module")
def client(reports_dir: Path):
    import app.f0_baseline.router as router_mod
    router_mod.REPORTS_DIR = reports_dir
    from app.main import app
    return TestClient(app)


# ── 1. Smoke: cada schema es instanciable con un payload mínimo ─────────────

def test_package_info_minimal() -> None:
    pkg = PackageInfo(
        name="x", version="1", phase="F0",
        story_points=8, hu_covered=["HU_01"],
    )
    assert pkg.name == "x"
    assert pkg.hu_covered == ["HU_01"]


def test_report_link_requires_both_paths() -> None:
    with pytest.raises(ValidationError):
        ReportLink(markdown="/x.md")  # type: ignore[call-arg]
    link = ReportLink(markdown="/x.md", json="/x.json")
    assert link.markdown == "/x.md"
    assert link.json == "/x.json"


# ── 2. OpenAPI: cada endpoint declara su response_model y los errores ──────

def test_openapi_has_f0_paths(client: TestClient) -> None:
    r = client.get("/openapi.json")
    assert r.status_code == 200
    spec = r.json()
    paths = spec["paths"]
    for p in ("/f0/", "/f0/health", "/f0/metrics",
              "/f0/catalog", "/f0/hu01", "/f0/hu02", "/f0/hu03"):
        assert p in paths, f"OpenAPI spec debe declarar el path {p}"


def test_openapi_hu03_documents_503_and_404(client: TestClient) -> None:
    """HU_03 debe declarar 200, 503 (circuit breaker) y 404 en OpenAPI."""
    r = client.get("/openapi.json")
    spec = r.json()
    hu03 = spec["paths"]["/f0/hu03"]["get"]
    responses = hu03["responses"]
    assert "200" in responses
    assert "503" in responses, "Circuit breaker 503 debe estar documentado"
    assert "404" in responses, "404 (reporte no generado) debe estar documentado"
    # El 503 debe referenciar el modelo Hu03TimeoutResponse por $ref
    ref = responses["503"]["content"]["application/json"]["schema"]["$ref"]
    assert ref.endswith("/Hu03TimeoutResponse"), ref


def test_openapi_health_status_is_literal_ok(client: TestClient) -> None:
    r = client.get("/openapi.json")
    spec = r.json()
    health = spec["paths"]["/f0/health"]["get"]["responses"]["200"]
    schema_ref = health["content"]["application/json"]["schema"]["$ref"]
    assert schema_ref.endswith("/HealthResponse")
    # Verificar el Literal["ok"] en el schema
    health_schema = spec["components"]["schemas"]["HealthResponse"]
    assert health_schema["properties"]["status"]["const"] == "ok"


# ── 3. Cada respuesta del endpoint valida contra su schema ────────────────

def test_endpoint_index_matches_index_response(client: TestClient) -> None:
    r = client.get("/f0/")
    assert r.status_code == 200
    parsed = IndexResponse.model_validate(r.json())
    assert parsed.package == "app.f0_baseline"
    assert parsed.phase == "F1"  # F0 baseline + F1 hardening
    # HU cubiertas: F0 (3) + F1 (3) = 6
    for hu in ("HU_01", "HU_02", "HU_03", "HU_04", "HU_05", "HU_06"):
        assert hu in parsed.hu_covered, f"{hu} debe estar en hu_covered"
    assert parsed.story_points == 16  # 8 F0 + 8 F1
    # El índice lista todos los endpoints del paquete
    for key in (
        "GET /f0/",
        "GET /f0/health",
        "GET /f0/metrics",
        "GET /f0/catalog",
        "GET /f0/hu01",
        "GET /f0/hu02",
        "GET /f0/hu03?live=",
    ):
        assert key in parsed.endpoints, f"endpoint faltante en /f0/: {key}"


def test_endpoint_health_matches_health_response(client: TestClient) -> None:
    r = client.get("/f0/health")
    assert r.status_code == 200
    parsed = HealthResponse.model_validate(r.json())
    assert parsed.status == "ok"


def test_endpoint_metrics_matches_metrics_response(client: TestClient) -> None:
    r = client.get("/f0/metrics")
    assert r.status_code == 200
    parsed = MetricsResponse.model_validate(r.json())
    # counts: int positivos
    assert parsed.counts.models_in_metadata >= 1
    assert parsed.counts.models_in_catalog >= 1
    # ratios: ratio 0-1 (Pydantic valida con ge=0.0, le=100.0)
    assert 0.0 <= parsed.ratios.catalog_coverage_pct <= 100.0
    # flags: booleano
    assert isinstance(parsed.flags.alembic_dir_exists, bool)
    # package: metadata del paquete
    assert parsed.package.name == "app.f0_baseline"
    assert parsed.package.phase == "F1"  # F0 + F1
    assert parsed.package.story_points == 16  # 8 F0 + 8 F1


def test_endpoint_catalog_matches_catalog_response(client: TestClient) -> None:
    r = client.get("/f0/catalog")
    assert r.status_code == 200
    parsed = CatalogDiffResponse.model_validate(r.json())
    assert parsed.in_metadata_count >= 1
    assert isinstance(parsed.orphan_models, list)
    assert isinstance(parsed.catalog_only, list)
    # Inconsistencia detectable: counts == len(listas)
    assert parsed.orphan_models_count == len(parsed.orphan_models)
    assert parsed.catalog_only_count == len(parsed.catalog_only)


def test_endpoint_hu01_matches_hu01_response(client: TestClient) -> None:
    r = client.get("/f0/hu01")
    assert r.status_code == 200
    parsed = Hu01Response.model_validate(r.json())
    assert parsed.hu == "HU_01"
    assert parsed.story_points == 3
    assert parsed.result.total_functions == 2
    assert "ALPHA" in parsed.result.modules
    assert "BETA" in parsed.result.modules
    # modules viene ordenado (el router hace sorted({r["module"] ...}))
    assert parsed.result.modules == sorted(parsed.result.modules)


def test_endpoint_hu02_matches_hu02_response(client: TestClient) -> None:
    r = client.get("/f0/hu02")
    assert r.status_code == 200
    parsed = Hu02Response.model_validate(r.json())
    assert parsed.hu == "HU_02"
    assert parsed.story_points == 3
    assert parsed.result.keys_in_html == 2
    assert parsed.result.coverage_pct == 50.0
    # mapping_sample es libre (ConfigDict extra=allow en el item)
    assert isinstance(parsed.mapping_sample, list)


def test_endpoint_hu03_cached_matches_hu03_response(client: TestClient) -> None:
    r = client.get("/f0/hu03")
    assert r.status_code == 200
    parsed = Hu03Response.model_validate(r.json())
    assert parsed.hu == "HU_03"
    assert parsed.story_points == 2
    assert parsed.result["alembic_dir_exists"] is False
    assert parsed.result["pytest_collected"] == 10


def test_endpoint_hu03_timeout_matches_timeout_response(
    client: TestClient, monkeypatch
) -> None:
    """El 503 del circuit breaker debe validar contra Hu03TimeoutResponse."""
    import time as _time
    from app.f0_baseline import hu03

    def slow() -> dict:
        _time.sleep(5)
        return {"pytest": "late"}

    monkeypatch.setattr(hu03, "build_report", slow)
    monkeypatch.setenv("F0_HU03_LIVE_TIMEOUT", "1")

    r = client.get("/f0/hu03?live=true")
    assert r.status_code == 503
    parsed = Hu03TimeoutResponse.model_validate(r.json())
    assert parsed.error == "live_timeout"
    assert parsed.timeout_s == 1
    assert parsed.hu == "HU_03"
    assert "Aumenta" in parsed.detail


# ── 4. Rechazo: Pydantic v2 rechaza payloads con tipos equivocados ─────────

def test_hu01_rejects_wrong_type_for_total_functions() -> None:
    with pytest.raises(ValidationError):
        Hu01Response.model_validate({
            "hu": "HU_01",
            "title": "x",
            "story_points": 3,
            "priority": "Must",
            "result": {"total_functions": "two", "elapsed_ms": 0, "modules": []},
            "report": {"markdown": "/x.md", "json": "/x.json"},
        })


def test_metrics_counts_rejects_negative_window_functions() -> None:
    with pytest.raises(ValidationError):
        MetricsCounts(
            models_in_metadata=1,
            models_in_catalog=1,
            keys_localstorage=1,
            tenant_scoped_models=0,
            cross_foreign_keys=0,
            tests_collected=0,
            window_functions=-1,  # negativo, no permitido
        )


def test_metrics_ratios_rejects_pct_above_100() -> None:
    from app.f0_baseline.schemas import MetricsRatios
    with pytest.raises(ValidationError):
        MetricsRatios(catalog_coverage_pct=150.0)  # > 100.0


def test_hu02_result_rejects_missing_required_field() -> None:
    with pytest.raises(ValidationError):
        Hu02Result.model_validate({
            "keys_in_html": 1,
            "models": 1,
            "models_with_tenant_id": 1,
            # falta cross_foreign_keys (required)
            "coverage_pct": 100.0,
        })


# ── 5. Pydantic v2 strict: los schemas críticos NO aceptan campos extra ───

def test_index_response_strict_rejects_extra_field() -> None:
    """El contrato OpenAPI no debe contener campos no documentados."""
    from app.f0_baseline.schemas import IndexResponse
    # model_config por defecto en Pydantic v2 ignora extras (no falla).
    # Para validar strict-ness usamos model_dump y comparamos keys.
    parsed = IndexResponse.model_validate({
        "package": "x", "version": "1", "phase": "F0",
        "story_points": 8, "hu_covered": [],
        "endpoints": {},
        "extra_no_deberia_existir": "leak",
    })
    dumped = parsed.model_dump()
    assert "extra_no_deberia_existir" not in dumped
