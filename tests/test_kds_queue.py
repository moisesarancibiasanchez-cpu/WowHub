"""HU_21 — Tests del KDS (Kitchen Display System) — cola de cocina.

Cubre:
  - GET /tenants/{tid}/kds/queue con cola vacía → []
  - GET /tenants/{tid}/kds/queue con pedidos → sólo los activos (no LISTO ni CANCELADO)
  - Aislamiento multi-tenant: tenant B no ve la cola de tenant A
  - Cálculo de age_minutes (>=0, basado en created_at)

Diseño:
  - Usa el mismo bootstrap que el resto de tests (auth/register → tenant).
  - Inserta pedidos directamente via OrderService.create para controlar
    el estado de manera determinista (transicionar a CONFIRMADO /
    EN_PREPARACION antes de pedir la cola).
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from uuid import UUID


# ── Helpers ──────────────────────────────────────────────────────
def _bootstrap(client, slug="kds-co"):
    """Registra usuario + tenant y devuelve (token, tenant_id)."""
    r = client.post("/api/v1/auth/register", json={
        "email": f"{slug}@e.com",
        "password": "test1234",
        "full_name": "Owner",
        "create_tenant": True,
        "tenant_legal_name": f"KDS {slug}",
        "tenant_slug": slug,
    })
    assert r.status_code == 201, r.text
    data = r.json()
    return data["access_token"], data["current_tenant"]["tenant_id"]


def _create_product(client, token, tid, sku_suffix="X", name="Café KDS", price_cents=1500):
    r = client.post(
        f"/api/v1/tenants/{tid}/products",
        json={
            "sku": f"KDS-{sku_suffix}",
            "name": name,
            "slug": f"cafe-kds-{sku_suffix.lower()}",
            "price_cents": price_cents,
            "status": "active",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 201, r.text
    return r.json()


def _create_order(client, token, tid, pid, qty=1, options=None, customer_name="Cliente KDS"):
    body = {
        "items": [{"product_id": pid, "quantity": qty, "options": options or {}}],
        "source": "kds-test",
        "customer_name": customer_name,
    }
    r = client.post(
        f"/api/v1/tenants/{tid}/orders",
        json=body,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 201, r.text
    return r.json()


def _transition(client, tid, oid, new_status, token):
    """Transiciona un pedido a `new_status` (lowercase)."""
    r = client.post(
        f"/api/v1/tenants/{tid}/orders/{oid}/transition",
        json={"new_status": new_status},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    return r.json()


def _get_queue(client, token, tid):
    return client.get(
        f"/api/v1/tenants/{tid}/kds/queue",
        headers={"Authorization": f"Bearer {token}"},
    )


# ── Tests ────────────────────────────────────────────────────────
def test_queue_empty_returns_empty_list(client):
    """Si no hay pedidos, la cola viene vacía y count = 0."""
    token, tid = _bootstrap(client, "kds-empty")

    r = _get_queue(client, token, tid)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["count"] == 0
    assert data["queue"] == []
    assert data["tenant_id"] == str(tid)
    # Los 3 estados activos que el KDS considera "en cocina".
    assert set(data["active_statuses"]) == {"recibido", "confirmado", "en_preparacion"}


def test_queue_with_orders(client):
    """La cola incluye pedidos activos y excluye LISTO/CANCELADO.

    Insertamos 4 pedidos:
      - A: RECIBIDO        → debe estar en cola
      - B: CONFIRMADO      → debe estar en cola
      - C: EN_PREPARACION  → debe estar en cola
      - D: LISTO           → NO debe estar en cola (sale del KDS)
      - E: CANCELADO       → NO debe estar en cola
    """
    token, tid = _bootstrap(client, "kds-mix")
    pid = _create_product(client, token, tid)["id"]

    # A — recién creado, queda en RECIBIDO
    a = _create_order(client, token, tid, pid, customer_name="Ana A")
    # B — transiciona a CONFIRMADO
    b = _create_order(client, token, tid, pid, customer_name="Bea B")
    _transition(client, tid, b["id"], "confirmado", token)
    # C — transiciona a CONFIRMADO y luego a EN_PREPARACION
    c = _create_order(client, token, tid, pid, customer_name="Cris C")
    _transition(client, tid, c["id"], "confirmado", token)
    _transition(client, tid, c["id"], "en_preparacion", token)
    # D — sale del KDS (LISTO)
    d = _create_order(client, token, tid, pid, customer_name="Dario D")
    _transition(client, tid, d["id"], "confirmado", token)
    _transition(client, tid, d["id"], "en_preparacion", token)
    _transition(client, tid, d["id"], "listo", token)
    # E — sale del KDS (CANCELADO)
    e = _create_order(client, token, tid, pid, customer_name="Eli E")
    r = client.post(
        f"/api/v1/tenants/{tid}/orders/{e['id']}/cancel",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text

    r = _get_queue(client, token, tid)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["count"] == 3, f"esperaba 3, получил {data['count']}: {data}"
    ids = {item["order_id"] for item in data["queue"]}
    assert str(a["id"]) in ids
    assert str(b["id"]) in ids
    assert str(c["id"]) in ids
    assert str(d["id"]) not in ids
    assert str(e["id"]) not in ids

    # Verificar que cada item tiene la shape esperada.
    sample = data["queue"][0]
    assert set(sample.keys()) >= {
        "order_id", "order_number", "status", "customer_name",
        "items", "priority", "age_minutes", "created_at",
    }
    # Status debe ser uno de los 3 activos.
    assert sample["status"] in {"recibido", "confirmado", "en_preparacion"}
    # Items: cada item con product_name, quantity, options.
    assert len(sample["items"]) >= 1
    item = sample["items"][0]
    assert "product_name" in item
    assert "quantity" in item
    assert "options" in item


def test_queue_respects_tenant_isolation(client):
    """Tenant B NO debe ver la cola de Tenant A.

    Insertamos un pedido en tenant A y verificamos que la cola de B
    viene vacía (y que A sí ve el suyo).
    """
    token_a, tid_a = _bootstrap(client, "kds-iso-a")
    token_b, tid_b = _bootstrap(client, "kds-iso-b")

    pid_a = _create_product(client, token_a, tid_a)["id"]
    order_a = _create_order(client, token_a, tid_a, pid_a, customer_name="Secreto A")

    # Tenant A ve el suyo.
    r = _get_queue(client, token_a, tid_a)
    assert r.status_code == 200
    assert r.json()["count"] == 1
    assert r.json()["queue"][0]["order_id"] == order_a["id"]

    # Tenant B: no debe ver nada de A.
    r = _get_queue(client, token_b, tid_b)
    assert r.status_code == 200
    assert r.json()["count"] == 0
    assert r.json()["queue"] == []

    # Defensa adicional: tenant B NO debe poder pedir la cola de A
    # (sería 404 porque no es miembro de ese tenant → NotFoundError
    # en get_current_membership se traduce a 403/401 según el guard).
    r = _get_queue(client, token_b, tid_a)
    assert r.status_code in (401, 403, 404), (
        f"cross-tenant leak: tenant_b pidiendo cola de tenant_a "
        f"devolvió {r.status_code}: {r.text}"
    )


def test_age_minutes_calculation(client):
    """El campo `age_minutes` refleja correctamente los minutos desde `created_at`.

    Insertamos un pedido, esperamos ~1.2s y validamos que age_minutes
    sea al menos 1 (en CI puede haber jitter — aceptamos ≥ 1 si pasó
    > 60s reales; en este test la latencia es < 1s pero dejamos un
    margen con backdating del created_at para hacerlo determinista).
    """
    token, tid = _bootstrap(client, "kds-age")
    pid = _create_product(client, token, tid)["id"]
    order = _create_order(client, token, tid, pid, customer_name="Edad Test")

    # Backdating: ajustar el created_at 5 minutos en el pasado, vía DB.
    # Usamos una sesión directa (mismo engine que el test).
    from app.database import SessionLocal
    from app.models.order import Order
    backdated = datetime.now(timezone.utc) - timedelta(minutes=5, hours=1)  # 65 min
    with SessionLocal() as db:
        o = db.get(Order, UUID(order["id"]))
        assert o is not None
        # Guardar naive-UTC (la columna en SQLite se guarda sin tzinfo).
        o.created_at = backdated.replace(tzinfo=None)
        db.commit()

    r = _get_queue(client, token, tid)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["count"] == 1
    item = data["queue"][0]
    # Aceptamos un margen ±2 min (backdating puede tener jitter de segundos).
    assert 63 <= item["age_minutes"] <= 67, (
        f"age_minutes esperaba ~65, obtuvo {item['age_minutes']}"
    )
    # Con 65 min, la prioridad debe ser 'critical' (>= 15 min).
    assert item["priority"] == "critical", (
        f"priority esperaba 'critical' para 65 min, obtuvo {item['priority']}"
    )


def test_mark_ready_endpoint_transitions_to_listo(client):
    """POST /kds/orders/{oid}/ready transiciona EN_PREPARACION → LISTO.

    Smoke test del segundo endpoint para garantizar coherencia con el
    state machine. No estaba en el contrato original pero el frontend
    lo usa (botón "✅ LISTO" del KDS).
    """
    token, tid = _bootstrap(client, "kds-ready")
    pid = _create_product(client, token, tid)["id"]
    o = _create_order(client, token, tid, pid)
    _transition(client, tid, o["id"], "confirmado", token)
    _transition(client, tid, o["id"], "en_preparacion", token)

    r = client.post(
        f"/api/v1/tenants/{tid}/kds/orders/{o['id']}/ready",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["ok"] is True
    assert data["status"] == "listo"
    assert data["order_id"] == o["id"]

    # Idempotente: llamar de nuevo no rompe.
    r = client.post(
        f"/api/v1/tenants/{tid}/kds/orders/{o['id']}/ready",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "listo"

    # Y el pedido ya no aparece en la cola.
    r = _get_queue(client, token, tid)
    assert r.status_code == 200
    assert r.json()["count"] == 0