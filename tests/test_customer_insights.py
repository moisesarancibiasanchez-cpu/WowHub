"""HU_25 — Tests del endpoint /insights (perfil 360° del cliente).

Smoke test del contrato que la HU_25 exige:
- ``customer`` (objeto con datos básicos)
- ``lifetime_value_cents``
- ``total_orders``
- ``last_order_at`` (timestamp crudo, NO sólo days_since)
- ``top_products`` (top N productos)
- ``segmento`` (RFM-like: nuevo/regular/recurrente/vip/inactivo)

No valida reglas de negocio (eso está cubierto por tests del customer
service). Sólo verifica que el endpoint existe, requiere auth, y devuelve
los campos prometidos.
"""
import os
import sys
import uuid
from datetime import datetime, timezone

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
from app.models import customer, order, product, tenant, user  # noqa: E402,F401
from app.models.customer import Customer  # noqa: E402
from app.models.order import Order, OrderItem, OrderStatus  # noqa: E402
from app.models.product import Product, ProductStatus  # noqa: E402
from app.models.tenant import Tenant, TenantMembership, UserRole  # noqa: E402
from app.models.user import User  # noqa: E402
from app.security import create_access_token  # noqa: E402


# ── Deshabilitar rate limit (igual que conftest.py) ──
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
        d = SessionLocal()
        try:
            yield d
        finally:
            d.close()

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _make_user_tenant_customer(db: Session):
    """Crea user owner + tenant + customer con 1 pedido."""
    u = User(
        id=uuid.uuid4(),
        email="owner-hu25@example.com",
        full_name="Owner HU25",
        password_hash="x",
        is_active=True,
    )
    t = Tenant(
        id=uuid.uuid4(),
        slug=f"hu25-{uuid.uuid4().hex[:6]}",
        legal_name="HU25 Test SL",
        display_name="HU25 Test",
        is_active=True,
    )
    db.add_all([u, t])
    db.flush()
    db.add(TenantMembership(
        user_id=u.id, tenant_id=t.id, role=UserRole.OWNER, is_active=True,
    ))
    # Producto + cliente + pedido no cancelado
    p = Product(
        id=uuid.uuid4(),
        tenant_id=t.id,
        name="Café HU25",
        sku=f"HU25-{uuid.uuid4().hex[:6]}",
        slug=f"cafe-hu25-{uuid.uuid4().hex[:6]}",
        price_cents=2500,
        cost_cents=500,
        status=ProductStatus.ACTIVE,
        stock=10,
    )
    c = Customer(
        id=uuid.uuid4(),
        tenant_id=t.id,
        full_name="Cliente HU25",
        email="cliente@example.com",
        phone="+56911111111",
    )
    db.add_all([p, c])
    db.flush()
    last_iso = datetime.now(timezone.utc).isoformat()
    o = Order(
        id=uuid.uuid4(),
        tenant_id=t.id,
        customer_id=c.id,
        number=f"HU25-{uuid.uuid4().hex[:6]}",
        status=OrderStatus.PAGADO,
        total_cents=5000,
        subtotal_cents=5000,
        currency="CLP",
        created_at=datetime.now(timezone.utc),
    )
    db.add(o)
    db.flush()
    db.add(OrderItem(
        order_id=o.id,
        product_id=p.id,
        product_name=p.name,
        product_sku=p.sku,
        quantity=2,
        unit_price_cents=2500,
        total_cents=5000,
    ))
    # Métricas agregadas del cliente (lo que el endpoint lee)
    c.total_orders = 1
    c.total_spent_cents = 5000
    c.points = 50
    c.last_order_at = last_iso
    db.commit()
    return u, t, c


def _auth_headers(user: User, tenant: Tenant) -> dict:
    token = create_access_token(
        subject=str(user.id),
        extra_claims={"tid": str(tenant.id)},
    )
    return {"Authorization": f"Bearer {token}"}


# ══════════════════════════════════════════════════════════════
# Tests
# ══════════════════════════════════════════════════════════════


def test_insights_requires_auth(client, db):
    """Sin Authorization → 401."""
    t, p, cust = _make_user_tenant_customer(db)
    r = client.get(f"/api/v1/tenants/{t.id}/customers/{cust.id}/insights")
    assert r.status_code == 401, r.text


def test_insights_contract_hu25(client, db):
    """El endpoint /insights devuelve los campos del spec HU_25."""
    u, t, c = _make_user_tenant_customer(db)
    r = client.get(
        f"/api/v1/tenants/{t.id}/customers/{c.id}/insights",
        headers=_auth_headers(u, t),
    )
    assert r.status_code == 200, r.text
    body = r.json()

    # ── Campos del spec original del endpoint ──
    assert body["customer_id"] == str(c.id)
    assert body["lifetime_value_cents"] == 5000
    assert body["total_orders"] == 1
    assert body["avg_ticket_cents"] == 5000
    assert body["points"] == 50
    assert body["days_since_last_order"] == 0
    assert body["segmento"] in {"nuevo", "regular", "recurrente", "vip", "inactivo"}
    assert body["churn_risk_pct"] >= 0
    assert body["churn_risk_label"] in {"bajo", "medio", "alto"}
    assert isinstance(body["top_products"], list)
    assert len(body["top_products"]) >= 1
    prod = body["top_products"][0]
    assert prod["name"] == "Café HU25"
    assert prod["quantity"] == 2
    assert prod["revenue_cents"] == 5000
    assert body["recommended_promotion"]
    assert body["next_action"]

    # ── Campos nuevos HU_25 (perfil 360°) ──
    assert "last_order_at" in body
    assert body["last_order_at"] is not None
    assert "customer" in body
    cust_out = body["customer"]
    assert cust_out is not None
    assert cust_out["id"] == str(c.id)
    assert cust_out["full_name"] == "Cliente HU25"
    assert cust_out["email"] == "cliente@example.com"
    assert cust_out["tenant_id"] == str(t.id)


def test_insights_404_for_unknown_customer(client, db):
    """UUID válido sin customer → 404."""
    u, t, _ = _make_user_tenant_customer(db)
    r = client.get(
        f"/api/v1/tenants/{t.id}/customers/{uuid.uuid4()}/insights",
        headers=_auth_headers(u, t),
    )
    assert r.status_code == 404