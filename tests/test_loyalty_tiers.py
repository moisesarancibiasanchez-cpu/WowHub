"""HU_29 — Tests de tiers de fidelidad (LoyaltyTier).

Cubre:
  - POST /loyalty/campaigns/{cid}/tiers crear tier
  - GET /loyalty/campaigns/{cid}/tiers listar tiers
  - PATCH /loyalty/tiers/{tid} actualizar tier
  - DELETE /loyalty/tiers/{tid} eliminar tier
  - Auto-asignación al sumar sellos (scan del POS)
"""
from __future__ import annotations

from app.config import settings
from app.services.loyalty_pass_service import QR_TOKEN_TTL_SECONDS


def _bootstrap(client, slug="lt-co"):
    r = client.post("/api/v1/auth/register", json={
        "email": f"{slug}@e.com",
        "password": "test1234",
        "full_name": "Owner",
        "create_tenant": True,
        "tenant_legal_name": f"Tiers {slug}",
        "tenant_slug": slug,
    })
    assert r.status_code == 201, r.text
    data = r.json()
    return data["access_token"], data["current_tenant"]["tenant_id"], slug


def _create_campaign(client, token, tid, **overrides):
    body = {
        "name": "Café gratis",
        "reward_label": "1 Café",
        "stamps_required": 10,
    }
    body.update(overrides)
    r = client.post(
        f"/api/v1/tenants/{tid}/loyalty/campaigns",
        json=body,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 201, r.text
    return r.json()


def _create_tier(client, token, tid, cid, **overrides):
    body = {
        "campaign_id": cid,
        "name": "Bronce",
        "min_stamps": 0,
        "discount_pct": 0.0,
    }
    body.update(overrides)
    r = client.post(
        f"/api/v1/tenants/{tid}/loyalty/campaigns/{cid}/tiers",
        json=body,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_create_tier_returns_201(client):
    token, tid, _ = _bootstrap(client, "lt-create")
    c = _create_campaign(client, token, tid)

    r = client.post(
        f"/api/v1/tenants/{tid}/loyalty/campaigns/{c['id']}/tiers",
        json={
            "campaign_id": c["id"],
            "name": "Bronce",
            "min_stamps": 0,
            "discount_pct": 0.0,
            "color": "#CD7F32",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["name"] == "Bronce"
    assert data["min_stamps"] == 0
    assert data["discount_pct"] == 0.0


def test_list_tiers_returns_in_order(client):
    token, tid, _ = _bootstrap(client, "lt-list")
    c = _create_campaign(client, token, tid)

    for name, min_stamps, sort_order in [
        ("Bronce", 0, 1),
        ("Plata", 5, 2),
        ("Oro", 10, 3),
    ]:
        _create_tier(
            client, token, tid, c["id"],
            name=name, min_stamps=min_stamps, sort_order=sort_order,
        )

    r = client.get(
        f"/api/v1/tenants/{tid}/loyalty/campaigns/{c['id']}/tiers",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    items = r.json()
    assert len(items) == 3
    names = [it["name"] for it in items]
    # Devuelve ordenados por sort_order
    assert names == ["Bronce", "Plata", "Oro"]


def test_patch_tier_updates_discount_pct(client):
    token, tid, _ = _bootstrap(client, "lt-patch")
    c = _create_campaign(client, token, tid)
    t = _create_tier(client, token, tid, c["id"], name="Bronce", min_stamps=0)

    r = client.patch(
        f"/api/v1/tenants/{tid}/loyalty/tiers/{t['id']}",
        json={"discount_pct": 5.0, "perks": {"freebie": "Agua"}},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["discount_pct"] == 5.0
    assert r.json()["perks"]["freebie"] == "Agua"


def test_delete_tier_returns_204(client):
    token, tid, _ = _bootstrap(client, "lt-del")
    c = _create_campaign(client, token, tid)
    t = _create_tier(client, token, tid, c["id"], name="Bronce", min_stamps=0)

    r = client.delete(
        f"/api/v1/tenants/{tid}/loyalty/tiers/{t['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 204


def test_unique_min_stamps_rejected(client):
    """Dos tiers con el mismo min_stamps en la misma campaña → 409."""
    token, tid, _ = _bootstrap(client, "lt-unique")
    c = _create_campaign(client, token, tid)
    _create_tier(client, token, tid, c["id"], name="Bronce", min_stamps=0)

    r = client.post(
        f"/api/v1/tenants/{tid}/loyalty/campaigns/{c['id']}/tiers",
        json={
            "campaign_id": c["id"],
            "name": "Cobre",
            "min_stamps": 0,  # colisiona con Bronce
            "discount_pct": 0,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 409, r.text


def test_tier_auto_assigned_on_scan(client):
    """Cuando stamps_current ≥ min_stamps, current_tier_id se asigna al tier.

    Validamos el hook ``recompute_tier_for_pass`` directamente,
    que es lo que dispara ``LoyaltyPassService.scan`` en el flujo real.
    """
    from app.models.loyalty_pass import CustomerPass
    from app.database import SessionLocal
    from app.services.loyalty_tier_service import LoyaltyTierService

    token, tid, slug = _bootstrap(client, "lt-auto")
    c = _create_campaign(client, token, tid, stamps_required=20)
    _create_tier(client, token, tid, c["id"], name="Bronce", min_stamps=0, sort_order=1)
    plata = _create_tier(
        client, token, tid, c["id"],
        name="Plata", min_stamps=5, discount_pct=5.0, sort_order=2,
    )

    # Registrar un cliente vía endpoint público
    r = client.post(
        f"/api/v1/loyalty/c/{slug}/register",
        json={
            "full_name": "Cliente Test",
            "email": "auto@example.com",
            "accepts_terms": True,
        },
    )
    assert r.status_code == 200, r.text
    pass_data = r.json()
    serial = pass_data["serial_number"]

    # Subir stamps_current a 5 (alcanza el umbral de Plata)
    # y disparar recompute_tier_for_pass (el hook que llama scan).
    with SessionLocal() as db:
        cp = db.execute(
            CustomerPass.__table__.select().where(
                CustomerPass.serial_number == serial,
            )
        ).first()
        assert cp is not None

        cp_obj = db.get(CustomerPass, cp.id)
        cp_obj.stamps_current = 5
        LoyaltyTierService(db, tenant_id=tid).recompute_tier_for_pass(cp_obj)
        db.commit()
        db.refresh(cp_obj)

        assert str(cp_obj.current_tier_id) == str(plata["id"]), (
            f"Esperaba tier Plata ({plata['id']}), "
            f"got current_tier_id={cp_obj.current_tier_id}"
        )
