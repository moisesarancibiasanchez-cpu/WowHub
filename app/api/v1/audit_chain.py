"""HU_40 — Audit log hash chain API (superadmin only).

Endpoints:
  - POST /api/v1/audit/backfill-chain  → rellena prev/current de todos los logs.
  - GET  /api/v1/audit/verify-chain    → verifica la integridad de la cadena.

Ambos requieren rol SUPERUSER de plataforma (mismo guard que el resto del
panel ``/api/v1/superadmin``). Los endpoints son cross-tenant: el hash chain
se verifica sobre la BD completa (la cadena es por-tenant, pero el recorrido
es global).
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import require_superuser
from app.models.user import User
from app.services import audit_chain

logger = logging.getLogger("wowhub.audit_chain")

router = APIRouter(prefix="/audit", tags=["audit-chain"])


@router.post("/backfill-chain")
def backfill_chain(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_superuser),
):
    """Recorre todos los audit logs y rellena prev_hash/current_hash.

    Retorna ``{updated: int}`` con el número de filas tocadas.
    Útil para inicializar la cadena en DBs pre-existentes o re-correr
    después de un fallo parcial.
    """
    updated = audit_chain.backfill_chain(db)
    return {"updated": updated}


@router.get("/verify-chain")
def verify_chain(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_superuser),
):
    """Verifica la integridad de la cadena de hashes.

    Retorna ``{ok: bool, broken_at: id|null, count: int}``.

    - ``ok=True``: la cadena está intacta.
    - ``ok=False``: la cadena está rota en ``broken_at`` (UUID string).
    - ``count=0``: no hay registros con hash (no se ha hecho backfill o la
      BD está vacía). Se considera OK porque no hay nada que verificar.
    """
    return audit_chain.verify_chain(db)
