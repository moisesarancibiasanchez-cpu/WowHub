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
import hashlib
import logging
import secrets
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

# Asegurar import del paquete app
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import SessionLocal, init_db
from app.models.booking import Booking, BookingStatus
from app.models.branch import Branch
from app.models.business_costs import BusinessCosts
from app.models.category import Category
from app.models.customer import Customer
from app.models.landing import LandingConfig
from app.models.loyalty_pass import (
    CustomerPass,
    LoyaltyCampaign,
    PassSource,
    PassStatus,
)
from app.models.order import Order, OrderItem, OrderStatus
from app.models.product import Product, ProductStatus
from app.models.promotion import DiscountType, Promotion, PromotionType
from app.models.qr import QrCode, QrTarget
from app.models.quote import Quote, QuoteItem, QuoteStatus
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


# ─── BusinessCosts (Fase 2 V8) ────────────────────────────
def _get_or_create_business_costs(db: Session, tenant: Tenant) -> BusinessCosts:
    """Config de costos fijos mensuales para el tenant demo.

    Datos realistas para una cafetería de especialidad en Santiago,
    Chile. Todos los campos quedan seteados (sin "No aplica") para que
    el módulo Costos muestre el cálculo completo desde el primer
    ingreso del usuario.
    """
    bc = db.execute(
        select(BusinessCosts).where(BusinessCosts.tenant_id == str(tenant.id))
    ).scalar_one_or_none()
    if bc:
        log.info("✓ BusinessCosts ya existe")
        return bc

    bc = BusinessCosts(
        id=uuid4(),
        tenant_id=str(tenant.id),
        # Personal
        owner_salary_cents=1_200_000,      # Dueña María: $1.200.000 CLP/mes
        workers_salary_cents=2_400_000,    # 2 baristas a $1.200.000 c/u
        # Operación
        productive_hours_per_month=160,    # 8h × 20 días hábiles
        target_margin_pct=30,              # 30% de margen objetivo
        # Básicos
        rent_cents=650_000,                # Arriendo local centro
        electricity_cents=180_000,         # Luz + equipos
        water_cents=45_000,                # Agua
        gas_cents=80_000,                  # Gas cafetera/espresso
        # Otros fijos
        software_cents=120_000,            # WowHub + POS + email
        advertising_cents=150_000,         # IG Ads + Google
        payment_commission_cents=80_000,   # Comisiones Webpay/Transbank
        packaging_cents=90_000,            # Vasos, tapas, bolsas
        maintenance_cents=60_000,          # Mantención cafetera
        depreciation_cents=100_000,        # Depreciación equipos
        # Merma
        waste_pct=3,                       # 3% merma promedio café/leche
        # Flags
        is_na={},                          # todos los campos aplican
        notes=(
            "Configuración demo para Cafetería El Rincón. "
            "Refleja costos operativos de un local de cafetería de "
            "especialidad en el centro de Santiago (1 dueña + 2 baristas)."
        ),
    )
    # Recalcular derivados (total_fixed_cents + cost_hour_cents)
    bc.recompute_derived()
    db.add(bc)
    db.flush()
    log.info(
        "✓ BusinessCosts creado: total=$%s, costo_hora=$%s",
        f"{bc.total_fixed_cents:,}".replace(",", "."),
        f"{bc.cost_hour_cents:,}".replace(",", "."),
    )
    return bc


# ─── Orders (Fase 4 — Kanban) ────────────────────────────
def _get_or_create_orders(
    db: Session, tenant: Tenant, products: list, customers: list, branch: Branch
) -> list:
    """Crea ~10 pedidos distribuidos en las 5 columnas del Kanban.

    Estados: PENDING, CONFIRMED, PREPARING, READY, DELIVERED
    (no incluimos CANCELED en el seed para mostrar flujo activo).
    """
    # Si ya hay pedidos para este tenant, no duplicar
    existing = db.execute(
        select(Order).where(Order.tenant_id == str(tenant.id))
    ).scalars().all()
    if existing:
        log.info("✓ Orders ya existen (%d)", len(existing))
        return existing

    now = datetime.now(timezone.utc)
    prods_by_sku = {p.sku: p for p in products}
    out: list[Order] = []

    # (status, minutos_atras, customer_idx, productos[(sku, qty)], notes)
    # customer_idx = 0..4 → customers[0..4]; -1 = sin cliente (guest)
    specs = [
        # ── DELIVERED (ayer / hoy) ──
        (
            OrderStatus.DELIVERED,
            -90,  # hace 1.5h
            0,  # Camila
            [("CAF-002", 1), ("PAS-001", 1)],
            "Para llevar, sin azúcar por favor.",
        ),
        (
            OrderStatus.DELIVERED,
            -150,  # hace 2.5h
            2,  # Fernanda
            [("CAF-005", 1), ("SAN-001", 1)],
            "Cliente VIP, saludo especial.",
        ),
        # ── READY (esperando retiro) ──
        (
            OrderStatus.READY,
            -20,  # hace 20min
            4,  # Valentina
            [("CAF-003", 2), ("BEB-001", 1)],
            "Pasará a retirar en 5 min.",
        ),
        # ── PREPARING (en cocina) ──
        (
            OrderStatus.PREPARING,
            -8,  # hace 8min
            1,  # Diego
            [("SAN-002", 1), ("BEB-002", 1), ("PAS-002", 1)],
            None,
        ),
        # ── CONFIRMED (esperando entrar a cocina) ──
        (
            OrderStatus.CONFIRMED,
            -3,  # hace 3min
            3,  # Matías
            [("CAF-001", 1), ("PAS-003", 2)],
            "Pagó con tarjeta.",
        ),
        # ── PENDING (recién llegados, sin confirmar) ──
        (
            OrderStatus.PENDING,
            -1,  # hace 1min
            -1,  # guest
            [("CAF-004", 1), ("BEB-003", 1)],
            "Cliente nuevo, primera compra.",
        ),
        (
            OrderStatus.PENDING,
            0,  # recién
            -1,  # guest
            [("CAF-002", 3)],
            "Para 3 personas del local.",
        ),
    ]

    for i, (status, minutes_ago, cust_idx, line_specs, notes) in enumerate(specs, start=1):
        items: list[OrderItem] = []
        subtotal = 0
        for sku, qty in line_specs:
            p = prods_by_sku.get(sku)
            if not p:
                continue
            line_total = p.price_cents * qty
            items.append(OrderItem(
                product_id=str(p.id),
                product_name=p.name,
                product_sku=p.sku,
                product_image=p.image_url,
                quantity=qty,
                unit_price_cents=p.price_cents,
                total_cents=line_total,
                options={},
            ))
            subtotal += line_total

        if not items:
            continue

        cust = customers[cust_idx] if cust_idx >= 0 else None
        number = f"ORD-DEMO-{now.strftime('%Y%m%d')}-{i:03d}"
        created = now + timedelta(minutes=minutes_ago)

        order = Order(
            id=uuid4(),
            tenant_id=str(tenant.id),
            number=number,
            status=status,
            customer_id=str(cust.id) if cust else None,
            branch_id=str(branch.id),
            subtotal_cents=subtotal,
            discount_cents=0,
            shipping_cents=0,
            tax_cents=0,
            total_cents=subtotal,
            currency=tenant.currency or "CLP",
            customer_name=cust.full_name if cust else "Cliente Mostrador",
            customer_phone=cust.phone if cust else None,
            customer_email=cust.email if cust else None,
            shipping_address=None,
            notes=notes,
            source="web" if cust else "pos",
            qr_code_id=None,
            items=items,
            created_at=created,
            updated_at=created,
        )
        # Seteamos created/updated explícitamente porque el seed
        # se ejecuta fuera del flujo normal de la API.
        order.created_at = created
        order.updated_at = created
        db.add(order)
        out.append(order)

    db.flush()
    log.info("✓ Orders creadas (%d) — distribuidas en 5 columnas Kanban", len(out))
    return out


# ─── Quotes (Fase 5 — Cotizaciones con PDF) ───────────────
def _get_or_create_quotes(
    db: Session, tenant: Tenant, products: list, customers: list, branch: Branch
) -> list:
    """Crea cotizaciones de ejemplo en distintos estados.

    Cubren el flujo: DRAFT (en edición), SENT (enviada al cliente),
    VIEWED (cliente abrió el link público), ACCEPTED (cliente la aceptó).
    No incluimos REJECTED/EXPIRED en el seed.
    """
    existing = db.execute(
        select(Quote).where(Quote.tenant_id == str(tenant.id))
    ).scalars().all()
    if existing:
        log.info("✓ Quotes ya existen (%d)", len(existing))
        return existing

    now = datetime.now(timezone.utc)
    prods_by_sku = {p.sku: p for p in products}
    out: list[Quote] = []

    specs = [
        # (status, title, customer_idx, productos, days_valid, notes)
        (
            QuoteStatus.DRAFT,
            "Cotización — Servicio de café para evento corporativo",
            -1,  # guest lead
            [("CAF-001", 30), ("CAF-002", 30), ("PAS-001", 20)],
            7,
            "Evento para 60 personas en oficina. Esperando confirmación del cliente.",
        ),
        (
            QuoteStatus.SENT,
            "Cotización — Coffee break semanal",
            0,  # Camila
            [("CAF-002", 10), ("PAS-002", 10), ("BEB-002", 5)],
            10,
            "Cliente VIP. Enviar PDF y seguimiento por WhatsApp.",
        ),
        (
            QuoteStatus.VIEWED,
            "Cotización — Brunch dominical para grupo familiar",
            2,  # Fernanda
            [("SAN-001", 6), ("CAF-003", 6), ("BEB-003", 3)],
            5,
            "Cliente abrió el link 2 veces. Pendiente respuesta.",
        ),
        (
            QuoteStatus.ACCEPTED,
            "Cotización — Pedido mensual de pastelería",
            4,  # Valentina
            [("PAS-001", 30), ("PAS-003", 30), ("PAS-002", 15)],
            14,
            "Aceptada el viernes pasado. Lista para producción.",
        ),
    ]

    for i, (status, title, cust_idx, line_specs, days_valid, notes) in enumerate(specs, start=1):
        items: list[QuoteItem] = []
        subtotal = 0
        for sku, qty in line_specs:
            p = prods_by_sku.get(sku)
            if not p:
                continue
            line_total = p.price_cents * qty
            items.append(QuoteItem(
                product_id=str(p.id),
                product_name=p.name,
                product_sku=p.sku,
                description=p.short_description,
                quantity=qty,
                unit_price_cents=p.price_cents,
                discount_cents=0,
                total_cents=line_total,
            ))
            subtotal += line_total

        if not items:
            continue

        cust = customers[cust_idx] if cust_idx >= 0 else None
        number = f"COT-DEMO-{now.strftime('%Y%m')}-{i:03d}"
        public_token = f"qt_{secrets.token_urlsafe(16)}"
        valid_until = now + timedelta(days=days_valid)

        # Tiempos según estado
        sent_at = now - timedelta(days=2) if status != QuoteStatus.DRAFT else None
        viewed_at = now - timedelta(days=1) if status in (QuoteStatus.VIEWED, QuoteStatus.ACCEPTED) else None
        accepted_at = now - timedelta(hours=8) if status == QuoteStatus.ACCEPTED else None

        quote = Quote(
            id=uuid4(),
            tenant_id=str(tenant.id),
            number=number,
            title=title,
            status=status,
            customer_id=str(cust.id) if cust else None,
            branch_id=str(branch.id),
            recipient_name=cust.full_name if cust else "Empresa XYZ SpA",
            recipient_email=cust.email if cust else "compras@xyz.cl",
            recipient_phone=cust.phone if cust else "+56 2 2345 0000",
            subtotal_cents=subtotal,
            discount_cents=0,
            tax_cents=0,
            total_cents=subtotal,
            currency=tenant.currency or "CLP",
            notes=notes,
            terms=(
                "Precios en CLP, IVA incluido. "
                "Vigencia: 7 días desde la fecha de emisión. "
                "Pago: 50% adelantado, 50% contra entrega."
            ),
            valid_until=valid_until,
            sent_at=sent_at,
            viewed_at=viewed_at,
            accepted_at=accepted_at,
            rejected_at=None,
            public_token=public_token,
            converted_order_id=None,
            extra={"source": "seed_demo"},
            items=items,
        )
        db.add(quote)
        out.append(quote)

    db.flush()
    log.info("✓ Quotes creadas (%d) — DRAFT/SENT/VIEWED/ACCEPTED", len(out))
    return out


# ─── Bookings (Fase 8 — Reservas web) ─────────────────────
def _get_or_create_bookings(
    db: Session, tenant: Tenant, products: list, customers: list, branch: Branch
) -> list:
    """Reservas de ejemplo (mix de pasadas, futuras confirmadas y futuras pendientes).

    Como el tenant demo es GASTRO, simulamos reservas tipo "catación de café"
    o "cata privada" usando un producto cualquiera como "servicio".
    """
    existing = db.execute(
        select(Booking).where(Booking.tenant_id == str(tenant.id))
    ).scalars().all()
    if existing:
        log.info("✓ Bookings ya existen (%d)", len(existing))
        return existing

    # Buscar un producto para usar como "servicio reservado"
    servicio = next((p for p in products if "CAF" in p.sku or "torta" in (p.slug or "")), products[0])

    now = datetime.now(timezone.utc)
    out: list[Booking] = []

    specs = [
        # (status, days_offset, hour, duration_min, customer_idx, notes, staff)
        (
            BookingStatus.COMPLETED,
            -7,                              # semana pasada
            16,                              # hora
            30,                              # minutos (¡ojo, NO 16,30 — eso es una tuple!)
            60,                              # duración en minutos
            2,                               # Fernanda (VIP)
            "Cata privada de café de especialidad para 4 personas. Muy buena recepción.",
            "María González",
        ),
        (
            BookingStatus.CONFIRMED,
            2,                               # pasado mañana
            11,
            0,
            45,
            0,                               # Camila
            "Sesión de cata + brunch. Confirmada por WhatsApp.",
            "Camila Soto (staff)",
        ),
        (
            BookingStatus.PENDING,
            5,                               # en 5 días
            15,
            0,
            30,
            4,                               # Valentina
            "Consulta inicial para asesoría de barista en casa.",
            None,
        ),
    ]

    for i, (status, days_offset, hour, minute, duration, cust_idx, notes, staff) in enumerate(specs, start=1):
        cust = customers[cust_idx] if cust_idx >= 0 else None
        starts = (now + timedelta(days=days_offset)).replace(
            hour=hour, minute=minute, second=0, microsecond=0
        )
        ends = starts + timedelta(minutes=duration)

        # Customer name fallback (Booking requiere name + phone NOT NULL)
        cust_name = cust.full_name if cust else f"Lead Demo {i}"
        cust_phone = cust.phone if cust else "+56 9 4000 0000"
        cust_email = cust.email if cust else None

        booking = Booking(
            id=uuid4(),
            tenant_id=str(tenant.id),
            branch_id=str(branch.id),
            customer_id=str(cust.id) if cust else None,
            product_id=str(servicio.id),
            status=status,
            starts_at=starts,
            ends_at=ends,
            customer_name=cust_name,
            customer_phone=cust_phone,
            customer_email=cust_email,
            price_cents=servicio.price_cents if status != BookingStatus.PENDING else 0,
            currency=tenant.currency or "CLP",
            notes=notes,
            staff_name=staff,
            extra={"source": "seed_demo"},
            created_at=starts - timedelta(days=1),
            updated_at=starts - timedelta(days=1),
        )
        db.add(booking)
        out.append(booking)

    db.flush()
    log.info("✓ Bookings creados (%d) — COMPLETED/CONFIRMED/PENDING", len(out))
    return out


# ─── Loyalty (Fase 8 — Tarjetas de fidelidad) ────────────
def _hash_pin(pin: str) -> str:
    """SHA-256 hex digest (64 chars) — formato esperado por la columna cashier_pin."""
    return hashlib.sha256(pin.encode("utf-8")).hexdigest()


def _get_or_create_loyalty(
    db: Session, tenant: Tenant, customers: list
) -> tuple:
    """Crea 1 campaña activa "6 cafés = 1 gratis" y passes para los clientes demo.

    Distribuye sellos entre los 5 clientes para que el Kanban de fidelidad
    muestre variedad:
      - Camila (VIP):  5/6 (casi completa)
      - Diego:         1/6 (nuevo)
      - Fernanda (VIP): 6/6 REDEEMED (ya canjeó)
      - Matías:        0/6 (apenas se inscribió)
      - Valentina:     3/6 (a mitad de camino)
    """
    # 1) Campaña
    campaign = db.execute(
        select(LoyaltyCampaign).where(
            LoyaltyCampaign.tenant_id == str(tenant.id),
            LoyaltyCampaign.name == "6 cafés = 1 gratis",
        )
    ).scalar_one_or_none()
    if not campaign:
        campaign = LoyaltyCampaign(
            id=uuid4(),
            tenant_id=str(tenant.id),
            name="6 cafés = 1 gratis",
            reward_label="1 café espresso de regalo",
            stamps_required=6,
            primary_color="#7c5cff",
            text_color="#FFFFFF",
            accent_color="#00d4a8",
            logo_url="https://picsum.photos/seed/el-rincon-logo/200/200",
            strip_url="https://picsum.photos/seed/el-rincon-strip/600/200",
            is_active=True,
            starts_at=datetime.now(timezone.utc) - timedelta(days=30),
            ends_at=None,
            cashier_pin=_hash_pin("1234"),  # PIN demo para el garzón
            pin_hint="1234",
            total_passes=0,
            total_stamps_issued=0,
            total_rewards_redeemed=0,
        )
        db.add(campaign)
        db.flush()
        log.info("✓ LoyaltyCampaign creada: %s", campaign.name)
    else:
        log.info("✓ LoyaltyCampaign ya existe: %s", campaign.name)

    # 2) Passes por cliente
    out: list[CustomerPass] = []
    # (customer_idx, stamps_current, status)
    customer_stamps = [
        (0, 5, PassStatus.ACTIVE),       # Camila: casi completa
        (1, 1, PassStatus.ACTIVE),       # Diego: nuevo
        (2, 6, PassStatus.REDEEMED),     # Fernanda: ya canjeó
        (3, 0, PassStatus.ACTIVE),       # Matías: recién inscrito
        (4, 3, PassStatus.ACTIVE),       # Valentina: a mitad de camino
    ]
    now = datetime.now(timezone.utc)
    for cust_idx, stamps, status in customer_stamps:
        cust = customers[cust_idx]
        existing = db.execute(
            select(CustomerPass).where(
                CustomerPass.tenant_id == str(tenant.id),
                CustomerPass.campaign_id == str(campaign.id),
                CustomerPass.customer_id == str(cust.id),
            )
        ).scalar_one_or_none()
        if existing:
            out.append(existing)
            continue

        serial = f"ELR-{secrets.token_hex(6).upper()}"
        qr_payload = f"wowhub://loyalty/{campaign.id}/{serial}"
        last_stamp = now - timedelta(days=stamps) if stamps > 0 else None
        installed_at = now - timedelta(days=max(stamps, 1) + 1)
        redeemed_at = (
            now - timedelta(days=2) if status == PassStatus.REDEEMED else None
        )

        cp = CustomerPass(
            id=uuid4(),
            tenant_id=str(tenant.id),
            campaign_id=str(campaign.id),
            customer_id=str(cust.id),
            serial_number=serial,
            source=PassSource.WEB.value,
            status=status.value,
            stamps_current=stamps,
            rewards_earned=1 if status == PassStatus.REDEEMED else 0,
            qr_payload=qr_payload,
            installed_at=installed_at,
            last_stamp_at=last_stamp,
            redeemed_at=redeemed_at,
            expires_at=None,
        )
        db.add(cp)
        out.append(cp)

    # 3) Métricas desnormalizadas de la campaña
    campaign.total_passes = len(out)
    campaign.total_stamps_issued = sum(c.stamps_current for c in out)
    campaign.total_rewards_redeemed = sum(c.rewards_earned for c in out)

    db.flush()
    log.info(
        "✓ CustomerPasses creados (%d) — 5/6, 1/6, 6/6 redeemed, 0/6, 3/6",
        len(out),
    )
    return campaign, out


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
            customers = _get_or_create_customers(db, tenant)
            _get_or_create_qr(db, tenant, branch)
            _get_or_create_landing(db, tenant)

            # ── V8: features nuevos ─────────────────────────
            # Fase 2: Costos fijos + costo_hora
            _get_or_create_business_costs(db, tenant)
            # Fase 4: Pedidos (Kanban 5 columnas)
            _get_or_create_orders(db, tenant, products, customers, branch)
            # Fase 5: Cotizaciones (DRAFT/SENT/VIEWED/ACCEPTED)
            _get_or_create_quotes(db, tenant, products, customers, branch)
            # Fase 8: Bookings + Loyalty Pass
            _get_or_create_bookings(db, tenant, products, customers, branch)
            _get_or_create_loyalty(db, tenant, customers)

            # Feature flags para features que vienen (Fases 3-7)
            # Activamos todos en el tenant demo para que la UI
            # muestre los nuevos módulos desde el primer login.
            tenant.settings = {
                **(tenant.settings or {}),
                "demo": True,
                "feature_costs_enabled": True,
                "feature_pricing_suggestion_enabled": True,
                "feature_kanban_enabled": True,
                "feature_quotes_enabled": True,
                "feature_notifications_enabled": True,
                "feature_marketing_ai_enabled": True,
                "feature_bookings_enabled": True,
                "feature_loyalty_enabled": True,
                "web_booking_enabled": True,
                "show_costs_to_owner": True,
            }

            db.commit()
            log.info("=" * 60)
            log.info("✅ Seed completado")
            log.info("=" * 60)
            log.info("Credenciales demo:")
            log.info("  Email:    %s", DEMO_EMAIL)
            log.info("  Password: %s", DEMO_PASSWORD)
            log.info("  Tenant:   %s (%s)", DEMO_TENANT_DISPLAY, DEMO_TENANT_SLUG)
            log.info("")
            log.info("Landing pública: /u/%s", DEMO_TENANT_SLUG)
            log.info("Catálogo:         /u/%s/catalogo", DEMO_TENANT_SLUG)
            log.info("")
            log.info("URLs del dashboard:")
            log.info("  /dashboard                  → Home")
            log.info("  /dashboard/costs            → Costos (Fase 2)")
            log.info("  /dashboard/products         → Catálogo")
            log.info("  /dashboard/orders           → Kanban Pedidos (Fase 4)")
            log.info("  /dashboard/quotes           → Cotizaciones (Fase 5)")
            log.info("  /dashboard/bookings         → Reservas (Fase 8)")
            log.info("  /dashboard/loyalty          → Fidelidad (Fase 8)")
            return 0
        except Exception as e:
            db.rollback()
            log.exception("❌ Error en seed: %s", e)
            return 1


if __name__ == "__main__":
    sys.exit(main())
