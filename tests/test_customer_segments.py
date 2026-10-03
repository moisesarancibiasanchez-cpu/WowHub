"""HU_26 — Tests del endpoint /customers/segments (segmentación RFM-like).

Smoke test del contrato que la HU_26 exige:
- El endpoint existe en /api/v1/tenants/{tenant_id}/customers/segments
- Requiere autenticación (membership del tenant)
- Devuelve lista ``[{name, count, criteria}, ...]`` con 5 buckets:
    vip, recurrente, regular, nuevo, inactivo
- Los conteos son correctos contra un dataset controlado
"""
import os
import sys
import uuid as _uuid
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

from app.core.security import RateLimitMiddleware  # noqa: E402
from app.database import Base, SessionLocal, engine, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import customer, order, product, tenant, user  # noqa: E402,F401
from app.models.customer import Customer  # noqa: E402
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


@pytest.fixture
def owner_client(db, client):
    """Crea tenant + usuario owner + membership + clientes de prueba."""
    tenant = Tenant(
        id=_uuid.uuid4(),
        slug=f"t-{_uuid.uuid4().hex[:8]}",
        legal_name="Tenant Test SpA",
        display_name="Tenant Test",
        currency="CLP",
    )
    db.add(tenant)
    db.flush()

    user = User(
        id=_uuid.uuid4(),
        email=f"owner-{_uuid.uuid4().hex[:8]}@test.local",
        password_hash="x",
        full_name="Owner Test",
        is_active=True,
    )
    db.add(user)
    db.flush()

    membership = TenantMembership(
        id=_uuid.uuid4(),
        tenant_id=tenant.id,
        user_id=user.id,
        role=UserRole.OWNER,
        is_active=True,
    )
    db.add(membership)

    now = datetime.now(timezone.utc)
    iso_recent = now.isoformat()
    iso_old = (now - timedelta(days=120)).isoformat()

    # 1 cliente VIP: gastó >= 1M CLP y última compra reciente
    db.add(Customer(
        id=_uuid.uuid4(),
        tenant_id=tenant.id,
        full_name="VIP Mega",
        email="vip@test.local",
        total_orders=10,
        total_spent_cents=150_000_000,  # 1.5M CLP
        points=1500,
        last_order_at=iso_recent,
    ))
    # 2 clientes recurrentes: 3+ pedidos
    for i in range(2):
        db.add(Customer(
            id=_uuid.uuid4(),
            tenant_id=tenant.id,
            full_name=f"Recurrente {i}",
            email=f"r{i}@test.local",
            total_orders=4 + i,
            total_spent_cents=20_000 + i * 1000,
            points=200 + i * 10,
            last_order_at=iso_recent,
        ))
    # 3 clientes regulares: 1-2 pedidos
    for i in range(3):
        db.add(Customer(
            id=_uuid.uuid4(),
            tenant_id=tenant.id,
            full_name=f"Regular {i}",
            email=f"reg{i}@test.local",
            total_orders=1 + (i % 2),
            total_spent_cents=5_000 + i * 500,
            points=50 + i * 5,
            last_order_at=iso_recent,
        ))
    # 2 clientes nuevos: sin pedidos
    for i in range(2):
        db.add(Customer(
            id=_uuid.uuid4(),
            tenant_id=tenant.id,
            full_name=f"Nuevo {i}",
            email=f"n{i}@test.local",
            total_orders=0,
            total_spent_cents=0,
            points=0,
            last_order_at=None,
        ))
    # 1 cliente inactivo: órdenes pero última hace 120 días
    db.add(Customer(
        id=_uuid.uuid4(),
        tenant_id=tenant.id,
        full_name="Inactivo",
        email="i@test.local",
        total_orders=2,
        total_spent_cents=10_000,
        points=50,
        last_order_at=iso_old,
    ))

    db.commit()
    db.refresh(tenant)

    token = create_access_token(
        subject=str(user.id),
        tenant_id=tenant.id,
        role="owner",
    )
    headers = {"Authorization": f"Bearer {token}"}
    return client, tenant, headers


def test_segments_requires_auth(client):
    """Sin token el endpoint responde 401."""
    resp = client.get(f"/api/v1/tenants/{_uuid.uuid4()}/customers/segments")
    assert resp.status_code == 401


def test_segments_response_shape(owner_client):
    """Verifica shape y orden de los 5 buckets del HU_26."""
    client, tenant, headers = owner_client
    resp = client.get(
        f"/api/v1/tenants/{tenant.id}/customers/segments",
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert isinstance(body, list)
    assert len(body) == 5

    expected_names = ["vip", "recurrente", "regular", "nuevo", "inactivo"]
    actual_names = [b["name"] for b in body]
    assert actual_names == expected_names

    # Cada bucket debe tener los 3 campos requeridos
    for bucket in body:
        assert set(bucket.keys()) == {"name", "count", "criteria"}
        assert isinstance(bucket["count"], int)
        assert isinstance(bucket["criteria"], str)
        assert bucket["count"] >= 0


def test_segments_counts_match_fixture(owner_client):
    """Con 1 VIP + 2 recurrentes + 3 regulares + 2 nuevos + 1 inactivo = 9."""
    client, tenant, headers = owner_client
    resp = client.get(
        f"/api/v1/tenants/{tenant.id}/customers/segments",
        headers=headers,
    )
    body = resp.json()
    by_name = {b["name"]: b["count"] for b in body}

    assert by_name["vip"] == 1
    assert by_name["recurrente"] == 2
    assert by_name["regular"] == 3
    assert by_name["nuevo"] == 2
    assert by_name["inactivo"] == 1
    assert sum(by_name.values()) == 9


def test_segments_inactive_priority(owner_client):
    """Un cliente VIP con última compra > 90 días debe caer en 'inactivo',
    no en 'vip' (orden de evaluación: inactivo gana)."""
    client, tenant, headers = owner_client
    # Insertar un cliente que cumple VIP (>=$1M) pero inactivo (120 días)
    db = SessionLocal()
    try:
        iso_old = (datetime.now(timezone.utc) - timedelta(days=120)).isoformat()
        db.add(Customer(
            id=_uuid.uuid4(),
            tenant_id=tenant.id,
            full_name="VIP Inactivo",
            email="vip-inactivo@test.local",
            total_orders=20,
            total_spent_cents=200_000_000,
            points=2000,
            last_order_at=iso_old,
        ))
        db.commit()
    finally:
        db.close()

    resp = client.get(
        f"/api/v1/tenants/{tenant.id}/customers/segments",
        headers=headers,
    )
    body = resp.json()
    by_name = {b["name"]: b["count"] for b in body}

    # El cliente VIP original + este nuevo = ambos cayeron en inactivo
    assert by_name["inactivo"] == 2
    assert by_name["vip"] == 1  # solo el VIP "fresco"