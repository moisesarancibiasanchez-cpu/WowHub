"""Seed — datos demo para WowHub.

Crea 2 tenants (Café Norte y BiciFix) con productos, categorías, promos, QRs
y landing config. Idempotente: si ya existen, no duplica.

Uso:
    python -m app.seed            # crea demo
    python -m app.seed --reset    # borra todo y recrea
"""
import sys
from uuid import UUID

from app.database import SessionLocal, init_db, engine
from app.database import Base
from app.models import (
    User, Tenant, TenantMembership, Branch, Category, Product,
    Customer, Promotion, QrCode, LandingConfig, Order,
)
from app.models.tenant import Industry, TenantPlan, TenantStatus
from app.models.user import UserRole
from app.models.product import ProductStatus
from app.models.promotion import PromotionType, DiscountType
from app.models.qr import QrTarget
from app.security import hash_password


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
            from datetime import datetime, timezone, timedelta
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
