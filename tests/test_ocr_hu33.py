"""HU_33 — Tests del API OCR."""
from __future__ import annotations

import pytest


# ── Helpers ─────────────────────────────────────────────────────────────
def _register_with_tenant(client, slug: str) -> dict:
    r = client.post("/api/v1/auth/register", json={
        "email": f"{slug}@example.com",
        "password": "test1234",
        "full_name": "HU33 Tester",
        "create_tenant": True,
        "tenant_legal_name": f"HU33 Test {slug}",
        "tenant_slug": slug,
    })
    assert r.status_code in (200, 201), f"register falló: {r.status_code} {r.text}"
    return r.json()


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ── 1. POST /ocr/receipt sync=true procesa en línea ─────────────────────
def test_process_receipt_sync(client):
    """POST con sync=true procesa en línea (sin Celery)."""
    data = _register_with_tenant(client, slug="hu33-sync")
    token = data["access_token"]
    tid = data["current_tenant"]["tenant_id"]

    r = client.post(
        f"/api/v1/tenants/{tid}/ocr/receipt",
        headers=_headers(token),
        json={
            "image_url": "https://example.com/test-receipt.jpg",
            "sync": True,
        },
    )
    assert r.status_code in (200, 202), r.text
    body = r.json()
    assert body["processed_synchronously"] is True
    assert body["receipt_id"]
    assert body["status"] in ("processed", "failed")
    # Mock provider debería detectar items y total.
    assert isinstance(body["items"], list)
    assert body["total_cents"] > 0
    print(f"  items={len(body['items'])}, total={body['total_cents']}")


# ── 2. POST /ocr/receipt async encola ──────────────────────────────────
def test_process_receipt_async(client):
    """POST sin sync=true encola Celery."""
    data = _register_with_tenant(client, slug="hu33-async")
    token = data["access_token"]
    tid = data["current_tenant"]["tenant_id"]

    r = client.post(
        f"/api/v1/tenants/{tid}/ocr/receipt",
        headers=_headers(token),
        json={
            "image_url": "https://example.com/test-receipt2.jpg",
        },
    )
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["processed_synchronously"] is False
    assert body["task_id"]
    assert body["status"] == "pending"


# ── 3. GET /ocr/receipts lista los receipts del tenant ─────────────────
def test_list_receipts(client):
    """GET /ocr/receipts devuelve los receipts del tenant."""
    data = _register_with_tenant(client, slug="hu33-list")
    token = data["access_token"]
    tid = data["current_tenant"]["tenant_id"]

    # Crear 2 receipts sync
    for i in range(2):
        client.post(
            f"/api/v1/tenants/{tid}/ocr/receipt",
            headers=_headers(token),
            json={
                "image_url": f"https://example.com/r{i}.jpg",
                "sync": True,
            },
        )

    r = client.get(
        f"/api/v1/tenants/{tid}/ocr/receipts",
        headers=_headers(token),
    )
    assert r.status_code == 200, r.text
    receipts = r.json()
    assert len(receipts) >= 2
    # Orden descendente por created_at.
    for i in range(len(receipts) - 1):
        assert receipts[i]["created_at"] >= receipts[i + 1]["created_at"]


# ── 4. GET /ocr/receipts/{id} devuelve detalle ──────────────────────────
def test_get_receipt_by_id(client):
    """GET con UUID devuelve el receipt específico."""
    data = _register_with_tenant(client, slug="hu33-detail")
    token = data["access_token"]
    tid = data["current_tenant"]["tenant_id"]

    # Crear uno
    r1 = client.post(
        f"/api/v1/tenants/{tid}/ocr/receipt",
        headers=_headers(token),
        json={
            "image_url": "https://example.com/detail.jpg",
            "sync": True,
        },
    )
    receipt_id = r1.json()["receipt_id"]

    r2 = client.get(
        f"/api/v1/tenants/{tid}/ocr/receipts/{receipt_id}",
        headers=_headers(token),
    )
    assert r2.status_code == 200
    body = r2.json()
    assert body["id"] == receipt_id
    assert body["status"] == "processed"


# ── 5. POST /ocr/payment-proof verifica monto ──────────────────────────
def test_payment_proof_verified(client):
    """POST /ocr/payment-proof verifica monto detectado vs esperado."""
    data = _register_with_tenant(client, slug="hu33-payment")
    token = data["access_token"]
    tid = data["current_tenant"]["tenant_id"]

    # El Mock provider detecta $19.597 CLP = 1.959.700 cents.
    r = client.post(
        f"/api/v1/tenants/{tid}/ocr/payment-proof",
        headers=_headers(token),
        json={
            "image_url": "https://example.com/ticket1.jpg",
            "order_id": "order-test-001",
            "expected_amount_cents": 1_959_700,
            "tolerance_cents": 100,
            "sync": True,
        },
    )
    assert r.status_code in (200, 202), r.text
    body = r.json()
    assert body["verified"] is True
    assert body["delta_cents"] == 0
    assert body["detected_total_cents"] == 1_959_700


# ── 6. POST /ocr/payment-proof con mismatch → verified=False ──────────
def test_payment_proof_mismatch(client):
    """Mismatch > tolerance → verified=False."""
    data = _register_with_tenant(client, slug="hu33-mismatch")
    token = data["access_token"]
    tid = data["current_tenant"]["tenant_id"]

    r = client.post(
        f"/api/v1/tenants/{tid}/ocr/payment-proof",
        headers=_headers(token),
        json={
            "image_url": "https://example.com/ticket1.jpg",
            "order_id": "order-test-002",
            "expected_amount_cents": 99_999_999,  # muy distinto
            "tolerance_cents": 100,
            "sync": True,
        },
    )
    assert r.status_code in (200, 202), r.text
    body = r.json()
    assert body["verified"] is False


# ── 7. Auth requerida ───────────────────────────────────────────────────
def test_ocr_requires_auth(client):
    """Sin Authorization → 401."""
    # Sin register — endpoint pelado.
    fake_uuid = "00000000-0000-0000-0000-000000000000"
    r = client.post(
        f"/api/v1/tenants/{fake_uuid}/ocr/receipt",
        json={"image_url": "https://example.com/x.jpg", "sync": True},
    )
    assert r.status_code in (401, 403)


# ── 8. Filtros en /receipts ─────────────────────────────────────────────
def test_list_receipts_filter_status(client):
    """Filtro status=processed solo devuelve procesados."""
    data = _register_with_tenant(client, slug="hu33-filter")
    token = data["access_token"]
    tid = data["current_tenant"]["tenant_id"]

    # Crear 1 receipt sync (processed)
    client.post(
        f"/api/v1/tenants/{tid}/ocr/receipt",
        headers=_headers(token),
        json={
            "image_url": "https://example.com/filter.jpg",
            "sync": True,
        },
    )

    r = client.get(
        f"/api/v1/tenants/{tid}/ocr/receipts?status_filter=processed",
        headers=_headers(token),
    )
    assert r.status_code == 200
    receipts = r.json()
    for r in receipts:
        assert r["status"] == "processed"


# ── 9. Receipt 404 si no pertenece al tenant ──────────────────────────
def test_get_receipt_wrong_tenant(client):
    """UUID de otro tenant → 404 (no revela existencia)."""
    data1 = _register_with_tenant(client, slug="hu33-t1")
    token1 = data1["access_token"]
    tid1 = data1["current_tenant"]["tenant_id"]

    # Crear receipt en tenant 1
    r1 = client.post(
        f"/api/v1/tenants/{tid1}/ocr/receipt",
        headers=_headers(token1),
        json={"image_url": "https://example.com/t1.jpg", "sync": True},
    )
    receipt_id = r1.json()["receipt_id"]

    # Crear tenant 2 y consultar el receipt de tenant 1
    data2 = _register_with_tenant(client, slug="hu33-t2")
    token2 = data2["access_token"]
    tid2 = data2["current_tenant"]["tenant_id"]

    r2 = client.get(
        f"/api/v1/tenants/{tid2}/ocr/receipts/{receipt_id}",
        headers=_headers(token2),
    )
    assert r2.status_code == 404  # no revela existencia