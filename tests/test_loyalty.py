"""Tests del sistema de fidelización con tarjetas digitales (Fase 1 y 2).

Cubre:
  - CRUD de campañas (owner)
  - QR del mostrador rotativo (issue + validación)
  - Registro público de cliente (con términos, email/phone, reuso)
  - Scan del POS:
      * happy path (suma 1 sello)
      * replay (jti 1-shot)
      * QR de otro tenant (aislamiento)
      * PIN requerido y validado
      * campaign mismatch
      * pass_not_found
  - Reward unlock tras N scans (REDEEMED + reset)
  - Métricas básicas

Estos tests usan el bootstrap _register() estándar del proyecto, con DB en
memoria (conftest.py) y rate limit / auditoría desactivados.
"""
from __future__ import annotations

import pytest
from jose import jwt

from app.config import settings
from app.services.loyalty_pass_service import (
    QR_TOKEN_MAX_CLOCK_SKEW, QR_TOKEN_TTL_SECONDS,
)


# ── Helpers ────────────────────────────────────────────────
def _bootstrap(client, slug="loy-co"):
    """Crea un usuario owner con tenant. Devuelve (token, tenant_id, slug)."""
    r = client.post("/api/v1/auth/register", json={
        "email": f"{slug}@e.com",
        "password": "test1234",
        "full_name": "Owner",
        "create_tenant": True,
        "tenant_legal_name": f"Loyalty {slug}",
        "tenant_slug": slug,
    })
    assert r.status_code == 201, r.text
    data = r.json()
    return (
        data["access_token"],
        data["current_tenant"]["tenant_id"],
        slug,
    )


def _create_campaign(client, token, tid, **overrides):
    body = {
        "name": "Café gratis",
        "reward_label": "1 Café Gratis",
        "stamps_required": 5,
        "primary_color": "#1A73E8",
        "text_color": "#FFFFFF",
    }
    body.update(overrides)
    r = client.post(
        f"/api/v1/tenants/{tid}/loyalty/campaigns",
        json=body,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 201, r.text
    return r.json()


def _issue_qr(client, token, tid, cid):
    r = client.post(
        f"/api/v1/tenants/{tid}/loyalty/campaigns/{cid}/qr-token",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    return r.json()


def _register_customer(client, slug, **overrides):
    body = {
        "full_name": "Cliente Test",
        "email": "c@e.com",
        "accepts_terms": True,
    }
    body.update(overrides)
    r = client.post(f"/api/v1/loyalty/c/{slug}/register", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def _scan(client, token, tid, qr_payload, pass_serial, **kwargs):
    body = {"qr_payload": qr_payload, "pass_serial": pass_serial}
    body.update(kwargs)
    r = client.post(
        "/api/v1/loyalty/scan",
        json=body,
        headers={
            "Authorization": f"Bearer {token}",
            "X-Tenant-Id": str(tid),
        },
    )
    return r


# ══════════════════════════════════════════════════════════
# Campaign CRUD
# ══════════════════════════════════════════════════════════
class TestCampaignCrud:
    def test_create_campaign_success(self, client):
        token, tid, _ = _bootstrap(client, "loy-create")
        c = _create_campaign(client, token, tid)
        assert c["name"] == "Café gratis"
        assert c["stamps_required"] == 5
        assert c["cashier_pin_set"] is False
        assert c["is_active"] is True
        # total_passes y demás métricas arrancan en 0
        assert c["total_passes"] == 0

    def test_create_campaign_rejects_invalid_color(self, client):
        token, tid, _ = _bootstrap(client, "loy-color")
        r = client.post(
            f"/api/v1/tenants/{tid}/loyalty/campaigns",
            json={
                "name": "Café",
                "reward_label": "1 Café",
                "primary_color": "not-a-color",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 422

    def test_create_campaign_with_pin_does_not_leak_pin(self, client):
        token, tid, _ = _bootstrap(client, "loy-pin")
        c = _create_campaign(
            client, token, tid,
            cashier_pin="1234", pin_hint="mostrador",
        )
        # El flag se setea pero el PIN NO aparece en la respuesta
        assert c["cashier_pin_set"] is True
        assert "1234" not in str(c)
        assert "cashier_pin" not in c

    def test_list_campaigns_excludes_archived_by_default(self, client):
        token, tid, _ = _bootstrap(client, "loy-list")
        c1 = _create_campaign(client, token, tid, name="A")
        c2 = _create_campaign(client, token, tid, name="B")
        # Archivar c2
        r = client.delete(
            f"/api/v1/tenants/{tid}/loyalty/campaigns/{c2['id']}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 204
        # Listar activas
        r = client.get(
            f"/api/v1/tenants/{tid}/loyalty/campaigns",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        ids = [c["id"] for c in r.json()]
        assert c1["id"] in ids
        assert c2["id"] not in ids
        # include_inactive=True las devuelve
        r = client.get(
            f"/api/v1/tenants/{tid}/loyalty/campaigns?include_inactive=true",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert len(r.json()) == 2

    def test_update_campaign_changes_reward_label(self, client):
        token, tid, _ = _bootstrap(client, "loy-upd")
        c = _create_campaign(client, token, tid)
        r = client.patch(
            f"/api/v1/tenants/{tid}/loyalty/campaigns/{c['id']}",
            json={"reward_label": "2 Cafés Gratis"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        assert r.json()["reward_label"] == "2 Cafés Gratis"

    def test_update_campaign_can_remove_pin_with_empty_string(self, client):
        token, tid, _ = _bootstrap(client, "loy-unpin")
        c = _create_campaign(client, token, tid, cashier_pin="1234")
        assert c["cashier_pin_set"] is True
        r = client.patch(
            f"/api/v1/tenants/{tid}/loyalty/campaigns/{c['id']}",
            json={"cashier_pin": ""},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        assert r.json()["cashier_pin_set"] is False

    def test_get_metrics_returns_zero_when_empty(self, client):
        token, tid, _ = _bootstrap(client, "loy-met0")
        c = _create_campaign(client, token, tid)
        r = client.get(
            f"/api/v1/tenants/{tid}/loyalty/campaigns/{c['id']}/metrics",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        m = r.json()
        assert m["active_passes"] == 0
        assert m["total_stamps_today"] == 0
        assert m["total_rewards_today"] == 0


# ══════════════════════════════════════════════════════════
# QR Token del mostrador
# ══════════════════════════════════════════════════════════
class TestCounterQrToken:
    def test_issue_token_returns_jwt_with_expected_claims(self, client):
        token, tid, _ = _bootstrap(client, "loy-tok1")
        c = _create_campaign(client, token, tid)
        qt = _issue_qr(client, token, tid, c["id"])
        # jti, qr_payload, expires_at presentes
        assert qt["jti"]
        assert qt["qr_payload"]
        assert qt["refresh_in_seconds"] == QR_TOKEN_TTL_SECONDS
        # Decodificar el JWT y validar claims
        claims = jwt.decode(
            qt["qr_payload"], settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
        assert claims["jti"] == qt["jti"]
        assert claims["kind"] == "counter"
        assert claims["tid"] == tid
        assert claims["cid"] == c["id"]
        assert "exp" in claims

    def test_issue_token_creates_unique_jtis(self, client):
        token, tid, _ = _bootstrap(client, "loy-tok2")
        c = _create_campaign(client, token, tid)
        jtis = {_issue_qr(client, token, tid, c["id"])["jti"] for _ in range(5)}
        assert len(jtis) == 5

    def test_issue_token_for_archived_campaign_404s(self, client):
        token, tid, _ = _bootstrap(client, "loy-tok3")
        c = _create_campaign(client, token, tid)
        client.delete(
            f"/api/v1/tenants/{tid}/loyalty/campaigns/{c['id']}",
            headers={"Authorization": f"Bearer {token}"},
        )
        r = client.post(
            f"/api/v1/tenants/{tid}/loyalty/campaigns/{c['id']}/qr-token",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 404


# ══════════════════════════════════════════════════════════
# Registro público de cliente
# ══════════════════════════════════════════════════════════
class TestPublicRegistration:
    def test_get_public_campaign_no_auth(self, client):
        token, tid, slug = _bootstrap(client, "loy-pub1")
        _create_campaign(client, token, tid)
        r = client.get(f"/api/v1/loyalty/c/{slug}/campaign")
        assert r.status_code == 200
        body = r.json()
        assert body["tenant_slug"] == slug
        assert body["campaign"]["stamps_required"] == 5
        assert body["campaign"]["primary_color"] == "#1A73E8"

    def test_get_public_campaign_404_when_no_active(self, client):
        _bootstrap(client, "loy-pub2")
        r = client.get("/api/v1/loyalty/c/loy-pub2/campaign")
        # tenant existe pero no hay campaña activa
        assert r.status_code == 404

    def test_register_creates_pass(self, client):
        token, tid, slug = _bootstrap(client, "loy-reg1")
        _create_campaign(client, token, tid)
        p = _register_customer(client, slug, email="a@e.com")
        assert p["stamps_current"] == 0
        assert p["stamps_required"] == 5
        assert p["status"] == "active"
        assert p["qr_payload"]
        # El qr_payload del pass NO debe filtrar email/phone
        assert "a@e.com" not in p["qr_payload"]
        assert "email" not in str(p).lower() or "@e.com" not in p["qr_payload"]

    def test_register_requires_accepts_terms(self, client):
        token, tid, slug = _bootstrap(client, "loy-reg2")
        _create_campaign(client, token, tid)
        r = client.post(f"/api/v1/loyalty/c/{slug}/register", json={
            "full_name": "X", "email": "x@e.com",
            "accepts_terms": False,
        })
        assert r.status_code == 422

    def test_register_requires_email_or_phone(self, client):
        token, tid, slug = _bootstrap(client, "loy-reg3")
        _create_campaign(client, token, tid)
        r = client.post(f"/api/v1/loyalty/c/{slug}/register", json={
            "full_name": "Solo Nombre",
            "accepts_terms": True,
        })
        assert r.status_code == 422

    def test_register_reuses_existing_customer(self, client):
        token, tid, slug = _bootstrap(client, "loy-reg4")
        _create_campaign(client, token, tid)
        p1 = _register_customer(client, slug, email="dup@e.com")
        p2 = _register_customer(client, slug, email="dup@e.com")
        # Mismo pass (mismo serial), no se duplica
        assert p1["id"] == p2["id"]
        assert p1["serial_number"] == p2["serial_number"]

    def test_register_same_customer_different_campaign_creates_new_pass(
        self, client,
    ):
        token, tid, slug = _bootstrap(client, "loy-reg5")
        c1 = _create_campaign(client, token, tid, name="A")
        c2 = _create_campaign(client, token, tid, name="B")
        # C1 es la activa, registro
        p1 = _register_customer(client, slug, email="m@e.com")
        # Archivamos c1, activamos c2 — ahora un nuevo registro
        # genera un pass para c2
        client.delete(
            f"/api/v1/tenants/{tid}/loyalty/campaigns/{c1['id']}",
            headers={"Authorization": f"Bearer {token}"},
        )
        # c2 sigue activa desde el create (is_active por default = True)
        p2 = _register_customer(client, slug, email="m@e.com")
        # Pases diferentes (distinta campaign)
        assert p1["id"] != p2["id"]


# ══════════════════════════════════════════════════════════
# Scan del POS — el flow crítico
# ══════════════════════════════════════════════════════════
class TestScanFlow:
    def test_happy_path_sums_one_stamp(self, client):
        token, tid, slug = _bootstrap(client, "loy-scan1")
        c = _create_campaign(client, token, tid, stamps_required=5)
        p = _register_customer(client, slug, email="a@e.com")
        qt = _issue_qr(client, token, tid, c["id"])
        r = _scan(client, token, tid, qt["qr_payload"], p["serial_number"])
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["ok"] is True
        assert body["error_code"] is None
        assert body["stamps_after"] == 1
        assert body["pass"]["stamps_current"] == 1
        assert body["reward_unlocked"] is False

    def test_replay_attack_rejects_second_use(self, client):
        """El jti del QR del mostrador es 1-shot."""
        token, tid, slug = _bootstrap(client, "loy-scan2")
        c = _create_campaign(client, token, tid)
        p = _register_customer(client, slug, email="b@e.com")
        qt = _issue_qr(client, token, tid, c["id"])
        r1 = _scan(client, token, tid, qt["qr_payload"], p["serial_number"])
        assert r1.json()["ok"] is True
        r2 = _scan(client, token, tid, qt["qr_payload"], p["serial_number"])
        assert r2.status_code == 200
        body = r2.json()
        assert body["ok"] is False
        assert body["error_code"] == "qr_invalid"
        assert "ya fue usado" in body["error"]

    def test_expired_token_rejected(self, client):
        """Un QR expirado (exp < now) se rechaza."""
        from datetime import datetime, timezone, timedelta
        token, tid, slug = _bootstrap(client, "loy-scan3")
        c = _create_campaign(client, token, tid)
        p = _register_customer(client, slug, email="c@e.com")
        # Forjar un JWT con exp ya vencido
        expired = jwt.encode(
            {
                "jti": "expired-jti-123",
                "tid": tid,
                "cid": c["id"],
                "kind": "counter",
                "exp": int((datetime.now(timezone.utc) - timedelta(minutes=2)).timestamp()),
            },
            settings.jwt_secret, algorithm=settings.jwt_algorithm,
        )
        r = _scan(client, token, tid, expired, p["serial_number"])
        body = r.json()
        assert body["ok"] is False
        assert body["error_code"] == "qr_invalid"

    def test_cross_tenant_qr_rejected(self, client):
        """Un QR emitido para tenant A no se puede usar en tenant B."""
        token_a, tid_a, slug_a = _bootstrap(client, "loy-a")
        token_b, tid_b, _ = _bootstrap(client, "loy-b")
        c_a = _create_campaign(client, token_a, tid_a, name="A")
        c_b = _create_campaign(client, token_b, tid_b, name="B")
        # Cliente en tenant A
        p = _register_customer(client, slug_a, email="a@e.com")
        # QR del tenant A
        qt_a = _issue_qr(client, token_a, tid_a, c_a["id"])
        # Intentar usarlo en tenant B
        r = _scan(client, token_b, tid_b, qt_a["qr_payload"], p["serial_number"])
        body = r.json()
        assert body["ok"] is False
        assert body["error_code"] == "qr_invalid"
        # El contador de tenant B no debe haberse movido
        r2 = client.get(
            f"/api/v1/tenants/{tid_b}/loyalty/campaigns/{c_b['id']}/metrics",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert r2.json()["total_stamps_today"] == 0

    def test_pin_required_when_campaign_has_pin(self, client):
        token, tid, slug = _bootstrap(client, "loy-pin1")
        c = _create_campaign(client, token, tid, cashier_pin="1234")
        p = _register_customer(client, slug, email="p@e.com")
        qt = _issue_qr(client, token, tid, c["id"])
        # Sin PIN
        r = _scan(client, token, tid, qt["qr_payload"], p["serial_number"])
        body = r.json()
        assert body["ok"] is False
        assert body["error_code"] == "pin_invalid"

    def test_wrong_pin_rejected(self, client):
        token, tid, slug = _bootstrap(client, "loy-pin2")
        c = _create_campaign(client, token, tid, cashier_pin="1234")
        p = _register_customer(client, slug, email="p2@e.com")
        qt = _issue_qr(client, token, tid, c["id"])
        r = _scan(
            client, token, tid, qt["qr_payload"], p["serial_number"],
            cashier_pin="0000",
        )
        body = r.json()
        assert body["ok"] is False
        assert body["error_code"] == "pin_invalid"

    def test_correct_pin_succeeds(self, client):
        token, tid, slug = _bootstrap(client, "loy-pin3")
        c = _create_campaign(client, token, tid, cashier_pin="1234")
        p = _register_customer(client, slug, email="p3@e.com")
        qt = _issue_qr(client, token, tid, c["id"])
        r = _scan(
            client, token, tid, qt["qr_payload"], p["serial_number"],
            cashier_pin="1234",
        )
        assert r.json()["ok"] is True
        assert r.json()["stamps_after"] == 1

    def test_pass_not_found(self, client):
        token, tid, _ = _bootstrap(client, "loy-pnf")
        c = _create_campaign(client, token, tid)
        qt = _issue_qr(client, token, tid, c["id"])
        r = _scan(
            client, token, tid, qt["qr_payload"], "WH-DOES-NOT-EXIST-0000",
        )
        body = r.json()
        assert body["ok"] is False
        assert body["error_code"] == "pass_not_found"

    def test_campaign_mismatch_rejected(self, client):
        """QR de una campaña, pass de otra → error."""
        token, tid, slug = _bootstrap(client, "loy-cmm")
        c1 = _create_campaign(client, token, tid, name="C1")
        # Registrar cuando c1 es la única activa
        p = _register_customer(client, slug, email="m@e.com")
        # Crear c2 y emitir QR de c2
        c2 = _create_campaign(client, token, tid, name="C2")
        qt_c2 = _issue_qr(client, token, tid, c2["id"])
        r = _scan(
            client, token, tid, qt_c2["qr_payload"], p["serial_number"],
        )
        body = r.json()
        assert body["ok"] is False
        assert body["error_code"] == "campaign_mismatch"

    def test_unauthenticated_scan_401(self, client):
        """Scan sin token devuelve 401."""
        _, tid, _ = _bootstrap(client, "loy-401")
        r = client.post("/api/v1/loyalty/scan", json={
            "qr_payload": "fake", "pass_serial": "fake",
        })
        assert r.status_code in (401, 403)


# ══════════════════════════════════════════════════════════
# Reward unlock (N stamps → reward + reset)
# ══════════════════════════════════════════════════════════
class TestRewardUnlock:
    def test_reward_unlocks_after_required_stamps(self, client):
        token, tid, slug = _bootstrap(client, "loy-rew1")
        c = _create_campaign(client, token, tid, stamps_required=3)
        p = _register_customer(client, slug, email="r@e.com")
        # 3 scans, cada uno con un QR distinto
        for i in range(3):
            qt = _issue_qr(client, token, tid, c["id"])
            r = _scan(client, token, tid, qt["qr_payload"], p["serial_number"])
            body = r.json()
            if i < 2:
                assert body["ok"] is True
                assert body["reward_unlocked"] is False
                assert body["stamps_after"] == i + 1
            else:
                # 3er scan → reward unlocked, stamps reseteados
                assert body["ok"] is True
                assert body["reward_unlocked"] is True
                assert body["stamps_after"] == 0

    def test_redeemed_pass_can_scan_again_to_start_new_cycle(self, client):
        """Tras redeem, el siguiente scan devuelve a ACTIVE con stamps=1."""
        token, tid, slug = _bootstrap(client, "loy-rew2")
        c = _create_campaign(client, token, tid, stamps_required=2)
        p = _register_customer(client, slug, email="s@e.com")
        # Primer ciclo
        qt = _issue_qr(client, token, tid, c["id"])
        _scan(client, token, tid, qt["qr_payload"], p["serial_number"])
        qt = _issue_qr(client, token, tid, c["id"])
        r = _scan(client, token, tid, qt["qr_payload"], p["serial_number"])
        assert r.json()["reward_unlocked"] is True
        # Estado del pass: REDEEMED con rewards_earned=1
        r = client.get(
            f"/api/v1/loyalty/c/{slug}/campaign",
        )
        # Necesitamos el serial — lo teníamos arriba; consultamos vía endpoint
        # público no expone admin. Usamos el siguiente scan.
        qt = _issue_qr(client, token, tid, c["id"])
        r = _scan(client, token, tid, qt["qr_payload"], p["serial_number"])
        body = r.json()
        assert body["ok"] is True
        assert body["reward_unlocked"] is False
        # stamps_after = 1 (nuevo ciclo desde 0 + 1)
        assert body["stamps_after"] == 1


# ══════════════════════════════════════════════════════════
# Auditoría: PassStamp
# ══════════════════════════════════════════════════════════
class TestAuditTrail:
    def test_each_successful_scan_creates_stamp_row(self, client):
        from app.models.loyalty_pass import PassStamp
        from app.database import SessionLocal
        token, tid, slug = _bootstrap(client, "loy-aud1")
        c = _create_campaign(client, token, tid)
        p = _register_customer(client, slug, email="au@e.com")
        qt = _issue_qr(client, token, tid, c["id"])
        r = _scan(client, token, tid, qt["qr_payload"], p["serial_number"])
        assert r.json()["ok"] is True
        # Verificar fila PassStamp
        db = SessionLocal()
        try:
            stamps = db.query(PassStamp).filter(
                PassStamp.tenant_id == tid,
            ).all()
            assert len(stamps) == 1
            s = stamps[0]
            assert s.delta == 1
            assert s.reason == "scan"
            assert s.qr_token_jti == qt["jti"]
            assert s.stamps_after == 1
            assert s.reward_unlocked is False
        finally:
            db.close()

    def test_audit_row_records_jti_for_replay_tracing(self, client):
        """El jti del QR queda en la fila PassStamp para forensics."""
        from app.models.loyalty_pass import PassStamp
        from app.database import SessionLocal
        token, tid, slug = _bootstrap(client, "loy-aud2")
        c = _create_campaign(client, token, tid, cashier_pin="1234")
        p = _register_customer(client, slug, email="j@e.com")
        qt = _issue_qr(client, token, tid, c["id"])
        r = _scan(
            client, token, tid, qt["qr_payload"], p["serial_number"],
            cashier_pin="1234",
        )
        assert r.json()["ok"] is True
        db = SessionLocal()
        try:
            s = db.query(PassStamp).filter(
                PassStamp.tenant_id == tid,
            ).first()
            assert s.qr_token_jti == qt["jti"]
            assert s.cashier_pin_validated is True
        finally:
            db.close()
