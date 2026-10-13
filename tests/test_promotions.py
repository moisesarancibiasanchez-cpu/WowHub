"""Tests de promociones."""
import pytest
from datetime import datetime, timezone, timedelta


def _bootstrap(client, slug="promo-co"):
    r = client.post("/api/v1/auth/register", json={
        "email": f"{slug}@e.com", "password": "test1234", "full_name": "Test User",
        "create_tenant": True,
        "tenant_legal_name": f"Test {slug}", "tenant_slug": slug,
    })
    return r.json()


def test_create_and_list_promotions(client):
    auth = _bootstrap(client, "promo1")
    token = auth["access_token"]
    tid = auth["current_tenant"]["tenant_id"]

    r = client.post(f"/api/v1/tenants/{tid}/promotions", json={
        "name": "20% OFF",
        "code": "VERANO20",
        "promo_type": "percent",
        "discount_type": "percent",
        "discount_value": 20,
    }, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 201, r.text
    assert r.json()["code"] == "VERANO20"
    assert r.json()["is_valid_now"] is True

    r = client.get(f"/api/v1/tenants/{tid}/promotions", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert len(r.json()) == 1


def test_promotion_with_expiration_in_past_is_invalid(client):
    auth = _bootstrap(client, "promo2")
    token = auth["access_token"]
    tid = auth["current_tenant"]["tenant_id"]

    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    r = client.post(f"/api/v1/tenants/{tid}/promotions", json={
        "name": "Old", "promo_type": "percent", "discount_type": "percent",
        "discount_value": 10, "ends_at": past,
    }, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 201
    assert r.json()["is_valid_now"] is False


def test_promotion_exhausted_usage_limit(client):
    auth = _bootstrap(client, "promo3")
    token = auth["access_token"]
    tid = auth["current_tenant"]["tenant_id"]

    r = client.post(f"/api/v1/tenants/{tid}/promotions", json={
        "name": "Limited", "promo_type": "percent", "discount_type": "percent",
        "discount_value": 50, "usage_limit": 2,
    }, headers={"Authorization": f"Bearer {token}"})
    promo_id = r.json()["id"]
    # Patcher used_count al máximo
    r = client.patch(f"/api/v1/tenants/{tid}/promotions/{promo_id}", json={"used_count": 2},
                     headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    r = client.get(f"/api/v1/tenants/{tid}/promotions/{promo_id}", headers={"Authorization": f"Bearer {token}"})
    assert r.json()["is_valid_now"] is False
