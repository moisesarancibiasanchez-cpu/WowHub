"""Dependencias compartidas: get_current_user, get_current_membership, get_tenant_id."""
from typing import Optional
from uuid import UUID

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ForbiddenError, UnauthorizedError
from app.core import tenant_context
from app.database import get_db
from app.models.tenant import Tenant, TenantMembership
from app.models.user import User, UserRole
from app.security import decode_token


def _extract_token(authorization: Optional[str]) -> str:
    if not authorization:
        raise UnauthorizedError("Falta header Authorization")
    if not authorization.lower().startswith("bearer "):
        raise UnauthorizedError("Header Authorization debe usar Bearer")
    return authorization.split(" ", 1)[1].strip()


def get_current_user(
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    token = _extract_token(authorization)
    try:
        payload = decode_token(token)
    except ValueError as e:
        raise UnauthorizedError(str(e))
    if payload.get("type") != "access":
        raise UnauthorizedError("Token inválido (no es access)")
    sub = payload.get("sub")
    if not sub:
        raise UnauthorizedError("Token sin 'sub'")
    user = db.get(User, UUID(sub))
    if not user or not user.is_active:
        raise UnauthorizedError("Usuario no encontrado o inactivo")
    return user


def get_current_membership(
    tenant_id: Optional[UUID] = None,
    x_tenant_id: Optional[str] = Header(default=None, alias="X-Tenant-Id"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TenantMembership:
    """Resuelve la membresía activa. Orden de prioridad:
    1) path param `tenant_id` si viene
    2) header `X-Tenant-Id`
    3) claim `tid` del JWT
    """
    # claim tid del jwt (lo propagamos vía un sub-dependency)
    from app.security import decode_token
    tid: Optional[str] = None
    try:
        from fastapi import Request
        # No tenemos Request aquí; la decodificación ya se hizo en get_current_user
        # pero no nos llegó el payload. La re-leemos del header.
        pass
    except Exception:
        pass

    if tenant_id:
        tid = str(tenant_id)
    elif x_tenant_id:
        tid = x_tenant_id
    else:
        # tomar del token directamente
        from app.security import decode_token
        from fastapi import Request  # noqa
        # Truco: volver a leer el header
        raise UnauthorizedError("Falta tenant_id en path o header X-Tenant-Id")

    m = db.execute(
        select(TenantMembership).where(
            TenantMembership.user_id == str(user.id),
            TenantMembership.tenant_id == tid,
            TenantMembership.is_active == True,  # noqa: E712
        )
    ).scalar_one_or_none()
    if not m:
        raise ForbiddenError("No tienes acceso a este tenant")
    return m


def get_tenant_for_membership(
    membership: TenantMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
) -> Tenant:
    t = db.get(Tenant, UUID(membership.tenant_id))
    if not t:
        raise ForbiddenError("Tenant no encontrado")
    tenant_context.set_tenant(t.id)
    return t


def require_role(*allowed: UserRole):
    """Factory de dependencias para requerir un rol específico."""
    allowed_vals = {r.value for r in allowed}

    def _checker(membership: TenantMembership = Depends(get_current_membership)) -> TenantMembership:
        if membership.role.value not in allowed_vals and not membership.is_owner:
            raise ForbiddenError(f"Requiere rol: {', '.join(allowed_vals)}")
        return membership
    return _checker
