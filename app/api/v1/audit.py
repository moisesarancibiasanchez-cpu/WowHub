"""Audit API — consulta del log de auditoría."""
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_membership
from app.models.tenant import TenantMembership
from app.services.audit_service import AuditService

router = APIRouter(prefix="/tenants/{tenant_id}/audit", tags=["audit"])


@router.get("")
def list_audit_logs(
    tenant_id: UUID,
    action: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    membership: TenantMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    """Lista los últimos eventos de auditoría del tenant."""
    logs = AuditService(db).list_for_tenant(str(tenant_id), limit=limit, action=action)
    return [
        {
            "id": str(l.id),
            "actor_user_id": l.actor_user_id,
            "actor_email": l.actor_email,
            "action": l.action,
            "resource_type": l.resource_type,
            "resource_id": l.resource_id,
            "method": l.method,
            "path": l.path,
            "ip": l.ip,
            "user_agent": l.user_agent,
            "status_code": l.status_code,
            "extra": l.extra,
            "description": l.description,
            "created_at": l.created_at.isoformat() if l.created_at else None,
        }
        for l in logs
    ]
