"""AuditService — registro de acciones para compliance."""
import logging
from typing import Optional

from fastapi import Request
from sqlalchemy.orm import Session

from app.models.audit import AuditLog
from app.models.user import User
from app.services import audit_chain

logger = logging.getLogger("wowhub.audit")


def request_meta(request: Optional[Request]) -> tuple[Optional[str], Optional[str]]:
    """Extrae ``(ip, user_agent)`` del request para auditoría.

    - IP: ``request.client.host`` si está disponible, con override por
      ``X-Forwarded-For`` (primer valor, ya que puede traer ``client, proxy1,
      proxy2``). Esto es importante porque WowHub se deploya detrás de
      Railway/Render/etc. que inyectan XFF.
    - UA: truncado a 500 chars (igual que la columna ``user_agent`` del modelo).
    """
    if request is None:
        return None, None
    ip = request.client.host if request.client else None
    xff = request.headers.get("X-Forwarded-For") if request else None
    if xff:
        ip = xff.split(",")[0].strip()
    ua = (request.headers.get("user-agent", "") or "")[:500]
    return ip, ua


class AuditService:
    def __init__(self, db: Session):
        self.db = db

    def log(
        self,
        *,
        tenant_id: Optional[str] = None,
        actor: Optional[User] = None,
        action: str,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        method: Optional[str] = None,
        path: Optional[str] = None,
        ip: Optional[str] = None,
        user_agent: Optional[str] = None,
        status_code: Optional[int] = None,
        description: Optional[str] = None,
        extra: Optional[dict] = None,
    ) -> AuditLog:
        log = AuditLog(
            tenant_id=tenant_id,
            actor_user_id=str(actor.id) if actor else None,
            actor_email=actor.email if actor else None,
            action=action,
            resource_type=resource_type,
            resource_id=str(resource_id) if resource_id else None,
            method=method,
            path=path,
            ip=ip,
            user_agent=user_agent,
            status_code=str(status_code) if status_code else None,
            description=description,
            extra=extra or {},
        )
        self.db.add(log)
        # HU_40 — calcular hash chain (best-effort). Si falla, NO rompemos
        # el insert: el registro queda con prev_hash/current_hash NULL y
        # puede rellenarse después con `POST /api/v1/audit/backfill-chain`.
        try:
            self.db.flush()  # asegura log.id antes de leer el último hash
            self._attach_chain_hash(log)
        except Exception as exc:
            logger.warning("audit_chain: hash computation failed (id=%s): %s", getattr(log, "id", None), exc)
        self.db.commit()
        self.db.refresh(log)
        return log

    def list_for_tenant(self, tenant_id: str, *, limit: int = 100, action: Optional[str] = None):
        from sqlalchemy import select
        q = select(AuditLog).where(AuditLog.tenant_id == tenant_id)
        if action:
            q = q.where(AuditLog.action == action)
        q = q.order_by(AuditLog.created_at.desc()).limit(limit)
        return list(self.db.execute(q).scalars())

    # ── HU_40 — Hash chain helpers ──────────────────────────────────
    def _attach_chain_hash(self, log: AuditLog) -> None:
        """Calcula y persiste prev_hash/current_hash en la fila recién creada.

        1. Lee el último ``current_hash`` del tenant (excluyendo esta fila).
        2. Construye el payload canónico vía ``audit_chain.payload_from_record``.
        3. Calcula ``current_hash = SHA-256(prev_hash || canonical_json(payload))``.

        Best-effort: cualquier excepción se propaga al caller que la envuelve
        en try/except para no romper el insert del audit log.
        """
        from sqlalchemy import select  # import local para no tocar imports del módulo

        tenant_id = log.tenant_id
        if tenant_id is None:
            # Sin tenant no podemos encadenar — sólo guardamos genesis.
            prev_hash = audit_chain.GENESIS_PREV_HASH
        else:
            prev_hash = (
                self.db.execute(
                    select(AuditLog.current_hash)
                    .where(
                        AuditLog.tenant_id == tenant_id,
                        AuditLog.id != log.id,
                    )
                    .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
                    .limit(1)
                ).scalar()
            ) or audit_chain.GENESIS_PREV_HASH

        payload = audit_chain.payload_from_record(log)
        current_hash = audit_chain.compute_hash(prev_hash, payload)

        log.prev_hash = prev_hash
        log.current_hash = current_hash
        self.db.flush()
