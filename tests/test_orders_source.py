"""HU_16 follow-up — Tests de aceptación de `source="whatsapp"` en Order.

El webhook de WhatsApp (HU_16) crea pedidos con `source="whatsapp"`. Aunque el
modelo `Order` y los schemas ya son strings libres (max 40 chars) y por lo
tanto aceptan el valor sin 422, este test fija el contrato explícitamente
para evitar regresiones si en el futuro alguien restringe la columna a un
Enum cerrado.

Cubre:
  - Test 1: Crear `Order` con `source="whatsapp"` no lanza ValidationError.
  - Test 2: `OrderCreate` schema acepta `source="whatsapp"`.
  - Test 3: `OrderOut` schema serializa `source="whatsapp"` correctamente.
"""
from __future__ import annotations

import uuid as _uuid


def test_order_model_accepts_whatsapp_source(db_session):
    """El modelo SQLAlchemy `Order` acepta `source="whatsapp"` sin lanzar error."""
    from app.models.order import Order

    o = Order(
        tenant_id=str(_uuid.uuid4()),
        number="#WH-1",
        status="recibido",
        total_cents=0,
        source="whatsapp",
    )
    # La asignación directa NO debe lanzar — la columna es String(40) libre.
    assert o.source == "whatsapp"

    # Persistir y flush también debe funcionar (sin Enum que restrinja el valor).
    db_session.add(o)
    db_session.flush()
    assert o.source == "whatsapp"
    db_session.rollback()


def test_order_create_schema_accepts_whatsapp_source():
    """`OrderCreate` (Pydantic) acepta `source="whatsapp"` en input."""
    from app.schemas.order import OrderCreate

    payload = OrderCreate(
        items=[{"product_id": _uuid.uuid4(), "quantity": 1}],
        source="whatsapp",
    )
    assert payload.source == "whatsapp"
    # El default sigue siendo "web" cuando no se especifica.
    default_payload = OrderCreate(
        items=[{"product_id": _uuid.uuid4(), "quantity": 1}],
    )
    assert default_payload.source == "web"


def test_order_out_schema_serializes_whatsapp_source(db_session):
    """`OrderOut` (Pydantic) serializa correctamente `source="whatsapp"`."""
    from datetime import datetime, timezone

    from app.models.order import Order, OrderItem, OrderStatus
    from app.schemas.order import OrderOut

    tenant_id = str(_uuid.uuid4())
    o = Order(
        tenant_id=tenant_id,
        number="#WH-OUT",
        status=OrderStatus.RECIBIDO,
        total_cents=1500,
        source="whatsapp",
    )
    db_session.add(o)
    db_session.flush()

    line = OrderItem(
        order_id=o.id,
        product_name="Café WhatsApp",
        quantity=1,
        unit_price_cents=1500,
        total_cents=1500,
    )
    db_session.add(line)
    db_session.flush()
    db_session.refresh(o)

    out = OrderOut.model_validate(o)
    assert out.source == "whatsapp"
    assert out.number == "#WH-OUT"
    assert isinstance(out.created_at, datetime)
