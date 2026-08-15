"""Tests del módulo Bookings / Reservas (Fase 2).

Cubre:
  - CRUD admin: list, get, create, update, delete
  - Validación de ventana temporal (ends_at > starts_at, >= 1 min)
  - Validación de conflictos (no se solapan reservas en la misma sucursal)
  - Validación de horarios de sucursal (Branch.hours)
  - Acciones de estado: confirm, complete, no-show, cancel
  - Stats y availability
  - Endpoints públicos: check, create, cancel
  - AI tools: list_bookings, check_availability, create_booking (dispatch + schema)
  - Aislamiento multi-tenant
"""
from __future__ import annotations

import pytest
from datetime import datetime, timedelta, timezone


# ── Helpers ────────────────────────────────────────────────
def _bootstrap(client, slug="bk-co"):
    """Crea un usuario owner con tenant. Devuelve (token, tenant_id, slug)."""
    r = client.post("/api/v1/auth/register", json={
        "email": f"{slug}@e.com",
        "password": "test1234",
        "full_name": "Owner",
        "create_tenant": True,
        "tenant_legal_name": f"Bookings {slug}",
        "tenant_slug": slug,
    })
    assert r.status_code == 201, r.text
    data = r.json()
    return (
        data["access_token"],
        data["current_tenant"]["tenant_id"],
        slug,
    )


def _create_branch(client, token, tid, **overrides):
    body = {
        "name": "Sucursal Centro",
        "code": "CENTRO",
        "address": "Av. Principal 123",
        "city": "Santiago",
    }
    body.update(overrides)
    r = client.post(
        f"/api/v1/tenants/{tid}/branches",
        json=body,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code in (200, 201), r.text
    return r.json()


def _create_booking(client, token, tid, **overrides):
    starts = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=1)
    body = {
        "customer_name": "Juan Pérez",
        "customer_phone": "+56912345678",
        "customer_email": "juan@example.com",
        "starts_at": starts.isoformat(),
        "ends_at": (starts + timedelta(hours=1)).isoformat(),
    }
    body.update(overrides)
    r = client.post(
        f"/api/v1/tenants/{tid}/bookings",
        json=body,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code in (200, 201), r.text
    return r.json()


def _at(hour, minute=0, day_offset=1):
    """Helper: datetime en UTC con día offset."""
    base = datetime.now(timezone.utc).replace(
        hour=hour, minute=minute, second=0, microsecond=0
    ) + timedelta(days=day_offset)
    return base


# ══════════════════════════════════════════════════════════
# CRUD básico
# ══════════════════════════════════════════════════════════
class TestBookingCRUD:
    def test_create_booking_success(self, client):
        token, tid, _ = _bootstrap(client, "bk-create")
        b = _create_booking(client, token, tid)
        assert b["status"] == "pending"
        assert b["customer_name"] == "Juan Pérez"
        assert b["price_cents"] == 0
        assert b["currency"] == "CLP"
        assert "id" in b

    def test_create_booking_with_branch(self, client):
        token, tid, _ = _bootstrap(client, "bk-branch")
        br = _create_branch(client, token, tid)
        b = _create_booking(client, token, tid, branch_id=br["id"])
        assert b["branch_id"] == br["id"]

    def test_list_bookings(self, client):
        token, tid, _ = _bootstrap(client, "bk-list")
        _create_booking(client, token, tid, customer_name="Ana",
                        starts_at=_at(9, 0, 1).isoformat(),
                        ends_at=_at(10, 0, 1).isoformat())
        _create_booking(client, token, tid, customer_name="Bea",
                        starts_at=_at(14, 0, 1).isoformat(),
                        ends_at=_at(15, 0, 1).isoformat())
        r = client.get(
            f"/api/v1/tenants/{tid}/bookings",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 2

    def test_list_bookings_filter_by_status(self, client):
        token, tid, _ = _bootstrap(client, "bk-filt")
        b = _create_booking(client, token, tid)
        # Cancelarla
        client.post(
            f"/api/v1/tenants/{tid}/bookings/{b['id']}/cancel",
            headers={"Authorization": f"Bearer {token}"},
        )
        r = client.get(
            f"/api/v1/tenants/{tid}/bookings?status=canceled",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 1
        assert data[0]["status"] == "canceled"

    def test_get_booking_detail(self, client):
        token, tid, _ = _bootstrap(client, "bk-detail")
        b = _create_booking(client, token, tid)
        r = client.get(
            f"/api/v1/tenants/{tid}/bookings/{b['id']}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        assert r.json()["id"] == b["id"]

    def test_get_booking_not_found(self, client):
        from uuid import uuid4
        token, tid, _ = _bootstrap(client, "bk-404")
        r = client.get(
            f"/api/v1/tenants/{tid}/bookings/{uuid4()}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 404

    def test_update_booking_changes_status(self, client):
        token, tid, _ = _bootstrap(client, "bk-upd")
        b = _create_booking(client, token, tid)
        r = client.patch(
            f"/api/v1/tenants/{tid}/bookings/{b['id']}",
            json={"status": "confirmed", "notes": "Cliente VIP"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "confirmed"
        assert data["notes"] == "Cliente VIP"

    def test_delete_booking(self, client):
        token, tid, _ = _bootstrap(client, "bk-del")
        b = _create_booking(client, token, tid)
        r = client.delete(
            f"/api/v1/tenants/{tid}/bookings/{b['id']}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 204
        # 404 al volver a pedir
        r = client.get(
            f"/api/v1/tenants/{tid}/bookings/{b['id']}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 404


# ══════════════════════════════════════════════════════════
# Validación
# ══════════════════════════════════════════════════════════
class TestBookingValidation:
    def test_rejects_ends_before_starts(self, client):
        token, tid, _ = _bootstrap(client, "bk-err1")
        starts = _at(10)
        r = client.post(
            f"/api/v1/tenants/{tid}/bookings",
            json={
                "customer_name": "Ximena",
                "customer_phone": "+56912345678",
                "starts_at": starts.isoformat(),
                "ends_at": (starts - timedelta(hours=1)).isoformat(),
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 422

    def test_rejects_too_short_booking(self, client):
        token, tid, _ = _bootstrap(client, "bk-err2")
        starts = _at(10)
        r = client.post(
            f"/api/v1/tenants/{tid}/bookings",
            json={
                "customer_name": "Ximena",
                "customer_phone": "+56912345678",
                "starts_at": starts.isoformat(),
                "ends_at": (starts + timedelta(seconds=10)).isoformat(),
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 422

    def test_rejects_conflicting_booking_same_branch(self, client):
        token, tid, _ = _bootstrap(client, "bk-conf1")
        br = _create_branch(client, token, tid)
        # Primera reserva en slot fijo
        starts = _at(10)
        _create_booking(
            client, token, tid, branch_id=br["id"],
            starts_at=starts.isoformat(),
            ends_at=(starts + timedelta(hours=1)).isoformat(),
        )
        # Segunda reserva que solapa la misma ventana
        r = client.post(
            f"/api/v1/tenants/{tid}/bookings",
            json={
                "customer_name": "Yo",
                "customer_phone": "+56987654321",
                "branch_id": br["id"],
                "starts_at": (starts + timedelta(minutes=15)).isoformat(),
                "ends_at": (starts + timedelta(hours=1, minutes=30)).isoformat(),
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 409
        assert "Ya existe una reserva" in r.json()["detail"]

    def test_allows_non_overlapping_booking_same_branch(self, client):
        token, tid, _ = _bootstrap(client, "bk-conf2")
        br = _create_branch(client, token, tid)
        # Primera reserva
        b1 = _create_booking(client, token, tid, branch_id=br["id"])
        # Segunda reserva 2h después
        starts = datetime.fromisoformat(b1["ends_at"].replace("Z", "+00:00")) + timedelta(hours=1)
        r = client.post(
            f"/api/v1/tenants/{tid}/bookings",
            json={
                "customer_name": "Zoe",
                "customer_phone": "+56987654321",
                "branch_id": br["id"],
                "starts_at": starts.isoformat(),
                "ends_at": (starts + timedelta(hours=1)).isoformat(),
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 201

    def test_rejects_booking_outside_branch_hours(self, client):
        token, tid, _ = _bootstrap(client, "bk-hours")
        # Branch abierto solo de 09:00 a 18:00
        br = _create_branch(
            client, token, tid,
            hours={
                "mon": {"open": "09:00", "close": "18:00"},
                "tue": {"open": "09:00", "close": "18:00"},
                "wed": {"open": "09:00", "close": "18:00"},
                "thu": {"open": "09:00", "close": "18:00"},
                "fri": {"open": "09:00", "close": "18:00"},
                "sat": None, "sun": None,
            },
        )
        # Reserva a las 22:00 — fuera de horario
        # Calculamos un martes a las 22:00
        from datetime import datetime as _dt
        target = _dt.now(timezone.utc).replace(microsecond=0) + timedelta(days=2)
        while target.weekday() != 1:  # martes
            target += timedelta(days=1)
        target = target.replace(hour=22, minute=0, second=0)
        r = client.post(
            f"/api/v1/tenants/{tid}/bookings",
            json={
                "customer_name": "Walter",
                "customer_phone": "+56912345678",
                "branch_id": br["id"],
                "starts_at": target.isoformat(),
                "ends_at": (target + timedelta(hours=1)).isoformat(),
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 422
        detail = r.json()["detail"]
        if isinstance(detail, list):
            detail = " ".join(str(x) for x in detail)
        assert "fuera de apertura" in detail.lower() or "horario" in detail.lower()

    def test_rejects_booking_on_closed_day(self, client):
        token, tid, _ = _bootstrap(client, "bk-closed")
        br = _create_branch(
            client, token, tid,
            hours={
                "mon": {"open": "09:00", "close": "18:00"},
                "tue": {"open": "09:00", "close": "18:00"},
                "wed": {"open": "09:00", "close": "18:00"},
                "thu": {"open": "09:00", "close": "18:00"},
                "fri": {"open": "09:00", "close": "18:00"},
                "sat": None, "sun": None,
            },
        )
        # Sábado
        from datetime import datetime as _dt
        target = _dt.now(timezone.utc).replace(microsecond=0) + timedelta(days=1)
        while target.weekday() != 5:  # sábado
            target += timedelta(days=1)
        target = target.replace(hour=10, minute=0, second=0)
        r = client.post(
            f"/api/v1/tenants/{tid}/bookings",
            json={
                "customer_name": "Wenceslao",
                "customer_phone": "+56912345678",
                "branch_id": br["id"],
                "starts_at": target.isoformat(),
                "ends_at": (target + timedelta(hours=1)).isoformat(),
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 422


# ══════════════════════════════════════════════════════════
# Acciones de estado
# ══════════════════════════════════════════════════════════
class TestBookingStateActions:
    def test_confirm_booking(self, client):
        token, tid, _ = _bootstrap(client, "bk-conf1")
        b = _create_booking(client, token, tid)
        r = client.post(
            f"/api/v1/tenants/{tid}/bookings/{b['id']}/confirm",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        assert r.json()["status"] == "confirmed"

    def test_complete_booking(self, client):
        token, tid, _ = _bootstrap(client, "bk-comp")
        b = _create_booking(client, token, tid)
        r = client.post(
            f"/api/v1/tenants/{tid}/bookings/{b['id']}/complete",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        assert r.json()["status"] == "completed"

    def test_cancel_booking(self, client):
        token, tid, _ = _bootstrap(client, "bk-cancel")
        b = _create_booking(client, token, tid)
        r = client.post(
            f"/api/v1/tenants/{tid}/bookings/{b['id']}/cancel",
            json={"reason": "cliente no puede"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        assert r.json()["status"] == "canceled"
        assert "cliente no puede" in r.json()["notes"]

    def test_no_show_booking(self, client):
        token, tid, _ = _bootstrap(client, "bk-noshow")
        b = _create_booking(client, token, tid)
        r = client.post(
            f"/api/v1/tenants/{tid}/bookings/{b['id']}/no-show",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        assert r.json()["status"] == "no_show"

    def test_cancel_does_not_block_new_booking_same_slot(self, client):
        token, tid, _ = _bootstrap(client, "bk-cancelok")
        br = _create_branch(client, token, tid)
        b1 = _create_booking(client, token, tid, branch_id=br["id"])
        # Cancelar la primera
        client.post(
            f"/api/v1/tenants/{tid}/bookings/{b1['id']}/cancel",
            headers={"Authorization": f"Bearer {token}"},
        )
        # Crear otra en el mismo slot — debe pasar
        starts = _at(10)
        r = client.post(
            f"/api/v1/tenants/{tid}/bookings",
            json={
                "customer_name": "Nuevo",
                "customer_phone": "+56912345678",
                "branch_id": br["id"],
                "starts_at": starts.isoformat(),
                "ends_at": (starts + timedelta(hours=1)).isoformat(),
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 201


# ══════════════════════════════════════════════════════════
# Stats & availability
# ══════════════════════════════════════════════════════════
class TestBookingStatsAndAvailability:
    def test_stats_zero_when_empty(self, client):
        token, tid, _ = _bootstrap(client, "bk-stat0")
        r = client.get(
            f"/api/v1/tenants/{tid}/bookings/stats",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        s = r.json()
        assert s["total"] == 0
        assert s["pending"] == 0

    def test_stats_counts_by_status(self, client):
        token, tid, _ = _bootstrap(client, "bk-stat1")
        b1 = _create_booking(client, token, tid, customer_name="Ana",
                             starts_at=_at(9, 0, 1).isoformat(),
                             ends_at=_at(10, 0, 1).isoformat())
        b2 = _create_booking(client, token, tid, customer_name="Bea",
                             starts_at=_at(14, 0, 1).isoformat(),
                             ends_at=_at(15, 0, 1).isoformat())
        # b1 -> confirmed, b2 -> canceled
        client.post(f"/api/v1/tenants/{tid}/bookings/{b1['id']}/confirm",
                    headers={"Authorization": f"Bearer {token}"})
        client.post(f"/api/v1/tenants/{tid}/bookings/{b2['id']}/cancel",
                    headers={"Authorization": f"Bearer {token}"})
        r = client.get(f"/api/v1/tenants/{tid}/bookings/stats",
                       headers={"Authorization": f"Bearer {token}"})
        s = r.json()
        assert s["total"] == 2
        assert s["confirmed"] == 1
        assert s["canceled"] == 1

    def test_availability_returns_free_slots(self, client):
        token, tid, _ = _bootstrap(client, "bk-avail1")
        br = _create_branch(client, token, tid)
        # Sin reservas → todos disponibles
        from_time = _at(9)
        to_time = _at(18)
        r = client.post(
            f"/api/v1/tenants/{tid}/bookings/availability",
            json={
                "branch_id": br["id"],
                "date_from": from_time.isoformat(),
                "date_to": to_time.isoformat(),
                "duration_minutes": 60,
                "slot_step_minutes": 60,
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["total_slots"] >= 8
        # Sin reservas, todos los slots deberían estar disponibles
        assert data["available_slots"] == data["total_slots"]

    def test_availability_marks_busy_when_booking_exists(self, client):
        token, tid, _ = _bootstrap(client, "bk-avail2")
        br = _create_branch(client, token, tid)
        # Crear reserva a las 10
        starts = _at(10)
        _create_booking(
            client, token, tid, branch_id=br["id"],
            starts_at=starts.isoformat(),
            ends_at=(starts + timedelta(hours=1)).isoformat(),
        )
        # Consultar availability 9-18
        r = client.post(
            f"/api/v1/tenants/{tid}/bookings/availability",
            json={
                "branch_id": br["id"],
                "date_from": _at(9).isoformat(),
                "date_to": _at(18).isoformat(),
                "duration_minutes": 60,
                "slot_step_minutes": 60,
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        data = r.json()
        busy = [s for s in data["slots"] if not s["available"]]
        assert len(busy) >= 1
        assert data["available_slots"] < data["total_slots"]


# ══════════════════════════════════════════════════════════
# Endpoints públicos
# ══════════════════════════════════════════════════════════
class TestPublicBooking:
    def test_public_create_requires_accepts_terms(self, client):
        _token, _tid, slug = _bootstrap(client, "bk-pub1")
        starts = _at(10)
        r = client.post(
            f"/api/v1/bookings/t/{slug}/public-create",
            json={
                "customer_name": "Cliente",
                "customer_phone": "+56912345678",
                "starts_at": starts.isoformat(),
                "ends_at": (starts + timedelta(hours=1)).isoformat(),
                "accepts_terms": False,
            },
        )
        assert r.status_code == 422

    def test_public_create_success_masks_email(self, client):
        _token, _tid, slug = _bootstrap(client, "bk-pub2")
        starts = _at(10)
        r = client.post(
            f"/api/v1/bookings/t/{slug}/public-create",
            json={
                "customer_name": "Cliente Público",
                "customer_phone": "+56912345678",
                "customer_email": "juan.perez@example.com",
                "starts_at": starts.isoformat(),
                "ends_at": (starts + timedelta(hours=1)).isoformat(),
                "accepts_terms": True,
            },
        )
        assert r.status_code == 201
        data = r.json()
        assert data["status"] == "pending"
        # Email enmascarado (juan.perez → j********z@example.com)
        assert data["customer_email_masked"] == "j********z@example.com"
        # No se filtra el email crudo
        assert "juan.perez" not in str(data)
        assert data["cancel_token"]  # token opaco

    def test_public_check_availability(self, client):
        _token, _tid, slug = _bootstrap(client, "bk-pub3")
        r = client.post(
            f"/api/v1/bookings/t/{slug}/public-check",
            json={
                "date_from": _at(9).isoformat(),
                "date_to": _at(18).isoformat(),
                "duration_minutes": 60,
            },
        )
        assert r.status_code == 200
        data = r.json()
        assert "slots" in data
        assert "available_slots" in data

    def test_public_cancel_with_valid_token(self, client):
        _token, _tid, slug = _bootstrap(client, "bk-pub4")
        starts = _at(10)
        r = client.post(
            f"/api/v1/bookings/t/{slug}/public-create",
            json={
                "customer_name": "Cliente",
                "customer_phone": "+56912345678",
                "starts_at": starts.isoformat(),
                "ends_at": (starts + timedelta(hours=1)).isoformat(),
                "accepts_terms": True,
            },
        )
        data = r.json()
        r = client.post(
            f"/api/v1/bookings/t/{slug}/public-cancel",
            params={"booking_id": data["id"], "cancel_token": data["cancel_token"]},
        )
        assert r.status_code == 200
        assert r.json()["status"] == "canceled"

    def test_public_cancel_with_invalid_token_rejected(self, client):
        _token, _tid, slug = _bootstrap(client, "bk-pub5")
        starts = _at(10)
        r = client.post(
            f"/api/v1/bookings/t/{slug}/public-create",
            json={
                "customer_name": "Cliente",
                "customer_phone": "+56912345678",
                "starts_at": starts.isoformat(),
                "ends_at": (starts + timedelta(hours=1)).isoformat(),
                "accepts_terms": True,
            },
        )
        data = r.json()
        r = client.post(
            f"/api/v1/bookings/t/{slug}/public-cancel",
            params={"booking_id": data["id"], "cancel_token": "WRONG_TOKEN!"},
        )
        assert r.status_code == 403

    def test_public_404_for_unknown_tenant(self, client):
        r = client.post(
            "/api/v1/bookings/t/no-existe-slug/public-check",
            json={"date_from": _at(9).isoformat(), "date_to": _at(18).isoformat()},
        )
        assert r.status_code == 404


# ══════════════════════════════════════════════════════════
# Aislamiento multi-tenant
# ══════════════════════════════════════════════════════════
class TestMultiTenantIsolation:
    def test_other_tenant_cannot_see_booking(self, client):
        token_a, tid_a, _ = _bootstrap(client, "bk-iso-a")
        token_b, tid_b, _ = _bootstrap(client, "bk-iso-b")
        b_a = _create_booking(client, token_a, tid_a)
        # tenant_b NO debe ver la reserva de tenant_a
        r = client.get(
            f"/api/v1/tenants/{tid_b}/bookings/{b_a['id']}",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert r.status_code == 404
        # Tampoco en la lista
        r = client.get(
            f"/api/v1/tenants/{tid_b}/bookings",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert r.status_code == 200
        ids = [x["id"] for x in r.json()]
        assert b_a["id"] not in ids


# ══════════════════════════════════════════════════════════
# AI tools (catálogo y dispatch)
# ══════════════════════════════════════════════════════════
class TestAITools:
    def test_booking_tools_in_global_catalog(self):
        from app.services.ai_tools import TOOL_SCHEMAS, TOOL_DISPATCH, get_tools_for_agent
        names = [t["function"]["name"] for t in TOOL_SCHEMAS]
        assert "list_bookings" in names
        assert "check_availability" in names
        assert "create_booking" in names
        # Están en el dispatch
        for n in ("list_bookings", "check_availability", "create_booking"):
            assert n in TOOL_DISPATCH
            assert callable(TOOL_DISPATCH[n])

    def test_marketing_and_growth_have_booking_tools(self):
        from app.services.ai_tools import get_tools_for_agent
        for agent in ("marketing", "growth", "automation"):
            tools = get_tools_for_agent(agent)
            names = {t["function"]["name"] for t in tools}
            assert "list_bookings" in names, f"{agent} no tiene list_bookings"
            assert "check_availability" in names, f"{agent} no tiene check_availability"
            assert "create_booking" in names, f"{agent} no tiene create_booking"

    def test_marketplace_does_not_have_booking_tools(self):
        # marketplace es para catálogos de productos, no para reservas
        from app.services.ai_tools import get_tools_for_agent
        tools = get_tools_for_agent("marketplace")
        names = {t["function"]["name"] for t in tools}
        assert "list_bookings" not in names
        assert "create_booking" not in names

    def test_tool_schemas_have_required_params(self):
        from app.services.ai_tools import TOOL_SCHEMAS
        schemas = {t["function"]["name"]: t for t in TOOL_SCHEMAS}
        # check_availability requiere date_from y date_to
        assert "date_from" in schemas["check_availability"]["function"]["parameters"]["required"]
        assert "date_to" in schemas["check_availability"]["function"]["parameters"]["required"]
        # create_booking requiere los 4 básicos
        required = set(schemas["create_booking"]["function"]["parameters"]["required"])
        assert {"customer_name", "customer_phone", "starts_at", "ends_at"} <= required


# ══════════════════════════════════════════════════════════
# UI pages (HTML)
# ══════════════════════════════════════════════════════════
class TestUIPages:
    def test_dashboard_bookings_page_renders(self, client):
        r = client.get("/dashboard/bookings")
        assert r.status_code == 200
        assert "Reservas" in r.text or "reservas" in r.text

    def test_public_booking_page_renders(self, client):
        _token, _tid, slug = _bootstrap(client, "bk-ui")
        r = client.get(f"/u/{slug}/reservar")
        assert r.status_code == 200
        assert "Reservar" in r.text or "reserva" in r.text.lower()

    def test_public_booking_page_404_for_unknown_slug(self, client):
        r = client.get("/u/no-existe-slug/reservar")
        assert r.status_code == 404
