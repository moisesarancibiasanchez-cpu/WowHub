# -*- coding: utf-8 -*-
"""HU_31 — Tests del endpoint de catálogo de reportes programables.

Cubre:
  - GET /api/v1/tenants/{tid}/reports devuelve los 3 reportes hardcoded.
  - La respuesta tiene la forma del schema (id/type/format/last_run_at/schedule).
  - Sin Authorization devuelve 401.
  - Con token válido del tenant la respuesta es 200 OK con la lista esperada.
"""
from __future__ import annotations

from typing import Tuple


# ── Helpers ─────────────────────────────────────────────────────────────
def _register_with_tenant(client, slug: str) -> dict:
    """Registra un usuario nuevo con su tenant (helper estándar de tests)."""
    r = client.post("/api/v1/auth/register", json={
        "email": f"{slug}@example.com",
        "password": "test1234",
        "full_name": "HU31 Tester",
        "create_tenant": True,
        "tenant_legal_name": f"HU31 Test {slug}",
        "tenant_slug": slug,
    })
    assert r.status_code in (200, 201), f"register falló: {r.status_code} {r.text}"
    return r.json()


def _bootstrap(client, slug: str) -> Tuple[str, str]:
    """Crea usuario + tenant y devuelve (token, tenant_id)."""
    data = _register_with_tenant(client, slug)
    token = data["access_token"]
    tid = data["current_tenant"]["tenant_id"]
    return token, tid


# ── 1. GET /reports sin auth → 401 ──────────────────────────────────────
def test_list_reports_requires_auth(client):
    """Sin Authorization el endpoint devuelve 401 (UnauthorizedError)."""
    # Primero necesitamos un tenant válido en la URL; usamos cualquier UUID.
    fake_tid = "00000000-0000-0000-0000-000000000000"
    r = client.get(f"/api/v1/tenants/{fake_tid}/reports")
    assert r.status_code == 401, r.text


# ── 2. GET /reports con auth devuelve catálogo completo ────────────────────
def test_list_reports_returns_catalog(client):
    """Devuelve 3 reportes con la forma y valores esperados."""
    token, tid = _bootstrap(client, slug="hu31-list")

    r = client.get(
        f"/api/v1/tenants/{tid}/reports",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    items = r.json()
    assert isinstance(items, list)
    assert len(items) == 3, f"esperaba 3 reportes, obtuve {len(items)}"

    # Validar la forma completa de cada item (schema ReportOut).
    expected_ids = {"sales-monthly", "customers-weekly", "inventory-daily"}
    seen_ids = set()
    for it in items:
        assert set(it.keys()) == {"id", "type", "format", "last_run_at", "schedule"}, it
        assert it["type"] in ("sales", "customers", "inventory"), it
        assert it["format"] in ("pdf", "csv"), it
        assert it["schedule"] in ("daily", "weekly", "monthly"), it
        # HU_31 mínimo: last_run_at es null hasta que se persistan ejecuciones.
        assert it["last_run_at"] is None, it
        seen_ids.add(it["id"])
    assert seen_ids == expected_ids


# ── 3. Smoke: respuesta es JSON parseable y contiene campos clave ───────
def test_list_reports_smoke_shape(client):
    """Smoke test — confirma que la respuesta es una lista JSON con campos clave."""
    token, tid = _bootstrap(client, slug="hu31-smoke")

    r = client.get(
        f"/api/v1/tenants/{tid}/reports",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/json")
    body = r.json()
    assert isinstance(body, list)
    assert all("id" in x and "schedule" in x for x in body)