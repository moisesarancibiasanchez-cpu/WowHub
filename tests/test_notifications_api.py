"""Tests de la API de notifications (Fase 5).

Cubre:
- GET /tenants/{tid}/notifications/summary — bell badge
- GET /tenants/{tid}/notifications         — lista con filtros
- Auth: requiere token + membresía
- Aislamiento entre tenants (no leak)
- Validación de filtros (severity/category)
- Edge cases: tenant sin datos, límite, formato

Estrategia: usar el bootstrap de test_notifications.py (mismo patrón de
`_make_tenant`, `_make_business_costs`, `_make_product`) y consumir la
API vía TestClient. Esto valida el contrato HTTP completo (Pydantic +
routing + motor).
"""
from __future__ import annotations

import uuid as _uuid

import pytest


# ── Bootstrap helpers (idénticos a test_notifications.py) ────────
def _make_tenant(db, slug: str | None = None):
    from app.models.tenant import Tenant
    t = Tenant(
        id=_uuid.uuid4(),
        slug=slug or f"t-{_uuid.uuid4().hex[:8]}",
        legal_name="Test",
        display_name="Test",
        currency="CLP",
        is_active=True,
    )
    db.add(t)
    db.flush()
    return t


def _make_business_costs(db, tenant_id: str, *, cost_hour_cents: int = 0,
                          target_margin_pct: int = 30, version: int = 1,
                          productive_hours: int = 160, rent_cents: int = 0):
    from app.models.business_costs import BusinessCosts
    bc = BusinessCosts(
        tenant_id=tenant_id,
        owner_salary_cents=0, workers_salary_cents=0,
        productive_hours_per_month=productive_hours,
        target_margin_pct=target_margin_pct,
        rent_cents=rent_cents, electricity_cents=0, water_cents=0, gas_cents=0,
        software_cents=0, advertising_cents=0, payment_commission_cents=0,
        packaging_cents=0, maintenance_cents=0, depreciation_cents=0,
        waste_pct=0, is_na={},
        total_fixed_cents=rent_cents,
        cost_hour_cents=cost_hour_cents,
        version=version,
    )
    db.add(bc)
    db.commit()  # commit para que la API (otra sesión) lo vea
    return bc


def _make_product(db, tenant_id: str, *, name="Prod", price_cents=5000,
                   cost_cents=1000, production_time_min=10, stock=10,
                   low_stock_threshold=5, track_inventory=False, status="active"):
    from app.models.product import Product, ProductStatus
    p = Product(
        id=str(_uuid.uuid4()),
        tenant_id=tenant_id,
        name=name,
        sku=f"sku-{_uuid.uuid4().hex[:6]}",
        slug=f"slug-{_uuid.uuid4().hex[:6]}",
        price_cents=price_cents,
        cost_cents=cost_cents,
        production_time_min=production_time_min,
        stock=stock,
        low_stock_threshold=low_stock_threshold,
        track_inventory=track_inventory,
        status=ProductStatus.ACTIVE if status == "active" else ProductStatus.ARCHIVED,
    )
    db.add(p)
    db.commit()  # commit para que la API (otra sesión) lo vea
    return p


# ── Auth helpers ────────────────────────────────────────────────
def _register_with_tenant(client, slug: str, email: str = "u@e.com"):
    r = client.post("/api/v1/auth/register", json={
        "email": email, "password": "test1234", "full_name": "Test",
        "create_tenant": True,
        "tenant_legal_name": f"Test {slug}", "tenant_slug": slug,
    })
    assert r.status_code in (200, 201), r.text
    return r.json()


def _bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ───────────────────────────────────────────────
# Tests
# ───────────────────────────────────────────────

def test_summary_requires_auth(client):
    """Sin token, el endpoint debe responder 401/403."""
    r = client.get("/api/v1/tenants/00000000-0000-0000-0000-000000000000/notifications/summary")
    assert r.status_code in (401, 403), r.text


def test_summary_empty_tenant(client, db_session):
    """Tenant recién creado: N9 (welcome) siempre aparece (< 24h).
    N7 (costs sin configurar) también aparece porque BusinessCosts no existe.
    Conteos por severidad/categoría deben sumar el total exacto.
    """
    data = _register_with_tenant(client, slug="empty-tenant", email="e@e.com")
    tid = data["current_tenant"]["tenant_id"]
    token = data["access_token"]

    r = client.get(
        f"/api/v1/tenants/{tid}/notifications/summary",
        headers=_bearer(token),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    # Conteos coherentes
    assert sum(body["by_severity"].values()) == body["total"]
    assert sum(body["by_category"].values()) == body["total"]
    # Al menos N9 (welcome) debe aparecer
    assert body["by_category"].get("system", 0) >= 1
    assert body["top_3"]  # no vacío
    assert len(body["top_3"]) <= 3
    assert "generated_at" in body


def test_summary_with_notifications(client, db_session):
    """Tenant con Costos sin configurar (version=1) + stock bajo → 2 notifs."""
    data = _register_with_tenant(client, slug="with-notifs", email="w@e.com")
    tid = data["current_tenant"]["tenant_id"]
    token = data["access_token"]

    # N7 — Costos sin configurar (siempre aparece cuando version=1)
    _make_business_costs(db_session, tid, cost_hour_cents=0, version=1)
    # N5 — Stock bajo (track_inventory=True, stock<=threshold)
    _make_product(
        db_session, tid, name="Item A", price_cents=5000,
        track_inventory=True, stock=2, low_stock_threshold=5,
    )

    r = client.get(
        f"/api/v1/tenants/{tid}/notifications/summary",
        headers=_bearer(token),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["total"] >= 2
    # Los conteos por severidad suman el total
    assert sum(body["by_severity"].values()) == body["total"]
    assert sum(body["by_category"].values()) == body["total"]
    # top_3 nunca tiene más de 3 items
    assert len(body["top_3"]) <= 3
    # Cada item del top_3 respeta el schema
    for n in body["top_3"]:
        assert {"id", "severity", "category", "title", "body",
                "action_label", "action_url", "entity_type", "entity_id",
                "detected_at"}.issubset(n.keys())


def test_summary_top3_ordered_by_severity(client, db_session):
    """top_3 debe estar ordenado: critical > warning > info."""
    data = _register_with_tenant(client, slug="order-test", email="o@e.com")
    tid = data["current_tenant"]["tenant_id"]
    token = data["access_token"]

    # Generamos 1 critical (N4 out_of_stock) + 1 info (N7 costs)
    _make_business_costs(db_session, tid, cost_hour_cents=0, version=1)
    _make_product(
        db_session, tid, name="Critical", price_cents=5000,
        track_inventory=True, stock=0, low_stock_threshold=5,
    )

    r = client.get(
        f"/api/v1/tenants/{tid}/notifications/summary",
        headers=_bearer(token),
    )
    body = r.json()
    severities = [n["severity"] for n in body["top_3"]]
    # critical debe estar antes que info
    if "critical" in severities and "info" in severities:
        assert severities.index("critical") < severities.index("info")


def test_list_notifications_default(client, db_session):
    """GET /notifications sin filtros devuelve todas las notifs del tenant."""
    data = _register_with_tenant(client, slug="list-default", email="l@e.com")
    tid = data["current_tenant"]["tenant_id"]
    token = data["access_token"]

    _make_business_costs(db_session, tid, version=1)  # N7 info

    r = client.get(
        f"/api/v1/tenants/{tid}/notifications",
        headers=_bearer(token),
    )
    assert r.status_code == 200
    body = r.json()
    assert "items" in body
    assert "count" in body
    assert "total_by_severity" in body
    assert "total_by_category" in body
    assert body["count"] == len(body["items"])


def test_list_notifications_filter_by_severity(client, db_session):
    """Filtro ?severity=critical devuelve solo critical."""
    data = _register_with_tenant(client, slug="filter-sev", email="f@e.com")
    tid = data["current_tenant"]["tenant_id"]
    token = data["access_token"]

    # 1 critical (sin stock) + 1 info (costos sin configurar)
    _make_business_costs(db_session, tid, version=1)
    _make_product(
        db_session, tid, name="Sin Stock", price_cents=5000,
        track_inventory=True, stock=0, low_stock_threshold=5,
    )

    r = client.get(
        f"/api/v1/tenants/{tid}/notifications",
        params={"severity": "critical"},
        headers=_bearer(token),
    )
    assert r.status_code == 200
    body = r.json()
    assert all(n["severity"] == "critical" for n in body["items"])


def test_list_notifications_filter_by_category(client, db_session):
    """Filtro ?category=inventory devuelve solo inventory."""
    data = _register_with_tenant(client, slug="filter-cat", email="c@e.com")
    tid = data["current_tenant"]["tenant_id"]
    token = data["access_token"]

    _make_business_costs(db_session, tid, version=1)  # category=costs
    _make_product(
        db_session, tid, name="Low Stock", price_cents=5000,
        track_inventory=True, stock=1, low_stock_threshold=5,
    )  # category=inventory

    r = client.get(
        f"/api/v1/tenants/{tid}/notifications",
        params={"category": "inventory"},
        headers=_bearer(token),
    )
    assert r.status_code == 200
    body = r.json()
    assert all(n["category"] == "inventory" for n in body["items"])
    assert body["count"] >= 1


def test_list_notifications_invalid_filter(client, db_session):
    """severity inválido → 422 con detalle claro."""
    data = _register_with_tenant(client, slug="invalid-filter", email="i@e.com")
    tid = data["current_tenant"]["tenant_id"]
    token = data["access_token"]

    r = client.get(
        f"/api/v1/tenants/{tid}/notifications",
        params={"severity": "nuclear"},
        headers=_bearer(token),
    )
    assert r.status_code == 422
    assert "severity" in r.text.lower()


def test_list_notifications_limit_caps(client, db_session):
    """limit > 100 debe ser rechazado por la validación de Query."""
    data = _register_with_tenant(client, slug="limit-test", email="lt@e.com")
    tid = data["current_tenant"]["tenant_id"]
    token = data["access_token"]

    r = client.get(
        f"/api/v1/tenants/{tid}/notifications",
        params={"limit": 9999},
        headers=_bearer(token),
    )
    assert r.status_code == 422  # FastAPI rechaza por ge/le


def test_list_notifications_combined_filters(client, db_session):
    """Filtros severity + category se combinan (AND)."""
    data = _register_with_tenant(client, slug="combined", email="co@e.com")
    tid = data["current_tenant"]["tenant_id"]
    token = data["access_token"]

    _make_business_costs(db_session, tid, version=1)
    _make_product(
        db_session, tid, name="P", price_cents=5000,
        track_inventory=True, stock=0, low_stock_threshold=5,
    )

    # severity=critical AND category=inventory → debería matchear N4
    r = client.get(
        f"/api/v1/tenants/{tid}/notifications",
        params={"severity": "critical", "category": "inventory"},
        headers=_bearer(token),
    )
    assert r.status_code == 200
    body = r.json()
    for n in body["items"]:
        assert n["severity"] == "critical"
        assert n["category"] == "inventory"


def test_notifications_tenant_isolation(client, db_session):
    """Las notificaciones de un tenant NO deben leakear a otro tenant."""
    data_a = _register_with_tenant(client, slug="iso-a", email="ia@e.com")
    data_b = _register_with_tenant(client, slug="iso-b", email="ib@e.com")
    tid_a = data_a["current_tenant"]["tenant_id"]
    tid_b = data_b["current_tenant"]["tenant_id"]
    token_a = data_a["access_token"]
    token_b = data_b["access_token"]

    # Solo A tiene Costos sin configurar (N7 — category=costs)
    _make_business_costs(db_session, tid_a, version=1)
    _make_business_costs(db_session, tid_b, version=2)  # B tiene costos OK

    r_a = client.get(
        f"/api/v1/tenants/{tid_a}/notifications",
        headers=_bearer(token_a),
    )
    r_b = client.get(
        f"/api/v1/tenants/{tid_b}/notifications",
        headers=_bearer(token_b),
    )
    assert r_a.status_code == 200
    assert r_b.status_code == 200
    # A tiene al menos N7 (costs)
    a_categories = {n["category"] for n in r_a.json()["items"]}
    assert "costs" in a_categories
    # B NO debe tener N7 (porque tiene version=2), aunque puede tener N9 (welcome)
    b_categories = {n["category"] for n in r_b.json()["items"]}
    assert "costs" not in b_categories


def test_notifications_cross_tenant_forbidden(client, db_session):
    """User A no puede leer notifications del tenant B (403)."""
    data_a = _register_with_tenant(client, slug="forbid-a", email="fa@e.com")
    data_b = _register_with_tenant(client, slug="forbid-b", email="fb@e.com")
    tid_b = data_b["current_tenant"]["tenant_id"]
    token_a = data_a["access_token"]

    r = client.get(
        f"/api/v1/tenants/{tid_b}/notifications",
        headers=_bearer(token_a),
    )
    # 403 Forbidden porque A no es miembro de B
    assert r.status_code == 403, r.text
