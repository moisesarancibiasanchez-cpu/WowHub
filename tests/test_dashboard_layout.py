"""HU_34 — Tests del layout personalizable del dashboard (GridStack).

Cubre los 4 tests mínimos del DoD:

  1. test_default_layout_when_no_saved
     GET /api/v1/dashboard/layout sin layout previo → devuelve default
     de 4 widgets, con ``is_default=True``.
  2. test_save_layout
     PUT /api/v1/dashboard/layout con un array de widgets → persiste
     la fila en ``dashboard_layouts`` y devuelve ``is_default=False``.
  3. test_get_layout_returns_saved
     Después de un PUT, un nuevo GET devuelve los widgets guardados
     (no el default).
  4. test_get_layout_no_auth_401
     GET sin Authorization → 401/403 (UnauthorizedError del guard
     ``get_current_user``).

Los tests son DB-aware: usan las fixtures ``client`` (TestClient de
FastAPI con DB SQLite en memoria) y ``db_session`` del conftest
existente. NO tocan ``tests/conftest.py``.

Para crear el owner + tenant + membresía usamos ``/api/v1/auth/register``
(igual que el resto de tests del repo).
"""
from __future__ import annotations

import pytest


# ── Helpers ──────────────────────────────────────────────────────────────
def _register_with_tenant(client, slug: str = "hu34-test") -> dict:
    """Crea un owner + tenant y devuelve el JSON del registro.

    Devuelve un dict con al menos:
        - ``access_token`` (str)
        - ``current_tenant.tenant_id`` (str, UUID)
    """
    r = client.post("/api/v1/auth/register", json={
        "email": f"{slug}@example.com",
        "password": "test1234",
        "full_name": "HU34 Tester",
        "create_tenant": True,
        "tenant_legal_name": f"HU34 Test {slug}",
        "tenant_slug": slug,
    })
    assert r.status_code in (200, 201), f"register falló: {r.status_code} {r.text}"
    return r.json()


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ── 1. GET sin layout previo → default ──────────────────────────────────
def test_default_layout_when_no_saved(client):
    """GET /api/v1/dashboard/layout sin fila previa devuelve default 4 widgets."""
    data = _register_with_tenant(client, slug="hu34-default")
    token = data["access_token"]
    tid = data["current_tenant"]["tenant_id"]

    r = client.get("/api/v1/dashboard/layout", headers=_headers(token))
    assert r.status_code == 200, r.text
    body = r.json()

    # Estructura básica de la respuesta.
    assert body["tenant_id"] == tid
    assert body["is_default"] is True
    assert "widgets" in body and isinstance(body["widgets"], list)
    # FIX 2026-10-03: el default de HU_34 ahora trae 10 widgets
    # (post-refactor dashboard), no los 4 originales.
    assert len(body["widgets"]) == 10

    # Geometría: los 10 widgets default actuales del dashboard real.
    expected_types = {
        "ai_brief", "metrics", "orders", "opportunities", "products",
        "performance", "activity", "ai_bar", "public_url", "cta_widgets",
    }
    types = {w["type"] for w in body["widgets"]}
    assert types == expected_types

    # Cada widget tiene los 6 campos del contrato GridStack.
    for w in body["widgets"]:
        assert {"id", "x", "y", "w", "h", "type"} <= set(w.keys())


# ── 2. PUT persiste un layout custom ────────────────────────────────────
def test_save_layout(client, db_session):
    """PUT /api/v1/dashboard/layout guarda la fila en dashboard_layouts."""
    data = _register_with_tenant(client, slug="hu34-save")
    token = data["access_token"]
    tid = data["current_tenant"]["tenant_id"]

    payload = {
        "widgets": [
            # FIX 2026-10-04 — Migración de tipos legacy.
            # ANTES el test usaba 'stats' y 'ai' (tipos placeholder pre-HU_34).
            # Como _load_or_default ahora normaliza 'stats'→'metrics' y
            # 'ai'→'ai_brief' en lectura, el round-trip PUT→GET refleja los
            # nuevos nombres. Usamos los legacy para verificar que la
            # normalización funciona, y luego assertamos los nombres nuevos.
            {"id": "stats",    "x": 0, "y": 0, "w": 6, "h": 2, "type": "stats"},
            {"id": "orders",   "x": 6, "y": 0, "w": 6, "h": 3, "type": "orders"},
            {"id": "products", "x": 0, "y": 2, "w": 6, "h": 3, "type": "products"},
            {"id": "ai",       "x": 6, "y": 3, "w": 6, "h": 2, "type": "ai"},
        ]
    }

    r = client.put(
        "/api/v1/dashboard/layout",
        json=payload,
        headers=_headers(token),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["is_default"] is False
    assert body["tenant_id"] == tid
    assert len(body["widgets"]) == 4
    # El primer widget refleja la posición custom enviada.
    assert body["widgets"][0]["x"] == 0
    assert body["widgets"][0]["w"] == 6
    # FIX 2026-10-04 — El PUT persiste los nombres legacy ('stats', 'ai')
    # tal cual. La normalización al namespace nuevo (metrics, ai_brief)
    # solo aplica en LECTURA (GET). Ver test_get_layout_returns_saved.
    assert body["widgets"][0]["type"] == "stats"
    assert body["widgets"][3]["type"] == "ai"

    # La fila quedó persistida en la DB.
    from app.models.dashboard import DashboardLayout
    row = (
        db_session.query(DashboardLayout)
        .filter(DashboardLayout.tenant_id == tid)
        .one_or_none()
    )
    assert row is not None, "PUT no creó la fila en dashboard_layouts"
    assert isinstance(row.layout_json, list)
    assert len(row.layout_json) == 4
    assert row.layout_json[0]["type"] == "stats"


# ── 3. GET después de PUT devuelve lo guardado ─────────────────────────
def test_get_layout_returns_saved(client):
    """GET tras un PUT devuelve los widgets guardados (no el default)."""
    data = _register_with_tenant(client, slug="hu34-get")
    token = data["access_token"]
    tid = data["current_tenant"]["tenant_id"]

    # Layout custom: invertimos el orden (ai primero) y usamos tamaños distintos.
    custom = [
        {"id": "ai",       "x": 0, "y": 0, "w": 12, "h": 1, "type": "ai"},
        {"id": "stats",    "x": 0, "y": 1, "w": 3,  "h": 2, "type": "stats"},
        {"id": "orders",   "x": 3, "y": 1, "w": 5,  "h": 4, "type": "orders"},
        {"id": "products", "x": 8, "y": 1, "w": 4,  "h": 4, "type": "products"},
    ]
    r = client.put(
        "/api/v1/dashboard/layout",
        json={"widgets": custom},
        headers=_headers(token),
    )
    assert r.status_code == 200, r.text

    # GET → debe devolver lo que guardamos, con is_default=False.
    r2 = client.get("/api/v1/dashboard/layout", headers=_headers(token))
    assert r2.status_code == 200, r2.text
    body = r2.json()
    assert body["tenant_id"] == tid
    assert body["is_default"] is False
    assert len(body["widgets"]) == 4

    # El orden lo define GridStack; validamos contenido y geometría.
    by_id = {w["id"]: w for w in body["widgets"]}
    assert set(by_id.keys()) == {"ai", "stats", "orders", "products"}
    assert by_id["ai"]["w"] == 12
    assert by_id["ai"]["h"] == 1
    assert by_id["orders"]["w"] == 5
    assert by_id["orders"]["h"] == 4
    # FIX 2026-10-04 — Tipos legacy normalizados en lectura.
    # 'stats' → 'metrics', 'ai' → 'ai_brief'.
    assert by_id["stats"]["type"] == "metrics"
    assert by_id["ai"]["type"] == "ai_brief"
    assert by_id["products"]["type"] == "products"
    assert by_id["orders"]["type"] == "orders"

    # updated_at queda seteado.
    assert body["updated_at"] is not None


# ── 4. GET sin Authorization → 401/403 ─────────────────────────────────
def test_get_layout_no_auth_401(client):
    """GET sin Authorization devuelve 401 (UnauthorizedError)."""
    # No llamamos _register_with_tenant — sólo necesitamos el endpoint pelado.
    r = client.get("/api/v1/dashboard/layout")
    # FastAPI/Starlette puede devolver 401 (UnauthorizedError -> 401) o
    # 403 según el guard que se dispare primero. Aceptamos ambos códigos
    # como "no autorizado".
    assert r.status_code in (401, 403), (
        f"esperaba 401/403 sin auth, recibí {r.status_code} {r.text}"
    )