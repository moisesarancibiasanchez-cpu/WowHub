"""Tests de productos y catálogo público."""
import pytest


def _bootstrap(client, slug="test-co"):
    r = client.post("/api/v1/auth/register", json={
        "email": f"{slug}@e.com", "password": "test1234", "full_name": "Test User",
        "create_tenant": True,
        "tenant_legal_name": f"Test {slug}", "tenant_slug": slug,
    })
    return r.json()


def test_create_and_list_products(client):
    auth = _bootstrap(client, "shop1")
    token = auth["access_token"]
    tid = auth["current_tenant"]["tenant_id"]

    r = client.post(f"/api/v1/tenants/{tid}/products", json={
        "sku": "P-1", "name": "Café", "slug": "cafe", "price_cents": 2500, "status": "active",
    }, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 201, r.text
    assert r.json()["on_sale"] is False
    assert r.json()["discount_pct"] is None

    # List
    r = client.get(f"/api/v1/tenants/{tid}/products", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 1
    assert data["items"][0]["sku"] == "P-1"


def test_product_with_compare_price_shows_discount(client):
    auth = _bootstrap(client, "shop2")
    token = auth["access_token"]
    tid = auth["current_tenant"]["tenant_id"]

    r = client.post(f"/api/v1/tenants/{tid}/products", json={
        "sku": "P-2", "name": "Café Promo", "slug": "cafe-promo",
        "price_cents": 2000, "compare_at_cents": 2500, "status": "active",
    }, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 201
    p = r.json()
    assert p["on_sale"] is True
    assert p["discount_pct"] == 20


def test_product_compare_price_must_be_gte(client):
    auth = _bootstrap(client, "shop3")
    token = auth["access_token"]
    tid = auth["current_tenant"]["tenant_id"]

    r = client.post(f"/api/v1/tenants/{tid}/products", json={
        "sku": "P-3", "name": "X", "slug": "x",
        "price_cents": 3000, "compare_at_cents": 2500,  # invalid
    }, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 422


def test_product_unique_sku_per_tenant(client):
    auth = _bootstrap(client, "shop4")
    token = auth["access_token"]
    tid = auth["current_tenant"]["tenant_id"]
    body = {"sku": "UNIQ-1", "name": "Test Product", "slug": "test-prod-1", "price_cents": 100}
    r1 = client.post(f"/api/v1/tenants/{tid}/products", json=body, headers={"Authorization": f"Bearer {token}"})
    assert r1.status_code == 201
    r2 = client.post(f"/api/v1/tenants/{tid}/products", json={**body, "slug": "test-prod-2"}, headers={"Authorization": f"Bearer {token}"})
    assert r2.status_code == 409


def test_public_catalog_no_auth(client):
    auth = _bootstrap(client, "shop-public")
    token = auth["access_token"]
    tid = auth["current_tenant"]["tenant_id"]
    # Create active product
    client.post(f"/api/v1/tenants/{tid}/products", json={
        "sku": "PUB-1", "name": "Visible", "slug": "visible",
        "price_cents": 1000, "status": "active",
    }, headers={"Authorization": f"Bearer {token}"})
    # Public catalog (no auth)
    r = client.get(f"/api/v1/public/t/shop-public/catalog")
    assert r.status_code == 200
    items = r.json()["items"]
    assert any(p["sku"] == "PUB-1" for p in items)


def test_public_catalog_excludes_drafts(client):
    auth = _bootstrap(client, "shop-mix")
    token = auth["access_token"]
    tid = auth["current_tenant"]["tenant_id"]
    # active
    client.post(f"/api/v1/tenants/{tid}/products", json={
        "sku": "ACT-1", "name": "Active Product", "slug": "active-prod", "price_cents": 100, "status": "active",
    }, headers={"Authorization": f"Bearer {token}"})
    # draft
    client.post(f"/api/v1/tenants/{tid}/products", json={
        "sku": "DRF-1", "name": "Draft Product", "slug": "draft-prod", "price_cents": 100, "status": "draft",
    }, headers={"Authorization": f"Bearer {token}"})
    r = client.get(f"/api/v1/public/t/shop-mix/catalog")
    items = r.json()["items"]
    skus = [p["sku"] for p in items]
    assert "ACT-1" in skus
    assert "DRF-1" not in skus


# ── Fase 3 (V8) — production_time_min + pricing derivado ──
def test_product_create_accepts_production_time_min(client):
    auth = _bootstrap(client, "shop-time")
    token = auth["access_token"]
    tid = auth["current_tenant"]["tenant_id"]

    r = client.post(f"/api/v1/tenants/{tid}/products", json={
        "sku": "T-1", "name": "Latte", "slug": "latte-t1",
        "price_cents": 3200, "cost_cents": 1200, "production_time_min": 4,
        "status": "active",
    }, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 201, r.text
    p = r.json()
    assert p["production_time_min"] == 4
    # Sin BusinessCosts configurado, los derivados quedan en 0/unknown
    assert p["cost_real_cents"] == 0
    assert p["suggested_price_cents"] == 0
    assert p["current_margin_pct"] is None
    assert p["target_margin_pct"] is None
    assert p["health"] == "unknown"
    assert p["health_message"] is None


def test_product_pricing_endpoint_with_business_costs(client):
    """Con BusinessCosts configurado, los derivados se calculan."""
    auth = _bootstrap(client, "shop-pricing")
    token = auth["access_token"]
    tid = auth["current_tenant"]["tenant_id"]

    # Crear producto con cost_cents + production_time_min
    r = client.post(f"/api/v1/tenants/{tid}/products", json={
        "sku": "PR-1", "name": "Cappuccino", "slug": "cap-pr1",
        "price_cents": 3200, "cost_cents": 1000, "production_time_min": 4,
        "status": "active",
    }, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 201, r.text
    pid = r.json()["id"]

    # Configurar BusinessCosts (costo_hora + margen objetivo)
    r = client.put(f"/api/v1/tenants/{tid}/costs", json={
        "owner_salary_cents": 1_000_000,
        "workers_salary_cents": 0,
        "rent_cents": 0, "electricity_cents": 0, "water_cents": 0, "gas_cents": 0,
        "software_cents": 0, "advertising_cents": 0, "payment_commission_cents": 0,
        "packaging_cents": 0, "maintenance_cents": 0, "depreciation_cents": 0,
        "productive_hours_per_month": 100,  # 1.000.000 / 100 = 10.000
        "target_margin_pct": 30,
        "waste_pct": 0,
        "is_na": {},
    }, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text

    # Llamar al endpoint /pricing
    r = client.get(f"/api/v1/tenants/{tid}/products/{pid}/pricing",
                   headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    p = r.json()
    # costo_hora = 10.000, labor = 4/60 * 10.000 = 666.67 → 667
    # costo_real = 1000 + 667 = 1667
    assert p["cost_real_cents"] == 1667
    # sugerido = 1667 / 0.7 = 2381.43 → 2382
    assert p["suggested_price_cents"] == 2382
    # target_margin_pct = 30
    assert p["target_margin_pct"] == 30
    assert p["cost_hour_used_cents"] == 10_000
    # margen actual: (3200-1667)/3200 * 100 = 47.91% (redondeado a 2 dec)
    assert abs(p["current_margin_pct"] - 47.91) < 0.01
    # 47.91% >= 30% target → healthy
    assert p["health"] == "healthy"
    assert p["health_message"] == "Saludable"


def test_product_list_includes_pricing_derivatives(client):
    auth = _bootstrap(client, "shop-listp")
    token = auth["access_token"]
    tid = auth["current_tenant"]["tenant_id"]

    # Producto
    r = client.post(f"/api/v1/tenants/{tid}/products", json={
        "sku": "LP-1", "name": "Espresso", "slug": "esp-lp1",
        "price_cents": 1800, "cost_cents": 500, "production_time_min": 2,
        "status": "active",
    }, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 201

    # Sin Costos: derivados vacíos en el list
    r = client.get(f"/api/v1/tenants/{tid}/products",
                   headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    items = r.json()["items"]
    assert items[0]["production_time_min"] == 2
    assert items[0]["cost_real_cents"] == 0
    assert items[0]["current_margin_pct"] is None
    assert items[0]["health"] == "unknown"

    # Activar Costos
    client.put(f"/api/v1/tenants/{tid}/costs", json={
        "owner_salary_cents": 800_000,
        "workers_salary_cents": 0,
        "rent_cents": 0, "electricity_cents": 0, "water_cents": 0, "gas_cents": 0,
        "software_cents": 0, "advertising_cents": 0, "payment_commission_cents": 0,
        "packaging_cents": 0, "maintenance_cents": 0, "depreciation_cents": 0,
        "productive_hours_per_month": 80,  # 800.000/80 = 10.000
        "target_margin_pct": 50,  # margen agresivo
        "waste_pct": 0,
        "is_na": {},
    }, headers={"Authorization": f"Bearer {token}"})

    # Con Costos: derivados poblados
    r = client.get(f"/api/v1/tenants/{tid}/products",
                   headers={"Authorization": f"Bearer {token}"})
    items = r.json()["items"]
    p = items[0]
    # labor = 2/60*10000 = 333.34 → 334; real = 500 + 334 = 834
    assert p["cost_real_cents"] == 834
    assert p["target_margin_pct"] == 50
    # margen: (1800-834)/1800 = 53.67% → healthy (>= 50%)
    assert abs(p["current_margin_pct"] - 53.67) < 0.01
    assert p["health"] == "healthy"


def test_product_update_with_production_time_min(client):
    auth = _bootstrap(client, "shop-upd")
    token = auth["access_token"]
    tid = auth["current_tenant"]["tenant_id"]

    r = client.post(f"/api/v1/tenants/{tid}/products", json={
        "sku": "UP-1", "name": "Moka", "slug": "moka-up1",
        "price_cents": 3500, "production_time_min": 3,
        "status": "active",
    }, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 201
    pid = r.json()["id"]
    assert r.json()["production_time_min"] == 3

    r = client.patch(f"/api/v1/tenants/{tid}/products/{pid}",
                     json={"production_time_min": 6},
                     headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["production_time_min"] == 6


def test_product_validation_production_time_negative(client):
    """Pydantic debe rechazar production_time_min negativo."""
    auth = _bootstrap(client, "shop-val")
    token = auth["access_token"]
    tid = auth["current_tenant"]["tenant_id"]

    r = client.post(f"/api/v1/tenants/{tid}/products", json={
        "sku": "V-1", "name": "X", "slug": "x-v1",
        "price_cents": 1000, "production_time_min": -5,
    }, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 422


def test_product_danger_health_with_low_margin(client):
    """Producto con margen muy bajo → health = 'danger'."""
    auth = _bootstrap(client, "shop-danger")
    token = auth["access_token"]
    tid = auth["current_tenant"]["tenant_id"]

    # Producto caro de producir y barato de vender
    r = client.post(f"/api/v1/tenants/{tid}/products", json={
        "sku": "DG-1", "name": "Pendón", "slug": "pendon",
        "price_cents": 9990, "cost_cents": 7420, "production_time_min": 25,
        "status": "active",
    }, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 201
    pid = r.json()["id"]

    # Costos: target 30%, costo_hora = $32.000/h
    client.put(f"/api/v1/tenants/{tid}/costs", json={
        "owner_salary_cents": 5_000_000, "workers_salary_cents": 0,
        "rent_cents": 0, "electricity_cents": 0, "water_cents": 0, "gas_cents": 0,
        "software_cents": 0, "advertising_cents": 0, "payment_commission_cents": 0,
        "packaging_cents": 0, "maintenance_cents": 0, "depreciation_cents": 0,
        "productive_hours_per_month": 160,  # 5.000.000/160 = 31.250
        "target_margin_pct": 30,
        "waste_pct": 0,
        "is_na": {},
    }, headers={"Authorization": f"Bearer {token}"})

    r = client.get(f"/api/v1/tenants/{tid}/products/{pid}/pricing",
                   headers={"Authorization": f"Bearer {token}"})
    p = r.json()
    # labor = 25/60 * 31.250 = 13.020.83 → 13.021
    # real = 7420 + 13021 = 20.441
    assert p["cost_real_cents"] == 20441
    # margen: (9990-20441)/9990 = -104.61% → danger
    assert p["current_margin_pct"] < -100
    assert p["health"] == "danger"


# ── HU_11 — Margen producto + simulación ─────────────────
def test_product_margin_endpoint_without_business_costs(client):
    """HU_11 — GET /margin sin BusinessCosts: degradación elegante.

    Sin Costos configurados, ``compute_for_product`` devuelve el
    snapshot vacío (cost_real=0, margin=None, health=unknown) — igual
    que el endpoint ``/pricing`` ya existente. El endpoint debe
    reportar el ``cost_cents`` y ``price_cents`` crudos del producto
    más la sugerencia de configurar Costos vía ``health=unknown``.
    """
    auth = _bootstrap(client, "shop-margin")
    token = auth["access_token"]
    tid = auth["current_tenant"]["tenant_id"]

    r = client.post(f"/api/v1/tenants/{tid}/products", json={
        "sku": "MG-1", "name": "Cappuccino", "slug": "cap-mg1",
        "price_cents": 3200, "cost_cents": 1000, "production_time_min": 4,
        "status": "active",
    }, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 201, r.text
    pid = r.json()["id"]

    # Sin BusinessCosts: derivados en estado empty (mismo patrón que /pricing)
    r = client.get(f"/api/v1/tenants/{tid}/products/{pid}/margin",
                   headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    m = r.json()
    assert m["product_id"] == pid
    assert m["cost_cents"] == 1000     # costo cargado crudo
    assert m["cost_real_cents"] == 0   # sin Costos → degradación
    assert m["price_cents"] == 3200
    assert m["margin_cents"] == 3200   # price - 0
    assert m["margin_pct"] is None     # sin precio target no se calcula
    assert m["target_margin_pct"] is None
    assert m["suggested_price_cents"] == 0
    assert m["cost_hour_used_cents"] == 0
    # Sin target → health unknown (mismo que pricing endpoint)
    assert m["health"] == "unknown"
    assert m["health_message"] is None


def test_product_margin_endpoint_with_business_costs(client):
    """HU_11 — GET /margin con BusinessCosts: incluye mano de obra + target."""
    auth = _bootstrap(client, "shop-mg2")
    token = auth["access_token"]
    tid = auth["current_tenant"]["tenant_id"]

    r = client.post(f"/api/v1/tenants/{tid}/products", json={
        "sku": "MG-2", "name": "Latte", "slug": "latte-mg2",
        "price_cents": 3200, "cost_cents": 1000, "production_time_min": 4,
        "status": "active",
    }, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 201
    pid = r.json()["id"]

    # Configurar Costos: costo_hora 10.000, target 30%
    client.put(f"/api/v1/tenants/{tid}/costs", json={
        "owner_salary_cents": 1_000_000, "workers_salary_cents": 0,
        "rent_cents": 0, "electricity_cents": 0, "water_cents": 0, "gas_cents": 0,
        "software_cents": 0, "advertising_cents": 0, "payment_commission_cents": 0,
        "packaging_cents": 0, "maintenance_cents": 0, "depreciation_cents": 0,
        "productive_hours_per_month": 100,
        "target_margin_pct": 30,
        "waste_pct": 0, "is_na": {},
    }, headers={"Authorization": f"Bearer {token}"})

    r = client.get(f"/api/v1/tenants/{tid}/products/{pid}/margin",
                   headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    m = r.json()
    # labor = ceil(4/60 * 10000) = 667; real = 1667
    assert m["cost_real_cents"] == 1667
    # margin_cents = 3200 - 1667 = 1533
    assert m["margin_cents"] == 1533
    assert abs(m["margin_pct"] - 47.91) < 0.01
    assert m["target_margin_pct"] == 30
    assert m["suggested_price_cents"] == 2382
    assert m["cost_hour_used_cents"] == 10000
    assert m["health"] == "healthy"
    assert m["health_message"] == "Saludable"


def test_product_margin_not_found(client):
    """HU_11 — GET /margin sobre producto inexistente → 404."""
    auth = _bootstrap(client, "shop-mg3")
    token = auth["access_token"]
    tid = auth["current_tenant"]["tenant_id"]

    fake_pid = "00000000-0000-0000-0000-000000000000"
    r = client.get(f"/api/v1/tenants/{tid}/products/{fake_pid}/margin",
                   headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 404


def test_product_margin_simulate_lower_cost(client):
    """HU_11 — POST /margin/simulate con costo más barato."""
    auth = _bootstrap(client, "shop-sim1")
    token = auth["access_token"]
    tid = auth["current_tenant"]["tenant_id"]

    r = client.post(f"/api/v1/tenants/{tid}/products", json={
        "sku": "SM-1", "name": "Moka", "slug": "moka-sm1",
        "price_cents": 3200, "cost_cents": 1500, "production_time_min": 0,
        "status": "active",
    }, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 201
    pid = r.json()["id"]

    # Activar Costos para que el snapshot actual no salga vacío
    client.put(f"/api/v1/tenants/{tid}/costs", json={
        "owner_salary_cents": 0, "workers_salary_cents": 0,
        "rent_cents": 0, "electricity_cents": 0, "water_cents": 0, "gas_cents": 0,
        "software_cents": 0, "advertising_cents": 0, "payment_commission_cents": 0,
        "packaging_cents": 0, "maintenance_cents": 0, "depreciation_cents": 0,
        "productive_hours_per_month": 100, "target_margin_pct": 30,
        "waste_pct": 0, "is_na": {},
    }, headers={"Authorization": f"Bearer {token}"})

    # Simular costo nuevo = 500 (más barato)
    r = client.post(f"/api/v1/tenants/{tid}/products/{pid}/margin/simulate",
                    json={"new_cost_cents": 500},
                    headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    s = r.json()
    # Snapshot actual: real=1500 (sin mano de obra, production_time_min=0)
    assert s["current"]["cost_real_cents"] == 1500
    assert s["current"]["margin_cents"] == 1700
    assert s["current"]["target_margin_pct"] == 30
    # Proyección: real=500, margin=2700
    assert s["projected_cost_cents"] == 500
    assert s["projected_cost_real_cents"] == 500
    assert s["projected_margin_cents"] == 2700
    # 2700/3200 * 100 = 84.375%
    assert abs(s["projected_margin_pct"] - 84.375) < 0.01
    assert s["projected_health"] == "healthy"


def test_product_margin_simulate_higher_cost_danger(client):
    """HU_11 — POST /margin/simulate con costo casi igual al precio → danger."""
    auth = _bootstrap(client, "shop-sim2")
    token = auth["access_token"]
    tid = auth["current_tenant"]["tenant_id"]

    r = client.post(f"/api/v1/tenants/{tid}/products", json={
        "sku": "SM-2", "name": "Espresso", "slug": "esp-sm2",
        "price_cents": 1800, "cost_cents": 500, "production_time_min": 0,
        "status": "active",
    }, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 201
    pid = r.json()["id"]

    # Costos con target 30%
    client.put(f"/api/v1/tenants/{tid}/costs", json={
        "owner_salary_cents": 0, "workers_salary_cents": 0,
        "rent_cents": 0, "electricity_cents": 0, "water_cents": 0, "gas_cents": 0,
        "software_cents": 0, "advertising_cents": 0, "payment_commission_cents": 0,
        "packaging_cents": 0, "maintenance_cents": 0, "depreciation_cents": 0,
        "productive_hours_per_month": 100,
        "target_margin_pct": 30,
        "waste_pct": 0, "is_na": {},
    }, headers={"Authorization": f"Bearer {token}"})

    # Simular costo 1600 (casi el precio): margen = 200/1800 = 11.11%
    # 11.11% < 50% de 30% (15%) → danger
    r = client.post(f"/api/v1/tenants/{tid}/products/{pid}/margin/simulate",
                    json={"new_cost_cents": 1600},
                    headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    s = r.json()
    assert s["projected_cost_real_cents"] == 1600
    assert s["projected_margin_cents"] == 200
    assert abs(s["projected_margin_pct"] - 11.11) < 0.01
    assert s["projected_health"] == "danger"


def test_product_margin_simulate_negative_cost_rejected(client):
    """HU_11 — Pydantic rechaza new_cost_cents negativo."""
    auth = _bootstrap(client, "shop-sim3")
    token = auth["access_token"]
    tid = auth["current_tenant"]["tenant_id"]

    r = client.post(f"/api/v1/tenants/{tid}/products", json={
        "sku": "SM-3", "name": "Prod", "slug": "prod-sm3",
        "price_cents": 1000, "cost_cents": 100,
    }, headers={"Authorization": f"Bearer {token}"})
    pid = r.json()["id"]

    r = client.post(f"/api/v1/tenants/{tid}/products/{pid}/margin/simulate",
                    json={"new_cost_cents": -100},
                    headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 422


def test_product_margin_simulate_does_not_mutate_product(client):
    """HU_11 — El simulador NO modifica cost_cents en la DB."""
    auth = _bootstrap(client, "shop-sim4")
    token = auth["access_token"]
    tid = auth["current_tenant"]["tenant_id"]

    r = client.post(f"/api/v1/tenants/{tid}/products", json={
        "sku": "SM-4", "name": "Prod Y", "slug": "prod-y-sm4",
        "price_cents": 2000, "cost_cents": 800, "status": "active",
    }, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 201
    pid = r.json()["id"]
    original_cost = r.json()["cost_cents"]
    assert original_cost == 800

    # Simular costo 100 (mucho más bajo)
    r = client.post(f"/api/v1/tenants/{tid}/products/{pid}/margin/simulate",
                    json={"new_cost_cents": 100},
                    headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200

    # Re-leer el producto: cost_cents debe seguir intacto
    r = client.get(f"/api/v1/tenants/{tid}/products/{pid}",
                   headers={"Authorization": f"Bearer {token}"})
    assert r.json()["cost_cents"] == 800
