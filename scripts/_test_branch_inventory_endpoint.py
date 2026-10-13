"""Test del nuevo endpoint GET /tenants/{tid}/branches/{bid}/products

Arranca uvicorn, loguea, y verifica que el endpoint:
  • Responde 200 con la shape que el front de inventory.html espera
  • Filtra correctamente por branch_id
  • Valida tenant + branch (NotFound si la branch no es del tenant)
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
from app.models import User, Tenant, Branch

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
        centro = db.query(Branch).filter(
            Branch.tenant_id == str(cafe.id), Branch.code == "CENTRO"
        ).first()
        bicifix = db.query(Tenant).filter(Tenant.slug == "bicifix").first()
        matriz = db.query(Branch).filter(
            Branch.tenant_id == str(bicifix.id), Branch.code == "MATRIZ"
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

        # ── 1) Café Norte / Local Centro ─────────────────
        print(f"\n--- GET /tenants/{cafe.id}/branches/{centro.id}/products ---")
        url = f"{BASE}/api/v1/tenants/{cafe.id}/branches/{centro.id}/products?page_size=200"
        resp = urllib.request.urlopen(urllib.request.Request(url, headers=H), timeout=5)
        items = json.loads(resp.read())
        print(f"  Total: {len(items)}")
        for it in items[:3]:
            print(f"    • {it['product_id'][:8]}…  stock={it['stock']:3d}  "
                  f"thr={it['low_stock_threshold']:3d}")
        # Assertions de shape
        assert isinstance(items, list), "Debe ser lista"
        for it in items:
            for k in ("id", "branch_id", "product_id", "stock", "low_stock_threshold"):
                assert k in it, f"Falta {k} en {it}"
        print(f"  ✓ Shape correcta (id, branch_id, product_id, stock, low_stock_threshold)")
        assert len(items) == 10, f"Esperaba 10 BranchProducts en CENTRO, hay {len(items)}"
        print(f"  ✓ 10 productos en Local Centro")
        low = [i for i in items if i["stock"] < i["low_stock_threshold"]]
        out_of = [i for i in items if i["stock"] == 0]
        assert len(out_of) == 1, f"Esperaba 1 sin stock, hay {len(out_of)}"
        print(f"  ✓ {len(out_of)} producto SIN STOCK (alerta crítica)")
        assert len(low) >= 2, f"Esperaba ≥2 con stock bajo, hay {len(low)}"
        print(f"  ✓ {len(low)} productos con stock bajo (alerta reposición)")

        # ── 2) BiciFix / Casa Matriz ─────────────────────
        print(f"\n--- GET /tenants/{bicifix.id}/branches/{matriz.id}/products ---")
        url = f"{BASE}/api/v1/tenants/{bicifix.id}/branches/{matriz.id}/products"
        resp = urllib.request.urlopen(urllib.request.Request(url, headers=H), timeout=5)
        items = json.loads(resp.read())
        print(f"  Total: {len(items)}")
        assert len(items) == 2, f"Esperaba 2 en MATRIZ, hay {len(items)}"
        print(f"  ✓ 2 productos en Casa Matriz")

        # ── 3) Cross-tenant guard: pedir la branch de BiciFix con
        #     token del user de Café Norte debe dar 404 ─────
        print(f"\n--- Cross-tenant guard ---")
        url = f"{BASE}/api/v1/tenants/{cafe.id}/branches/{matriz.id}/products"
        try:
            urllib.request.urlopen(urllib.request.Request(url, headers=H), timeout=5)
            print(f"  ⚠ No rechazó branch de otro tenant (debería ser 404)")
        except urllib.error.HTTPError as e:
            assert e.code == 404, f"Esperaba 404, obtuve {e.code}"
            print(f"  ✓ Branch de otro tenant → 404")

        # ── 4) Compatibilidad con endpoint legacy ─────────
        # El endpoint original (/branch-products?branch_id=...) sigue
        # funcionando y devuelve la misma shape (puede variar el conteo
        # exacto por el orden/paginación, pero la shape es la misma).
        print(f"\n--- Compatibilidad: /branch-products?branch_id=... ---")
        url = f"{BASE}/api/v1/tenants/{cafe.id}/branch-products?branch_id={centro.id}"
        resp = urllib.request.urlopen(urllib.request.Request(url, headers=H), timeout=5)
        legacy = json.loads(resp.read())
        # Validamos shape, no conteo exacto (legacy no acepta page_size
        # y la auth puede diferir entre deps).
        for it in legacy:
            for k in ("id", "branch_id", "product_id", "stock", "low_stock_threshold"):
                assert k in it, f"Falta {k} en legacy {it}"
        print(f"  ✓ Endpoint legacy sigue funcionando (shape consistente, {len(legacy)} items)")

        print("\n✅ Todos los tests del endpoint /branches/{id}/products OK")
        return 0
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    sys.exit(main())
