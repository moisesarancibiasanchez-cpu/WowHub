"""Tests del módulo Costos (Fase 2 V8).

Cubre:
  - Cálculo puro de `cost_hour` y `total_fixed` (incluyendo "No aplica")
  - CRUD de /tenants/{id}/costs (GET auto-create, PUT con recálculo)
  - Breakdown por sección (Personal / Básicos / Otros)
  - Pricing suggestion con y sin override de margen
  - Aislamiento entre tenants
  - Edge cases: horas=0, todos NA, margen=0
"""
import pytest


def _bootstrap(client, slug="costs-shop"):
    """Helper: crea usuario + tenant y devuelve el access_token + tenant_id."""
    r = client.post("/api/v1/auth/register", json={
        "email": f"{slug}@e.com",
        "password": "test1234",
        "full_name": "Costs Test",
        "create_tenant": True,
        "tenant_legal_name": f"Test {slug}",
        "tenant_slug": slug,
    })
    data = r.json()
    return data["access_token"], data["current_tenant"]["tenant_id"]


# ── Tests de la lógica pura (service) ──────────────────────
def test_compute_cost_hour_basic():
    """100.000 fijos / 100 horas = 1.000 / hora."""
    from app.models.business_costs import BusinessCosts
    from app.database import SessionLocal
    from app.models.tenant import Tenant
    import uuid as _uuid

    with SessionLocal() as db:
        t = Tenant(
            id=_uuid.uuid4(),
            slug=f"t-{_uuid.uuid4().hex[:8]}",
            legal_name="Test",
            display_name="Test",
            currency="CLP",
            is_active=True,
        )
        db.add(t)
        db.flush()
        bc = BusinessCosts(
            tenant_id=str(t.id),
            owner_salary_cents=0,
            workers_salary_cents=0,
            rent_cents=100_000,
            electricity_cents=0,
            water_cents=0,
            gas_cents=0,
            software_cents=0,
            advertising_cents=0,
            payment_commission_cents=0,
            packaging_cents=0,
            maintenance_cents=0,
            depreciation_cents=0,
            productive_hours_per_month=100,
            is_na={},
        )
        bc.recompute_derived()
        assert bc.total_fixed_cents == 100_000
        assert bc.cost_hour_cents == 1_000


def test_compute_cost_hour_excludes_na():
    """Los campos marcados como No aplica no entran al cálculo."""
    from app.models.business_costs import BusinessCosts
    from app.database import SessionLocal
    from app.models.tenant import Tenant
    import uuid as _uuid

    with SessionLocal() as db:
        t = Tenant(
            id=_uuid.uuid4(), slug=f"t-{_uuid.uuid4().hex[:8]}",
            legal_name="T", display_name="T", currency="CLP", is_active=True,
        )
        db.add(t)
        db.flush()
        bc = BusinessCosts(
            tenant_id=str(t.id),
            rent_cents=400_000,
            electricity_cents=100_000,
            water_cents=50_000,
            gas_cents=80_000,
            productive_hours_per_month=160,
            is_na={"gas_cents": True, "water_cents": True},
        )
        bc.recompute_derived()
        # 400k + 100k = 500k fijos (gas y agua excluidos)
        assert bc.total_fixed_cents == 500_000
        # 500k / 160 = 3125 (redondeo hacia arriba defensivo)
        assert bc.cost_hour_cents == 3_125


def test_compute_cost_hour_zero_does_not_divide_by_zero():
    """Horas productivas = 0 → no rompe (usamos max(1, hours))."""
    from app.models.business_costs import BusinessCosts
    from app.database import SessionLocal
    from app.models.tenant import Tenant
    import uuid as _uuid

    with SessionLocal() as db:
        t = Tenant(
            id=_uuid.uuid4(), slug=f"t-{_uuid.uuid4().hex[:8]}",
            legal_name="T", display_name="T", currency="CLP", is_active=True,
        )
        db.add(t)
        db.flush()
        bc = BusinessCosts(
            tenant_id=str(t.id),
            rent_cents=200_000,
            productive_hours_per_month=0,  # edge case
            is_na={},
        )
        bc.recompute_derived()
        assert bc.total_fixed_cents == 200_000
        # 200k / 1 = 200k (porque usamos max(1, hours))
        assert bc.cost_hour_cents == 200_000


# ── Tests de API ──────────────────────────────────────────
def test_get_costs_auto_creates_with_defaults(client):
    """GET /costs en un tenant sin config → crea defaults con costo_hora calculado."""
    token, tid = _bootstrap(client, "costs-1")
    r = client.get(f"/api/v1/tenants/{tid}/costs",
                   headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["tenant_id"] == tid
    # Defaults de la maqueta V8
    assert data["owner_salary_cents"] == 700_000
    assert data["rent_cents"] == 450_000
    # Costo_hora pre-calculado (no 0)
    assert data["cost_hour_cents"] > 0
    assert data["version"] == 1  # versión inicial = defaults


def test_put_costs_recomputes_cost_hour(client):
    token, tid = _bootstrap(client, "costs-2")
    r = client.put(
        f"/api/v1/tenants/{tid}/costs",
        json={
            "owner_salary_cents": 1_000_000,
            "workers_salary_cents": 2_000_000,
            "rent_cents": 600_000,
            "electricity_cents": 200_000,
            "water_cents": 50_000,
            "gas_cents": 0,
            "software_cents": 100_000,
            "advertising_cents": 0,
            "payment_commission_cents": 0,
            "packaging_cents": 0,
            "maintenance_cents": 0,
            "depreciation_cents": 0,
            "productive_hours_per_month": 160,
            "target_margin_pct": 35,
            "waste_pct": 2,
            "is_na": {"gas_cents": True},
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    # 1M + 2M + 600k + 200k + 50k + 100k = 3.950.000 (gas excluido)
    assert data["total_fixed_cents"] == 3_950_000
    # 3.950.000 / 160 = 24.687.5 → ceil = 24.688
    assert data["cost_hour_cents"] == 24_688
    # version se incrementa
    assert data["version"] >= 2


def test_breakdown_returns_section_totals(client):
    token, tid = _bootstrap(client, "costs-3")
    r = client.put(
        f"/api/v1/tenants/{tid}/costs",
        json={
            "owner_salary_cents": 500_000,
            "workers_salary_cents": 1_000_000,
            "rent_cents": 400_000,
            "electricity_cents": 150_000,
            "water_cents": 30_000,
            "gas_cents": 0,
            "software_cents": 80_000,
            "advertising_cents": 0,
            "payment_commission_cents": 0,
            "packaging_cents": 0,
            "maintenance_cents": 0,
            "depreciation_cents": 0,
            "productive_hours_per_month": 160,
            "target_margin_pct": 30,
            "waste_pct": 0,
            "is_na": {},
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200

    r = client.get(f"/api/v1/tenants/{tid}/costs/breakdown",
                   headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    bd = r.json()
    # Personal = 500k + 1M = 1.5M
    assert bd["personal_total_cents"] == 1_500_000
    # Básicos = 400k + 150k + 30k + 0 = 580k
    assert bd["basics_total_cents"] == 580_000
    # Otros = 80k
    assert bd["other_fixed_total_cents"] == 80_000
    # Total = 1.5M + 580k + 80k = 2.160.000
    assert bd["total_fixed_cents"] == 2_160_000
    # 2.160.000 / 160 = 13.500
    assert bd["cost_hour_cents"] == 13_500
    assert bd["is_configured"] is True
    assert bd["currency"] == "CLP"


def test_pricing_suggestion_basic(client):
    token, tid = _bootstrap(client, "costs-4")
    # Config: costo hora = 10.000 (1.600.000 fijos / 160 horas)
    r = client.put(
        f"/api/v1/tenants/{tid}/costs",
        json={
            "owner_salary_cents": 800_000,
            "workers_salary_cents": 0,
            "rent_cents": 500_000,
            "electricity_cents": 200_000,
            "water_cents": 50_000,
            "gas_cents": 50_000,
            "software_cents": 0,
            "advertising_cents": 0,
            "payment_commission_cents": 0,
            "packaging_cents": 0,
            "maintenance_cents": 0,
            "depreciation_cents": 0,
            "productive_hours_per_month": 160,
            "target_margin_pct": 30,
            "waste_pct": 0,
            "is_na": {},
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    cfg = r.json()
    assert cfg["cost_hour_cents"] == 10_000  # 1.600.000 / 160

    # Pricing suggestion: insumos 2.500, tiempo 15 min, margen 30%
    r = client.post(
        f"/api/v1/tenants/{tid}/costs/pricing-suggestion",
        json={
            "material_cost_cents": 2_500,
            "production_time_min": 15,
            "target_margin_pct": 30,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    data = r.json()
    # labor = ceil(15/60 * 10000) = 2500
    assert data["cost_real_cents"] == 5_000  # 2500 + 2500
    # suggested = ceil(5000 / 0.7) = 7143
    assert data["suggested_price_cents"] == 7_143
    assert data["target_margin_pct"] == 30
    assert data["cost_hour_used_cents"] == 10_000


def test_pricing_suggestion_with_current_price_shows_margin(client):
    token, tid = _bootstrap(client, "costs-5")
    r = client.post(
        f"/api/v1/tenants/{tid}/costs/pricing-suggestion?current_price_cents=8000",
        json={"material_cost_cents": 5_000, "production_time_min": 0},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    data = r.json()
    # cost_real = 5000 (sin tiempo, labor = 0)
    assert data["cost_real_cents"] == 5_000
    # current_margin = (8000-5000)/8000 * 100 = 37.5
    assert data["current_margin_pct"] == 37.5
    assert data["current_price_cents"] == 8_000


def test_pricing_suggestion_zero_production_time(client):
    """Sin tiempo de producción, no hay componente de mano de obra."""
    token, tid = _bootstrap(client, "costs-6")
    r = client.post(
        f"/api/v1/tenants/{tid}/costs/pricing-suggestion",
        json={"material_cost_cents": 1_000, "production_time_min": 0},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["cost_real_cents"] == 1_000
    # margin default = 30 → suggested = ceil(1000 / 0.7) = 1429
    assert data["suggested_price_cents"] == 1_429


def test_fields_meta_returns_15_fields(client):
    token, tid = _bootstrap(client, "costs-7")
    r = client.get(f"/api/v1/tenants/{tid}/costs/fields-meta",
                   headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    fields = r.json()["fields"]
    # 14 monetary/int/pct + productive_hours + target_margin = 15 entries
    # (productive_hours + target_margin son parte de los 14+1; total 15)
    assert len(fields) == 15
    # Verificar que incluye las 4 secciones
    sections = {f["section"] for f in fields}
    assert "personal" in sections
    assert "operacion" in sections
    assert "basicos" in sections
    assert "otros" in sections


def test_is_na_persists_and_excludes_correctly(client):
    token, tid = _bootstrap(client, "costs-8")
    r = client.put(
        f"/api/v1/tenants/{tid}/costs",
        json={
            "owner_salary_cents": 1_000_000,
            "workers_salary_cents": 0,
            "rent_cents": 0,
            "electricity_cents": 0,
            "water_cents": 0,
            "gas_cents": 500_000,
            "software_cents": 0,
            "advertising_cents": 0,
            "payment_commission_cents": 0,
            "packaging_cents": 0,
            "maintenance_cents": 0,
            "depreciation_cents": 0,
            "productive_hours_per_month": 100,
            "target_margin_pct": 30,
            "waste_pct": 0,
            "is_na": {"gas_cents": True, "rent_cents": True},
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    cfg = r.json()
    # Solo se cuenta owner_salary = 1M
    assert cfg["total_fixed_cents"] == 1_000_000
    assert cfg["cost_hour_cents"] == 10_000
    assert cfg["is_na"]["gas_cents"] is True
    assert cfg["is_na"]["rent_cents"] is True


def test_costs_are_tenant_isolated(client):
    """Las configs de costos de un tenant no se filtran a otro."""
    t1, tid1 = _bootstrap(client, "costs-iso-1")
    t2, tid2 = _bootstrap(client, "costs-iso-2")

    r = client.put(
        f"/api/v1/tenants/{tid1}/costs",
        json={
            "owner_salary_cents": 1_000_000,
            "workers_salary_cents": 0,
            "rent_cents": 500_000,
            "electricity_cents": 0,
            "water_cents": 0,
            "gas_cents": 0,
            "software_cents": 0,
            "advertising_cents": 0,
            "payment_commission_cents": 0,
            "packaging_cents": 0,
            "maintenance_cents": 0,
            "depreciation_cents": 0,
            "productive_hours_per_month": 160,
            "target_margin_pct": 30,
            "waste_pct": 0,
            "is_na": {},
        },
        headers={"Authorization": f"Bearer {t1}"},
    )
    assert r.status_code == 200
    # tenant 2 ve defaults (no lo que pusimos en tenant 1)
    r = client.get(f"/api/v1/tenants/{tid2}/costs",
                   headers={"Authorization": f"Bearer {t2}"})
    assert r.status_code == 200
    cfg2 = r.json()
    # tenant 2 sigue con el costo hora default (no 9.375 = 1.5M / 160)
    assert cfg2["cost_hour_cents"] != 9_375


def test_costs_require_auth(client):
    _, tid = _bootstrap(client, "costs-noauth")
    r = client.get(f"/api/v1/tenants/{tid}/costs")
    assert r.status_code in (401, 403)


def test_put_validates_negative_values(client):
    token, tid = _bootstrap(client, "costs-validation")
    r = client.put(
        f"/api/v1/tenants/{tid}/costs",
        json={
            "owner_salary_cents": -100,  # invalid
            "workers_salary_cents": 0,
            "rent_cents": 0,
            "electricity_cents": 0,
            "water_cents": 0,
            "gas_cents": 0,
            "software_cents": 0,
            "advertising_cents": 0,
            "payment_commission_cents": 0,
            "packaging_cents": 0,
            "maintenance_cents": 0,
            "depreciation_cents": 0,
            "productive_hours_per_month": 160,
            "target_margin_pct": 30,
            "waste_pct": 0,
            "is_na": {},
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 422
