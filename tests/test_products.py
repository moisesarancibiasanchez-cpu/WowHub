"""Tests de productos y catálogo público."""
import pytest


def _bootstrap(client, slug="test-co"):
    r = client.post("/api/v1/auth/register", json={
        "email": f"{slug}@e.com", "password": "test1234", "full_name": "Test User",
        "create_tenant": True,
        "tenant_legal_name": f"Test {slug}", "tenant_slug": slug,
    })
    return r.json()


def test_create_and_list_products(client):
    auth = _bootstrap(client, "shop1")
    token = auth["access_token"]
    tid = auth["current_tenant"]["tenant_id"]

    r = client.post(f"/api/v1/tenants/{tid}/products", json={
        "sku": "P-1", "name": "Café", "slug": "cafe", "price_cents": 2500, "status": "active",
    }, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 201, r.text
    assert r.json()["on_sale"] is False
    assert r.json()["discount_pct"] is None

    # List
    r = client.get(f"/api/v1/tenants/{tid}/products", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 1
    assert data["items"][0]["sku"] == "P-1"


def test_product_with_compare_price_shows_discount(client):
    auth = _bootstrap(client, "shop2")
    token = auth["access_token"]
    tid = auth["current_tenant"]["tenant_id"]

    r = client.post(f"/api/v1/tenants/{tid}/products", json={
        "sku": "P-2", "name": "Café Promo", "slug": "cafe-promo",
        "price_cents": 2000, "compare_at_cents": 2500, "status": "active",
    }, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 201
    p = r.json()
    assert p["on_sale"] is True
    assert p["discount_pct"] == 20


def test_product_compare_price_must_be_gte(client):
    auth = _bootstrap(client, "shop3")
    token = auth["access_token"]
    tid = auth["current_tenant"]["tenant_id"]

    r = client.post(f"/api/v1/tenants/{tid}/products", json={
        "sku": "P-3", "name": "X", "slug": "x",
        "price_cents": 3000, "compare_at_cents": 2500,  # invalid
    }, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 422


def test_product_unique_sku_per_tenant(client):
    auth = _bootstrap(client, "shop4")
    token = auth["access_token"]
    tid = auth["current_tenant"]["tenant_id"]
    body = {"sku": "UNIQ-1", "name": "Test Product", "slug": "test-prod-1", "price_cents": 100}
    r1 = client.post(f"/api/v1/tenants/{tid}/products", json=body, headers={"Authorization": f"Bearer {token}"})
    assert r1.status_code == 201
    r2 = client.post(f"/api/v1/tenants/{tid}/products", json={**body, "slug": "test-prod-2"}, headers={"Authorization": f"Bearer {token}"})
    assert r2.status_code == 409


def test_public_catalog_no_auth(client):
    auth = _bootstrap(client, "shop-public")
    token = auth["access_token"]
    tid = auth["current_tenant"]["tenant_id"]
    # Create active product
    client.post(f"/api/v1/tenants/{tid}/products", json={
        "sku": "PUB-1", "name": "Visible", "slug": "visible",
        "price_cents": 1000, "status": "active",
    }, headers={"Authorization": f"Bearer {token}"})
    # Public catalog (no auth)
    r = client.get(f"/api/v1/public/t/shop-public/catalog")
    assert r.status_code == 200
    items = r.json()["items"]
    assert any(p["sku"] == "PUB-1" for p in items)


def test_public_catalog_excludes_drafts(client):
    auth = _bootstrap(client, "shop-mix")
    token = auth["access_token"]
    tid = auth["current_tenant"]["tenant_id"]
    # active
    client.post(f"/api/v1/tenants/{tid}/products", json={
        "sku": "ACT-1", "name": "Active Product", "slug": "active-prod", "price_cents": 100, "status": "active",
    }, headers={"Authorization": f"Bearer {token}"})
    # draft
    client.post(f"/api/v1/tenants/{tid}/products", json={
        "sku": "DRF-1", "name": "Draft Product", "slug": "draft-prod", "price_cents": 100, "status": "draft",
    }, headers={"Authorization": f"Bearer {token}"})
    r = client.get(f"/api/v1/public/t/shop-mix/catalog")
    items = r.json()["items"]
    skus = [p["sku"] for p in items]
    assert "ACT-1" in skus
    assert "DRF-1" not in skus
