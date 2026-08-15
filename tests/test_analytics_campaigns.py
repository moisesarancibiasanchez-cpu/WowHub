"""Tests para los nuevos endpoints /analytics y /campaigns + AI tools."""
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

# Forzar DB en memoria ANTES de importar la app
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["SECRET_KEY"] = "test-secret-key-min-32-chars-ok-test"
os.environ["JWT_SECRET"] = "test-jwt-secret-min-32-chars-ok-test"
os.environ["RATE_LIMIT_ENABLED"] = "false"
os.environ["AUDIT_ENABLED"] = "false"

sys.path.insert(0, ".")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.security import RateLimitMiddleware  # noqa: E402
from app.database import Base, SessionLocal, engine, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import user, tenant, branch, product, customer, order  # noqa: E402,F401
from app.models.user import User  # noqa: E402
from app.models.tenant import Tenant, TenantMembership, UserRole  # noqa: E402
from app.models.product import Product, ProductStatus  # noqa: E402
from app.models.customer import Customer  # noqa: E402
from app.models.order import Order, OrderItem, OrderStatus  # noqa: E402
from app.security import create_access_token  # noqa: E402


# ── Setup: deshabilitar rate limit (igual que conftest.py) ──
for spec in list(getattr(app, "user_middleware", [])):
    cls = getattr(spec, "cls", None)
    if cls is RateLimitMiddleware:
        spec.options = {**getattr(spec, "options", {}), "enabled": False}


@pytest.fixture(autouse=True)
def _reset_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture
def client():
    def _override_get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _create_user_and_tenant(db: Session) -> tuple[User, Tenant]:
    """Crea un usuario, un tenant y una membresía owner."""
    u = User(
        id=uuid.uuid4(),
        email="owner@example.com",
        full_name="Owner Test",
        password_hash="x",
        is_active=True,
    )
    db.add(u)
    db.flush()

    t = Tenant(
        id=uuid.uuid4(),
        legal_name="Demo Tenant SpA",
        display_name="Demo Tenant",
        slug="demo",
        is_active=True,
    )
    db.add(t)
    db.flush()

    m = TenantMembership(
        id=uuid.uuid4(),
        user_id=str(u.id),
        tenant_id=str(t.id),
        role=UserRole.OWNER,
        is_active=True,
    )
    db.add(m)
    db.commit()
    db.refresh(u)
    db.refresh(t)
    return u, t


def _auth_headers(user: User, tenant: Tenant) -> dict:
    token = create_access_token(
        subject=str(user.id),
        extra_claims={"tid": str(tenant.id)},
    )
    return {"Authorization": f"Bearer {token}"}


def _make_products(db: Session, tenant: Tenant) -> list[Product]:
    """Crea 4 productos con distintos estados de stock."""
    prods = [
        Product(
            id=uuid.uuid4(), tenant_id=str(tenant.id), sku="SKU-1", name="Café",
            slug="cafe", price_cents=1000, track_inventory=True,
            stock=2, low_stock_threshold=5, status=ProductStatus.ACTIVE,
        ),
        Product(
            id=uuid.uuid4(), tenant_id=str(tenant.id), sku="SKU-2", name="Té",
            slug="te", price_cents=800, track_inventory=True,
            stock=0, low_stock_threshold=5, status=ProductStatus.ACTIVE,
        ),
        Product(
            id=uuid.uuid4(), tenant_id=str(tenant.id), sku="SKU-3", name="Galleta",
            slug="galleta", price_cents=500, track_inventory=True,
            stock=200, low_stock_threshold=5, status=ProductStatus.ACTIVE,
        ),
        Product(
            id=uuid.uuid4(), tenant_id=str(tenant.id), sku="SKU-4", name="Muffin",
            slug="muffin", price_cents=1500, track_inventory=True,
            stock=50, low_stock_threshold=5, status=ProductStatus.ACTIVE,
        ),
    ]
    for p in prods:
        db.add(p)
    db.commit()
    return prods


def _make_customers(db: Session, tenant: Tenant) -> list[Customer]:
    """Crea 5 clientes con distintos perfiles."""
    now = datetime.now(timezone.utc)
    old = now - timedelta(days=90)  # Hace 90 días (no es "new" ni "inactive" por orden)
    cs = [
        Customer(
            id=uuid.uuid4(), tenant_id=str(tenant.id), full_name="VIP Ana",
            email="ana@example.com", accepts_marketing=True, is_active=True,
            total_orders=10, total_spent_cents=200000, points=500,
            last_order_at=now.isoformat(),
            created_at=old,
        ),
        Customer(
            id=uuid.uuid4(), tenant_id=str(tenant.id), full_name="Top Bruno",
            email="bruno@example.com", accepts_marketing=True, is_active=True,
            total_orders=3, total_spent_cents=90000, points=100,
            last_order_at=now.isoformat(),
            created_at=old,
        ),
        Customer(
            id=uuid.uuid4(), tenant_id=str(tenant.id), full_name="Nuevo Carla",
            email="carla@example.com", accepts_marketing=True, is_active=True,
            total_orders=0, total_spent_cents=0, points=0,
            last_order_at=None, created_at=now,
        ),
        Customer(
            id=uuid.uuid4(), tenant_id=str(tenant.id), full_name="Inactivo Diego",
            email="diego@example.com", accepts_marketing=True, is_active=True,
            total_orders=2, total_spent_cents=30000, points=20,
            last_order_at=(now - timedelta(days=120)).isoformat(),
            created_at=old,
        ),
        Customer(
            id=uuid.uuid4(), tenant_id=str(tenant.id), full_name="NoMark Elena",
            email="elena@example.com", accepts_marketing=False, is_active=True,
            total_orders=1, total_spent_cents=5000, points=0,
            last_order_at=now.isoformat(),
            created_at=old,
        ),
    ]
    for c in cs:
        db.add(c)
    db.commit()
    return cs


def _make_orders_for_active_customers(
    db: Session, tenant: Tenant, customers: list[Customer]
) -> list[Order]:
    """Crea órdenes recientes para los clientes activos (Ana, Bruno, Elena).
    Esto permite que el filtro 'inactive' los EXCLUYA correctamente.
    Diego y Carla no reciben órdenes (Diego=inactivo, Carla=nuevo)."""
    now = datetime.now(timezone.utc)
    active = [c for c in customers if c.full_name in ("VIP Ana", "Top Bruno", "NoMark Elena")]
    orders = []
    for c in active:
        o = Order(
            id=uuid.uuid4(),
            tenant_id=str(tenant.id),
            number=f"ORD-{c.id.hex[:6]}",
            customer_id=str(c.id),
            status=OrderStatus.DELIVERED,
            subtotal_cents=1000,
            total_cents=1000,
            currency="CLP",
            created_at=now,
        )
        db.add(o)
        orders.append(o)
    db.commit()
    return orders


# ─────────────────────────────────────────────────────────
#  Inventory analytics
# ─────────────────────────────────────────────────────────
def test_inventory_all(client, db):
    u, t = _create_user_and_tenant(db)
    _make_products(db, t)
    r = client.get(
        f"/api/v1/tenants/{t.id}/analytics/inventory",
        params={"category": "all"},
        headers=_auth_headers(u, t),
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["category"] == "all"
    assert data["count"] == 4
    assert data["summary"]["total_tracked"] == 4
    # SKU-2 (Té) está sin stock
    assert data["summary"]["out_of_stock"] == 1
    # SKU-1 (Café) tiene stock 2 <= threshold 5
    assert data["summary"]["low_stock"] == 1
    # SKU-3 (Galleta) tiene stock 200 > 100 (overstock_threshold default)
    assert data["summary"]["overstock"] == 1


def test_inventory_low_stock(client, db):
    u, t = _create_user_and_tenant(db)
    _make_products(db, t)
    r = client.get(
        f"/api/v1/tenants/{t.id}/analytics/inventory",
        params={"category": "low_stock"},
        headers=_auth_headers(u, t),
    )
    assert r.status_code == 200
    data = r.json()
    assert data["count"] == 1
    assert data["items"][0]["sku"] == "SKU-1"
    assert data["items"][0]["alert"] == "low_stock"


def test_inventory_out_of_stock(client, db):
    u, t = _create_user_and_tenant(db)
    _make_products(db, t)
    r = client.get(
        f"/api/v1/tenants/{t.id}/analytics/inventory",
        params={"category": "out_of_stock"},
        headers=_auth_headers(u, t),
    )
    assert r.status_code == 200
    data = r.json()
    assert data["count"] == 1
    assert data["items"][0]["sku"] == "SKU-2"
    assert data["items"][0]["alert"] == "out_of_stock"


def test_inventory_overstock(client, db):
    u, t = _create_user_and_tenant(db)
    _make_products(db, t)
    r = client.get(
        f"/api/v1/tenants/{t.id}/analytics/inventory",
        params={"category": "overstock", "overstock_threshold": 100},
        headers=_auth_headers(u, t),
    )
    assert r.status_code == 200
    data = r.json()
    assert data["count"] == 1
    assert data["items"][0]["sku"] == "SKU-3"
    assert data["items"][0]["alert"] == "overstock"


# ─────────────────────────────────────────────────────────
#  Customer segments
# ─────────────────────────────────────────────────────────
def test_customer_segments_summary(client, db):
    u, t = _create_user_and_tenant(db)
    customers = _make_customers(db, t)
    _make_orders_for_active_customers(db, t, customers)
    r = client.get(
        f"/api/v1/tenants/{t.id}/analytics/customer-segments",
        params={"segment": "all"},
        headers=_auth_headers(u, t),
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["summary"]["total_active"] == 5
    assert data["summary"]["accepts_marketing"] == 4  # 5 - Elena (no marketing)
    assert data["summary"]["vip"] == 1  # Ana
    assert data["summary"]["new"] == 1  # Carla
    # Inactivos: Diego (sin orden reciente) + Carla (nunca compró)
    # El filtro de "inactive" mira la tabla orders, no la fecha de creación,
    # por lo que un cliente nuevo sin órdenes también cuenta como inactivo.
    assert data["summary"]["inactive"] == 2  # Diego + Carla


def test_customer_segment_inactive(client, db):
    u, t = _create_user_and_tenant(db)
    customers = _make_customers(db, t)
    _make_orders_for_active_customers(db, t, customers)
    r = client.get(
        f"/api/v1/tenants/{t.id}/analytics/customer-segments",
        params={"segment": "inactive", "days_inactive": 60},
        headers=_auth_headers(u, t),
    )
    assert r.status_code == 200
    data = r.json()
    names = [c["full_name"] for c in data["items"]]
    assert "Inactivo Diego" in names
    assert "VIP Ana" not in names


def test_customer_segment_vip(client, db):
    u, t = _create_user_and_tenant(db)
    _make_customers(db, t)
    r = client.get(
        f"/api/v1/tenants/{t.id}/analytics/customer-segments",
        params={"segment": "vip"},
        headers=_auth_headers(u, t),
    )
    assert r.status_code == 200
    data = r.json()
    assert data["count"] == 1
    assert data["items"][0]["full_name"] == "VIP Ana"


def test_customer_segment_new(client, db):
    u, t = _create_user_and_tenant(db)
    _make_customers(db, t)
    r = client.get(
        f"/api/v1/tenants/{t.id}/analytics/customer-segments",
        params={"segment": "new", "days_new": 30},
        headers=_auth_headers(u, t),
    )
    assert r.status_code == 200
    data = r.json()
    assert data["count"] == 1
    assert data["items"][0]["full_name"] == "Nuevo Carla"


# ─────────────────────────────────────────────────────────
#  Campaigns
# ─────────────────────────────────────────────────────────
def test_campaign_preview_log_channel(client, db):
    """Test que el preview de campaña NO envía emails."""
    u, t = _create_user_and_tenant(db)
    _make_customers(db, t)
    payload = {
        "name": "Test campaign",
        "subject": "Hola!",
        "body": "<p>Esto es un test</p>",
        "segment": "all",
        "channel": "log",
        "only_marketing_opt_in": True,
    }
    r = client.post(
        f"/api/v1/tenants/{t.id}/campaigns/preview",
        json=payload,
        headers=_auth_headers(u, t),
    )
    assert r.status_code == 200, r.text
    data = r.json()
    # 4 clientes aceptan marketing (sin Elena)
    assert data["campaign"]["total_targets"] == 4
    assert data["campaign"]["sent"] == 0
    assert data["campaign"]["channel"] == "log"
    assert data["preview_html"] is not None
    assert len(data["sample_recipients"]) <= 5


def test_campaign_send_log_channel(client, db):
    """Test que el envío en modo 'log' solo registra y devuelve sent>0."""
    u, t = _create_user_and_tenant(db)
    _make_customers(db, t)
    payload = {
        "name": "Test campaign",
        "subject": "Hola!",
        "body": "<p>Esto es un test</p>",
        "segment": "all",
        "channel": "log",
        "only_marketing_opt_in": True,
    }
    r = client.post(
        f"/api/v1/tenants/{t.id}/campaigns",
        json=payload,
        headers=_auth_headers(u, t),
    )
    assert r.status_code == 200, r.text
    data = r.json()
    # 4 aceptan marketing → sent=4
    assert data["campaign"]["sent"] == 4
    assert data["campaign"]["failed"] == 0
    assert data["campaign"]["total_targets"] == 4


def test_campaign_send_vip_segment(client, db):
    """Test envío solo a VIPs."""
    u, t = _create_user_and_tenant(db)
    _make_customers(db, t)
    payload = {
        "name": "VIP Promo",
        "subject": "Descuento VIP",
        "body": "<p>Gracias por ser VIP</p>",
        "segment": "vip",
        "channel": "log",
    }
    r = client.post(
        f"/api/v1/tenants/{t.id}/campaigns",
        json=payload,
        headers=_auth_headers(u, t),
    )
    assert r.status_code == 200, r.text
    data = r.json()
    # Solo Ana es VIP
    assert data["campaign"]["total_targets"] == 1
    assert data["campaign"]["sent"] == 1
    assert data["sample_recipients"][0]["full_name"] == "VIP Ana"


# ─────────────────────────────────────────────────────────
#  AI tools (solo validar que están registradas y son ejecutables)
# ─────────────────────────────────────────────────────────
def test_ai_tools_registered():
    from app.services.ai_tools import TOOL_SCHEMAS, TOOL_DISPATCH, get_tools_for_agent

    names = [t["function"]["name"] for t in TOOL_SCHEMAS]
    assert "analyze_inventory" in names
    assert "get_customer_segments" in names
    assert "send_campaign" in names

    assert "analyze_inventory" in TOOL_DISPATCH
    assert "get_customer_segments" in TOOL_DISPATCH
    assert "send_campaign" in TOOL_DISPATCH

    # Cada agente debe tener al menos 1 tool nueva (excepto router)
    for agent in ("marketing", "growth", "automation", "marketplace"):
        tools = get_tools_for_agent(agent)
        new_tools = {"analyze_inventory", "get_customer_segments", "send_campaign"}
        present = new_tools & {t["function"]["name"] for t in tools}
        assert len(present) >= 1, f"Agent {agent} no tiene ninguna tool nueva"


def test_ai_agents_have_new_tools_in_prompts():
    """Verifica que los prompts de los agentes mencionan las nuevas tools."""
    from app.services.ai_agents import SUB_AGENTS

    # analyze_inventory aplica a todos los agentes (visible para todos)
    for agent_name in ("marketing", "growth", "automation", "marketplace"):
        agent = SUB_AGENTS[agent_name]
        assert "analyze_inventory" in agent.system_prompt, f"{agent_name} no menciona analyze_inventory"

    # get_customer_segments aplica a marketing, growth y automation
    # (marketplace es sobre catálogo/inventario, no clientes)
    for agent_name in ("marketing", "growth", "automation"):
        agent = SUB_AGENTS[agent_name]
        assert "get_customer_segments" in agent.system_prompt, (
            f"{agent_name} no menciona get_customer_segments"
        )

    # automation también debe mencionar send_campaign
    assert "send_campaign" in SUB_AGENTS["automation"].system_prompt


def test_heuristic_route_detects_new_intents():
    """Verifica que el router heurístico detecta los nuevos tipos de mensajes."""
    from app.services.ai_agents import heuristic_route

    # Inventario / catálogo (marketplace)
    assert heuristic_route("qué productos están sin stock") == "marketplace"
    assert heuristic_route("qué hay en el inventario sin ventas") == "marketplace"

    # Automatización
    assert heuristic_route("envíale un mensaje a mis clientes vip") == "automation"
    assert heuristic_route("avísale a los inactivos") == "automation"
    # Mensajes con keywords únicos de automation (sin "campaña" genérica que es ambigua con marketing)
    assert heuristic_route("envía una campaña masiva a los inactivos") == "automation"
    assert heuristic_route("haz un recordatorio a los clientes") == "automation"
