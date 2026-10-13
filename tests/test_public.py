"""Tests de endpoints públicos."""
import pytest


def _bootstrap(client, slug="pub"):
    r = client.post("/api/v1/auth/register", json={
        "email": f"{slug}@e.com", "password": "test1234", "full_name": "Test User",
        "create_tenant": True,
        "tenant_legal_name": f"Test {slug}", "tenant_slug": slug,
    })
    return r.json()


def test_public_profile(client):
    _bootstrap(client, "profile-co")
    r = client.get("/api/v1/public/t/profile-co/profile")
    assert r.status_code == 200
    data = r.json()
    assert data["slug"] == "profile-co"
    assert data["display_name"]


def test_public_profile_inactive_tenant_returns_404(client):
    auth = _bootstrap(client, "inactive-co")
    # suspender tenant
    token = auth["access_token"]
    tid = auth["current_tenant"]["tenant_id"]
    client.patch(f"/api/v1/tenants/{tid}", json={"is_active": False}, headers={"Authorization": f"Bearer {token}"})
    r = client.get("/api/v1/public/t/inactive-co/profile")
    assert r.status_code == 404


def test_public_unknown_tenant_returns_404(client):
    r = client.get("/api/v1/public/t/no-existe/profile")
    assert r.status_code == 404


def test_public_categories(client):
    auth = _bootstrap(client, "cat-co")
    token = auth["access_token"]
    tid = auth["current_tenant"]["tenant_id"]
    client.post(f"/api/v1/tenants/{tid}/categories", json={
        "name": "Cafés", "slug": "cafes",
    }, headers={"Authorization": f"Bearer {token}"})
    r = client.get("/api/v1/public/t/cat-co/categories")
    assert r.status_code == 200
    assert any(c["slug"] == "cafes" for c in r.json())


def test_public_promotions_filters_inactive(client):
    auth = _bootstrap(client, "promo-pub")
    token = auth["access_token"]
    tid = auth["current_tenant"]["tenant_id"]
    # promo activa
    client.post(f"/api/v1/tenants/{tid}/promotions", json={
        "name": "ON", "promo_type": "percent", "discount_type": "percent",
        "discount_value": 10, "is_active": True, "is_public": True,
    }, headers={"Authorization": f"Bearer {token}"})
    # promo pausada
    client.post(f"/api/v1/tenants/{tid}/promotions", json={
        "name": "OFF", "promo_type": "percent", "discount_type": "percent",
        "discount_value": 10, "is_active": False, "is_public": True,
    }, headers={"Authorization": f"Bearer {token}"})
    r = client.get("/api/v1/public/t/promo-pub/promotions")
    names = [p["name"] for p in r.json()]
    assert "ON" in names
    assert "OFF" not in names
