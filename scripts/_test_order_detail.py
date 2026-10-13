"""Quick check: GET /tenants/{tid}/orders/{oid} returns items.

Esto es lo que usa el modal del Pipeline al hacer click en una tarjeta.
"""
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from app.database import SessionLocal
from app.models import User, Tenant, Order

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
    user = db.query(User).filter(User.email == "maria@cafenorte.cl").first()
    cafe = db.query(Tenant).filter(Tenant.slug == "cafe-norte").first()
    order = db.query(Order).filter(
        Order.tenant_id == str(cafe.id),
        Order.status == "pending",
    ).first()
    db.close()

    proj_root = Path(__file__).resolve().parent.parent
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", "9999",
         "--host", "127.0.0.1", "--log-level", "warning"],
        cwd=str(proj_root), env={**__import__("os").environ, "PYTHONPATH": str(proj_root)},
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
        token = body.get("access_token")
        H = {"Authorization": f"Bearer {token}"}

        # Detalle del pedido
        url = f"{BASE}/api/v1/tenants/{cafe.id}/orders/{order.id}"
        resp = urllib.request.urlopen(urllib.request.Request(url, headers=H), timeout=5)
        detail = json.loads(resp.read())
        items = detail.get("items", [])
        print(f"Order {detail.get('order_number') or detail.get('number')}: "
              f"{detail.get('customer_name')} | status={detail.get('status')}")
        print(f"  items count: {len(items)}")
        for it in items:
            print(f"    • {it.get('quantity')}× {it.get('product_name')} "
                  f"@ ${(it.get('unit_price_cents', 0)/100):.0f}")
        assert len(items) >= 1, "Items no aparecen en el detalle"
        print("\n✓ El modal del Pipeline puede renderizar items")
        return 0
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    sys.exit(main())
