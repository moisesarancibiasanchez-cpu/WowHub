"""Test rápido de los endpoints que usan las 3 páginas de Gestión interna.

Arranca uvicorn en :9999, espera a que esté listo, y prueba:
  • GET /api/v1/tenants/{tid}/orders
  • GET /api/v1/tenants/{tid}/branch-products
"""
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from app.database import SessionLocal
from app.models import User, Tenant

BASE = "http://localhost:9999"


def wait_for_server(timeout=30):
    """Espera activa a que /health responda 200."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(f"{BASE}/health", timeout=1)
            return True
        except Exception:
            time.sleep(0.5)
    return False


def main():
    # 0) Datos del user + tenant
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == "maria@cafenorte.cl").first()
        cafe = db.query(Tenant).filter(Tenant.slug == "cafe-norte").first()
        if not user or not cafe:
            print("❌ Faltan datos seedeados (maria@cafenorte.cl o cafe-norte)")
            return 1
        print(f"User: {user.email}, Tenant: {cafe.slug} ({cafe.id})")
    finally:
        db.close()

    # 1) Levantar uvicorn en background
    proj_root = Path(__file__).resolve().parent.parent
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", "9999",
         "--host", "127.0.0.1", "--log-level", "warning"],
        cwd=str(proj_root), env={**__import__("os").environ, "PYTHONPATH": str(proj_root)},
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        if not wait_for_server(timeout=30):
            print("❌ Server no arrancó")
            return 1
        print("✓ Server up en :9999\n")

        # 2) Login
        req = urllib.request.Request(
            f"{BASE}/api/v1/auth/login",
            data=json.dumps({"email": "maria@cafenorte.cl", "password": "demo1234"}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            resp = urllib.request.urlopen(req, timeout=5)
            body = json.loads(resp.read())
            token = body.get("access_token")
            print(f"✓ Login OK (token: {token[:20]}...)")
        except urllib.error.HTTPError as e:
            print(f"❌ Login failed: {e.code} {e.read()[:200]}")
            return 1

        H = {"Authorization": f"Bearer {token}"}
        TID = str(cafe.id)

        # 3) Orders (Pedidos + Pipeline usan esto)
        print("\n--- Pedidos (orders) ---")
        resp = urllib.request.urlopen(urllib.request.Request(
            f"{BASE}/api/v1/tenants/{TID}/orders?page_size=50", headers=H), timeout=5)
        orders = json.loads(resp.read())
        if isinstance(orders, dict):
            orders = orders.get("items", orders.get("data", []))
        print(f"  Total: {len(orders)}")
        for o in orders[:3]:
            num = o.get("order_number") or o.get("number")
            items = o.get("items", [])
            items_str = ", ".join(f"{i.get('quantity')}× {i.get('product_name')}" for i in items[:2])
            print(f"  • {num} | {o.get('status')} | {o.get('customer_name')} | "
                  f"${(o.get('total_cents', 0) / 100):.0f} | items: {items_str}")
        by_status = {}
        for o in orders:
            by_status[o.get("status")] = by_status.get(o.get("status"), 0) + 1
        print(f"  Por estado: {by_status}")

        # 4) Branch products (Inventario usa esto)
        print("\n--- Inventario (branch-products) ---")
        resp = urllib.request.urlopen(urllib.request.Request(
            f"{BASE}/api/v1/tenants/{TID}/branch-products", headers=H), timeout=5)
        bps = json.loads(resp.read())
        print(f"  Total BranchProducts: {len(bps)}")
        low = [b for b in bps if b["stock"] < b["low_stock_threshold"]]
        out_of = [b for b in bps if b["stock"] == 0]
        ok = [b for b in bps if b["stock"] >= b["low_stock_threshold"]]
        print(f"  Stock OK: {len(ok)} | Stock bajo: {len(low)} | Sin stock: {len(out_of)}")
        for b in (out_of + low)[:5]:
            print(f"    ⚠ {b['product_id'][:8]}…  stock={b['stock']:3d}  thr={b['low_stock_threshold']:3d}")

        # 5) Assertions
        print("\n--- Assertions ---")
        assert len(orders) == 12, f"Esperaba 12 orders, hay {len(orders)}"
        print("  ✓ 12 orders en Café Norte")
        assert len(bps) == 10, f"Esperaba 10 BranchProducts, hay {len(bps)}"
        print("  ✓ 10 BranchProducts en Café Norte")
        assert len(out_of) >= 1, "Esperaba al menos 1 producto sin stock"
        print(f"  ✓ {len(out_of)} producto(s) sin stock (alerta crítica)")
        assert len(low) >= 2, "Esperaba al menos 2 productos con stock bajo"
        print(f"  ✓ {len(low)} producto(s) con stock bajo (alerta reposición)")
        # Que las 6 columnas del Pipeline tengan al menos 1 pedido
        for st in ("pending", "confirmed", "preparing", "ready", "delivered", "canceled"):
            assert by_status.get(st, 0) >= 1, f"Falta estado {st}"
        print("  ✓ Las 6 columnas del Pipeline tienen pedidos")
        print("\n✅ Todos los endpoints de Gestión interna OK")
        return 0
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    sys.exit(main())
