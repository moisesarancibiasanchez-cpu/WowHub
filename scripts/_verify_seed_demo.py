"""Verificación de los datos demo seedeados: Pedidos + Inventario.

Ejecutar: python scripts/_verify_seed_demo.py
"""
from app.database import SessionLocal
from app.models import Tenant, Order, BranchProduct, Product, Branch
from sqlalchemy import func


def main():
    db = SessionLocal()
    try:
        for slug in ("cafe-norte", "bicifix"):
            t = db.query(Tenant).filter(Tenant.slug == slug).first()
            if not t:
                print(f"❌ Tenant {slug} no existe")
                continue
            print(f"\n=== {t.display_name} ({t.id}) ===")

            # ── Pedidos por estado ────────────────────────
            rows = (
                db.query(Order.status, func.count(Order.id))
                .filter(Order.tenant_id == str(t.id))
                .group_by(Order.status)
                .all()
            )
            by_status = dict(rows)
            total = sum(by_status.values())
            print(f"  Pedidos: {total} total → {by_status}")
            expected = {
                "cafe-norte": {"pending", "confirmed", "preparing", "ready",
                               "delivered", "canceled"},
                "bicifix":    {"pending", "confirmed", "delivered"},
            }
            assert set(by_status.keys()) == expected[slug], (
                f"Estados faltantes en {slug}: "
                f"{expected[slug] - set(by_status.keys())}"
            )
            print(f"  ✓ 6 estados cubiertos (Café) o 3 (BiciFix)")

            # ── BranchProducts ───────────────────────────
            bps = (
                db.query(BranchProduct)
                .filter(BranchProduct.tenant_id == str(t.id))
                .all()
            )
            print(f"  Inventario: {len(bps)} BranchProduct(s)")
            for bp in bps:
                p = db.get(Product, bp.product_id)
                b = db.get(Branch, bp.branch_id)
                flag = ""
                if bp.stock == 0:
                    flag = " [SIN STOCK]"
                elif bp.stock < bp.low_stock_threshold:
                    flag = " [BAJO]"
                print(f"    • {b.code:8s} | {p.sku:10s} {p.name:24s} "
                      f"stock={bp.stock:3d} thr={bp.low_stock_threshold:3d}{flag}")

        print("\n✅ Verificación de demo data OK")
    finally:
        db.close()


if __name__ == "__main__":
    main()
