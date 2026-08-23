"""Tests para `app.services.product_pricing` (Fase 3 V8).

Cubre los cálculos puros (sin DB) y la clasificación de salud.
"""
import math

import pytest

from app.services.product_pricing import (
    Health,
    ProductPricing,
    compute_for_product,
    compute_labor_cents,
    compute_margin_pct,
    compute_real_cost,
    compute_suggested_price,
    health_for_margin,
    health_message,
)


# ── compute_labor_cents ────────────────────────────────────
def test_labor_cents_basic():
    # 30 min a $6000/h → 30/60 * 6000 = 3000
    assert compute_labor_cents(30, 6000) == 3000


def test_labor_cents_zero_time():
    assert compute_labor_cents(0, 6000) == 0


def test_labor_cents_zero_cost_hour():
    # Sin costo_hora → 0 (degradación elegante, no falla)
    assert compute_labor_cents(60, 0) == 0


def test_labor_cents_rounds_up():
    # 25 min a $1000/h → 25/60*1000 = 416.66... → ceil = 417
    assert compute_labor_cents(25, 1000) == 417


# ── compute_real_cost ──────────────────────────────────────
def test_real_cost_with_materials_and_labor():
    # Insumos 2000 + 30 min a $6000/h (3000) = 5000
    assert compute_real_cost(2000, 30, 6000) == 5000


def test_real_cost_with_none_materials():
    # `cost_cents` puede ser None (producto sin costo cargado)
    assert compute_real_cost(None, 60, 6000) == 6000


def test_real_cost_no_labor_when_no_hour():
    # Sin costo_hora → solo insumos
    assert compute_real_cost(2500, 60, 0) == 2500


def test_real_cost_zero_minutes():
    # Tiempo 0 → solo insumos
    assert compute_real_cost(2500, 0, 6000) == 2500


# ── compute_margin_pct ─────────────────────────────────────
def test_margin_50_percent():
    # Precio 10000, costo 5000 → margen 50%
    assert compute_margin_pct(10000, 5000) == 50.0


def test_margin_30_percent_rounded():
    # Precio 7000, costo 4900 → (7000-4900)/7000*100 = 30.0
    assert compute_margin_pct(7000, 4900) == 30.0


def test_margin_zero_price_returns_none():
    assert compute_margin_pct(0, 5000) is None


def test_margin_negative_when_cost_exceeds_price():
    # Precio 4000, costo 5000 → margen negativo
    assert compute_margin_pct(4000, 5000) == pytest.approx(-25.0)


# ── compute_suggested_price ────────────────────────────────
def test_suggested_price_30_margin():
    # costo 5000, margen 30% → 5000 / 0.7 = 7142.86 → ceil = 7143
    assert compute_suggested_price(5000, 30) == 7143


def test_suggested_price_50_margin():
    # costo 5000, margen 50% → 5000 / 0.5 = 10000
    assert compute_suggested_price(5000, 50) == 10000


def test_suggested_price_zero_cost():
    assert compute_suggested_price(0, 30) == 0


def test_suggested_price_degenerate_margin_100():
    # margen >= 100 → cota superior
    assert compute_suggested_price(1000, 100) == 100_000


def test_suggested_price_clamps_negative_margin_to_zero():
    # margin negativo se trata como 0
    assert compute_suggested_price(1000, -10) == 1000


# ── health_for_margin ──────────────────────────────────────
def test_health_unknown_when_no_data():
    assert health_for_margin(None, 30) == "unknown"
    assert health_for_margin(20.0, None) == "unknown"


def test_health_healthy_when_meets_target():
    assert health_for_margin(30.0, 30) == "healthy"
    assert health_for_margin(50.0, 30) == "healthy"


def test_health_warning_when_close_to_target():
    # 30% target, 15% actual → 50% del target → warning
    assert health_for_margin(15.0, 30) == "warning"


def test_health_danger_when_below_half_target():
    # 30% target, 10% actual → 33% del target → danger
    assert health_for_margin(10.0, 30) == "danger"


def test_health_danger_when_negative_margin():
    # Margin negativo siempre es danger
    assert health_for_margin(-5.0, 30) == "danger"


# ── health_message ─────────────────────────────────────────
def test_message_for_healthy():
    assert health_message("healthy", current_margin_pct=35.0, target_margin_pct=30,
                          suggested_price_cents=5000, price_cents=8000) == "Saludable"


def test_message_for_warning():
    msg = health_message("warning", current_margin_pct=15.0, target_margin_pct=30,
                         suggested_price_cents=7000, price_cents=5000)
    assert msg == "Margen bajo"


def test_message_for_danger_with_diff_suggested():
    # Si hay sugerido distinto del precio actual → "Subir precio"
    msg = health_message("danger", current_margin_pct=5.0, target_margin_pct=30,
                         suggested_price_cents=8000, price_cents=5000)
    assert msg == "Subir precio"


def test_message_for_danger_no_suggested():
    msg = health_message("danger", current_margin_pct=5.0, target_margin_pct=30,
                         suggested_price_cents=0, price_cents=5000)
    assert msg == "Margen crítico"


def test_message_for_unknown_is_none():
    assert health_message("unknown", current_margin_pct=None, target_margin_pct=None,
                          suggested_price_cents=0, price_cents=0) is None


# ── compute_for_product ────────────────────────────────────
def test_compute_for_product_with_full_data():
    """Producto con cost_cents + production_time + tenant con Costos."""

    class FakeProduct:
        cost_cents = 2000  # insumos
        price_cents = 5000
        production_time_min = 30  # 30 min a $6000/h = 3000

    pricing = compute_for_product(
        FakeProduct(),
        cost_hour_cents=6000,
        target_margin_pct=30,
    )
    assert pricing.cost_real_cents == 5000  # 2000 + 3000
    # margen actual: (5000-5000)/5000 = 0
    assert pricing.current_margin_pct == 0.0
    # sugerido: 5000 / 0.7 = 7143
    assert pricing.suggested_price_cents == 7143
    assert pricing.target_margin_pct == 30
    assert pricing.cost_hour_used_cents == 6000
    # margin 0% < 30% target → < 50% del target → danger
    assert pricing.health == "danger"
    assert pricing.health_message == "Subir precio"


def test_compute_for_product_no_costs_returns_empty():
    """Sin Costos configurados → ProductPricing.empty()."""

    class FakeProduct:
        cost_cents = 2000
        price_cents = 5000
        production_time_min = 30

    pricing = compute_for_product(
        FakeProduct(),
        cost_hour_cents=0,
        target_margin_pct=None,
    )
    assert pricing == ProductPricing.empty()


def test_compute_for_product_healthy_margin():
    """Producto con buen margen."""

    class FakeProduct:
        cost_cents = 1000
        price_cents = 5000
        production_time_min = 0  # sin mano de obra

    pricing = compute_for_product(
        FakeProduct(),
        cost_hour_cents=6000,
        target_margin_pct=30,
    )
    # margen actual: (5000-1000)/5000 = 80%
    assert pricing.current_margin_pct == 80.0
    assert pricing.health == "healthy"
    assert pricing.health_message == "Saludable"


def test_compute_for_product_no_cost_cents():
    """Producto sin cost_cents → solo mano de obra cuenta como costo real."""

    class FakeProduct:
        cost_cents = None
        price_cents = 5000
        production_time_min = 60  # 1h a $6000/h = 6000

    pricing = compute_for_product(
        FakeProduct(),
        cost_hour_cents=6000,
        target_margin_pct=30,
    )
    assert pricing.cost_real_cents == 6000
    # margen: (5000-6000)/5000 = -20% → danger
    assert pricing.current_margin_pct == -20.0
    assert pricing.health == "danger"
