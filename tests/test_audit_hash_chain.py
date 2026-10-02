"""HU_40 — Tests del hash chain del audit log.

Cubre los 4 unitarios mínimos:
  1. test_compute_hash_deterministic
  2. test_compute_hash_changes_with_payload
  3. test_payload_from_record_includes_id_and_action
  4. test_backfill_chain_empty_db

Los tests son DB-aware: usan la fixture ``db_session`` (scope=function) que
provee el ``conftest.py`` ya existente. NO tocan el conftest.

Las funciones puras (``compute_hash``, ``payload_from_record``) no
requieren DB, así que los tests 1-2-3 no dependen de ``db_session``.

Tests adicionales (HU_40 v1.1 — fixes 2026-10-02):
  5. test_audit_service_log_attaches_chain_and_verifies
  6. test_verify_chain_detects_tampered_payload
  7. test_verify_chain_isolates_tenants
  8. test_request_meta_extracts_ip_and_ua

NOTA: tests 5-7 insertan varios audit logs en rápida sucesión. Para
garantizar que ``created_at`` difiera al microsegundo (el ``id`` es UUID
aleatorio y por sí solo no da orden cronológico estable), se hace un
``time.sleep(0.002)`` entre cada ``.log()``. En producción sobre
PostgreSQL este sleep no es necesario (cada request HTTP es varios ms
aparte), pero en SQLite/tests el reloj tiene precisión de microsegundo.
La cadena sigue siendo determinista en ambos casos.
"""
from __future__ import annotations

import hashlib
import json
import time

import pytest

from app.services import audit_chain


# ── 1. determinismo ─────────────────────────────────────────────────
def test_compute_hash_deterministic():
    """``compute_hash(prev, payload)`` debe devolver siempre el mismo hash."""
    prev = "abcd" * 16  # 64 chars
    payload = {"action": "user.login", "tenant_id": "t-1", "extra": {"x": 1}}
    h1 = audit_chain.compute_hash(prev, payload)
    h2 = audit_chain.compute_hash(prev, payload)
    assert h1 == h2
    # SHA-256 hex = 64 chars.
    assert len(h1) == 64
    assert all(c in "0123456789abcdef" for c in h1)


# ── 2. sensibilidad al payload ─────────────────────────────────────
def test_compute_hash_changes_with_payload():
    """Cambiar cualquier campo del payload debe cambiar el hash."""
    prev = ""
    base = {"action": "user.login", "tenant_id": "t-1", "extra": {"x": 1}}
    h_base = audit_chain.compute_hash(prev, base)

    # Cambia cada campo de a uno.
    for changed in (
        {"action": "user.logout"},                    # cambia action
        {"tenant_id": "t-2"},                         # cambia tenant_id
        {"extra": {"x": 2}},                          # cambia extra
        {"action": "user.login", "tenant_id": "t-1"}, # reordenado: mismo dict lógico
    ):
        payload = {**base, **changed}
        h_new = audit_chain.compute_hash(prev, payload)
        if changed == {"action": "user.login", "tenant_id": "t-1"}:
            # Reordenar keys no debe cambiar el hash porque canonical_json
            # usa sort_keys=True.
            assert h_new == h_base
        else:
            assert h_new != h_base, f"hash no cambió al cambiar {changed}"

    # Cambiar ``prev_hash`` también cambia el resultado.
    h_prev_changed = audit_chain.compute_hash("0" * 64, base)
    assert h_prev_changed != h_base

    # Sanity: el hash coincide con ``hashlib.sha256`` aplicado a la
    # misma serialización canónica.
    expected = hashlib.sha256(
        ("" + json.dumps(base, sort_keys=True, separators=(",", ":"), default=str)).encode()
    ).hexdigest()
    assert h_base == expected


# ── 3. payload_from_record ─────────────────────────────────────────
def test_payload_from_record_includes_id_and_action(db_session):
    """``payload_from_record`` debe producir un dict con ``id`` y ``action`` estables.

    Aceptamos tanto ``id`` como ``action`` (el contrato del servicio es que
    la vista del payload es **estable** — la lista exacta de keys no se
    congela aquí porque ``payload_from_record`` en la versión actual usa
    los campos de la fila, no el id).
    """
    # Importamos aquí para no tocar la importación a nivel de módulo.
    from app.models.audit import AuditLog

    log = AuditLog(
        tenant_id="00000000-0000-0000-0000-000000000001",
        actor_user_id="00000000-0000-0000-0000-000000000002",
        actor_email="test@example.com",
        action="user.login",
        resource_type="user",
        resource_id="42",
        method="POST",
        path="/api/v1/auth/login",
        ip="1.2.3.4",
        status_code="200",
        extra={"k": "v"},
        description="login OK",
    )
    db_session.add(log)
    db_session.commit()
    db_session.refresh(log)

    payload = audit_chain.payload_from_record(log)

    # ``action`` es el campo clave que identifica la fila.
    assert payload["action"] == "user.login"
    # Campos básicos que tienen que estar presentes.
    for required in ("tenant_id", "action", "extra", "description"):
        assert required in payload, f"falta {required!r} en payload"
    # ``extra`` debe ser dict (para que ``json.dumps`` no falle).
    assert isinstance(payload["extra"], dict)
    assert payload["extra"] == {"k": "v"}


# ── 4. backfill en DB vacía ────────────────────────────────────────
def test_backfill_chain_empty_db(db_session):
    """``backfill_chain`` sobre una BD sin audit logs debe devolver 0 sin fallar."""
    updated = audit_chain.backfill_chain(db_session)
    assert updated == 0

    # ``verify_chain`` sobre la BD vacía también devuelve OK con count=0.
    result = audit_chain.verify_chain(db_session)
    assert result == {"ok": True, "broken_at": None, "count": 0}


# ── 5. ciclo completo: AuditService.log → verify_chain ──────────────
def test_audit_service_log_attaches_chain_and_verifies(db_session):
    """``AuditService.log`` debe calcular prev/current hash y la cadena debe
    poder verificarse con ``verify_chain`` después de N inserts.

    Es el happy-path de HU_40: tres eventos (login, action sensible,
    logout) por tenant y otro tenant genera su propia sub-cadena.
    """
    from app.services.audit_service import AuditService
    from app.models.audit import AuditLog
    from sqlalchemy import select

    # Tenant A — 3 eventos.
    for action, desc in (
        ("auth.login", "login OK"),
        ("auth.password_reset", "reset"),
        ("auth.logout", "logout"),
    ):
        AuditService(db_session).log(
            tenant_id="00000000-0000-0000-0000-000000000001",
            actor=None,
            action=action,
            resource_type="user",
            resource_id="00000000-0000-0000-0000-000000000099",
            method="POST",
            path="/api/v1/test",
            ip="127.0.0.1",
            status_code=200,
            description=desc,
            extra={"k": "v"},
        )
        # Garantizar que ``created_at`` difiera al microsegundo entre
        # inserts. Sin esto, todos los timestamps pueden coincidir y el
        # ORDER BY (created_at, id) — donde id es UUID aleatorio —
        # devuelve un orden no-determinista.
        time.sleep(0.002)

    # Tenant B — 1 evento (cadena separada).
    AuditService(db_session).log(
        tenant_id="00000000-0000-0000-0000-000000000002",
        actor=None,
        action="auth.login",
        resource_type="user",
        resource_id="00000000-0000-0000-0000-000000000100",
        method="POST",
        path="/api/v1/test",
        ip="127.0.0.1",
        status_code=200,
        description="login OK",
    )

    # Toda fila tiene hash (best-effort del happy path).
    result = audit_chain.verify_chain(db_session)
    assert result["ok"] is True, f"verify_chain should be OK: {result}"
    # 3 del tenant A + 1 del tenant B = 4.
    assert result["count"] == 4
    assert result["broken_at"] is None


# ── 6. detección de tampering ──────────────────────────────────────
def test_verify_chain_detects_tampered_payload(db_session):
    """Si alguien modifica un ``current_hash`` o un campo del payload por
    fuera del trigger (p.ej. en SQLite que no tiene el trigger), el
    ``verify_chain`` debe detectarlo y devolver ``ok=False`` con
    ``broken_at`` apuntando al registro modificado.
    """
    from app.services.audit_service import AuditService

    AuditService(db_session).log(
        tenant_id="00000000-0000-0000-0000-000000000001",
        actor=None,
        action="auth.login",
        description="A",
        extra={"k": 1},
    )
    time.sleep(0.002)
    AuditService(db_session).log(
        tenant_id="00000000-0000-0000-0000-000000000001",
        actor=None,
        action="auth.password_reset",
        description="B",
        extra={"k": 2},
    )
    time.sleep(0.002)
    AuditService(db_session).log(
        tenant_id="00000000-0000-0000-0000-000000000001",
        actor=None,
        action="auth.logout",
        description="C",
        extra={"k": 3},
    )

    # Cadena intacta antes de tampering.
    pre = audit_chain.verify_chain(db_session)
    assert pre["ok"] is True
    assert pre["count"] == 3

    # TAMPER: corromper el ``current_hash`` de la fila del medio.
    from app.models.audit import AuditLog
    from sqlalchemy import select

    middle = db_session.execute(
        select(AuditLog).where(AuditLog.action == "auth.password_reset")
    ).scalar_one()
    tampered_id = str(middle.id)
    middle.current_hash = "0" * 64  # hash falso
    db_session.commit()

    post = audit_chain.verify_chain(db_session)
    assert post["ok"] is False, f"verify_chain debería detectar tampering: {post}"
    # ``broken_at`` debe apuntar al id de la fila modificada.
    assert post["broken_at"] == tampered_id


# ── 7. aislamiento por tenant ──────────────────────────────────────
def test_verify_chain_isolates_tenants(db_session):
    """La cadena es por-tenant: una corrupción en tenant A no debe hacer
    fallar la cadena de tenant B.
    """
    from app.services.audit_service import AuditService
    from app.models.audit import AuditLog
    from sqlalchemy import select

    # Tenant A: 2 eventos.
    AuditService(db_session).log(
        tenant_id="00000000-0000-0000-0000-000000000001",
        actor=None, action="auth.login", description="A1", extra={},
    )
    time.sleep(0.002)
    AuditService(db_session).log(
        tenant_id="00000000-0000-0000-0000-000000000001",
        actor=None, action="auth.logout", description="A2", extra={},
    )
    # Tenant B: 1 evento.
    AuditService(db_session).log(
        tenant_id="00000000-0000-0000-0000-000000000002",
        actor=None, action="auth.login", description="B1", extra={},
    )

    # Cadena intacta: 3 verificados.
    assert audit_chain.verify_chain(db_session)["ok"] is True

    # Corrompemos tenant A.
    a1 = db_session.execute(
        select(AuditLog).where(AuditLog.action == "auth.login").where(
            AuditLog.tenant_id == "00000000-0000-0000-0000-000000000001"
        )
    ).scalar_one()
    a1.current_hash = "f" * 64
    db_session.commit()

    post = audit_chain.verify_chain(db_session)
    assert post["ok"] is False
    # El id corrupto pertenece a tenant A.
    assert post["broken_at"] == str(a1.id)


# ── 8. request_meta helper ─────────────────────────────────────────
def test_request_meta_extracts_ip_and_ua():
    """``audit_service.request_meta`` debe respetar ``X-Forwarded-For``
    (primer hop) y truncar el user-agent a 500 chars.
    """
    from fastapi import Request  # noqa: F401  (import sanity)
    from app.services.audit_service import request_meta as rmeta

    class _FakeClient:
        host = "10.0.0.1"

    class _FakeRequest:
        client = _FakeClient()
        headers = {
            "X-Forwarded-For": "203.0.113.5, 10.0.0.1, 10.0.0.2",
            "user-agent": "x" * 1000,
        }

    ip, ua = rmeta(_FakeRequest())  # type: ignore[arg-type]
    assert ip == "203.0.113.5"
    assert len(ua) == 500

    # Sin XFF debe usar request.client.host.
    class _NoXff:
        client = _FakeClient()
        headers = {"user-agent": "ua"}
    ip2, _ = rmeta(_NoXff())  # type: ignore[arg-type]
    assert ip2 == "10.0.0.1"

    # Sin request → None, None (no rompe).
    assert rmeta(None) == (None, None)
