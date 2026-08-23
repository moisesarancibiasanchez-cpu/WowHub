"""Seed — datos demo para WowHub.

Crea 2 tenants (Café Norte y BiciFix) con productos, categorías, promos, QRs,
landing config, pedidos (Pedidos + Pipeline) e inventario por sucursal.
Idempotente: si ya existen, no duplica.

Uso:
    python -m app.seed            # crea demo
    python -m app.seed --reset    # borra todo y recrea
"""
import sys
from datetime import datetime, timezone, timedelta
from uuid import UUID

from app.database import SessionLocal, init_db, engine
from app.database import Base
from app.models import (
    User, Tenant, TenantMembership, Branch, Category, Product,
    Customer, Promotion, QrCode, LandingConfig,
    Order, OrderItem, OrderStatus, BranchProduct,
)
from app.models.tenant import Industry, TenantPlan, TenantStatus
from app.models.user import UserRole
from app.models.product import ProductStatus
from app.models.promotion import PromotionType, DiscountType
from app.models.qr import QrTarget
from app.security import hash_password


# ── Helpers para construir pedidos demo ─────────────────────────────
def _make_order(*, db, tenant_id, branch_id, number, status, source,
                customer_name, customer_phone, customer_email,
                customer_id=None, items, notes=None,
                shipping_cents=0, discount_cents=0, tax_cents=0,
                days_ago=0):
    """Crea un Order + sus OrderItems (snapshots) con totales calculados."""
    subtotal = sum(p["unit_price_cents"] * p["quantity"] for p in items)
    total = subtotal + shipping_cents + tax_cents - discount_cents
    created = datetime.now(timezone.utc) - timedelta(days=days_ago, hours=2)
    order = Order(
        tenant_id=tenant_id, branch_id=branch_id,
        number=number, status=status, source=source,
        customer_id=customer_id,
        customer_name=customer_name, customer_phone=customer_phone,
        customer_email=customer_email,
        subtotal_cents=subtotal, discount_cents=discount_cents,
        shipping_cents=shipping_cents, tax_cents=tax_cents,
        total_cents=total, currency="CLP",
        notes=notes,
    )
    db.add(order); db.flush()
    for p in items:
        db.add(OrderItem(
            order_id=str(order.id), product_id=p["product_id"],
            product_name=p["name"], product_sku=p["sku"],
            product_image=p.get("image"),
            quantity=p["quantity"],
            unit_price_cents=p["unit_price_cents"],
            total_cents=p["unit_price_cents"] * p["quantity"],
        ))
    return order


def reset():
    print("⚠️  Borrando todas las tablas...")
    Base.metadata.drop_all(bind=engine)
    init_db()
    print("✓ Tablas recreadas")


def seed():
    init_db()
    db = SessionLocal()
    try:
        # ── Usuario demo ─────────────────────────────────
        if not db.query(User).filter(User.email == "maria@cafenorte.cl").first():
            user = User(
                email="maria@cafenorte.cl",
                password_hash=hash_password("demo1234"),
                full_name="María González",
                phone="+56 9 1234 5678",
                default_role=UserRole.OWNER,
            )
            db.add(user)
            db.flush()
            print(f"✓ Usuario demo: {user.email} / demo1234")
        else:
            user = db.query(User).filter(User.email == "maria@cafenorte.cl").first()
            print(f"  Usuario ya existe: {user.email}")

        # ── Tenant 1: Café Norte ─────────────────────────
        if not db.query(Tenant).filter(Tenant.slug == "cafe-norte").first():
            t1 = Tenant(
                slug="cafe-norte",
                legal_name="Café Norte SpA",
                display_name="Café Norte",
                industry=Industry.GASTRO,
                plan=TenantPlan.GROW,
                status=TenantStatus.ACTIVE,
                country="CL",
                currency="CLP",
                locale="es-CL",
                timezone="America/Santiago",
            )
            db.add(t1); db.flush()
            db.add(TenantMembership(
                user_id=str(user.id), tenant_id=str(t1.id),
                role=UserRole.OWNER, is_owner=True, is_active=True,
            ))
            # Branch
            db.add(Branch(
                tenant_id=str(t1.id),
                name="Local Centro",
                code="CENTRO",
                address="Av. Libertador 1234",
                city="Santiago",
                region="RM",
                phone="+56 2 2345 6789",
                is_main=True,
                hours={"Lun-Vie": "8:00 - 20:00", "Sáb": "9:00 - 18:00"},
            ))
            # Categorías
            cats = {
                "cafes": Category(tenant_id=str(t1.id), name="Cafés", slug="cafes", position=1, icon="☕"),
                "te": Category(tenant_id=str(t1.id), name="Tés e infusiones", slug="tes", position=2, icon="🍵"),
                "pasteleria": Category(tenant_id=str(t1.id), name="Pastelería", slug="pasteleria", position=3, icon="🥐"),
                "sandwiches": Category(tenant_id=str(t1.id), name="Sándwiches", slug="sandwiches", position=4, icon="🥪"),
            }
            for c in cats.values():
                db.add(c)
            db.flush()
            # Productos
            prods = [
                Product(tenant_id=str(t1.id), sku="ESP-001", name="Espresso", slug="espresso",
                        short_description="Café espresso tradicional, 30ml.", price_cents=1500,
                        category_id=str(cats["cafes"].id), status=ProductStatus.ACTIVE, is_featured=True,
                        image_url="https://images.unsplash.com/photo-1510707577719-ae7c14805e3a?w=400"),
                Product(tenant_id=str(t1.id), sku="CAP-001", name="Cappuccino", slug="cappuccino",
                        short_description="Espresso con leche espumada y cocoa.", price_cents=2800,
                        compare_at_cents=3200, category_id=str(cats["cafes"].id),
                        status=ProductStatus.ACTIVE, is_featured=True,
                        image_url="https://images.unsplash.com/photo-1572442388796-11668a67e53d?w=400"),
                Product(tenant_id=str(t1.id), sku="LAT-001", name="Latte", slug="latte",
                        short_description="Espresso con leche vaporizada.", price_cents=2900,
                        category_id=str(cats["cafes"].id), status=ProductStatus.ACTIVE,
                        image_url="https://images.unsplash.com/photo-1561882468-9110e03e0f78?w=400"),
                Product(tenant_id=str(t1.id), sku="MOC-001", name="Mochaccino", slug="mochaccino",
                        short_description="Cappuccino con chocolate.", price_cents=3200,
                        category_id=str(cats["cafes"].id), status=ProductStatus.ACTIVE,
                        image_url="https://images.unsplash.com/photo-1578314675229-23d3e2231a04?w=400"),
                Product(tenant_id=str(t1.id), sku="TE-MATCHA", name="Matcha Latte", slug="matcha-latte",
                        short_description="Té matcha con leche de almendras.", price_cents=3500,
                        category_id=str(cats["te"].id), status=ProductStatus.ACTIVE, is_featured=True,
                        image_url="https://images.unsplash.com/photo-1536013455834-d2cea4bb8e15?w=400"),
                Product(tenant_id=str(t1.id), sku="TE-VERDE", name="Té Verde", slug="te-verde",
                        short_description="Té verde Sencha, 300ml.", price_cents=2200,
                        category_id=str(cats["te"].id), status=ProductStatus.ACTIVE,
                        image_url="https://images.unsplash.com/photo-1597481499750-3e6b22637e12?w=400"),
                Product(tenant_id=str(t1.id), sku="CRU-001", name="Croissant", slug="croissant",
                        short_description="Croissant de mantequilla recién horneado.", price_cents=1800,
                        category_id=str(cats["pasteleria"].id), status=ProductStatus.ACTIVE, is_featured=True,
                        image_url="https://images.unsplash.com/photo-1555507036-ab1f4038808a?w=400"),
                Product(tenant_id=str(t1.id), sku="TOR-001", name="Torta de Chocolate", slug="torta-chocolate",
                        short_description="Porción de torta húmeda de chocolate.", price_cents=3500,
                        category_id=str(cats["pasteleria"].id), status=ProductStatus.ACTIVE,
                        image_url="https://images.unsplash.com/photo-1606313564200-e75d5e30476c?w=400"),
                Product(tenant_id=str(t1.id), sku="SAN-001", name="Sándwich de Pollo", slug="sandwich-pollo",
                        short_description="Pollo grill, palta, tomate, mayo de la casa.", price_cents=4500,
                        category_id=str(cats["sandwiches"].id), status=ProductStatus.ACTIVE,
                        image_url="https://images.unsplash.com/photo-1528735602780-2552fd46c7af?w=400"),
                Product(tenant_id=str(t1.id), sku="SAN-002", name="Sándwich Veggie", slug="sandwich-veggie",
                        short_description="Queso de cabra, espinaca, tomate seco, pesto.", price_cents=4200,
                        category_id=str(cats["sandwiches"].id), status=ProductStatus.ACTIVE,
                        image_url="https://images.unsplash.com/photo-1509722747041-616f39b57569?w=400"),
            ]
            for p in prods:
                db.add(p)
            db.flush()
            # Promos
            now = datetime.now(timezone.utc)
            db.add(Promotion(
                tenant_id=str(t1.id), name="20% OFF en Cafés",
                description="Todos los cafés con 20% de descuento.",
                code="CAFE20",
                promo_type=PromotionType.PERCENT, discount_type=DiscountType.PERCENT,
                discount_value=20, is_active=True, is_public=True,
                starts_at=now, ends_at=now + timedelta(days=30),
                applies_to_all=False, category_ids=[str(cats["cafes"].id)],
                badge_text="-20%", color="#ff6b6b",
            ))
            db.add(Promotion(
                tenant_id=str(t1.id), name="2x1 en Pastelería",
                description="Lleva 2 pasteles y paga 1. Solo los viernes.",
                code="VIERNES2X1",
                promo_type=PromotionType.BUY_X_GET_Y,
                discount_type=DiscountType.PERCENT, discount_value=50,
                is_active=True, is_public=True, priority=10,
                applies_to_all=False, category_ids=[str(cats["pasteleria"].id)],
                badge_text="2x1", color="#00d4a8",
            ))
            # QR
            db.add(QrCode(
                tenant_id=str(t1.id), label="Mostrador Centro",
                short_code="mostrador01", target_type=QrTarget.CATALOG,
            ))
            db.add(QrCode(
                tenant_id=str(t1.id), label="Mesa 1",
                short_code="mesa001", target_type=QrTarget.CATALOG,
            ))
            # Landing
            db.add(LandingConfig(
                tenant_id=str(t1.id),
                hero_title="Café de especialidad en Santiago",
                hero_subtitle="Granos de origen, tostado en casa. Ven a probar nuestro nuevo Latte de matcha.",
                hero_image_url="https://images.unsplash.com/photo-1453614512568-c4024d13c247?w=1200",
                hero_cta_text="Ver el catálogo",
                brand_color="#7c5cff",
                accent_color="#00d4a8",
                contact_whatsapp="+56912345678",
                contact_phone="+56 2 2345 6789",
                contact_email="hola@cafenorte.cl",
                contact_address="Av. Libertador 1234, Santiago",
                social_instagram="@cafenorte",
                social_facebook="https://facebook.com/cafenorte",
                seo_title="Café Norte — Café de especialidad en Santiago",
                seo_description="Granos de origen, tostado en casa, y los mejores pasteles de la ciudad.",
            ))
            print(f"✓ Tenant: {t1.slug} ({len(prods)} productos, 2 promos, 2 QRs)")
        else:
            print("  Tenant cafe-norte ya existe")

        # ── Tenant 2: BiciFix ────────────────────────────
        if not db.query(Tenant).filter(Tenant.slug == "bicifix").first():
            t2 = Tenant(
                slug="bicifix",
                legal_name="BiciFix Repuestos Ltda",
                display_name="BiciFix",
                industry=Industry.RETAIL,
                plan=TenantPlan.FREE,
                status=TenantStatus.TRIAL,
                country="CL",
            )
            db.add(t2); db.flush()
            db.add(TenantMembership(
                user_id=str(user.id), tenant_id=str(t2.id),
                role=UserRole.OWNER, is_owner=True, is_active=True,
            ))
            db.add(Branch(
                tenant_id=str(t2.id), name="Casa Matriz", code="MATRIZ",
                address="Av. Las Bicis 456", city="Providencia", is_main=True,
                hours={"Lun-Sáb": "10:00 - 19:00"},
            ))
            cat_rep = Category(tenant_id=str(t2.id), name="Repuestos", slug="repuestos", position=1, icon="🔧")
            cat_acc = Category(tenant_id=str(t2.id), name="Accesorios", slug="accesorios", position=2, icon="🎒")
            db.add(cat_rep); db.add(cat_acc); db.flush()
            db.add(Product(
                tenant_id=str(t2.id), sku="CAM-001", name="Cámara 29''", slug="camara-29",
                short_description="Cámara para rueda 29 pulgadas.", price_cents=8900,
                category_id=str(cat_rep.id), status=ProductStatus.ACTIVE,
            ))
            db.add(Product(
                tenant_id=str(t2.id), sku="CAS-001", name="Casco adulto", slug="casco-adulto",
                short_description="Casco certificado, ajustable.", price_cents=18900,
                compare_at_cents=22000, category_id=str(cat_acc.id),
                status=ProductStatus.ACTIVE, is_featured=True,
            ))
            db.add(QrCode(
                tenant_id=str(t2.id), label="Vidriera",
                short_code="vidriera", target_type=QrTarget.CATALOG,
            ))
            db.add(LandingConfig(
                tenant_id=str(t2.id),
                hero_title="Repuestos y accesorios para tu bici",
                hero_subtitle="Todo lo que necesitas para mantener tu bicicleta a punto.",
                brand_color="#ffb454", accent_color="#7c5cff",
                contact_whatsapp="+56987654321",
            ))
            print(f"✓ Tenant: {t2.slug} (2 productos, 1 QR)")
        else:
            print("  Tenant bicifix ya existe")

        # ── Clientes demo para Café Norte ────────────────
        cafe = db.query(Tenant).filter(Tenant.slug == "cafe-norte").first()
        if cafe and not db.query(Customer).filter(Customer.tenant_id == str(cafe.id)).first():
            db.add(Customer(
                tenant_id=str(cafe.id), full_name="Juan Pérez",
                email="juan@example.com", phone="+56 9 1111 2222",
                city="Santiago", total_orders=5, total_spent_cents=14500, points=145,
            ))
            db.add(Customer(
                tenant_id=str(cafe.id), full_name="Ana Silva",
                email="ana@example.com", phone="+56 9 3333 4444",
                city="Las Condes", total_orders=2, total_spent_cents=6300, points=63,
            ))
            print("✓ 2 clientes demo")

        # ════════════════════════════════════════════════════════
        # GESTIÓN INTERNA — Pedidos (lista) + Pipeline (Kanban)
        # ════════════════════════════════════════════════════════
        # Los mismos Orders se renderizan en 2 vistas:
        #   • /dashboard/orders    → lista filtrable
        #   • /dashboard/pipeline  → Kanban con 6 columnas
        # Por eso sembramos 2 pedidos por cada uno de los 6 estados,
        # distribuidos en los últimos 30 días, con items reales.
        if not db.query(Order).first():
            now = datetime.now(timezone.utc)

            # ── Café Norte ─────────────────────────────────
            cafe = db.query(Tenant).filter(Tenant.slug == "cafe-norte").first()
            if cafe:
                cafe_branch = db.query(Branch).filter(
                    Branch.tenant_id == str(cafe.id),
                    Branch.code == "CENTRO",
                ).first()
                # Productos por SKU (lookup rápido)
                cafe_prods = {
                    p.sku: p for p in
                    db.query(Product).filter(Product.tenant_id == str(cafe.id)).all()
                }
                # Clientes del tenant
                cafe_custs = db.query(Customer).filter(
                    Customer.tenant_id == str(cafe.id)
                ).all()
                juan = next((c for c in cafe_custs if "Juan" in c.full_name), None)
                ana = next((c for c in cafe_custs if "Ana" in c.full_name), None)

                def _item(sku, qty):
                    """Snapshot de un producto del catálogo."""
                    p = cafe_prods[sku]
                    return {
                        "product_id": str(p.id), "sku": p.sku,
                        "name": p.name, "image": p.image_url,
                        "unit_price_cents": p.price_cents, "quantity": qty,
                    }

                # Genera un número legible: CAF-YYYYMMDD-NNNN
                def _num(i):
                    return f"CAF-{now.strftime('%Y%m%d')}-{i:04d}"

                # 12 pedidos, 2 por estado
                seed_orders = [
                    # PENDING
                    {
                        "status": OrderStatus.PENDING, "source": "web",
                        "customer_name": juan.full_name if juan else "Juan Pérez",
                        "customer_phone": juan.phone if juan else "+56 9 1111 2222",
                        "customer_email": juan.email if juan else "juan@example.com",
                        "customer_id": str(juan.id) if juan else None,
                        "items": [_item("CAP-001", 1), _item("CRU-001", 2)],
                        "notes": "Para llevar, sin azúcar.",
                        "days_ago": 0, "i": 1,
                    },
                    {
                        "status": OrderStatus.PENDING, "source": "qr",
                        "customer_name": "Visitante QR", "customer_phone": "+56 9 5555 0001",
                        "customer_email": None, "customer_id": None,
                        "items": [_item("LAT-001", 1), _item("TOR-001", 1)],
                        "days_ago": 0, "i": 2,
                    },
                    # CONFIRMED
                    {
                        "status": OrderStatus.CONFIRMED, "source": "web",
                        "customer_name": ana.full_name if ana else "Ana Silva",
                        "customer_phone": ana.phone if ana else "+56 9 3333 4444",
                        "customer_email": ana.email if ana else "ana@example.com",
                        "customer_id": str(ana.id) if ana else None,
                        "items": [_item("CAP-001", 2), _item("MOC-001", 1)],
                        "notes": "Pidió extra cocoa.",
                        "days_ago": 1, "i": 3,
                    },
                    {
                        "status": OrderStatus.CONFIRMED, "source": "pos",
                        "customer_name": "Cliente Mostrador", "customer_phone": None,
                        "customer_email": None, "customer_id": None,
                        "items": [_item("ESP-001", 2), _item("SAN-001", 1)],
                        "days_ago": 1, "i": 4,
                    },
                    # PREPARING
                    {
                        "status": OrderStatus.PREPARING, "source": "qr",
                        "customer_name": juan.full_name if juan else "Juan Pérez",
                        "customer_phone": juan.phone if juan else "+56 9 1111 2222",
                        "customer_email": juan.email if juan else "juan@example.com",
                        "customer_id": str(juan.id) if juan else None,
                        "items": [_item("TE-MATCHA", 2), _item("CRU-001", 1)],
                        "days_ago": 2, "i": 5,
                    },
                    {
                        "status": OrderStatus.PREPARING, "source": "web",
                        "customer_name": "Carla Mendoza", "customer_phone": "+56 9 7777 8888",
                        "customer_email": "carla@example.com", "customer_id": None,
                        "items": [_item("LAT-001", 3), _item("SAN-002", 2)],
                        "discount_cents": 500, "notes": "Descuento cliente VIP.",
                        "days_ago": 2, "i": 6,
                    },
                    # READY
                    {
                        "status": OrderStatus.READY, "source": "pos",
                        "customer_name": ana.full_name if ana else "Ana Silva",
                        "customer_phone": ana.phone if ana else "+56 9 3333 4444",
                        "customer_email": ana.email if ana else "ana@example.com",
                        "customer_id": str(ana.id) if ana else None,
                        "items": [_item("CAP-001", 1), _item("TE-MATCHA", 1),
                                  _item("TOR-001", 1)],
                        "days_ago": 0, "i": 7,
                    },
                    {
                        "status": OrderStatus.READY, "source": "web",
                        "customer_name": "Diego Rojas", "customer_phone": "+56 9 6666 5555",
                        "customer_email": "diego@example.com", "customer_id": None,
                        "items": [_item("LAT-001", 2), _item("SAN-001", 1)],
                        "days_ago": 0, "i": 8,
                    },
                    # DELIVERED
                    {
                        "status": OrderStatus.DELIVERED, "source": "web",
                        "customer_name": juan.full_name if juan else "Juan Pérez",
                        "customer_phone": juan.phone if juan else "+56 9 1111 2222",
                        "customer_email": juan.email if juan else "juan@example.com",
                        "customer_id": str(juan.id) if juan else None,
                        "items": [_item("ESP-001", 1), _item("TOR-001", 1)],
                        "days_ago": 7, "i": 9,
                    },
                    {
                        "status": OrderStatus.DELIVERED, "source": "qr",
                        "customer_name": "Mesa 3", "customer_phone": None,
                        "customer_email": None, "customer_id": None,
                        "items": [_item("CRU-001", 2), _item("TE-MATCHA", 1)],
                        "days_ago": 10, "i": 10,
                    },
                    # CANCELED
                    {
                        "status": OrderStatus.CANCELED, "source": "web",
                        "customer_name": "Pedro Soto", "customer_phone": "+56 9 4444 3333",
                        "customer_email": "pedro@example.com", "customer_id": None,
                        "items": [_item("LAT-001", 1), _item("SAN-001", 1)],
                        "notes": "Cancelado por timeout en el checkout.",
                        "days_ago": 5, "i": 11,
                    },
                    {
                        "status": OrderStatus.CANCELED, "source": "pos",
                        "customer_name": ana.full_name if ana else "Ana Silva",
                        "customer_phone": ana.phone if ana else "+56 9 3333 4444",
                        "customer_email": ana.email if ana else "ana@example.com",
                        "customer_id": str(ana.id) if ana else None,
                        "items": [_item("CAP-001", 2)],
                        "days_ago": 12, "i": 12,
                    },
                ]
                for o in seed_orders:
                    _make_order(
                        db=db, tenant_id=str(cafe.id),
                        branch_id=str(cafe_branch.id) if cafe_branch else None,
                        number=_num(o["i"]),
                        status=o["status"], source=o["source"],
                        customer_name=o["customer_name"],
                        customer_phone=o["customer_phone"],
                        customer_email=o["customer_email"],
                        customer_id=o.get("customer_id"),
                        items=o["items"], notes=o.get("notes"),
                        discount_cents=o.get("discount_cents", 0),
                        days_ago=o["days_ago"],
                    )
                print(f"✓ {len(seed_orders)} pedidos demo para Café Norte")

            # ── BiciFix ────────────────────────────────────
            bicifix = db.query(Tenant).filter(Tenant.slug == "bicifix").first()
            if bicifix:
                bf_branch = db.query(Branch).filter(
                    Branch.tenant_id == str(bicifix.id),
                    Branch.code == "MATRIZ",
                ).first()
                bf_prods = {
                    p.sku: p for p in
                    db.query(Product).filter(Product.tenant_id == str(bicifix.id)).all()
                }

                def _bf_item(sku, qty):
                    p = bf_prods[sku]
                    return {
                        "product_id": str(p.id), "sku": p.sku,
                        "name": p.name, "image": p.image_url,
                        "unit_price_cents": p.price_cents, "quantity": qty,
                    }

                def _bf_num(i):
                    return f"BFX-{now.strftime('%Y%m%d')}-{i:04d}"

                bf_orders = [
                    {"status": OrderStatus.PENDING, "source": "web",
                     "customer_name": "Luis Vargas", "customer_phone": "+56 9 2222 1111",
                     "customer_email": "luis@example.com", "customer_id": None,
                     "items": [_bf_item("CAM-001", 2)], "days_ago": 0, "i": 1},
                    {"status": OrderStatus.CONFIRMED, "source": "pos",
                     "customer_name": "Cliente Mostrador", "customer_phone": None,
                     "customer_email": None, "customer_id": None,
                     "items": [_bf_item("CAS-001", 1)], "days_ago": 1, "i": 2},
                    {"status": OrderStatus.DELIVERED, "source": "web",
                     "customer_name": "Marta León", "customer_phone": "+56 9 9999 0000",
                     "customer_email": "marta@example.com", "customer_id": None,
                     "items": [_bf_item("CAM-001", 1), _bf_item("CAS-001", 1)],
                     "days_ago": 8, "i": 3},
                    {"status": OrderStatus.DELIVERED, "source": "pos",
                     "customer_name": "Cliente Mostrador", "customer_phone": None,
                     "customer_email": None, "customer_id": None,
                     "items": [_bf_item("CAS-001", 1)], "days_ago": 15, "i": 4},
                ]
                for o in bf_orders:
                    _make_order(
                        db=db, tenant_id=str(bicifix.id),
                        branch_id=str(bf_branch.id) if bf_branch else None,
                        number=_bf_num(o["i"]),
                        status=o["status"], source=o["source"],
                        customer_name=o["customer_name"],
                        customer_phone=o["customer_phone"],
                        customer_email=o["customer_email"],
                        customer_id=o.get("customer_id"),
                        items=o["items"], days_ago=o["days_ago"],
                    )
                print(f"✓ {len(bf_orders)} pedidos demo para BiciFix")

        # ════════════════════════════════════════════════════════
        # GESTIÓN INTERNA — Inventario (stock por sucursal)
        # ════════════════════════════════════════════════════════
        # Sembramos BranchProduct para que la página de Inventario tenga
        # algo que mostrar. Algunos productos quedan con stock bajo o
        # en cero para que se disparen las alertas de reposición.
        if not db.query(BranchProduct).first():
            cafe = db.query(Tenant).filter(Tenant.slug == "cafe-norte").first()
            if cafe:
                cafe_branch = db.query(Branch).filter(
                    Branch.tenant_id == str(cafe.id),
                    Branch.code == "CENTRO",
                ).first()
                if cafe_branch:
                    # (sku, stock, threshold) — diseño de niveles:
                    #   • 3 productos con stock BAJO → alerta "Reposición"
                    #   • 1 producto SIN STOCK  → alerta crítica
                    #   • resto saludable
                    inv_seed = [
                        ("ESP-001", 45, 10),  # Espresso — OK
                        ("CAP-001", 2, 8),   # Cappuccino — BAJO
                        ("LAT-001", 18, 5),   # Latte — OK
                        ("MOC-001", 3, 6),   # Mochaccino — BAJO
                        ("TE-MATCHA", 22, 5),  # Matcha — OK
                        ("TE-VERDE", 0, 4),  # Té Verde — SIN STOCK
                        ("CRU-001", 4, 10),  # Croissant — BAJO
                        ("TOR-001", 12, 4),  # Torta — OK
                        ("SAN-001", 8, 6),   # Sándwich Pollo — OK
                        ("SAN-002", 15, 6),  # Sándwich Veggie — OK
                    ]
                    created = 0
                    for sku, stock, threshold in inv_seed:
                        p = db.query(Product).filter(
                            Product.tenant_id == str(cafe.id),
                            Product.sku == sku,
                        ).first()
                        if not p:
                            continue
                        db.add(BranchProduct(
                            tenant_id=str(cafe.id),
                            branch_id=str(cafe_branch.id),
                            product_id=str(p.id),
                            stock=stock,
                            low_stock_threshold=threshold,
                        ))
                        created += 1
                    print(f"✓ {created} BranchProduct para Café Norte (Local Centro)")

            bicifix = db.query(Tenant).filter(Tenant.slug == "bicifix").first()
            if bicifix:
                bf_branch = db.query(Branch).filter(
                    Branch.tenant_id == str(bicifix.id),
                    Branch.code == "MATRIZ",
                ).first()
                if bf_branch:
                    bf_inv = [
                        ("CAM-001", 25, 5),  # Cámara — OK
                        ("CAS-001", 1, 3),   # Casco — BAJO (alerta)
                    ]
                    created = 0
                    for sku, stock, threshold in bf_inv:
                        p = db.query(Product).filter(
                            Product.tenant_id == str(bicifix.id),
                            Product.sku == sku,
                        ).first()
                        if not p:
                            continue
                        db.add(BranchProduct(
                            tenant_id=str(bicifix.id),
                            branch_id=str(bf_branch.id),
                            product_id=str(p.id),
                            stock=stock,
                            low_stock_threshold=threshold,
                        ))
                        created += 1
                    print(f"✓ {created} BranchProduct para BiciFix (Casa Matriz)")

        db.commit()
        print("\n✅ Seed completo. URLs de demo:")
        print("   • https://.../u/cafe-norte")
        print("   • https://.../u/bicifix")
        print("   • Login: maria@cafenorte.cl / demo1234")
    finally:
        db.close()


if __name__ == "__main__":
    if "--reset" in sys.argv:
        reset()
    seed()
