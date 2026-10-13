"""Test end-to-end de los 2 bugs reportados:

  1. Pedidos: la API /orders devuelve Page{items:[...]}, no array.
     El JS viejo asumía array → siempre 'No hay pedidos'.
  2. Pipeline: el body de /transition debe ser {new_status}, no {to_status}.

Arranca uvicorn, loguea, simula las llamadas del front y verifica
que ahora funcionan.
"""
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from app.database import SessionLocal
from app.models import User, Tenant, Order
from app.models.order import OrderStatus

BASE = "http://localhost:9999"


def wait_for_server(timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(f"{BASE}/health", timeout=1)
            return True
        except Exception:
            time.sleep(0.5)
    return False


def main():
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == "maria@cafenorte.cl").first()
        cafe = db.query(Tenant).filter(Tenant.slug == "cafe-norte").first()
        # Tomamos el primer pedido PENDING para testear la transición
        pending = db.query(Order).filter(
            Order.tenant_id == str(cafe.id),
            Order.status == "pending",
        ).first()
    finally:
        db.close()

    proj_root = Path(__file__).resolve().parent.parent
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", "9999",
         "--host", "127.0.0.1", "--log-level", "warning"],
        cwd=str(proj_root),
        env={**os.environ, "PYTHONPATH": str(proj_root)},
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        if not wait_for_server():
            print("❌ Server no arrancó"); return 1

        # Login
        req = urllib.request.Request(
            f"{BASE}/api/v1/auth/login",
            data=json.dumps({"email": "maria@cafenorte.cl", "password": "demo1234"}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        body = json.loads(urllib.request.urlopen(req, timeout=5).read())
        H = {"Authorization": f"Bearer {body['access_token']}"}
        print("✓ Login OK")

        # ── 1) /orders devuelve Page[OrderListItem] ─────
        print("\n--- GET /orders (Pedidos) ---")
        url = f"{BASE}/api/v1/tenants/{cafe.id}/orders?page_size=100"
        resp = urllib.request.urlopen(urllib.request.Request(url, headers=H), timeout=5)
        data = json.loads(resp.read())
        print(f"  Tipo: {type(data).__name__}, keys: {list(data.keys()) if isinstance(data, dict) else 'N/A'}")
        assert isinstance(data, dict), "La API debería devolver un dict (Page)"
        assert "items" in data, f"Falta 'items' en {data}"
        assert "total" in data, f"Falta 'total' en {data}"
        assert isinstance(data["items"], list), "items debe ser array"
        print(f"  ✓ Page shape correcta: items={len(data['items'])}, total={data['total']}")
        assert len(data["items"]) == 12, f"Esperaba 12 orders, hay {len(data['items'])}"
        print(f"  ✓ 12 orders en Café Norte (como espera la página Pedidos)")

        # Validar que cada item tiene los campos que usa el JS actual
        o0 = data["items"][0]
        print(f"  Keys de un OrderListItem: {sorted(o0.keys())}")
        for k in ("id", "number", "status", "customer_name", "total_cents",
                  "currency", "item_count", "source", "created_at"):
            assert k in o0, f"Falta {k}"
        print(f"  ✓ Todos los campos que usa orders.html (number, item_count, etc.) están presentes")

        # El JS viejo fallaba con `o.order_number` (no existe) y `o.customer_phone`
        assert "order_number" not in o0, "OrderListItem NO debe tener order_number"
        assert "customer_phone" not in o0, "OrderListItem NO debe tener customer_phone (solo email)"
        assert "items" not in o0, "OrderListItem NO debe tener items (solo item_count)"
        print(f"  ✓ Confirma que orders.html viejo habría roto (order_number/phone/items ausentes)")

        # ── 2) /transition: body es {new_status} ─────────
        print(f"\n--- POST /orders/{pending.id}/transition ---")
        url = f"{BASE}/api/v1/tenants/{cafe.id}/orders/{pending.id}/transition"
        # Forma VIEJA (con to_status) — debe fallar
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps({"to_status": "confirmed"}).encode(),
                headers={**H, "Content-Type": "application/json"},
                method="POST",
            )
            urllib.request.urlopen(req, timeout=5)
            print("  ⚠ to_status fue aceptado (no debería)")
        except urllib.error.HTTPError as e:
            err = json.loads(e.read())
            assert e.code == 422, f"Esperaba 422, obtuve {e.code}"
            # Pydantic v2 reporta {type, loc: ["body","new_status"], msg, input}
            detail = err.get("detail", [])
            assert any(
                d.get("loc") == ["body", "new_status"]
                for d in detail
            ), f"422 debería mencionar loc=['body','new_status'], got {detail}"
            print(f"  ✓ to_status → 422, loc={detail[0].get('loc') if detail else 'N/A'}")

        # Forma NUEVA (con new_status) — debe funcionar
        # NB: OrderStatus es str-enum con VALORES lowercase ("confirmed", no "CONFIRMED").
        # El front (orders.html/pipeline.html) ahora envía el valor en minúsculas.
        req = urllib.request.Request(
            url,
            data=json.dumps({"new_status": "confirmed"}).encode(),
            headers={**H, "Content-Type": "application/json"},
            method="POST",
        )
        resp = urllib.request.urlopen(req, timeout=5)
        result = json.loads(resp.read())
        assert result["status"] == "confirmed", f"Esperaba 'confirmed', obtuve {result['status']!r}"
        print(f"  ✓ new_status → 200, order ahora status={result['status']}, "
              f"number={result['number']}")

        # Revertimos para no contaminar el seed.
        # NB: el state machine no permite confirmed → pending, así que
        # hacemos el revert directamente con el ORM (bypass del state machine).
        from app.database import SessionLocal as SL
        from app.services.order_service import OrderService
        db = SL()
        try:
            o = OrderService(db).get(cafe.id, pending.id)
            o.status = OrderStatus.PENDING
            db.commit()
            print(f"  ✓ Revertido a pending para no contaminar el seed")
        finally:
            db.close()

        # ── 3) /cancel: reason es query param ────────────
        print(f"\n--- POST /orders/{pending.id}/cancel?reason=... ---")
        url = (f"{BASE}/api/v1/tenants/{cafe.id}/orders/{pending.id}"
               f"/cancel?reason=test")
        req = urllib.request.Request(url, data=b"", headers=H, method="POST")
        resp = urllib.request.urlopen(req, timeout=5)
        result = json.loads(resp.read())
        assert result["status"] == "canceled", f"Esperaba 'canceled', obtuve {result['status']!r}"
        print(f"  ✓ cancel con reason como query → 200, status={result['status']}")

        # Revertimos
        db = SL()
        try:
            o = OrderService(db).get(cafe.id, pending.id)
            o.status = OrderStatus.PENDING
            db.commit()
            print(f"  ✓ Revertido a pending")
        finally:
            db.close()

        print("\n✅ Todos los contratos JS↔API verificados")
        return 0
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    sys.exit(main())
