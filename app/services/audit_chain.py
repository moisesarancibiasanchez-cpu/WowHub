"""HU_40 — Audit log hash chain (SHA-256).

Cadena de hashes por tenant: cada ``AuditLog`` apunta al hash del registro
anterior (``prev_hash``) y contiene su propio hash (``current_hash``).

Reglas:
  - ``current_hash = SHA-256(prev_hash || canonical_json(payload))``
  - El primer registro de la cadena de un tenant usa ``prev_hash = ""``.
  - ``compute_hash`` es **determinista** — mismas entradas ⇒ mismo hash.
  - ``payload_from_record`` debe ser **estable** — el orden de los keys del
    payload no debe cambiar entre llamadas para un mismo registro.

Este servicio NO toca la base de datos directamente fuera de las funciones
``backfill_chain`` y ``verify_chain``; ``compute_hash`` y
``payload_from_record`` son funciones puras (testeables sin DB).
"""
from __future__ import annotations

import hashlib
import json
import logging
import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.audit import AuditLog

logger = logging.getLogger("wowhub.audit_chain")


# ── Constantes ────────────────────────────────────────────────────────
GENESIS_PREV_HASH: str = ""
"""``prev_hash`` del primer registro de una cadena (cadena vacía)."""


# ── Helpers puros ─────────────────────────────────────────────────────
def _canonical_json(payload: Dict[str, Any]) -> str:
    """JSON con keys ordenadas y sin espacios — estable byte-a-byte.

    ``default=str`` convierte UUID/datetime/Decimal a su representación
    string para que ``json.dumps`` no falle.
    """
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def compute_hash(prev_hash: str, payload: Dict[str, Any]) -> str:
    """SHA-256(prev_hash || canonical_json(payload)) — hex digest 64 chars.

    Para el primer registro de la cadena, ``prev_hash = GENESIS_PREV_HASH = ""``.
    """
    raw = (prev_hash + _canonical_json(payload)).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def payload_from_record(audit_log: AuditLog) -> Dict[str, Any]:
    """Vista estable del payload usado en ``compute_hash``.

    NOTA: NO incluimos ``prev_hash`` ni ``current_hash`` en el payload para
    evitar dependencia circular. Los UUIDs se serializan como ``str``.

    Esta función es la **fuente de verdad** del formato: tanto
    ``AuditService.log`` (en el insert) como ``verify_chain`` (en la lectura)
    deben producir exactamente el mismo dict para que la cadena verifique.
    """
    return {
        "tenant_id": str(audit_log.tenant_id) if audit_log.tenant_id is not None else None,
        "actor_user_id": str(audit_log.actor_user_id) if audit_log.actor_user_id else None,
        "action": audit_log.action,
        "resource_type": audit_log.resource_type,
        "resource_id": str(audit_log.resource_id) if audit_log.resource_id else None,
        "method": audit_log.method,
        "path": audit_log.path,
        "ip": audit_log.ip,
        "status_code": audit_log.status_code,
        "extra": audit_log.extra if isinstance(audit_log.extra, dict) else {},
        "description": audit_log.description,
    }


# ── Backfill ──────────────────────────────────────────────────────────
def backfill_chain(db: Session) -> int:
    """Recorre todos los audit logs y rellena ``prev_hash``/``current_hash``.

    Estrategia:
      - Ordena por ``(tenant_id, created_at, id)`` para garantizar cadena
        determinista por tenant.
      - Para cada tenant, parte de ``prev = GENESIS_PREV_HASH``.
      - Si el registro ya tiene ``current_hash`` calculado Y ``prev_hash``
        coincide con la cadena esperada, se respeta (es decir, NO recalcula
        sobre filas que ya están bien — útil para re-correr después de un
        fallo parcial).
      - Si falta alguno de los dos, recalcula.

    Retorna el número de filas actualizadas.
    """
    rows: List[AuditLog] = list(
        db.execute(
            select(AuditLog)
            .order_by(AuditLog.tenant_id, AuditLog.created_at, AuditLog.id)
        ).scalars()
    )

    prev_by_tenant: Dict[str, str] = {}
    updated = 0
    for r in rows:
        tenant_key = str(r.tenant_id) if r.tenant_id is not None else "__null__"
        prev = prev_by_tenant.get(tenant_key, GENESIS_PREV_HASH)

        # Si la fila ya está bien enlazada y con hash, no la recalculamos.
        if r.prev_hash == prev and r.current_hash:
            prev_by_tenant[tenant_key] = r.current_hash
            continue

        payload = payload_from_record(r)
        new_current = compute_hash(prev, payload)
        r.prev_hash = prev
        r.current_hash = new_current
        prev_by_tenant[tenant_key] = new_current
        updated += 1

    if updated:
        db.commit()
    logger.info("audit_chain.backfill_chain: updated=%d rows=%d", updated, len(rows))
    return updated


# ── Verify ────────────────────────────────────────────────────────────
def verify_chain(db: Session) -> Dict[str, Any]:
    """Recorre la cadena y verifica integridad.

    Retorna ``{ok: bool, broken_at: id|null, count: int}``.

    Notas:
      - Registros sin ``current_hash`` (NULL) se ignoran: fueron insertados
        antes del cálculo del hash o durante un fallo. La cadena sólo se
        considera rota cuando un hash calculado no coincide con el esperado.
      - Si la BD está vacía o no hay registros con hash, devuelve
        ``{ok: True, count: 0}``.
    """
    rows: List[AuditLog] = list(
        db.execute(
            select(AuditLog)
            .where(AuditLog.current_hash.is_not(None))
            .order_by(AuditLog.tenant_id, AuditLog.created_at, AuditLog.id)
        ).scalars()
    )

    prev_by_tenant: Dict[str, str] = {}
    broken_at: Optional[str] = None
    count = 0

    for r in rows:
        tenant_key = str(r.tenant_id) if r.tenant_id is not None else "__null__"
        prev = prev_by_tenant.get(tenant_key, GENESIS_PREV_HASH)

        # Si prev_hash no encadena, está roto.
        if r.prev_hash != prev:
            broken_at = str(r.id)
            break

        # Recalcular el hash esperado y comparar.
        payload = payload_from_record(r)
        expected = compute_hash(prev, payload)
        if r.current_hash != expected:
            broken_at = str(r.id)
            break

        prev_by_tenant[tenant_key] = r.current_hash
        count += 1

    return {
        "ok": broken_at is None,
        "broken_at": broken_at,
        "count": count,
    }


# ── helpers internos (id UUID-safe) ──────────────────────────────────
def _safe_uuid(value: Any) -> Optional[str]:
    if value is None:
        return None
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        return str(value)
