"""HU_17 — Tests de la timeline del pedido (OrderEvent).

Cubre:
  - GET /orders/{oid}/timeline devuelve al menos el evento de creación
  - POST /orders/{oid}/events crea una nota manual
  - Cuando el estado de un Order cambia, se crea un evento STATUS_CHANGE
"""
from __future__ import annotations


def _bootstrap(client, slug="ev-co"):
    r = client.post("/api/v1/auth/register", json={
        "email": f"{slug}@e.com",
        "password": "test1234",
        "full_name": "Owner",
        "create_tenant": True,
        "tenant_legal_name": f"Events {slug}",
        "tenant_slug": slug,
    })
    assert r.status_code == 201, r.text
    data = r.json()
    return data["access_token"], data["current_tenant"]["tenant_id"]


def _create_product(client, token, tid):
    r = client.post(
        f"/api/v1/tenants/{tid}/products",
        json={
            "sku": "EV-1", "name": "Café", "slug": "cafe-ev",
            "price_cents": 1000, "status": "active",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 201, r.text
    return r.json()


def _create_order(client, token, tid, pid):
    r = client.post(
        f"/api/v1/tenants/{tid}/orders",
        json={
            "items": [{"product_id": pid, "quantity": 1}],
            "source": "test",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_create_note_event_returns_201(client):
    token, tid = _bootstrap(client, "ev-note")
    pid = _create_product(client, token, tid)["id"]
    order = _create_order(client, token, tid, pid)

    r = client.post(
        f"/api/v1/tenants/{tid}/orders/{order['id']}/events",
        json={
            "event_type": "note",
            "message": "Cliente pidió sin cebolla",
            "payload": {"by": "garzón"},
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["event_type"] == "note"
    assert data["message"] == "Cliente pidió sin cebolla"
    assert data["order_id"] == order["id"]


def test_timeline_includes_note_event(client):
    token, tid = _bootstrap(client, "ev-tl")
    pid = _create_product(client, token, tid)["id"]
    order = _create_order(client, token, tid, pid)

    # Crear 2 notas manuales
    for msg in ("Sin sal", "Para llevar"):
        client.post(
            f"/api/v1/tenants/{tid}/orders/{order['id']}/events",
            json={"event_type": "note", "message": msg},
            headers={"Authorization": f"Bearer {token}"},
        )

    r = client.get(
        f"/api/v1/tenants/{tid}/orders/{order['id']}/events/timeline",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    items = r.json()
    messages = [it["message"] for it in items if it["event_type"] == "note"]
    assert "Sin sal" in messages
    assert "Para llevar" in messages
    # Las dos notas + al menos un STATUS_CHANGE (del confirm) = orden cronológico
    assert len(items) >= 2


def test_status_transition_creates_status_change_event(client):
    """Al transicionar un Order se crea automáticamente un OrderEvent.

    Tras crearlo con status=RECIBIDO, lo transicionamos a CONFIRMADO.
    El timeline debe contener un evento STATUS_CHANGE con
    payload {from: 'recibido', to: 'confirmado'}.
    """
    token, tid = _bootstrap(client, "ev-trans")
    pid = _create_product(client, token, tid)["id"]
    order = _create_order(client, token, tid, pid)

    # Transición: RECIBIDO → CONFIRMADO
    r = client.post(
        f"/api/v1/tenants/{tid}/orders/{order['id']}/transition",
        json={"new_status": "confirmado"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text

    r = client.get(
        f"/api/v1/tenants/{tid}/orders/{order['id']}/events/timeline",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    items = r.json()
    sc_events = [it for it in items if it["event_type"] == "status_change"]
    assert len(sc_events) >= 1
    last = sc_events[-1]
    assert last["payload"]["from"] == "recibido"
    assert last["payload"]["to"] == "confirmado"


def test_status_change_event_cannot_be_emitted_manually(client):
    """POST /events rechaza event_type=status_change."""
    token, tid = _bootstrap(client, "ev-block")
    pid = _create_product(client, token, tid)["id"]
    order = _create_order(client, token, tid, pid)

    r = client.post(
        f"/api/v1/tenants/{tid}/orders/{order['id']}/events",
        json={"event_type": "status_change", "payload": {"from": "x", "to": "y"}},
        headers={"Authorization": f"Bearer {token}"},
    )
    # El router devuelve 400 — coherente con errores de lógica.
    assert r.status_code == 400, r.text
