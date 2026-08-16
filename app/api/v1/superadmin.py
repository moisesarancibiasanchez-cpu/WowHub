"""SUPERADMIN — endpoints cross-tenant para gestión de plataforma.

Protegido por `require_superuser` (user.is_superuser=True).

Endpoints MVP (Fase 1):
- GET  /api/v1/superadmin/stats                    → KPIs globales
- GET  /api/v1/superadmin/tenants                  → listar todos los tenants
- GET  /api/v1/superadmin/tenants/{tenant_id}      → detalle de un tenant
- PATCH /api/v1/superadmin/tenants/{tenant_id}     → status / plan / is_active
- GET  /api/v1/superadmin/users                    → listar todos los usuarios
- GET  /api/v1/superadmin/users/{user_id}          → detalle
- PATCH /api/v1/superadmin/users/{user_id}         → is_active, full_name
- POST /api/v1/superadmin/users/{user_id}/superuser → toggle is_superuser
- GET  /api/v1/superadmin/audit                    → logs de auditoría
- POST /api/v1/superadmin/impersonate/{user_id}    → SUPERADMIN entra como ese user
- POST /api/v1/superadmin/stop-impersonating       → volver a sesión admin

Fase 2 (futuro, ya con espacio en la UI):
- /superadmin/plans, /superadmin/coupons, /superadmin/integrations,
  /superadmin/maintenance, /superadmin/api-keys, /superadmin/domains.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user, require_superuser
from app.models.tenant import (
    Industry, Tenant, TenantMembership, TenantPlan, TenantStatus,
)
from app.models.user import User
from app.models.audit import AuditLog  # si existe; si no, fallback en log
from app.services.auth_service import AuthService

logger = logging.getLogger("wowhub.superadmin")
router = APIRouter(prefix="/superadmin", tags=["superadmin"])

# Duración máxima de una sesión de impersonación (minutos).
# 60 min es suficiente para soporte; pasado eso, el claim `imp.expires_at`
# se ignora y la sesión vuelve a la del admin.
IMPERSONATION_TTL_MINUTES = 60


# ── Helpers ──────────────────────────────────────────────────────
def _get_real_admin(request: Request, db: Session) -> User:
    """Devuelve el superuser REAL, no el usuario impersonado.

    Si la request tiene `imp` claim activo, lee el admin original de
    `request.state.admin_user` (que `get_current_user` ya pobló).
    Si no hay impersonación, hace un lookup directo por el `sub` del JWT.
    """
    admin = getattr(request.state, "admin_user", None)
    if admin and getattr(admin, "is_superuser", False) and admin.is_active:
        return admin
    # No estamos impersonando: leer directamente del JWT.
    from app.security import decode_token
    from app.core.errors import ForbiddenError, UnauthorizedError
    auth = request.headers.get("authorization") or request.headers.get("Authorization")
    if not auth or not auth.lower().startswith("bearer "):
        raise UnauthorizedError("Falta token")
    try:
        payload = decode_token(auth.split(" ", 1)[1].strip())
    except Exception:
        raise UnauthorizedError("Token inválido")
    sub = payload.get("sub")
    if not sub:
        raise UnauthorizedError("Token sin 'sub'")
    try:
        admin = db.get(User, UUID(sub))
    except (ValueError, TypeError):
        raise UnauthorizedError("Sub inválido")
    if not admin or not admin.is_active or not getattr(admin, "is_superuser", False):
        raise ForbiddenError("Requiere superuser")
    return admin


def _log_impersonation_event(
    *,
    db: Session,
    admin: User,
    action: str,
    target_user_id: str,
    target_user_email: str,
    tenant_id: Optional[str] = None,
    description: str = "",
    request: Optional[Request] = None,
    extra: Optional[dict] = None,
) -> None:
    """Escribe un audit log para eventos de impersonación.

    Usa un try/except defensivo: si falla, no rompe el flujo principal
    (ya escribimos log en el logger también).
    """
    try:
        from app.services.audit_service import AuditService
        ip = None
        if request is not None and request.client:
            ip = request.client.host
        xff = request.headers.get("X-Forwarded-For") if request is not None else None
        if xff:
            ip = xff.split(",")[0].strip()
        ua = (request.headers.get("user-agent", "")[:500] if request is not None else "")
        ex = dict(extra or {})
        ex["impersonated_user_id"] = target_user_id
        ex["impersonated_user_email"] = target_user_email
        if tenant_id:
            ex["impersonated_tenant_id"] = tenant_id
        AuditService(db).log(
            tenant_id=tenant_id,
            actor=admin,
            action=action,
            resource_type="user",
            resource_id=target_user_id,
            method="POST",
            path=(request.url.path if request is not None else None),
            ip=ip,
            user_agent=ua,
            status_code=200,
            description=description,
            extra=ex,
        )
    except Exception as e:
        logger.warning("[superadmin/impersonation] audit log error: %s", e)
        try:
            db.rollback()
        except Exception:
            pass


# ── Schemas ──────────────────────────────────────────────────────
class PlatformStats(BaseModel):
    total_tenants: int
    active_tenants: int
    trial_tenants: int
    suspended_tenants: int
    canceled_tenants: int
    past_due_tenants: int
    total_users: int
    superusers: int
    active_users_7d: int
    new_tenants_7d: int
    new_tenants_30d: int
    new_users_7d: int
    new_users_30d: int
    total_memberships: int


class TenantOut(BaseModel):
    id: str
    slug: str
    legal_name: str
    display_name: str
    industry: str
    plan: str
    status: str
    is_active: bool
    country: str
    locale: str
    currency: str
    timezone: str
    wow_score: int
    health_score: int
    active_branches: int
    members_count: int
    created_at: Optional[str] = None


class TenantUpdateIn(BaseModel):
    plan: Optional[TenantPlan] = None
    status: Optional[TenantStatus] = None
    is_active: Optional[bool] = None
    display_name: Optional[str] = None


class UserOut(BaseModel):
    id: str
    email: str
    full_name: str
    phone: Optional[str] = None
    is_active: bool
    is_superuser: bool
    default_role: str
    memberships_count: int
    tenants: list[str] = Field(default_factory=list)
    created_at: Optional[str] = None


class UserUpdateIn(BaseModel):
    is_active: Optional[bool] = None
    full_name: Optional[str] = None
    default_role: Optional[str] = None


class SuperuserToggleIn(BaseModel):
    is_superuser: bool


class AuditEntry(BaseModel):
    id: str
    actor_user_id: Optional[str] = None
    actor_email: Optional[str] = None
    action: str
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    description: Optional[str] = None
    method: Optional[str] = None
    path: Optional[str] = None
    status_code: Optional[str] = None
    ip: Optional[str] = None
    extra: dict = Field(default_factory=dict)
    created_at: Optional[str] = None


class AuditListOut(BaseModel):
    items: list[AuditEntry]
    total: int
    page: int
    page_size: int


# ── Helpers ──────────────────────────────────────────────────────
def _tenant_to_out(t: Tenant, members_count: int = 0) -> TenantOut:
    return TenantOut(
        id=str(t.id),
        slug=t.slug,
        legal_name=t.legal_name,
        display_name=t.display_name,
        industry=(t.industry.value if hasattr(t.industry, "value") else str(t.industry)),
        plan=(t.plan.value if hasattr(t.plan, "value") else str(t.plan)),
        status=(t.status.value if hasattr(t.status, "value") else str(t.status)),
        is_active=bool(t.is_active),
        country=t.country,
        locale=t.locale,
        currency=t.currency,
        timezone=t.timezone,
        wow_score=int(getattr(t, "wow_score", 0) or 0),
        health_score=int(getattr(t, "health_score", 0) or 0),
        active_branches=int(getattr(t, "active_branches", 0) or 0),
        members_count=members_count,
        created_at=getattr(t, "created_at", None).isoformat() if getattr(t, "created_at", None) else None,
    )


def _user_to_out(u: User) -> UserOut:
    memberships = list(getattr(u, "memberships", []) or [])
    tenants = []
    for m in memberships:
        if m.is_active and getattr(m, "tenant", None):
            tenants.append(f"{m.tenant.slug} ({m.role.value if hasattr(m.role, 'value') else m.role})")
    return UserOut(
        id=str(u.id),
        email=u.email,
        full_name=u.full_name,
        phone=u.phone,
        is_active=bool(u.is_active),
        is_superuser=bool(getattr(u, "is_superuser", False)),
        default_role=(u.default_role.value if hasattr(u.default_role, "value") else str(u.default_role)),
        memberships_count=len(memberships),
        tenants=tenants,
        created_at=getattr(u, "created_at", None).isoformat() if getattr(u, "created_at", None) else None,
    )


# ── /stats ───────────────────────────────────────────────────────
@router.get("/stats", response_model=PlatformStats)
def platform_stats(
    db: Session = Depends(get_db),
    user: User = Depends(require_superuser),
) -> PlatformStats:
    """KPIs globales de la plataforma. Cacheable 30s en el cliente."""
    now = datetime.now(timezone.utc)
    since_7d = now - timedelta(days=7)
    since_30d = now - timedelta(days=30)

    def _count(stmt):
        try:
            return int(db.execute(stmt).scalar() or 0)
        except Exception as e:
            logger.warning("[superadmin/stats] count error: %s", e)
            db.rollback()
            return 0

    total_tenants = _count(select(func.count(Tenant.id)))
    active_tenants = _count(select(func.count(Tenant.id)).where(Tenant.is_active == True))  # noqa
    trial_tenants = _count(select(func.count(Tenant.id)).where(Tenant.status == TenantStatus.TRIAL))
    suspended_tenants = _count(select(func.count(Tenant.id)).where(Tenant.status == TenantStatus.SUSPENDED))
    canceled_tenants = _count(select(func.count(Tenant.id)).where(Tenant.status == TenantStatus.CANCELED))
    past_due_tenants = _count(select(func.count(Tenant.id)).where(Tenant.status == TenantStatus.PAST_DUE))

    total_users = _count(select(func.count(User.id)))
    superusers = _count(select(func.count(User.id)).where(User.is_superuser == True))  # noqa
    new_users_7d = _count(select(func.count(User.id)).where(User.created_at >= since_7d))
    new_users_30d = _count(select(func.count(User.id)).where(User.created_at >= since_30d))

    # Tenants creados en últimos N días
    try:
        new_tenants_7d = int(
            db.execute(
                select(func.count(Tenant.id)).where(Tenant.created_at >= since_7d)
            ).scalar() or 0
        )
    except Exception:
        db.rollback()
        new_tenants_7d = 0
    try:
        new_tenants_30d = int(
            db.execute(
                select(func.count(Tenant.id)).where(Tenant.created_at >= since_30d)
            ).scalar() or 0
        )
    except Exception:
        db.rollback()
        new_tenants_30d = 0

    # Usuarios activos últimos 7d (cualquier membership activa reciente)
    try:
        active_users_7d = int(
            db.execute(
                select(func.count(func.distinct(TenantMembership.user_id))).where(
                    TenantMembership.is_active == True,  # noqa
                    TenantMembership.last_login_at.isnot(None),
                )
            ).scalar() or 0
        )
    except Exception:
        db.rollback()
        active_users_7d = 0

    total_memberships = _count(select(func.count(TenantMembership.id)))

    return PlatformStats(
        total_tenants=total_tenants,
        active_tenants=active_tenants,
        trial_tenants=trial_tenants,
        suspended_tenants=suspended_tenants,
        canceled_tenants=canceled_tenants,
        past_due_tenants=past_due_tenants,
        total_users=total_users,
        superusers=superusers,
        active_users_7d=active_users_7d,
        new_tenants_7d=new_tenants_7d,
        new_tenants_30d=new_tenants_30d,
        new_users_7d=new_users_7d,
        new_users_30d=new_users_30d,
        total_memberships=total_memberships,
    )


# ── /tenants ─────────────────────────────────────────────────────
@router.get("/tenants", response_model=list[TenantOut])
def list_tenants(
    db: Session = Depends(get_db),
    user: User = Depends(require_superuser),
    q: Optional[str] = Query(None, description="Búsqueda por slug/display_name"),
    status_filter: Optional[TenantStatus] = Query(None, alias="status"),
    plan_filter: Optional[TenantPlan] = Query(None, alias="plan"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> list[TenantOut]:
    """Lista todos los tenants. Filtros: q, status, plan."""
    stmt = select(Tenant)
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(
            (func.lower(Tenant.slug).like(like))
            | (func.lower(Tenant.display_name).like(like))
            | (func.lower(Tenant.legal_name).like(like))
        )
    if status_filter:
        stmt = stmt.where(Tenant.status == status_filter)
    if plan_filter:
        stmt = stmt.where(Tenant.plan == plan_filter)
    stmt = stmt.order_by(desc(Tenant.created_at)).offset(offset).limit(limit)
    try:
        rows = db.execute(stmt).scalars().all()
    except Exception as e:
        logger.exception("[superadmin/tenants] list error: %s", e)
        db.rollback()
        return []

    # members_count en una sola query agrupada
    tenant_ids = [str(t.id) for t in rows]
    counts: dict[str, int] = {}
    if tenant_ids:
        try:
            count_rows = db.execute(
                select(
                    TenantMembership.tenant_id,
                    func.count(TenantMembership.id),
                )
                .where(
                    TenantMembership.tenant_id.in_([UUID(t) for t in tenant_ids]),
                    TenantMembership.is_active == True,  # noqa
                )
                .group_by(TenantMembership.tenant_id)
            ).all()
            for tid, c in count_rows:
                counts[str(tid)] = int(c)
        except Exception as e:
            logger.warning("[superadmin/tenants] count error: %s", e)
            db.rollback()

    return [_tenant_to_out(t, counts.get(str(t.id), 0)) for t in rows]


@router.get("/tenants/{tenant_id}", response_model=TenantOut)
def get_tenant(
    tenant_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_superuser),
) -> TenantOut:
    t = db.get(Tenant, tenant_id)
    if not t:
        raise HTTPException(status_code=404, detail="Tenant no encontrado")
    members_count = int(
        db.execute(
            select(func.count(TenantMembership.id)).where(
                TenantMembership.tenant_id == str(tenant_id),
                TenantMembership.is_active == True,  # noqa
            )
        ).scalar() or 0
    )
    return _tenant_to_out(t, members_count)


@router.get("/tenants/{tenant_id}/owner")
def get_tenant_owner(
    tenant_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_superuser),
):
    """Devuelve el owner (o miembro primario) del tenant.

    Usado por el botón 'Entrar como admin' de la tab Tiendas para detectar
    automáticamente al usuario al que hay que impersonar para entrar a la
    tienda como admin.

    Reglas:
    - Si hay un owner, devuelve ese.
    - Si no hay owner pero hay miembros activos, devuelve el primero
      (caso raro: tenant sin owner explícito).
    - 404 si el tenant no existe o no tiene miembros activos.
    """
    t = db.get(Tenant, tenant_id)
    if not t:
        raise HTTPException(status_code=404, detail="Tenant no encontrado")
    memberships = list(
        db.execute(
            select(TenantMembership).where(
                TenantMembership.tenant_id == str(tenant_id),
                TenantMembership.is_active == True,  # noqa
            )
        ).scalars()
    )
    if not memberships:
        raise HTTPException(
            status_code=404,
            detail="Tenant sin miembros activos",
        )
    # Preferir el owner; si no hay, el primero activo.
    primary = next((m for m in memberships if m.is_owner), memberships[0])
    owner = db.get(User, primary.user_id)
    if not owner:
        raise HTTPException(status_code=404, detail="Usuario owner no encontrado")
    return {
        "user_id": str(owner.id),
        "email": owner.email,
        "full_name": owner.full_name,
        "is_active": bool(owner.is_active),
        "is_superuser": bool(getattr(owner, "is_superuser", False)),
        "role": (primary.role.value if hasattr(primary.role, "value") else str(primary.role)),
        "is_owner": bool(primary.is_owner),
        "tenant_id": str(t.id),
        "tenant_slug": t.slug,
        "tenant_display_name": t.display_name,
    }


@router.patch("/tenants/{tenant_id}", response_model=TenantOut)
def update_tenant(
    tenant_id: UUID,
    body: TenantUpdateIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_superuser),
) -> TenantOut:
    t = db.get(Tenant, tenant_id)
    if not t:
        raise HTTPException(status_code=404, detail="Tenant no encontrado")
    changes: list[str] = []
    if body.plan is not None and body.plan != t.plan:
        changes.append(f"plan {t.plan.value}→{body.plan.value}")
        t.plan = body.plan
    if body.status is not None and body.status != t.status:
        changes.append(f"status {t.status.value}→{body.status.value}")
        t.status = body.status
    if body.is_active is not None and body.is_active != t.is_active:
        changes.append(f"is_active {t.is_active}→{body.is_active}")
        t.is_active = body.is_active
    if body.display_name is not None and body.display_name != t.display_name:
        changes.append(f"display_name")
        t.display_name = body.display_name
    if changes:
        try:
            db.commit()
        except Exception as e:
            db.rollback()
            raise HTTPException(status_code=500, detail=f"Error guardando: {e}")
        logger.info(
            "[superadmin] user_id=%s (%s) updated tenant_id=%s: %s",
            user.id, user.email, t.id, ", ".join(changes),
        )
    db.refresh(t)
    members_count = int(
        db.execute(
            select(func.count(TenantMembership.id)).where(
                TenantMembership.tenant_id == str(tenant_id),
                TenantMembership.is_active == True,  # noqa
            )
        ).scalar() or 0
    )
    return _tenant_to_out(t, members_count)


# ── /users ───────────────────────────────────────────────────────
@router.get("/users", response_model=list[UserOut])
def list_users(
    db: Session = Depends(get_db),
    user: User = Depends(require_superuser),
    q: Optional[str] = Query(None, description="Búsqueda por email o nombre"),
    is_active: Optional[bool] = Query(None),
    is_superuser_only: Optional[bool] = Query(None, alias="is_superuser"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> list[UserOut]:
    """Lista todos los usuarios de la plataforma."""
    stmt = select(User)
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(
            (func.lower(User.email).like(like))
            | (func.lower(User.full_name).like(like))
        )
    if is_active is not None:
        stmt = stmt.where(User.is_active == is_active)
    if is_superuser_only is not None:
        stmt = stmt.where(User.is_superuser == is_superuser_only)
    stmt = stmt.order_by(desc(User.created_at)).offset(offset).limit(limit)
    try:
        rows = db.execute(stmt).scalars().all()
    except Exception as e:
        logger.exception("[superadmin/users] list error: %s", e)
        db.rollback()
        return []
    return [_user_to_out(u) for u in rows]


@router.get("/users/{user_id}", response_model=UserOut)
def get_user(
    user_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_superuser),
) -> UserOut:
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return _user_to_out(u)


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(
    user_id: UUID,
    body: UserUpdateIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_superuser),
) -> UserOut:
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    changes: list[str] = []
    if body.is_active is not None and body.is_active != u.is_active:
        changes.append(f"is_active {u.is_active}→{body.is_active}")
        u.is_active = body.is_active
    if body.full_name is not None and body.full_name != u.full_name:
        changes.append(f"full_name")
        u.full_name = body.full_name
    if body.default_role is not None:
        from app.models.user import UserRole
        try:
            new_role = UserRole(body.default_role)
            if new_role != u.default_role:
                changes.append(f"default_role {u.default_role.value}→{new_role.value}")
                u.default_role = new_role
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Rol inválido: {body.default_role}")
    if changes:
        try:
            db.commit()
        except Exception as e:
            db.rollback()
            raise HTTPException(status_code=500, detail=f"Error guardando: {e}")
        logger.info(
            "[superadmin] superuser_id=%s updated user_id=%s (%s): %s",
            user.id, u.id, u.email, ", ".join(changes),
        )
    db.refresh(u)
    return _user_to_out(u)


@router.post("/users/{user_id}/superuser", response_model=UserOut)
def toggle_superuser(
    user_id: UUID,
    body: SuperuserToggleIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_superuser),
) -> UserOut:
    """Promueve o revoca el flag `is_superuser` de un usuario.

    Reglas de seguridad:
    - No se puede revocar el superuser a sí mismo si es el único.
    - La acción queda logueada con quién la hizo y a quién.
    """
    if str(user_id) == str(user.id) and not body.is_superuser:
        # Revocar a sí mismo: checkear que quede al menos un superuser
        super_count = int(
            db.execute(
                select(func.count(User.id)).where(
                    User.is_superuser == True,  # noqa
                    User.id != user.id,
                    User.is_active == True,  # noqa
                )
            ).scalar() or 0
        )
        if super_count == 0:
            raise HTTPException(
                status_code=400,
                detail="No puedes revocar tu propio superuser si eres el único. Promueve a otro primero.",
            )
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    prev = bool(u.is_superuser)
    u.is_superuser = bool(body.is_superuser)
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error guardando: {e}")
    logger.warning(
        "[superadmin] superuser_id=%s (%s) cambió is_superuser de user_id=%s (%s): %s→%s",
        user.id, user.email, u.id, u.email, prev, u.is_superuser,
    )
    db.refresh(u)
    return _user_to_out(u)


# ── /audit ───────────────────────────────────────────────────────
@router.get("/audit", response_model=AuditListOut)
def list_audit(
    db: Session = Depends(get_db),
    user: User = Depends(require_superuser),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    action_prefix: Optional[str] = Query(None, description="Prefijo de action (ej: 'superadmin', 'auth', 'tenant')"),
    actor_user_id: Optional[UUID] = Query(None),
) -> AuditListOut:
    """Lee los logs de auditoría. Si AuditLog no existe, devuelve lista vacía."""
    try:
        stmt = select(AuditLog)
    except Exception:
        return AuditListOut(items=[], total=0, page=page, page_size=page_size)

    if action_prefix:
        stmt = stmt.where(AuditLog.action.like(f"{action_prefix}%"))
    if actor_user_id:
        stmt = stmt.where(AuditLog.actor_user_id == str(actor_user_id))

    try:
        total = int(
            db.execute(select(func.count()).select_from(stmt.subquery())).scalar() or 0
        )
        rows = db.execute(
            stmt.order_by(desc(AuditLog.created_at))
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).scalars().all()
    except Exception as e:
        logger.exception("[superadmin/audit] list error: %s", e)
        db.rollback()
        return AuditListOut(items=[], total=0, page=page, page_size=page_size)

    items: list[AuditEntry] = []
    for r in rows:
        items.append(
            AuditEntry(
                id=str(getattr(r, "id", "")),
                actor_user_id=getattr(r, "actor_user_id", None),
                actor_email=getattr(r, "actor_email", None),
                action=getattr(r, "action", ""),
                resource_type=getattr(r, "resource_type", None),
                resource_id=getattr(r, "resource_id", None),
                description=getattr(r, "description", None),
                method=getattr(r, "method", None),
                path=getattr(r, "path", None),
                status_code=str(getattr(r, "status_code", None)) if getattr(r, "status_code", None) is not None else None,
                ip=getattr(r, "ip", None),
                extra=dict(getattr(r, "extra", {}) or {}),
                created_at=getattr(r, "created_at", None).isoformat() if getattr(r, "created_at", None) else None,
            )
        )
    return AuditListOut(items=items, total=total, page=page, page_size=page_size)


# ── /impersonate ─────────────────────────────────────────────────
class ImpersonateOut(BaseModel):
    access_token: str
    expires_in: int
    expires_at: str
    impersonating: dict
    redirect: str = "/dashboard"


@router.post("/impersonate/{user_id}", response_model=ImpersonateOut)
def impersonate_user(
    user_id: UUID,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> ImpersonateOut:
    """SUPERADMIN entra como `user_id`. Devuelve un nuevo access token con
    claim `imp` que hace que `get_current_user` devuelva al usuario target
    en lugar del admin. Auto-expira a los 60 minutos.

    Reglas de seguridad:
    - Solo accesible por un superuser.
    - No se puede impersonar a sí mismo.
    - No se puede impersonar a otro superuser.
    - El target debe estar activo y tener al menos una membresía activa.
    - Queda registrado en `audit_logs` con `actor=admin, extra.impersonated_user_id`.
    """
    admin = _get_real_admin(request, db)

    target = db.get(User, user_id)
    if not target:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    if not target.is_active:
        raise HTTPException(status_code=400, detail="Usuario inactivo, no se puede impersonar")
    if str(target.id) == str(admin.id):
        raise HTTPException(status_code=400, detail="No podés impersonarte a vos mismo")
    if getattr(target, "is_superuser", False):
        raise HTTPException(
            status_code=403,
            detail="No se puede impersonar a un superuser (medida de seguridad)",
        )

    # Membresía primaria del target: preferimos OWNER, sino la primera activa.
    memberships = list(
        db.execute(
            select(TenantMembership).where(
                TenantMembership.user_id == str(target.id),
                TenantMembership.is_active == True,  # noqa: E712
            )
        ).scalars()
    )
    if not memberships:
        raise HTTPException(
            status_code=400,
            detail="El usuario no tiene membresías activas; no se puede impersonar",
        )
    primary = next((m for m in memberships if m.is_owner), memberships[0])

    # Construir claim `imp`
    now = datetime.now(timezone.utc)
    expires = now + timedelta(minutes=IMPERSONATION_TTL_MINUTES)
    imp_claim = {
        "uid": str(target.id),
        "email": target.email,
        "full_name": target.full_name,
        "tid": str(primary.tenant_id),
        "started_at": now.isoformat(),
        "expires_at": expires.isoformat(),
    }

    # Emitir nuevos tokens con imp claim. El `sub` sigue siendo el admin.
    svc = AuthService(db)
    access, _refresh, ttl = svc.issue_tokens(admin, primary, imp=imp_claim)

    # Seteamos la cookie httpOnly igual que en login/refresh para que el
    # guard server-side (que lee la cookie) siga dejando pasar.
    try:
        from app.api.v1.auth import _set_access_cookie
        _set_access_cookie(response, access)
    except Exception as e:
        logger.warning("[superadmin/impersonate] could not set cookie: %s", e)

    # Audit log
    _log_impersonation_event(
        db=db,
        admin=admin,
        action="superadmin.impersonate_start",
        target_user_id=str(target.id),
        target_user_email=target.email,
        tenant_id=str(primary.tenant_id),
        request=request,
        description=(
            f"Superadmin {admin.email} empezó a impersonar a "
            f"{target.email} (tenant {primary.tenant_id}) por {IMPERSONATION_TTL_MINUTES} min"
        ),
        extra={"started_at": now.isoformat(), "expires_at": expires.isoformat()},
    )

    logger.warning(
        "[superadmin] SUPERADMIN user_id=%s (%s) IMPERSONATING user_id=%s (%s) until %s",
        admin.id, admin.email, target.id, target.email, expires.isoformat(),
    )

    return ImpersonateOut(
        access_token=access,
        expires_in=ttl,
        expires_at=expires.isoformat(),
        impersonating={
            "user_id": str(target.id),
            "email": target.email,
            "full_name": target.full_name,
            "tenant_id": str(primary.tenant_id),
            "role": primary.role.value if hasattr(primary.role, "value") else str(primary.role),
            "is_owner": bool(primary.is_owner),
        },
        redirect="/dashboard",
    )


@router.post("/stop-impersonating")
def stop_impersonating(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    """Detiene la impersonación actual y emite un nuevo access token
    sin el claim `imp` (vuelve a la sesión normal del superuser)."""
    admin = _get_real_admin(request, db)

    # Leer el claim `imp` actual del JWT para registrar el fin.
    from app.security import decode_token
    current_imp = None
    auth = request.headers.get("authorization") or request.headers.get("Authorization")
    if auth and auth.lower().startswith("bearer "):
        try:
            payload = decode_token(auth.split(" ", 1)[1].strip())
            current_imp = payload.get("imp")
        except Exception:
            pass

    if not current_imp:
        # No estábamos impersonando. Devolvemos tokens frescos igual.
        pass

    # Encontrar membresía del admin (si tiene) para mantener contexto
    admin_memberships = list(
        db.execute(
            select(TenantMembership).where(
                TenantMembership.user_id == str(admin.id),
                TenantMembership.is_active == True,  # noqa: E712
            )
        ).scalars()
    )
    current = admin_memberships[0] if admin_memberships else None

    svc = AuthService(db)
    access, _refresh, ttl = svc.issue_tokens(admin, current, imp=None)

    try:
        from app.api.v1.auth import _set_access_cookie
        _set_access_cookie(response, access)
    except Exception as e:
        logger.warning("[superadmin/stop-impersonating] could not set cookie: %s", e)

    if current_imp:
        _log_impersonation_event(
            db=db,
            admin=admin,
            action="superadmin.impersonate_end",
            target_user_id=str(current_imp.get("uid") or ""),
            target_user_email=str(current_imp.get("email") or ""),
            tenant_id=str(current_imp.get("tid") or "") or None,
            request=request,
            description=(
                f"Superadmin {admin.email} terminó impersonación de "
                f"{current_imp.get('email') or 'usuario'}"
            ),
            extra={
                "started_at": current_imp.get("started_at"),
                "ended_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        logger.warning(
            "[superadmin] SUPERADMIN user_id=%s (%s) STOPPED impersonating user_id=%s (%s)",
            admin.id, admin.email, current_imp.get("uid"), current_imp.get("email"),
        )

    return {
        "access_token": access,
        "expires_in": ttl,
        "impersonating": None,
        "redirect": "/admin/superadmin",
    }


# ── /impersonation/status ────────────────────────────────────────
@router.get("/impersonation/status")
def impersonation_status(
    request: Request,
    db: Session = Depends(get_db),
):
    """Lee el JWT actual y devuelve el estado de impersonación, si lo hay.
    Útil para que el frontend hidrate el banner al cargar una página sin
    tener que esperar al primer fetch de datos.
    """
    from app.security import decode_token
    auth = request.headers.get("authorization") or request.headers.get("Authorization")
    if not auth or not auth.lower().startswith("bearer "):
        return {"impersonating": None}
    try:
        payload = decode_token(auth.split(" ", 1)[1].strip())
    except Exception:
        return {"impersonating": None}
    imp = payload.get("imp")
    if not imp:
        return {"impersonating": None}
    return {
        "impersonating": {
            "uid": imp.get("uid"),
            "email": imp.get("email"),
            "full_name": imp.get("full_name"),
            "tid": imp.get("tid"),
            "started_at": imp.get("started_at"),
            "expires_at": imp.get("expires_at"),
        },
        "admin": {
            "sub": payload.get("sub"),
        },
    }
