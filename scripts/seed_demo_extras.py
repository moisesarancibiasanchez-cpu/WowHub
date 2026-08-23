"""Seed EXTRAS — ajustes complementarios para `scripts/seed_demo.py`.

Este script es ADITIVO: NO modifica el seed principal. Lo que hace es
ajustar la data ya creada para que las secciones que dependen de reglas
derivadas (no de filas en tablas) muestren contenido al primer login:

  • Notificaciones (🔔) — el `NotificationsEngine` calcula alertas en
    runtime mirando el estado de productos/pedidos/costos. Por defecto el
    seed_demo no dispara ninguna regla (todos los stocks > 5, ningún
    pedido PENDING > 24h). Acá ajustamos:

        N4 (critical) — sin stock
        N5 (warning)  — stock bajo
        N6 (warning)  — pedido PENDING viejo (>24h)

  • Inventario (▤) — además de `Product.stock`, el módulo soporta
    `BranchProduct` para stock multi-sucursal. Sembramos algunas filas
    para que la UI pueda alternar entre "stock global" y "stock por
    sucursal" en el demo.

Idempotente: si ya corrió antes, no duplica (mismo set de SKUs/branch
siempre → detecta por combinación única).

Uso:
    # 1) Primero correr el seed principal (crea el tenant + productos + pedidos)
    python -m scripts.seed_demo

    # 2) Después correr este script para ajustar inventario + notificaciones
    python -m scripts.seed_demo_extras
"""
from __future__ import annotations

import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

# Asegurar import del paquete app
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.branch import Branch
from app.models.branch_product import BranchProduct
from app.models.order import Order, OrderStatus
from app.models.product import Product
from app.models.tenant import Tenant

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("seed_demo_extras")

DEMO_TENANT_SLUG = "el-rincon"


# ─── Helpers ─────────────────────────────────────────────────
def _get_tenant(db: Session) -> Tenant:
    t = db.execute(
        select(Tenant).where(Tenant.slug == DEMO_TENANT_SLUG)
    ).scalar_one_or_none()
    if not t:
        raise SystemExit(
            f"❌ Tenant '{DEMO_TENANT_SLUG}' no existe. "
            "Corré primero: python -m scripts.seed_demo"
        )
    return t


def _get_branch(db: Session, tenant: Tenant) -> Branch:
    b = db.execute(
        select(Branch).where(
            Branch.tenant_id == str(tenant.id),
            Branch.code == "SCL-01",
        )
    ).scalar_one_or_none()
    if not b:
        raise SystemExit(
            f"❌ Branch 'SCL-01' no existe para tenant {tenant.slug}. "
            "Corré primero: python -m scripts.seed_demo"
        )
    return b


# ─── 1) Ajustar stocks de productos ─────────────────────────
# SKUs del seed_demo.py que ajustamos:
#
#   • CROISSANT         → 0   (N4: critical — sin stock)
#   • TORTA-CHOCOLATE   → 2   (N5: warning — stock bajo, threshold 5)
#   • MUFFIN-ARANDANOS  → 4   (N5: warning — stock bajo, threshold 5)
#   • AVOCADO-TOAST     → 6   (N5: warning — stock bajo, threshold 5)
#   • SANDWICH-JAMON    → 14  (sin alerta — stock OK)
#   • (todos los demás)  → sin cambios
#
# Resultado esperado al consultar /api/v1/tenants/{id}/notifications/summary:
#   - 1 crítico (croissant)
#   - 3 warning (torta, muffin, avocado)
STOCK_ADJUSTMENTS = [
    # (sku, new_stock, new_threshold)
    ("PAS-001", 0, 5),     # Croissant  → out of stock (critical)
    ("PAS-002", 2, 5),     # Torta      → low stock (warning)
    ("PAS-003", 4, 5),     # Muffin     → low stock (warning)
    ("SAN-001", 6, 5),     # Avocado    → low stock (warning, stock > 0)
]


def _adjust_product_stocks(db: Session, tenant: Tenant) -> int:
    """Actualiza stock y low_stock_threshold de productos específicos.

    Idempotente: si el producto ya tiene el stock objetivo, no toca nada.
    """
    count = 0
    for sku, new_stock, new_threshold in STOCK_ADJUSTMENTS:
        p = db.execute(
            select(Product).where(
                Product.tenant_id == str(tenant.id),
                Product.sku == sku,
            )
        ).scalar_one_or_none()
        if not p:
            log.warning("  SKU %s no encontrado, saltando", sku)
            continue
        changed = False
        if p.stock != new_stock:
            log.info("  %s: stock %s → %s", sku, p.stock, new_stock)
            p.stock = new_stock
            changed = True
        if (p.low_stock_threshold or 0) != new_threshold:
            p.low_stock_threshold = new_threshold
            changed = True
        # Asegurar que track_inventory esté activo para que N4/N5 lo consideren
        if not p.track_inventory:
            p.track_inventory = True
            changed = True
        if changed:
            count += 1
    db.flush()
    log.info("✓ Productos ajustados (%d cambios)", count)
    return count


# ─── 2) Pedido PENDING > 24h para disparar N6 ───────────────
def _age_one_pending_order(db: Session, tenant: Tenant) -> int:
    """Mueve un pedido PENDING a hace 30h (para activar N6).

    Estrategia: agarra el pedido PENDING más reciente (o crea uno si no
    hay ninguno) y le ajusta `created_at` a 30h atrás.
    """
    target = db.execute(
        select(Order).where(
            Order.tenant_id == str(tenant.id),
            Order.status == OrderStatus.PENDING,
        ).order_by(Order.created_at.desc()).limit(1)
    ).scalar_one_or_none()

    if not target:
        log.warning("  No hay pedidos PENDING; saltando N6")
        return 0

    now = datetime.now(timezone.utc)
    new_created = now - timedelta(hours=30)
    if target.created_at and abs((target.created_at.replace(tzinfo=timezone.utc) - new_created).total_seconds()) < 60:
        log.info("  Pedido %s ya estaba viejo, no se toca", target.number)
        return 0
    log.info("  Pedido %s: created_at movido a hace 30h (era %s)", target.number, target.created_at)
    target.created_at = new_created
    target.updated_at = new_created
    db.flush()
    log.info("✓ Pedido PENDING envejecido para disparar N6")
    return 1


# ─── 3) BranchProduct: stock por sucursal ──────────────────
# Sembramos stock específico para la sucursal principal en algunos productos
# para que la UI de Inventario pueda mostrar la vista "por sucursal".
BRANCH_STOCK = [
    # (sku, stock, threshold)
    ("CAF-001", 200, 20),   # Espresso
    ("CAF-002", 150, 20),   # Cappuccino
    ("CAF-005",  10, 10),   # Cold Brew
    ("PAS-001",   0,  5),   # Croissant (sin stock en la sucursal también)
    ("SAN-001",   3,  5),   # Avocado Toast (stock bajo en sucursal)
]


def _seed_branch_stock(db: Session, tenant: Tenant, branch: Branch) -> int:
    """Crea filas de `BranchProduct` para el branch principal.

    Idempotente: si ya existe la fila (branch_id, product_id), no duplica.
    """
    count = 0
    for sku, stock, threshold in BRANCH_STOCK:
        p = db.execute(
            select(Product).where(
                Product.tenant_id == str(tenant.id),
                Product.sku == sku,
            )
        ).scalar_one_or_none()
        if not p:
            log.warning("  SKU %s no encontrado para branch_stock, saltando", sku)
            continue
        existing = db.execute(
            select(BranchProduct).where(
                BranchProduct.tenant_id == str(tenant.id),
                BranchProduct.branch_id == str(branch.id),
                BranchProduct.product_id == str(p.id),
            )
        ).scalar_one_or_none()
        if existing:
            # Actualizar in-place (idempotente)
            if existing.stock != stock or existing.low_stock_threshold != threshold:
                existing.stock = stock
                existing.low_stock_threshold = threshold
                count += 1
            continue
        bp = BranchProduct(
            id=uuid4(),
            tenant_id=str(tenant.id),
            branch_id=str(branch.id),
            product_id=str(p.id),
            stock=stock,
            low_stock_threshold=threshold,
        )
        db.add(bp)
        count += 1
    db.flush()
    log.info("✓ BranchProduct: %d filas creadas/actualizadas", count)
    return count


# ─── Main ───────────────────────────────────────────────────
def main() -> int:
    log.info("=" * 60)
    log.info("WowHub — Seed EXTRAS: ajuste para Notificaciones/Inventario")
    log.info("=" * 60)

    with SessionLocal() as db:
        try:
            tenant = _get_tenant(db)
            branch = _get_branch(db, tenant)
            log.info("Tenant: %s (%s)", tenant.slug, tenant.id)
            log.info("Branch: %s", branch.name)

            log.info("")
            log.info("─ 1) Ajustar stocks (disparar N4/N5) ─")
            _adjust_product_stocks(db, tenant)

            log.info("")
            log.info("─ 2) Envejecer pedido PENDING (disparar N6) ─")
            _age_one_pending_order(db, tenant)

            log.info("")
            log.info("─ 3) Sembrar BranchProduct (multi-sucursal) ─")
            _seed_branch_stock(db, tenant, branch)

            db.commit()
            log.info("")
            log.info("=" * 60)
            log.info("✅ Extras aplicados")
            log.info("=" * 60)
            log.info("")
            log.info("Notificaciones que debería ver el bell badge ahora:")
            log.info("  • 1 critical — 'Croissant' sin stock (N4)")
            log.info("  • 3 warning  — Torta/Muffin/Avocado con stock bajo (N5)")
            log.info("  • 1 warning  — Pedido PENDING con >24h (N6)")
            log.info("")
            log.info("Inventario: 5 productos tienen stock por sucursal")
            log.info("  (El módulo Inventario puede alternar entre vista global y por sucursal)")
            return 0
        except Exception as e:
            db.rollback()
            log.exception("❌ Error en extras: %s", e)
            return 1


if __name__ == "__main__":
    sys.exit(main())
