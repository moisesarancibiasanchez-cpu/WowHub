"""Tests del router F0 (HU_01/02/03 endpoints)."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def _client() -> TestClient:
    return TestClient(app)


def test_router_index() -> None:
    c = _client()
    r = c.get("/f0/")
    assert r.status_code == 200
    body = r.json()
    assert body["package"] == "app.f0_baseline"
    assert "HU_01" in body["hu_covered"]
    assert "HU_02" in body["hu_covered"]
    assert "HU_03" in body["hu_covered"]
    assert body["story_points"] == 8


def test_router_health() -> None:
    c = _client()
    r = c.get("/f0/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"


def test_router_hu01_returns_404_or_payload() -> None:
    c = _client()
    r = c.get("/f0/hu01")
    # Si no se ha ejecutado el script, debe ser 404 con detalle.
    # Si se ejecutó, debe devolver un JSON con los datos del inventario.
    assert r.status_code in (200, 404)
    if r.status_code == 200:
        body = r.json()
        assert body["hu"] == "HU_01"
        assert "result" in body
        assert "total_functions" in body["result"]
    else:
        body = r.json()
        assert "detail" in body


def test_router_hu02_returns_404_or_payload() -> None:
    c = _client()
    r = c.get("/f0/hu02")
    assert r.status_code in (200, 404)
    if r.status_code == 200:
        body = r.json()
        assert body["hu"] == "HU_02"
        assert body["result"]["coverage_pct"] == 100.0


def test_router_hu03_returns_cached_or_note() -> None:
    """El endpoint /f0/hu03 devuelve el reporte cacheado (o un "note" si
    no se ha generado todavía). En tests NO se invoca la corrida en vivo
    porque pytest bloquea si la suite está en marcha."""
    c = _client()
    r = c.get("/f0/hu03")
    assert r.status_code == 200
    body = r.json()
    assert body["hu"] == "HU_03"
    assert "result" in body
    # Si está cacheado, debe tener alembic_dir_exists; si no, debe tener un "note".
    if "alembic_dir_exists" in body["result"]:
        assert "models_loaded" in body["result"]
    else:
        assert "note" in body["result"]
