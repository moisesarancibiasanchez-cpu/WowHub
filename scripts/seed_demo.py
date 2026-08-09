"""Seed demo para WowHub: carga un cliente de ejemplo completamente operativo.

Uso:
    # Local (SQLite default)
    python -m scripts.seed_demo

    # Producción (PostgreSQL en Railway)
    DATABASE_URL="postgresql://user:pass@host:port/railway" python -m scripts.seed_demo

Idempotente: si el tenant o el usuario ya existen, no los duplica;
sólo agrega lo que falte (products, customers, promotions, branches).

Crea un cliente demo "Cafetería El Rincón" (Santiago, Chile) con:
  - User:    demo@wowhub.app / demo1234
  - Tenant:  el-rincon
  - 1 branch, 4 categorías, 12 productos, 3 promociones, 5 clientes, 1 QR
"""
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

# Asegurar import del paquete app
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import SessionLocal, init_db
from app.models.branch import Branch
from app.models.category import Category
from app.models.customer import Customer
from app.models.landing import LandingConfig
from app.models.product import Product, ProductStatus
from app.models.promotion import DiscountType, Promotion, PromotionType
from app.models.qr import QrCode, QrTarget
from app.models.tenant import Industry, Tenant, TenantMembership, TenantPlan, TenantStatus
from app.models.user import User, UserRole
from app.security import hash_password

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("seed_demo")

# ─── Configuración del cliente demo ──────────────────────────
DEMO_EMAIL = "demo@wowhub.app"
DEMO_PASSWORD = "demo1234"
DEMO_FULL_NAME = "María González"
DEMO_PHONE = "+56 9 8765 4321"

DEMO_TENANT_SLUG = "el-rincon"
DEMO_TENANT_LEGAL = "Cafetería El Rincón SpA"
DEMO_TENANT_DISPLAY = "Cafetería El Rincón"
DEMO_COUNTRY = "CL"
DEMO_CURRENCY = "CLP"
DEMO_LOCALE = "es-CL"
DEMO_TIMEZONE = "America/Santiago"


def _get_or_create_user(db: Session) -> User:
    user = db.execute(
        select(User).where(User.email == DEMO_EMAIL)
    ).scalar_one_or_none()
    if user:
        log.info("✓ User ya existe: %s (%s)", user.email, user.id)
        return user
    user = User(
        id=uuid4(),
        email=DEMO_EMAIL,
        password_hash=hash_password(DEMO_PASSWORD),
        full_name=DEMO_FULL_NAME,
        phone=DEMO_PHONE,
        is_active=True,
        is_superuser=False,
        default_role=UserRole.OWNER,
    )
    db.add(user)
    db.flush()
    log.info("✓ User creado: %s", user.email)
    return user


def _get_or_create_tenant(db: Session) -> Tenant:
    tenant = db.execute(
        select(Tenant).where(Tenant.slug == DEMO_TENANT_SLUG)
    ).scalar_one_or_none()
    if tenant:
        log.info("✓ Tenant ya existe: %s (%s)", tenant.slug, tenant.id)
        return tenant
    tenant = Tenant(
        id=uuid4(),
        slug=DEMO_TENANT_SLUG,
        legal_name=DEMO_TENANT_LEGAL,
        display_name=DEMO_TENANT_DISPLAY,
        industry=Industry.GASTRO,
        plan=TenantPlan.PRO,
        status=TenantStatus.ACTIVE,
        country=DEMO_COUNTRY,
        locale=DEMO_LOCALE,
        currency=DEMO_CURRENCY,
        timezone=DEMO_TIMEZONE,
        wow_score=82,
        health_score=91,
        active_branches=1,
        settings={
            "demo": True,
            "seeded_at": datetime.now(timezone.utc).isoformat(),
        },
        is_active=True,
    )
    db.add(tenant)
    db.flush()
    log.info("✓ Tenant creado: %s (%s)", tenant.slug, tenant.id)
    return tenant


def _get_or_create_membership(db: Session, user: User, tenant: Tenant) -> TenantMembership:
    m = db.execute(
        select(TenantMembership).where(
            TenantMembership.user_id == str(user.id),
            TenantMembership.tenant_id == str(tenant.id),
        )
    ).scalar_one_or_none()
    if m:
        log.info("✓ Membership ya existe")
        return m
    m = TenantMembership(
        id=uuid4(),
        user_id=str(user.id),
        tenant_id=str(tenant.id),
        role=UserRole.OWNER,
        is_owner=True,
        is_active=True,
    )
    db.add(m)
    db.flush()
    log.info("✓ Membership creada (OWNER)")
    return m


# ─── Branch ─────────────────────────────────────────────────
def _get_or_create_branch(db: Session, tenant: Tenant) -> Branch:
    b = db.execute(
        select(Branch).where(
            Branch.tenant_id == str(tenant.id),
            Branch.code == "SCL-01",
        )
    ).scalar_one_or_none()
    if b:
        log.info("✓ Branch ya existe: %s", b.name)
        return b
    b = Branch(
        id=uuid4(),
        tenant_id=str(tenant.id),
        name="El Rincón — Centro",
        code="SCL-01",
        address="Av. Libertador 1234, Local 5",
        city="Santiago",
        region="Región Metropolitana",
        country=DEMO_COUNTRY,
        phone="+56 2 2345 6789",
        email="contacto@el-rincon.cl",
        lat=-33.4172,
        lng=-70.6066,
        hours={
            "lun-vie": "08:00-20:00",
            "sab": "09:00-21:00",
            "dom": "09:00-14:00",
        },
        is_main=True,
        is_active=True,
    )
    db.add(b)
    db.flush()
    log.info("✓ Branch creado: %s", b.name)
    return b


# ─── Categories ─────────────────────────────────────────────
CATEGORIES = [
    ("cafes", "Cafés", "☕", "#7c5cff", 1),
    ("bebidas-frias", "Bebidas frías", "🧊", "#00d4a8", 2),
    ("pasteleria", "Pastelería", "🥐", "#f59e0b", 3),
    ("sandwiches", "Sándwiches & Salados", "🥪", "#ef4444", 4),
]


def _get_or_create_categories(db: Session, tenant: Tenant) -> dict:
    out: dict = {}
    for slug, name, icon, color, pos in CATEGORIES:
        c = db.execute(
            select(Category).where(
                Category.tenant_id == str(tenant.id),
                Category.slug == slug,
            )
        ).scalar_one_or_none()
        if c:
            out[slug] = c
            continue
        c = Category(
            id=uuid4(),
            tenant_id=str(tenant.id),
            name=name,
            slug=slug,
            description=f"Categoría {name}",
            position=pos,
            is_active=True,
            icon=icon,
            color=color,
        )
        db.add(c)
        db.flush()
        out[slug] = c
    db.flush()
    log.info("✓ Categorías OK (%d)", len(out))
    return out


# ─── Products ───────────────────────────────────────────────
# price_cents está en centavos de CLP (1 CLP = 1 cent, sin decimales)
PRODUCTS = [
    # (sku, slug, name, short, cat_slug, price_cents, compare_at, stock, featured, tags)
    ("CAF-001", "espresso", "Espresso",          "Shot de café 100% arábica, intenso y aromático.",
     "cafes", 1800, None, 999, True,  ["clásico", "energía"]),
    ("CAF-002", "cappuccino", "Cappuccino",      "Espresso con leche texturizada y arte latte.",
     "cafes", 3200, 3800, 999, True,  ["clásico", "leche"]),
    ("CAF-003", "latte",      "Latte",           "Espresso suave con leche cremosa.",
     "cafes", 3200, None, 999, False, ["leche", "suave"]),
    ("CAF-004", "moka",       "Moka",            "Espresso, chocolate y leche batida.",
     "cafes", 3500, None, 999, False, ["chocolate"]),
    ("CAF-005", "cold-brew",  "Cold Brew 500ml", "Café infusionado en frío 16h, suave y bajo en acidez.",
     "cafes", 4200, 4800, 30, True,   ["frío", "vegano"]),
    ("BEB-001", "frappe-oreo", "Frappé de Oreo", "Café, helado, leche y Oreo triturado.",
     "bebidas-frias", 4500, None, 25, True, ["frío", "dulce"]),
    ("BEB-002", "limonada-jeng", "Limonada de Jengibre", "Limón, jengibre fresco y miel.",
     "bebidas-frias", 2900, None, 40, False, ["vegano", "sin-cafeína"]),
    ("BEB-003", "te-matcha", "Matcha Latte Frío", "Matcha ceremonial con leche de almendras.",
     "bebidas-frias", 3900, None, 20, True, ["matcha", "vegano"]),
    ("PAS-001", "croissant", "Croissant de mantequilla", "Hojaldre francés artesanal.",
     "pasteleria", 2200, None, 18, True, ["artesanal"]),
    ("PAS-002", "torta-chocolate", "Torta de chocolate (porción)", "Bizcocho húmedo con ganache.",
     "pasteleria", 3800, None, 12, True, ["sin-gluten-opcional"]),
    ("PAS-003", "muffin-arandanos", "Muffin de arándanos", "Esponjoso, con arándanos frescos.",
     "pasteleria", 2500, None, 24, False, ["frutal"]),
    ("SAN-001", "avocado-toast", "Avocado Toast", "Pan de masa madre, palta, huevo pochado y semillas.",
     "sandwiches", 4900, 5500, 15, True, ["brunch", "vegano-opcional"]),
    ("SAN-002", "jamon-queso", "Sándwich de jamón y queso", "En pan ciabatta, al horno.",
     "sandwiches", 3800, None, 20, False, ["clásico"]),
]


def _get_or_create_products(db: Session, tenant: Tenant, cats: dict) -> list:
    out = []
    for sku, slug, name, short, cat_slug, price, compare, stock, featured, tags in PRODUCTS:
        p = db.execute(
            select(Product).where(
                Product.tenant_id == str(tenant.id),
                Product.sku == sku,
            )
        ).scalar_one_or_none()
        if p:
            out.append(p)
            continue
        p = Product(
            id=uuid4(),
            tenant_id=str(tenant.id),
            sku=sku,
            slug=slug,
            name=name,
            short_description=short,
            description=f"{short} Elaborado diariamente con ingredientes de primera calidad.",
            category_id=str(cats[cat_slug].id),
            price_cents=price,
            compare_at_cents=compare,
            cost_cents=int(price * 0.35),
            track_inventory=True,
            stock=stock,
            low_stock_threshold=5,
            image_url=f"https://picsum.photos/seed/{sku}/600/400",
            gallery=[],
            tags=tags,
            status=ProductStatus.ACTIVE,
            is_featured=featured,
            position=len(out) + 1,
            view_count=0,
            sold_count=0,
        )
        db.add(p)
        db.flush()
        out.append(p)
    log.info("✓ Productos OK (%d)", len(out))
    return out


# ─── Promotions ─────────────────────────────────────────────
def _get_or_create_promotions(db: Session, tenant: Tenant, products: list) -> list:
    out = []
    now = datetime.now(timezone.utc)
    end = now + timedelta(days=30)
    prods_by_sku = {p.sku: p for p in products}

    promos = [
        {
            "name": "20% OFF en Cafés después de las 15h",
            "code": "CAFEPMA",
            "promo_type": PromotionType.PERCENT,
            "discount_type": DiscountType.PERCENT,
            "discount_value": 20,
            "product_skus": ["CAF-001", "CAF-002", "CAF-003", "CAF-004"],
            "badge_text": "20% OFF",
            "color": "#7c5cff",
            "min_purchase_cents": 0,
            "is_public": True,
            "priority": 10,
        },
        {
            "name": "2x1 en Pastelería los martes",
            "code": None,
            "promo_type": PromotionType.BUY_X_GET_Y,
            "discount_type": DiscountType.PERCENT,
            "discount_value": 50,
            "product_skus": ["PAS-001", "PAS-002", "PAS-003"],
            "badge_text": "2x1",
            "color": "#f59e0b",
            "min_purchase_cents": 0,
            "is_public": True,
            "priority": 5,
        },
        {
            "name": "$1.000 OFF en Sándwiches",
            "code": "ALMUERZO",
            "promo_type": PromotionType.FIXED,
            "discount_type": DiscountType.FIXED,
            "discount_value": 1000,
            "product_skus": ["SAN-001", "SAN-002"],
            "badge_text": "-$1.000",
            "color": "#ef4444",
            "min_purchase_cents": 3000,
            "is_public": True,
            "priority": 7,
        },
    ]

    for spec in promos:
        p = db.execute(
            select(Promotion).where(
                Promotion.tenant_id == str(tenant.id),
                Promotion.name == spec["name"],
            )
        ).scalar_one_or_none()
        if p:
            out.append(p)
            continue
        ids = [str(prods_by_sku[s].id) for s in spec["product_skus"] if s in prods_by_sku]
        p = Promotion(
            id=uuid4(),
            tenant_id=str(tenant.id),
            name=spec["name"],
            description=spec["name"] + " — Válido hasta agotar stock.",
            code=spec["code"],
            promo_type=spec["promo_type"],
            discount_type=spec["discount_type"],
            discount_value=spec["discount_value"],
            min_purchase_cents=spec["min_purchase_cents"],
            max_discount_cents=spec.get("max_discount_cents"),
            starts_at=now - timedelta(days=1),
            ends_at=end,
            usage_limit=None,
            usage_limit_per_customer=5,
            used_count=0,
            applies_to_all=False,
            product_ids=ids,
            category_ids=[],
            is_active=True,
            is_public=spec["is_public"],
            priority=spec["priority"],
            badge_text=spec["badge_text"],
            color=spec["color"],
            image_url=None,
        )
        db.add(p)
        db.flush()
        out.append(p)
    log.info("✓ Promociones OK (%d)", len(out))
    return out


# ─── Customers ──────────────────────────────────────────────
CUSTOMERS = [
    # (full_name, email, phone, total_orders, total_spent_cents, points, tags)
    ("Camila Soto",     "camila.soto@gmail.com",    "+56 9 9111 2233", 8,  38400, 120, ["vip", "frecuente"]),
    ("Diego Vargas",    "diego.vargas@hotmail.com", "+56 9 9222 3344", 3,  12600,  40, ["nuevo"]),
    ("Fernanda López",  "fer.lopez@gmail.com",      "+56 9 9333 4455", 12, 64200, 240, ["vip", "vegano"]),
    ("Matías Rojas",    "matias.rojas@gmail.com",   "+56 9 9444 5566", 1,   4500,  10, ["nuevo"]),
    ("Valentina Cruz",  "vale.cruz@outlook.com",    "+56 9 9555 6677", 5,  22000,  70, ["frecuente"]),
]


def _get_or_create_customers(db: Session, tenant: Tenant) -> list:
    out = []
    for full, email, phone, orders, spent, pts, tags in CUSTOMERS:
        c = db.execute(
            select(Customer).where(
                Customer.tenant_id == str(tenant.id),
                Customer.email == email,
            )
        ).scalar_one_or_none()
        if c:
            out.append(c)
            continue
        c = Customer(
            id=uuid4(),
            tenant_id=str(tenant.id),
            full_name=full,
            email=email,
            phone=phone,
            address=None,
            city="Santiago",
            notes=None,
            total_orders=orders,
            total_spent_cents=spent,
            points=pts,
            last_order_at=datetime.now(timezone.utc).isoformat(),
            tags=tags,
            accepts_marketing=True,
            is_active=True,
        )
        db.add(c)
        db.flush()
        out.append(c)
    log.info("✓ Clientes OK (%d)", len(out))
    return out


# ─── QR Code ────────────────────────────────────────────────
def _get_or_create_qr(db: Session, tenant: Tenant, branch: Branch) -> QrCode:
    code = f"ELRINCON-{branch.code}"
    q = db.execute(
        select(QrCode).where(QrCode.short_code == code)
    ).scalar_one_or_none()
    if q:
        log.info("✓ QR ya existe: %s", code)
        return q
    q = QrCode(
        id=uuid4(),
        tenant_id=str(tenant.id),
        short_code=code,
        target_type=QrTarget.LANDING,
        target_id=None,
        external_url=None,
        label="QR Local Centro",
        branch_id=str(branch.id),
        is_active=True,
        scan_count=0,
    )
    db.add(q)
    db.flush()
    log.info("✓ QR creado: %s", code)
    return q


# ─── LandingConfig ──────────────────────────────────────────
def _get_or_create_landing(db: Session, tenant: Tenant) -> LandingConfig:
    lc = db.execute(
        select(LandingConfig).where(LandingConfig.tenant_id == str(tenant.id))
    ).scalar_one_or_none()
    if lc:
        log.info("✓ LandingConfig ya existe")
        return lc
    lc = LandingConfig(
        id=uuid4(),
        tenant_id=str(tenant.id),
        hero_title="Café de especialidad, hecho con amor",
        hero_subtitle=(
            "Granos de origen, pastelería artesanal y brunch en el corazón de Santiago. "
            "Pide online y retira en local sin fila."
        ),
        hero_image_url="https://picsum.photos/seed/el-rincon-hero/1200/600",
        hero_cta_text="Ver el menú",
        hero_cta_url=None,
        brand_color="#7c5cff",
        accent_color="#00d4a8",
        logo_url=None,
        favicon_url=None,
        contact_whatsapp="+56 9 8765 4321",
        contact_phone="+56 2 2345 6789",
        contact_email="contacto@el-rincon.cl",
        contact_address="Av. Libertador 1234, Local 5, Santiago",
        social_instagram="@el.rincon.cafe",
        social_facebook="/ElRinconCafe",
        social_tiktok="@elrinconcafe",
        show_categories=True,
        show_featured_products=True,
        show_promotions=True,
        show_branches=True,
        show_contact=True,
        seo_title="Cafetería El Rincón — Café de especialidad en Santiago",
        seo_description="Café de especialidad, pastelería artesanal y brunch en Santiago.",
        seo_image_url="https://picsum.photos/seed/el-rincon-seo/1200/630",
        custom_css=None,
        extra_blocks=[
            {
                "type": "banner",
                "title": "🎉 Martes de 2x1 en pastelería",
                "subtitle": "Croissants, muffins y tortas a mitad de precio.",
                "color": "#f59e0b",
            },
        ],
    )
    db.add(lc)
    db.flush()
    log.info("✓ LandingConfig creada")
    return lc


# ─── Main ──────────────────────────────────────────────────
def main() -> int:
    log.info("=" * 60)
    log.info("WowHub — Seed de cliente demo: %s", DEMO_TENANT_DISPLAY)
    log.info("=" * 60)

    # Asegurar tablas
    init_db()

    with SessionLocal() as db:
        try:
            user = _get_or_create_user(db)
            tenant = _get_or_create_tenant(db)
            _get_or_create_membership(db, user, tenant)
            branch = _get_or_create_branch(db, tenant)
            cats = _get_or_create_categories(db, tenant)
            products = _get_or_create_products(db, tenant, cats)
            _get_or_create_promotions(db, tenant, products)
            _get_or_create_customers(db, tenant)
            _get_or_create_qr(db, tenant, branch)
            _get_or_create_landing(db, tenant)

            db.commit()
            log.info("=" * 60)
            log.info("✅ Seed completado")
            log.info("=" * 60)
            log.info("Credenciales demo:")
            log.info("  Email:    %s", DEMO_EMAIL)
            log.info("  Password: %s", DEMO_PASSWORD)
            log.info("  Tenant:   %s (%s)", DEMO_TENANT_DISPLAY, DEMO_TENANT_SLUG)
            log.info("Landing pública: /u/%s", DEMO_TENANT_SLUG)
            log.info("Catálogo:         /u/%s/catalogo", DEMO_TENANT_SLUG)
            return 0
        except Exception as e:
            db.rollback()
            log.exception("❌ Error en seed: %s", e)
            return 1


if __name__ == "__main__":
    sys.exit(main())
