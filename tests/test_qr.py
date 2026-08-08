"""Tests de QR codes."""
import pytest


def _bootstrap(client, slug="qr-co"):
    r = client.post("/api/v1/auth/register", json={
        "email": f"{slug}@e.com", "password": "test1234", "full_name": "Test User",
        "create_tenant": True,
        "tenant_legal_name": f"Test {slug}", "tenant_slug": slug,
    })
    return r.json()


def test_create_qr_returns_short_code_and_image(client):
    auth = _bootstrap(client, "qr-shop")
    token = auth["access_token"]
    tid = auth["current_tenant"]["tenant_id"]

    r = client.post(f"/api/v1/tenants/{tid}/qrs", json={
        "label": "Mesa 1", "target_type": "catalog",
    }, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 201
    data = r.json()
    assert data["short_code"]
    assert data["qr_image_data_url"].startswith("data:image/png;base64,")
    assert data["full_url"].endswith(f"/r/{data['short_code']}")


def test_qr_short_codes_unique(client):
    auth = _bootstrap(client, "qr-uniq")
    token = auth["access_token"]
    tid = auth["current_tenant"]["tenant_id"]
    codes = set()
    for i in range(5):
        r = client.post(f"/api/v1/tenants/{tid}/qrs", json={
            "label": f"Mesa {i}", "target_type": "catalog",
        }, headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 201
        codes.add(r.json()["short_code"])
    assert len(codes) == 5  # todos únicos


def test_qr_redirect_resolves_to_public_catalog(client):
    auth = _bootstrap(client, "qr-redir")
    token = auth["access_token"]
    tid = auth["current_tenant"]["tenant_id"]

    # Crear producto y QR
    client.post(f"/api/v1/tenants/{tid}/products", json={
        "sku": "QR-P", "name": "X", "slug": "x", "price_cents": 100, "status": "active",
    }, headers={"Authorization": f"Bearer {token}"})
    r = client.post(f"/api/v1/tenants/{tid}/qrs", json={
        "label": "Mesa", "target_type": "catalog",
    }, headers={"Authorization": f"Bearer {token}"})
    short_code = r.json()["short_code"]

    # Acceder al redirect
    r = client.get(f"/r/{short_code}", follow_redirects=False)
    assert r.status_code == 302
    assert "/u/qr-redir/catalogo" in r.headers["location"]


def test_qr_redirect_increments_scan_count(client):
    auth = _bootstrap(client, "qr-scan")
    token = auth["access_token"]
    tid = auth["current_tenant"]["tenant_id"]
    r = client.post(f"/api/v1/tenants/{tid}/qrs", json={
        "label": "X", "target_type": "catalog",
    }, headers={"Authorization": f"Bearer {token}"})
    qr_id = r.json()["id"]
    short_code = r.json()["short_code"]

    # Scan 3 veces
    for _ in range(3):
        client.get(f"/r/{short_code}")

    r = client.get(f"/api/v1/tenants/{tid}/qrs/{qr_id}", headers={"Authorization": f"Bearer {token}"})
    assert r.json()["scan_count"] == 3
