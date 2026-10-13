"""HU_12 — Tests de variantes y modificadores de producto.

Cubre:
  - POST/GET /products/{pid}/variants (crear + listar)
  - PATCH/DELETE /variants/{vid} (actualizar + soft delete)
  - POST/GET /products/{pid}/modifiers (crear modifier con opciones + listar)
"""
from __future__ import annotations


def _bootstrap(client, slug="var-co"):
    r = client.post("/api/v1/auth/register", json={
        "email": f"{slug}@e.com",
        "password": "test1234",
        "full_name": "Owner",
        "create_tenant": True,
        "tenant_legal_name": f"Variants {slug}",
        "tenant_slug": slug,
    })
    assert r.status_code == 201, r.text
    data = r.json()
    return data["access_token"], data["current_tenant"]["tenant_id"]


def _create_product(client, token, tid, **overrides):
    body = {
        "sku": "PVAR-1",
        "name": "Café",
        "slug": "cafe",
        "price_cents": 1000,
        "status": "active",
    }
    body.update(overrides)
    r = client.post(
        f"/api/v1/tenants/{tid}/products",
        json=body,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_create_variant_returns_201_and_id(client):
    token, tid = _bootstrap(client, "var-create")
    p = _create_product(client, token, tid)

    r = client.post(
        f"/api/v1/tenants/{tid}/products/{p['id']}/variants",
        json={
            "sku": "VAR-L",
            "name": "Grande",
            "price_cents": 1500,
            "stock": 10,
            "is_active": True,
            "sort_order": 1,
            "attributes": {"size": "L"},
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["id"]
    assert data["sku"] == "VAR-L"
    assert data["price_cents"] == 1500
    assert data["attributes"]["size"] == "L"


def test_list_variants_returns_created(client):
    token, tid = _bootstrap(client, "var-list")
    p = _create_product(client, token, tid)

    for i in range(3):
        r = client.post(
            f"/api/v1/tenants/{tid}/products/{p['id']}/variants",
            json={"sku": f"VAR-{i}", "name": f"Var {i}", "price_cents": 100 * (i + 1)},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 201

    r = client.get(
        f"/api/v1/tenants/{tid}/products/{p['id']}/variants",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    items = r.json()
    assert len(items) == 3
    skus = {it["sku"] for it in items}
    assert skus == {"VAR-0", "VAR-1", "VAR-2"}


def test_patch_variant_updates_fields(client):
    token, tid = _bootstrap(client, "var-patch")
    p = _create_product(client, token, tid)
    r = client.post(
        f"/api/v1/tenants/{tid}/products/{p['id']}/variants",
        json={"sku": "VAR-X", "name": "Old", "price_cents": 500},
        headers={"Authorization": f"Bearer {token}"},
    )
    vid = r.json()["id"]

    r = client.patch(
        f"/api/v1/tenants/{tid}/variants/{vid}",
        json={"name": "New name", "price_cents": 800},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "New name"
    assert r.json()["price_cents"] == 800


def test_delete_variant_is_soft_delete(client):
    """El DELETE deja is_active=False (preserva historial de order_items)."""
    token, tid = _bootstrap(client, "var-del")
    p = _create_product(client, token, tid)
    r = client.post(
        f"/api/v1/tenants/{tid}/products/{p['id']}/variants",
        json={"sku": "VAR-D", "name": "x", "price_cents": 1},
        headers={"Authorization": f"Bearer {token}"},
    )
    vid = r.json()["id"]

    r = client.delete(
        f"/api/v1/tenants/{tid}/variants/{vid}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 204

    # La variante sigue existiendo con is_active=False
    r = client.get(
        f"/api/v1/tenants/{tid}/products/{p['id']}/variants",
        headers={"Authorization": f"Bearer {token}"},
    )
    items = r.json()
    var = next(i for i in items if i["id"] == vid)
    assert var["is_active"] is False


def test_create_modifier_with_options_returns_nested(client):
    token, tid = _bootstrap(client, "mod-co")
    p = _create_product(client, token, tid)
    r = client.post(
        f"/api/v1/tenants/{tid}/products/{p['id']}/modifiers",
        json={
            "name": "Extras",
            "type": "multi",
            "required": False,
            "sort_order": 1,
            "options": [
                {"name": "Queso", "price_delta_cents": 200},
                {"name": "Bacon", "price_delta_cents": 350, "is_default": False},
            ],
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["name"] == "Extras"
    assert data["type"] == "multi"
    assert len(data["options"]) == 2
    assert data["options"][0]["name"] == "Queso"
    assert data["options"][1]["price_delta_cents"] == 350


def test_list_modifiers_returns_nested_options(client):
    token, tid = _bootstrap(client, "mod-list")
    p = _create_product(client, token, tid)
    for i in range(2):
        client.post(
            f"/api/v1/tenants/{tid}/products/{p['id']}/modifiers",
            json={
                "name": f"Mod{i}",
                "type": "single",
                "options": [{"name": "opt", "price_delta_cents": 0}],
            },
            headers={"Authorization": f"Bearer {token}"},
        )

    r = client.get(
        f"/api/v1/tenants/{tid}/products/{p['id']}/modifiers",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    items = r.json()
    assert len(items) == 2
    for m in items:
        assert isinstance(m["options"], list)
        assert len(m["options"]) == 1
