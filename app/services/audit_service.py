"""AuditService — registro de acciones para compliance."""
from typing import Optional

from sqlalchemy.orm import Session

from app.models.audit import AuditLog
from app.models.user import User


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
