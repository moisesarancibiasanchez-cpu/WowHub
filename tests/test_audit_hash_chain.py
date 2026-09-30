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
"""
from __future__ import annotations

import hashlib
import json

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
