"""Tests del router F0 (HU_01/02/03 endpoints).

Los endpoints F0 leen artefactos cacheados en ``reports/f0_baseline/``.
Este módulo de tests pre-genera esos artefactos (en una ``tmp_path``)
apuntando el ``REPORTS_DIR`` del router ahí, de modo que los tests
verifican contenido real — no aceptan 404 como "válido".
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


# Pre-generar los artefactos ANTES de importar la app (que importa el router
# al instanciarse y congela REPORTS_DIR en el módulo).
@pytest.fixture(scope="module")
def reports_dir(tmp_path_factory) -> Path:
    d = tmp_path_factory.mktemp("f0_reports")
    # HU_01
    (d / "window-functions.json").write_text(
        json.dumps(
            {
                "html": "demo.html",
                "total": 5,
                "elapsed_ms": 7,
                "rows": [
                    {"n": 1, "name": "demo_func_01", "module": "DEMO",
                     "line": 1, "description": "ok"}
                ],
                "markdown": "# demo",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    # HU_02
    (d / "mapping.json").write_text(
        json.dumps(
            {
                "stats": {
                    "keys_in_html": 1,
                    "models": 1,
                    "models_with_tenant_id": 1,
                    "cross_foreign_keys": 0,
                    "coverage_pct": 100.0,
                },
                "mapping": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    # HU_03
    (d / "migrations.json").write_text(
        json.dumps(
            {
                "hu": "HU_03",
                "result": {
                    "alembic_dir_exists": False,
                    "alembic_upgrade": "n/a (no alembic/ en el proyecto)",
                    "pytest": "1 passed",
                    "pytest_collected": 1,
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
    # Redirigir REPORTS_DIR del router al tmp_path antes de instanciar el cliente.
    # `_read_json` lee REPORTS_DIR en cada request, así que el patch funciona
    # aunque la app ya esté construida.
    import app.f0_baseline.router as router_mod
    router_mod.REPORTS_DIR = reports_dir
    from app.main import app
    return TestClient(app)


def test_router_index(client: TestClient) -> None:
    r = client.get("/f0/")
    assert r.status_code == 200
    body = r.json()
    assert body["package"] == "app.f0_baseline"
    assert "HU_01" in body["hu_covered"]
    assert "HU_02" in body["hu_covered"]
    assert "HU_03" in body["hu_covered"]
    assert body["story_points"] == 8


def test_router_health(client: TestClient) -> None:
    r = client.get("/f0/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"


def test_router_hu01_returns_payload(client: TestClient) -> None:
    r = client.get("/f0/hu01")
    assert r.status_code == 200, (
        "El endpoint /f0/hu01 debe devolver 200 cuando el artefacto "
        "window-functions.json existe (los tests lo pre-generan en tmp_path)."
    )
    body = r.json()
    assert body["hu"] == "HU_01"
    assert "result" in body
    assert "total_functions" in body["result"]
    assert body["result"]["total_functions"] == 5
    # Los módulos deben venir ordenados
    assert body["result"]["modules"] == ["DEMO"]


def test_router_hu02_returns_payload(client: TestClient) -> None:
    r = client.get("/f0/hu02")
    assert r.status_code == 200, (
        "El endpoint /f0/hu02 debe devolver 200 cuando el artefacto "
        "mapping.json existe."
    )
    body = r.json()
    assert body["hu"] == "HU_02"
    assert body["result"]["coverage_pct"] == 100.0
    assert body["result"]["keys_in_html"] == 1


def test_router_hu03_returns_cached_report(client: TestClient) -> None:
    r = client.get("/f0/hu03")
    assert r.status_code == 200
    body = r.json()
    assert body["hu"] == "HU_03"
    assert "result" in body
    # El artefacto cacheado debe tener todos los campos esperados.
    assert "alembic_dir_exists" in body["result"]
    assert "models_loaded" in body["result"]
    assert "pytest_collected" in body["result"]


def test_router_hu03_live_runs_subprocess(client: TestClient, monkeypatch) -> None:
    """El parámetro ?live=true debe invocar ``build_report``.

    Mockeamos ``build_report`` para no spawnear pytest recursivamente
    (deadlock: pytest ya está corriendo cuando el test ejecuta el endpoint).
    """
    from app.f0_baseline import hu03
    monkeypatch.setattr(
        hu03, "build_report",
        lambda: {"alembic_dir_exists": False, "pytest": "mocked", "models_loaded": 0},
    )
    r = client.get("/f0/hu03?live=true")
    assert r.status_code == 200
    body = r.json()
    assert body["hu"] == "HU_03"
    # En modo live con el mock, el campo pytest debe venir del mock.
    assert body["result"]["pytest"] == "mocked"
    assert "alembic_dir_exists" in body["result"]

