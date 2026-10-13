"""Tests de tenants y multi-tenancy."""
import pytest


def _register_with_tenant(client, slug, email="u@e.com", name="Test User"):
    r = client.post("/api/v1/auth/register", json={
        "email": email, "password": "test1234", "full_name": name,
        "create_tenant": True,
        "tenant_legal_name": f"Test {slug}", "tenant_slug": slug,
    })
    return r.json()


def test_create_tenant(client):
    r = client.post("/api/v1/auth/register", json={
        "email": "a@b.com", "password": "test1234", "full_name": "Test User A",
    })
    token = r.json()["access_token"]
    r = client.post("/api/v1/tenants", json={
        "legal_name": "Mi Negocio SpA",
        "display_name": "Mi Negocio",
        "slug": "mi-negocio",
    }, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 201, r.text
    assert r.json()["slug"] == "mi-negocio"


def test_tenant_slug_unique(client):
    _register_with_tenant(client, slug="dup", email="a@b.com")
    # second user tries to create another tenant with same slug
    r2 = client.post("/api/v1/auth/register", json={
        "email": "c@d.com", "password": "test1234", "full_name": "Test User C",
    })
    token2 = r2.json()["access_token"]
    r = client.post("/api/v1/tenants", json={
        "legal_name": "Otro", "display_name": "Otro", "slug": "dup",
    }, headers={"Authorization": f"Bearer {token2}"})
    assert r.status_code == 409


def test_tenant_slug_format(client):
    r = client.post("/api/v1/auth/register", json={
        "email": "a@b.com", "password": "test1234", "full_name": "Test User A",
    })
    token = r.json()["access_token"]
    # MAYUSCULAS debe normalizarse a "mayusculas" (lowercase) y aceptarse (201)
    r = client.post("/api/v1/tenants", json={
        "legal_name": "X SpA", "display_name": "X Display", "slug": "MAYUSCULAS",
    }, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 201, r.text
    assert r.json()["slug"] == "mayusculas"

    # "Mas Redes" (con espacio) debe normalizarse a "mas-redes"
    r = client.post("/api/v1/tenants", json={
        "legal_name": "Y SpA", "display_name": "Y Display", "slug": "Mas Redes",
    }, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 201, r.text
    assert r.json()["slug"] == "mas-redes"

    # slug vacío tras normalizar (solo caracteres no permitidos) debe rechazarse
    r = client.post("/api/v1/tenants", json={
        "legal_name": "Z SpA", "display_name": "Z Display", "slug": "@@@",
    }, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 422

    # slug demasiado corto debe rechazarse
    r = client.post("/api/v1/tenants", json={
        "legal_name": "W SpA", "display_name": "W Display", "slug": "ab",
    }, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 422


def test_multi_tenant_isolation(client):
    """Un user de un tenant no puede acceder a datos de otro tenant."""
    # Crear user A con tenant A
    data_a = _register_with_tenant(client, slug="tenant-a", email="a@b.com")
    token_a = data_a["access_token"]
    tenant_a_id = data_a["current_tenant"]["tenant_id"]

    # User A crea un producto en su tenant
    r = client.post(f"/api/v1/tenants/{tenant_a_id}/products", json={
        "sku": "A-1", "name": "Prod A", "slug": "prod-a", "price_cents": 1000,
    }, headers={"Authorization": f"Bearer {token_a}"})
    assert r.status_code == 201

    # Crear user B sin acceso al tenant A
    r = client.post("/api/v1/auth/register", json={
        "email": "b@b.com", "password": "test1234", "full_name": "Test User B",
    })
    token_b = r.json()["access_token"]

    # User B intenta acceder al tenant A: 403
    r = client.get(f"/api/v1/tenants/{tenant_a_id}", headers={"Authorization": f"Bearer {token_b}"})
    assert r.status_code == 403
