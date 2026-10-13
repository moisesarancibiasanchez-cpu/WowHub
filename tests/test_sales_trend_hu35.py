"""HU_35 — Tests para el endpoint /sales-trend con presets y anomalías.

Cubre:
1. test_period_presets_available — endpoint acepta todos los presets
2. test_default_is_7d — sin parámetro usa '7d'
3. test_invalid_period_falls_back — período inválido no rompe (default a 7d)
4. test_back_compat_sales_7d — /sales-7d sigue funcionando
5. test_anomaly_detection_pure — _detect_anomalies función pura
"""
from __future__ import annotations

import pytest

from app.api.v1.analytics import _detect_anomalies, _PERIOD_PRESETS


# ── Tests unitarios de _detect_anomalies ─────────────────────────────────
def test_detect_anomalies_no_anomalies():
    """Serie uniforme → 0 anomalías."""
    values = [100, 110, 90, 105, 95, 100, 100]
    anomalies = _detect_anomalies(values)
    assert not any(anomalies), f"Expected no anomalies in uniform series, got {anomalies}"


def test_detect_anomalies_with_spike():
    """Serie con un spike → al menos 1 anomalía."""
    values = [100, 110, 90, 105, 95, 100, 100, 10_000]  # spike al final
    anomalies = _detect_anomalies(values)
    assert any(anomalies), f"Expected at least one anomaly for spike, got {anomalies}"
    # El último punto debería ser el anómalo.
    assert anomalies[-1] is True


def test_detect_anomalies_short_series():
    """Series con n<3 → no se detectan anomalías."""
    values = [100, 200]
    anomalies = _detect_anomalies(values)
    assert anomalies == [False, False]


def test_detect_anomalies_empty():
    """Serie vacía → todas False."""
    anomalies = _detect_anomalies([])
    assert anomalies == []


def test_detect_anomalies_constant():
    """Serie constante (std=0) → no detecta anomalías (evita división por cero)."""
    values = [100, 100, 100, 100, 100]
    anomalies = _detect_anomalies(values)
    assert anomalies == [False, False, False, False, False]


def test_period_presets_complete():
    """Los 6 presets requeridos están definidos."""
    expected = {"today", "7d", "14d", "30d", "90d", "1y"}
    assert set(_PERIOD_PRESETS.keys()) == expected
    # today=1 día, 1y=365 días
    assert _PERIOD_PRESETS["today"] == 1
    assert _PERIOD_PRESETS["1y"] == 365


# ── Tests de integración (requieren DB + tenant) ─────────────────────────
def _register_with_tenant(client, slug: str) -> dict:
    """Crea owner + tenant y devuelve dict con access_token y tenant_id."""
    r = client.post("/api/v1/auth/register", json={
        "email": f"{slug}@example.com",
        "password": "test1234",
        "full_name": "HU35 Tester",
        "create_tenant": True,
        "tenant_legal_name": f"HU35 Test {slug}",
        "tenant_slug": slug,
    })
    assert r.status_code in (200, 201), f"register falló: {r.status_code} {r.text}"
    return r.json()


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_sales_trend_default_7d(client):
    """Sin parámetro → período '7d' por default."""
    data = _register_with_tenant(client, slug="hu35-default")
    token = data["access_token"]
    tid = data["current_tenant"]["tenant_id"]

    r = client.get(
        f"/api/v1/tenants/{tid}/analytics/sales-trend",
        headers=_headers(token),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["period"] == "7d"
    assert body["window_days"] == 7
    assert len(body["series"]) == 7
    assert "comparison" in body
    assert "best_day" in body
    assert "anomalies_detected" in body


def test_sales_trend_period_30d(client):
    """Preset '30d' → 30 días de serie."""
    data = _register_with_tenant(client, slug="hu35-30d")
    token = data["access_token"]
    tid = data["current_tenant"]["tenant_id"]

    r = client.get(
        f"/api/v1/tenants/{tid}/analytics/sales-trend?period=30d",
        headers=_headers(token),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["period"] == "30d"
    assert body["window_days"] == 30
    assert len(body["series"]) == 30


def test_sales_trend_invalid_period_rejected(client):
    """Período inválido → 422 (Pydantic Literal valida estrictamente).

    NOTA: La validación Pydantic con ``Literal["today", "7d", ...]`` rechaza
    cualquier valor fuera del enum con 422 Unprocessable Entity. Esto es
    estricto y preferido — el cliente sabe inmediatamente que el valor es
    inválido en lugar de obtener un fallback silencioso a 7d.
    """
    data = _register_with_tenant(client, slug="hu35-invalid")
    token = data["access_token"]
    tid = data["current_tenant"]["tenant_id"]

    r = client.get(
        f"/api/v1/tenants/{tid}/analytics/sales-trend?period=invalid_period",
        headers=_headers(token),
    )
    assert r.status_code == 422, f"esperaba 422 (Literal invalid), recibí {r.status_code} {r.text}"
    body = r.json()
    # La respuesta debe mencionar el campo `period` y los valores esperados.
    assert "period" in str(body)


def test_sales_7d_back_compat(client):
    """/sales-7d sigue funcionando (back-compat con HU_30)."""
    data = _register_with_tenant(client, slug="hu35-backcompat")
    token = data["access_token"]
    tid = data["current_tenant"]["tenant_id"]

    r = client.get(
        f"/api/v1/tenants/{tid}/analytics/sales-7d",
        headers=_headers(token),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["period"] == "7d"
    assert body["window_days"] == 7
    assert len(body["series"]) == 7


def test_sales_trend_anomalies_disabled(client):
    """detect_anomalies=false → is_anomaly=False en todos."""
    data = _register_with_tenant(client, slug="hu35-noanom")
    token = data["access_token"]
    tid = data["current_tenant"]["tenant_id"]

    r = client.get(
        f"/api/v1/tenants/{tid}/analytics/sales-trend?period=7d&detect_anomalies=false",
        headers=_headers(token),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    for s in body["series"]:
        assert s["is_anomaly"] is False


def test_sales_trend_no_auth_401(client):
    """Sin Authorization → 401."""
    # No registramos — solo necesitamos el endpoint pelado.
    r = client.get("/api/v1/tenants/00000000-0000-0000-0000-000000000000/analytics/sales-trend")
    assert r.status_code in (401, 403), f"esperaba 401/403, recibí {r.status_code} {r.text}"