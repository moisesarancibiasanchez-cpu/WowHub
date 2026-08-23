"""Tests del módulo NotificationsEngine (Fase 4).

Cubre:
  - Constantes públicas (CATEGORIES, SEVERITIES, THRESHOLDS)
  - Helper _stable_id (estabilidad del ID → clave de caching en front)
  - Helper _format_money (formato de moneda sin decimales, p.ej. CLP)
  - _rule_costs_not_configured: aparece si BusinessCosts.version == 1
  - _rule_high_cost_hour: aparece si cost_hour_cents > umbral
  - _rule_critical_margin / _rule_low_margin: dependen de health
  - _rule_pricing_below_suggested: gap >= 10% entre actual y sugerido
  - _rule_out_of_stock / _rule_low_stock: solo si track_inventory
  - _rule_pending_orders_old: pedidos PENDING > N horas
  - detect_all: orden por severidad (critical primero)
  - summary: contadores correctos
  - by_category / by_severity: helpers de agrupación
  - Aislamiento entre tenants (no leak)
"""
from __future__ import annotations

import uuid as _uuid

import pytest


# ───────────────────────────────────────────────
# Helpers de bootstrap
# ───────────────────────────────────────────────

def _make_tenant(db, slug: str | None = None):
    """Crea un Tenant mínimo en la DB de test."""
    from app.models.tenant import Tenant
    t = Tenant(
        id=_uuid.uuid4(),
        slug=slug or f"t-{_uuid.uuid4().hex[:8]}",
        legal_name="Test",
        display_name="Test",
        currency="CLP",
        is_active=True,
    )
    db.add(t)
    db.flush()
    return t


def _make_business_costs(
    db, tenant_id: str,
    *,
    cost_hour_cents: int = 0,
    target_margin_pct: int = 30,
    version: int = 1,
    productive_hours: int = 160,
    rent_cents: int = 0,
):
    """Crea una fila de BusinessCosts manualmente."""
    from app.models.business_costs import BusinessCosts
    bc = BusinessCosts(
        tenant_id=tenant_id,
        owner_salary_cents=0, workers_salary_cents=0,
        productive_hours_per_month=productive_hours,
        target_margin_pct=target_margin_pct,
        rent_cents=rent_cents, electricity_cents=0, water_cents=0, gas_cents=0,
        software_cents=0, advertising_cents=0, payment_commission_cents=0,
        packaging_cents=0, maintenance_cents=0, depreciation_cents=0,
        waste_pct=0, is_na={},
        total_fixed_cents=rent_cents,
        cost_hour_cents=cost_hour_cents,
        version=version,
    )
    db.add(bc)
    db.flush()
    return bc


def _make_product(
    db, tenant_id: str, *,
    name: str = "Producto X", price_cents: int = 5000,
    cost_cents: int = 1000, production_time_min: int = 10,
    stock: int = 10, low_stock_threshold: int = 5,
    track_inventory: bool = False, status: str = "active",
):
    from app.models.product import Product, ProductStatus
    p = Product(
        tenant_id=tenant_id, sku=f"sku-{_uuid.uuid4().hex[:6]}",
        name=name, slug=f"slug-{_uuid.uuid4().hex[:6]}",
        price_cents=price_cents, cost_cents=cost_cents,
        production_time_min=production_time_min,
        stock=stock, low_stock_threshold=low_stock_threshold,
        track_inventory=track_inventory, status=ProductStatus(status),
    )
    db.add(p)
    db.flush()
    return p


def _make_order(db, tenant_id: str, *, status: str, age_hours: float = 0, total_cents: int = 10000):
    from app.models.order import Order, OrderStatus
    from datetime import datetime, timedelta, timezone
    o = Order(
        tenant_id=tenant_id, status=OrderStatus(status),
        number=f"#{_uuid.uuid4().hex[:6].upper()}",
        total_cents=total_cents,
        created_at=datetime.now(timezone.utc) - timedelta(hours=age_hours),
    )
    db.add(o)
    db.flush()
    return o


# ───────────────────────────────────────────────
# Tests de constantes y helpers
# ───────────────────────────────────────────────

def test_constants_defined():
    """Las constantes públicas existen y son inmutables."""
    from app.services.notifications import CATEGORIES, SEVERITIES, THRESHOLDS
    assert set(CATEGORIES) == {"pricing", "inventory", "orders", "costs", "system"}
    assert set(SEVERITIES) == {"info", "warning", "critical"}
    assert "low_stock_default" in THRESHOLDS
    assert "high_cost_hour_cents" in THRESHOLDS
    assert "pending_order_hours" in THRESHOLDS
    assert "pricing_gap_pct" in THRESHOLDS


def test_stable_id_is_deterministic():
    """El ID estable no cambia entre llamadas con los mismos inputs."""
    from app.services.notifications import _stable_id
    a = _stable_id("N1_critical_margin", "abc-123")
    b = _stable_id("N1_critical_margin", "abc-123")
    c = _stable_id("N1_critical_margin", "abc-456")
    d = _stable_id("N2_low_margin", "abc-123")
    assert a == b
    assert a != c  # cambia con entity_id
    assert a != d  # cambia con rule
    assert a.startswith("notif_")  # prefijo para que el front lo distinga


def test_format_money_basic():
    from app.services.notifications import _format_money
    # 1500 centavos = 15 unidades monetarias
    # 1_500_000 centavos = 15.000 unidades (con separador de miles)
    assert _format_money(0) == "$0"
    assert _format_money(1500) == "$15"
    assert _format_money(1_500_000) == "$15.000"
    assert _format_money(None) == "—"


# ───────────────────────────────────────────────
# Tests de reglas individuales
# ───────────────────────────────────────────────

def test_costs_not_configured_appears_when_version_is_1(db_session):
    """N7 — Si BusinessCosts.version == 1, aparece la notificación 'info'."""
    t = _make_tenant(db_session)
    _make_business_costs(db_session, str(t.id), version=1)
    from app.services.notifications import NotificationsEngine
    engine = NotificationsEngine(db_session, t.id)
    notifs = engine._rule_costs_not_configured()
    assert len(notifs) == 1
    n = notifs[0]
    assert n.severity == "info"
    assert n.category == "costs"
    assert "costos" in n.title.lower() or "configurá" in n.title.lower()
    assert n.action_url == "/dashboard/admin_costs"
    assert n.entity_type == "tenant"


def test_costs_not_configured_silent_when_version_gt_1(db_session):
    """Si version > 1, NO aparece la notificación de Costos sin configurar."""
    t = _make_tenant(db_session)
    _make_business_costs(db_session, str(t.id), version=2)
    from app.services.notifications import NotificationsEngine
    engine = NotificationsEngine(db_session, t.id)
    notifs = engine._rule_costs_not_configured()
    assert notifs == []


def test_costs_not_configured_silent_when_no_row(db_session):
    """Si no hay fila de BusinessCosts, también se notifica (info)."""
    t = _make_tenant(db_session)
    from app.services.notifications import NotificationsEngine
    engine = NotificationsEngine(db_session, t.id)
    notifs = engine._rule_costs_not_configured()
    assert len(notifs) == 1
    assert notifs[0].severity == "info"


def test_high_cost_hour_triggers_above_threshold(db_session):
    """N8 — cost_hour_cents > umbral → warning."""
    t = _make_tenant(db_session)
    _make_business_costs(
        db_session, str(t.id),
        cost_hour_cents=20_000,  # umbral es 15_000
        version=2,
    )
    from app.services.notifications import NotificationsEngine
    engine = NotificationsEngine(db_session, t.id)
    notifs = engine._rule_high_cost_hour()
    assert len(notifs) == 1
    assert notifs[0].severity == "warning"
    assert notifs[0].category == "costs"
    assert notifs[0].metric["cost_hour_cents"] == 20_000


def test_high_cost_hour_silent_below_threshold(db_session):
    """Si está por debajo del umbral, no alerta."""
    t = _make_tenant(db_session)
    _make_business_costs(db_session, str(t.id), cost_hour_cents=5_000, version=2)
    from app.services.notifications import NotificationsEngine
    engine = NotificationsEngine(db_session, t.id)
    assert engine._rule_high_cost_hour() == []


def test_out_of_stock_triggers(db_session):
    """N4 — Producto con stock=0 y track_inventory=True → critical."""
    t = _make_tenant(db_session)
    p = _make_product(db_session, str(t.id), stock=0, track_inventory=True)
    from app.services.notifications import NotificationsEngine
    engine = NotificationsEngine(db_session, t.id)
    notifs = engine._rule_out_of_stock()
    assert len(notifs) == 1
    assert notifs[0].severity == "critical"
    assert notifs[0].entity_id == p.id


def test_out_of_stock_silent_when_not_tracked(db_session):
    """Si track_inventory=False, no se considera 'sin stock' como alerta."""
    t = _make_tenant(db_session)
    _make_product(db_session, str(t.id), stock=0, track_inventory=False)
    from app.services.notifications import NotificationsEngine
    engine = NotificationsEngine(db_session, t.id)
    assert engine._rule_out_of_stock() == []


def test_low_stock_triggers(db_session):
    """N5 — stock <= threshold (con track_inventory) → warning."""
    t = _make_tenant(db_session)
    p = _make_product(
        db_session, str(t.id), stock=2, low_stock_threshold=5,
        track_inventory=True,
    )
    from app.services.notifications import NotificationsEngine
    engine = NotificationsEngine(db_session, t.id)
    notifs = engine._rule_low_stock()
    assert len(notifs) == 1
    assert notifs[0].severity == "warning"
    assert notifs[0].entity_id == p.id
    assert notifs[0].metric["stock"] == 2
    assert notifs[0].metric["threshold"] == 5


def test_low_stock_silent_when_above_threshold(db_session):
    """Si stock > threshold, no alerta."""
    t = _make_tenant(db_session)
    _make_product(
        db_session, str(t.id), stock=10, low_stock_threshold=5,
        track_inventory=True,
    )
    from app.services.notifications import NotificationsEngine
    engine = NotificationsEngine(db_session, t.id)
    assert engine._rule_low_stock() == []


def test_pending_orders_old_triggers(db_session):
    """N6 — Pedido PENDING > 24h → warning."""
    t = _make_tenant(db_session)
    _make_order(db_session, str(t.id), status="pending", age_hours=48)
    from app.services.notifications import NotificationsEngine
    engine = NotificationsEngine(db_session, t.id)
    notifs = engine._rule_pending_orders_old()
    assert len(notifs) == 1
    assert notifs[0].severity == "warning"
    assert notifs[0].category == "orders"


def test_pending_orders_silent_when_recent(db_session):
    """Pedido PENDING de hace 1h no alerta."""
    t = _make_tenant(db_session)
    _make_order(db_session, str(t.id), status="pending", age_hours=1)
    from app.services.notifications import NotificationsEngine
    engine = NotificationsEngine(db_session, t.id)
    assert engine._rule_pending_orders_old() == []


def test_pending_orders_silent_when_paid(db_session):
    """Pedido DELIVERED aunque sea viejo no alerta (ya se procesó)."""
    t = _make_tenant(db_session)
    _make_order(db_session, str(t.id), status="delivered", age_hours=48)
    from app.services.notifications import NotificationsEngine
    engine = NotificationsEngine(db_session, t.id)
    assert engine._rule_pending_orders_old() == []


def test_critical_margin_triggers(db_session):
    """N1 — Producto con margen crítico → critical."""
    t = _make_tenant(db_session)
    # cost_hour muy alto (20.000 CLP/h) + tiempo de producción de 30 min
    # → costo_real = 0 insumos + 30/60*20000 = 10000
    # → precio 5000 → margin = (5000-10000)/5000 = -100% → "danger"
    _make_business_costs(
        db_session, str(t.id),
        cost_hour_cents=20_000, target_margin_pct=30, version=2,
    )
    _make_product(
        db_session, str(t.id), name="Caro",
        price_cents=5000, cost_cents=0, production_time_min=30,
    )
    from app.services.notifications import NotificationsEngine
    engine = NotificationsEngine(db_session, t.id)
    notifs = engine._rule_critical_margin()
    assert len(notifs) == 1
    assert notifs[0].severity == "critical"
    assert notifs[0].category == "pricing"


def test_critical_margin_silent_when_healthy(db_session):
    """Producto con margen saludable NO genera alerta crítica."""
    t = _make_tenant(db_session)
    _make_business_costs(
        db_session, str(t.id),
        cost_hour_cents=1000, target_margin_pct=30, version=2,
    )
    # precio 5000, costo real ≈ 1000 → margin 80% > target 30% → healthy
    _make_product(
        db_session, str(t.id), name="Saludable",
        price_cents=5000, cost_cents=1000, production_time_min=0,
    )
    from app.services.notifications import NotificationsEngine
    engine = NotificationsEngine(db_session, t.id)
    assert engine._rule_critical_margin() == []


def test_pricing_below_suggested_triggers_when_gap_large(db_session):
    """N3 — gap >= 10% entre actual y sugerido → warning."""
    t = _make_tenant(db_session)
    # cost_hour = 1000, target = 30%
    # producto: cost=1000, time=0 → real_cost=1000
    #   sugerido = 1000 / (1-0.3) ≈ 1429
    #   price=1000 → gap = (1429-1000)/1429 = 30% > 10% ✓
    _make_business_costs(
        db_session, str(t.id),
        cost_hour_cents=1000, target_margin_pct=30, version=2,
    )
    _make_product(
        db_session, str(t.id), name="Barato",
        price_cents=1000, cost_cents=1000, production_time_min=0,
    )
    from app.services.notifications import NotificationsEngine
    engine = NotificationsEngine(db_session, t.id)
    notifs = engine._rule_pricing_below_suggested()
    assert len(notifs) == 1
    assert notifs[0].severity == "warning"
    assert notifs[0].metric["gap_pct"] >= 10


def test_pricing_below_suggested_silent_when_gap_small(db_session):
    """Si el gap es < 10%, no alerta (tolerancia a centavos)."""
    t = _make_tenant(db_session)
    _make_business_costs(
        db_session, str(t.id),
        cost_hour_cents=1000, target_margin_pct=30, version=2,
    )
    # price ≈ sugerido → gap < 10%
    _make_product(
        db_session, str(t.id), name="Adecuado",
        price_cents=1500, cost_cents=1000, production_time_min=0,
    )
    from app.services.notifications import NotificationsEngine
    engine = NotificationsEngine(db_session, t.id)
    assert engine._rule_pricing_below_suggested() == []


# ───────────────────────────────────────────────
# Tests de detect_all / summary
# ───────────────────────────────────────────────

def test_detect_all_returns_serializable_dicts(db_session):
    """Las notificaciones son dicts JSON-serializables."""
    import json
    t = _make_tenant(db_session)
    _make_business_costs(db_session, str(t.id), version=1)
    from app.services.notifications import NotificationsEngine
    engine = NotificationsEngine(db_session, t.id)
    items = engine.detect_all()
    assert isinstance(items, list)
    assert len(items) >= 1  # al menos la de Costos sin configurar
    # JSON-serializable?
    json.dumps(items)
    for it in items:
        assert "id" in it
        assert "severity" in it
        assert "category" in it
        assert "title" in it
        assert "body" in it
        assert "action_label" in it
        assert "action_url" in it
        assert "entity_type" in it
        assert "entity_id" in it
        assert "detected_at" in it
        assert "metric" in it


def test_detect_all_orders_critical_first(db_session):
    """Las críticas van antes que las warnings, y estas antes que las info."""
    t = _make_tenant(db_session)
    # Crear: 1 warning (costo_hora alto) + 1 critical (sin stock) + 1 info (costos)
    _make_business_costs(
        db_session, str(t.id),
        cost_hour_cents=20_000, version=1,  # genera info + warning
    )
    _make_product(
        db_session, str(t.id), stock=0, track_inventory=True, name="Sin stock",
    )
    from app.services.notifications import NotificationsEngine
    engine = NotificationsEngine(db_session, t.id)
    items = engine.detect_all()
    severities_in_order = [it["severity"] for it in items]
    # Construir el orden esperado: criticals → warnings → infos
    expected = ["critical"] * severities_in_order.count("critical") \
             + ["warning"] * severities_in_order.count("warning") \
             + ["info"] * severities_in_order.count("info")
    assert severities_in_order == expected


def test_summary_counts_correct(db_session):
    """summary() devuelve contadores correctos por severidad y categoría."""
    t = _make_tenant(db_session)
    # Costos sin configurar → genera 1 notificación "info" (costs)
    _make_business_costs(db_session, str(t.id), version=1)
    from app.services.notifications import NotificationsEngine
    engine = NotificationsEngine(db_session, t.id)
    summary = engine.summary()
    assert "total" in summary
    assert "by_severity" in summary
    assert "by_category" in summary
    assert "top_3" in summary
    assert summary["by_severity"]["info"] >= 1
    assert summary["by_category"]["costs"] >= 1
    assert isinstance(summary["top_3"], list)
    assert len(summary["top_3"]) <= 3


def test_by_category_groups_correctly(db_session):
    """by_category agrupa por categoría."""
    t = _make_tenant(db_session)
    _make_business_costs(db_session, str(t.id), version=1)
    from app.services.notifications import NotificationsEngine
    engine = NotificationsEngine(db_session, t.id)
    items = engine.detect_all()
    grouped = NotificationsEngine.by_category(items)
    assert "costs" in grouped
    assert "pricing" in grouped
    assert "inventory" in grouped
    assert "orders" in grouped
    assert "system" in grouped
    # Todos los items de la lista deben estar en algún bucket
    total = sum(len(v) for v in grouped.values())
    assert total == len(items)


def test_by_severity_groups_correctly(db_session):
    """by_severity agrupa por severidad."""
    t = _make_tenant(db_session)
    _make_business_costs(db_session, str(t.id), version=1)
    from app.services.notifications import NotificationsEngine
    engine = NotificationsEngine(db_session, t.id)
    items = engine.detect_all()
    grouped = NotificationsEngine.by_severity(items)
    assert set(grouped.keys()) == {"info", "warning", "critical"}


# ───────────────────────────────────────────────
# Tests de aislamiento
# ───────────────────────────────────────────────

def test_tenant_isolation(db_session):
    """Las notificaciones del tenant A no se filtran al tenant B."""
    t_a = _make_tenant(db_session)
    t_b = _make_tenant(db_session)
    # Solo A tiene Costos sin configurar
    _make_business_costs(db_session, str(t_a.id), version=1)
    _make_business_costs(db_session, str(t_b.id), version=2)

    from app.services.notifications import NotificationsEngine
    notifs_a = NotificationsEngine(db_session, t_a.id).detect_all()
    notifs_b = NotificationsEngine(db_session, t_b.id).detect_all()

    # A tiene 1 info (costos)
    assert any(n["category"] == "costs" and n["severity"] == "info" for n in notifs_a)
    # B no tiene la info de costos
    assert not any(n["category"] == "costs" and n["severity"] == "info" for n in notifs_b)


# ───────────────────────────────────────────────
# Tests de dataclass
# ───────────────────────────────────────────────

def test_notification_to_dict_has_all_fields():
    """Notification.to_dict() expone todos los campos."""
    from app.services.notifications import Notification
    n = Notification(
        id="notif_abc",
        severity="warning",
        category="pricing",
        title="Test",
        body="Body",
        action_label="Ir",
        action_url="/x",
        entity_type="product",
        entity_id="prod-1",
        detected_at="2026-01-01T00:00:00+00:00",
        metric={"k": 1},
    )
    d = n.to_dict()
    assert d["id"] == "notif_abc"
    assert d["severity"] == "warning"
    assert d["metric"] == {"k": 1}


def test_notification_metric_default_is_empty_dict():
    """Notification.metric por defecto es {} (no None)."""
    from app.services.notifications import Notification
    n = Notification(
        id="x", severity="info", category="system",
        title="t", body="b", action_label="a", action_url="u",
        entity_type="tenant", entity_id="tenant", detected_at="now",
    )
    assert n.metric == {}
