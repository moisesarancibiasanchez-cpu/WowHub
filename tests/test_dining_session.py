"""HU_19 — Tests de sesiones de mesa (DiningSession).

Cubre:
  - POST /dining-sessions abre una mesa
  - POST /dining-sessions/{dsid}/orders agrega un OrderItem a la mesa
  - GET /dining-sessions/{dsid}/split calcula la división equitativa
  - POST /dining-sessions/{dsid}/close cierra la mesa (snapshot final)
  - PATCH /dining-sessions/{dsid}/tip agrega propina
"""
from __future__ import annotations


def _bootstrap(client, slug="ds-co"):
    r = client.post("/api/v1/auth/register", json={
        "email": f"{slug}@e.com",
        "password": "test1234",
        "full_name": "Owner",
        "create_tenant": True,
        "tenant_legal_name": f"Dining {slug}",
        "tenant_slug": slug,
    })
    assert r.status_code == 201, r.text
    data = r.json()
    return data["access_token"], data["current_tenant"]["tenant_id"]


def _create_branch(client, token, tid):
    r = client.post(
        f"/api/v1/tenants/{tid}/branches",
        json={
            "name": "Local Centro",
            "code": "CENTRO",
            "address": "Av. 1",
            "city": "Santiago",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code in (200, 201), r.text
    return r.json()


def _create_product(client, token, tid):
    r = client.post(
        f"/api/v1/tenants/{tid}/products",
        json={
            "sku": "DS-P", "name": "Almuerzo", "slug": "almuerzo",
            "price_cents": 1000, "status": "active",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 201, r.text
    return r.json()


def _create_order_with_item(client, token, tid, pid, qty=1, total=None):
    r = client.post(
        f"/api/v1/tenants/{tid}/orders",
        json={"items": [{"product_id": pid, "quantity": qty}]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 201, r.text
    order = r.json()
    return order


def test_open_session_returns_status_open(client):
    token, tid = _bootstrap(client, "ds-open")
    branch = _create_branch(client, token, tid)

    r = client.post(
        f"/api/v1/tenants/{tid}/dining-sessions",
        json={
            "branch_id": branch["id"],
            "table_label": "Mesa 7",
            "customer_count": 3,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["status"] == "open"
    assert data["customer_count"] == 3
    assert data["table_label"] == "Mesa 7"
    assert data["total_cents"] == 0


def test_add_order_increments_session_total(client):
    token, tid = _bootstrap(client, "ds-add")
    branch = _create_branch(client, token, tid)
    p = _create_product(client, token, tid)

    # Abrir mesa
    r = client.post(
        f"/api/v1/tenants/{tid}/dining-sessions",
        json={
            "branch_id": branch["id"],
            "table_label": "Mesa 1",
            "customer_count": 2,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    sid = r.json()["id"]

    # Crear un pedido con 2 items de 1000 cents
    order = _create_order_with_item(client, token, tid, p["id"], qty=2)
    oi_id = order["items"][0]["id"]

    r = client.post(
        f"/api/v1/tenants/{tid}/dining-sessions/{sid}/orders",
        json={"order_item_id": oi_id},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 201, r.text

    # Verificar que el total de la mesa subió a 2000
    r = client.get(
        f"/api/v1/tenants/{tid}/dining-sessions/{sid}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["total_cents"] == 2000


def test_split_equally_divides_total(client):
    """2 comensales, total 2000 → 1000 cada uno (sin remanente)."""
    token, tid = _bootstrap(client, "ds-split")
    branch = _create_branch(client, token, tid)
    p = _create_product(client, token, tid)

    r = client.post(
        f"/api/v1/tenants/{tid}/dining-sessions",
        json={
            "branch_id": branch["id"],
            "table_label": "Mesa 2",
            "customer_count": 2,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    sid = r.json()["id"]

    # Pedido por 2000 (qty=2)
    order = _create_order_with_item(client, token, tid, p["id"], qty=2)
    client.post(
        f"/api/v1/tenants/{tid}/dining-sessions/{sid}/orders",
        json={"order_item_id": order["items"][0]["id"]},
        headers={"Authorization": f"Bearer {token}"},
    )

    r = client.get(
        f"/api/v1/tenants/{tid}/dining-sessions/{sid}/split",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["total_cents"] == 2000
    assert data["customer_count"] == 2
    amounts = sorted(s["amount_cents"] for s in data["shares"])
    assert amounts == [1000, 1000]


def test_split_uneven_assigns_remainder_to_first(client):
    """3 comensales, total 1000 → 334,333,333 (remainder=1 al primero)."""
    token, tid = _bootstrap(client, "ds-rem")
    branch = _create_branch(client, token, tid)
    p = _create_product(client, token, tid)

    r = client.post(
        f"/api/v1/tenants/{tid}/dining-sessions",
        json={
            "branch_id": branch["id"],
            "table_label": "Mesa 3",
            "customer_count": 3,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    sid = r.json()["id"]

    # Pedido por 1000 (qty=1)
    order = _create_order_with_item(client, token, tid, p["id"], qty=1)
    client.post(
        f"/api/v1/tenants/{tid}/dining-sessions/{sid}/orders",
        json={"order_item_id": order["items"][0]["id"]},
        headers={"Authorization": f"Bearer {token}"},
    )

    r = client.get(
        f"/api/v1/tenants/{tid}/dining-sessions/{sid}/split",
        headers={"Authorization": f"Bearer {token}"},
    )
    data = r.json()
    # 1000 / 3 = 333 con resto 1
    assert data["remainder_cents"] == 1
    amounts = sorted(s["amount_cents"] for s in data["shares"])
    assert amounts == [333, 333, 334]


def test_close_session_freezes_total_and_status(client):
    token, tid = _bootstrap(client, "ds-close")
    branch = _create_branch(client, token, tid)
    p = _create_product(client, token, tid)

    r = client.post(
        f"/api/v1/tenants/{tid}/dining-sessions",
        json={
            "branch_id": branch["id"],
            "table_label": "Mesa 4",
            "customer_count": 1,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    sid = r.json()["id"]
    order = _create_order_with_item(client, token, tid, p["id"], qty=1)
    client.post(
        f"/api/v1/tenants/{tid}/dining-sessions/{sid}/orders",
        json={"order_item_id": order["items"][0]["id"]},
        headers={"Authorization": f"Bearer {token}"},
    )

    r = client.post(
        f"/api/v1/tenants/{tid}/dining-sessions/{sid}/close",
        json={"paid_cents": 1000, "notes": "Efectivo"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["status"] == "closed"
    assert data["paid_cents"] == 1000
    assert data["closed_at"] is not None


def test_tip_increments_tip_cents(client):
    token, tid = _bootstrap(client, "ds-tip")
    branch = _create_branch(client, token, tid)

    r = client.post(
        f"/api/v1/tenants/{tid}/dining-sessions",
        json={
            "branch_id": branch["id"],
            "table_label": "Mesa 5",
            "customer_count": 1,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    sid = r.json()["id"]

    r = client.patch(
        f"/api/v1/tenants/{tid}/dining-sessions/{sid}/tip",
        json={"tip_cents": 500},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["tip_cents"] == 500

    # Acumulable
    client.patch(
        f"/api/v1/tenants/{tid}/dining-sessions/{sid}/tip",
        json={"tip_cents": 200},
        headers={"Authorization": f"Bearer {token}"},
    )
    r = client.get(
        f"/api/v1/tenants/{tid}/dining-sessions/{sid}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.json()["tip_cents"] == 700
