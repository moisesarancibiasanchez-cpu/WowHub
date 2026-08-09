"""Auth endpoints: register, login, refresh, me, switch tenant."""
from uuid import UUID

from fastapi import APIRouter, Depends, Form, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models.tenant import Tenant, TenantMembership
from app.models.user import User
from app.schemas.auth import (
    MembershipOut, TokenPair, TokenRefresh, UserCreate, UserLogin, UserOut, UserUpdate,
)
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenPair, status_code=201)
def register(payload: UserCreate, db: Session = Depends(get_db)):
    """Registro de usuario. Si `create_tenant=true`, crea también un tenant
    con el usuario como OWNER."""
    svc = AuthService(db)
    user, tenant, membership = svc.register(payload)
    access, refresh, ttl = svc.issue_tokens(user, membership)
    current = None
    if membership:
        t = db.get(Tenant, membership.tenant_id)
        current = MembershipOut(
            id=membership.id,
            user_id=user.id,
            tenant_id=t.id,
            role=membership.role,
            is_owner=membership.is_owner,
            is_active=membership.is_active,
            last_login_at=membership.last_login_at,
            tenant_slug=t.slug,
            tenant_display_name=t.display_name,
        )
    return TokenPair(
        access_token=access,
        refresh_token=refresh,
        expires_in=ttl,
        user=UserOut.model_validate(user),
        current_tenant=current,
    )


@router.post("/login", response_model=TokenPair)
def login(payload: UserLogin, db: Session = Depends(get_db)):
    svc = AuthService(db)
    user, current, _memberships = svc.login(payload.email, payload.password)
    access, refresh, ttl = svc.issue_tokens(user, current)
    current_out = None
    if current:
        t = db.get(Tenant, current.tenant_id)
        current_out = MembershipOut(
            id=current.id,
            user_id=user.id,
            tenant_id=t.id,
            role=current.role,
            is_owner=current.is_owner,
            is_active=current.is_active,
            last_login_at=current.last_login_at,
            tenant_slug=t.slug,
            tenant_display_name=t.display_name,
        )
    return TokenPair(
        access_token=access,
        refresh_token=refresh,
        expires_in=ttl,
        user=UserOut.model_validate(user),
        current_tenant=current_out,
    )


@router.post("/login/form", response_model=TokenPair, include_in_schema=False)
def login_form(
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    """Endpoint OAuth2 password para Swagger UI."""
    payload = UserLogin(email=username, password=password)
    return login(payload, db)


@router.post("/refresh", response_model=TokenPair)
def refresh(payload: TokenRefresh, db: Session = Depends(get_db)):
    svc = AuthService(db)
    user, current = svc.refresh(payload.refresh_token)
    access, refresh_t, ttl = svc.issue_tokens(user, current)
    current_out = None
    if current:
        t = db.get(Tenant, current.tenant_id)
        current_out = MembershipOut(
            id=current.id,
            user_id=user.id,
            tenant_id=t.id,
            role=current.role,
            is_owner=current.is_owner,
            is_active=current.is_active,
            last_login_at=current.last_login_at,
            tenant_slug=t.slug,
            tenant_display_name=t.display_name,
        )
    return TokenPair(
        access_token=access,
        refresh_token=refresh_t,
        expires_in=ttl,
        user=UserOut.model_validate(user),
        current_tenant=current_out,
    )


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


@router.patch("/me", response_model=UserOut)
def update_me(payload: UserUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(user, k, v)
    db.commit()
    db.refresh(user)
    return user


@router.get("/me/session")
def my_session(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Estado completo de la sesión: user + current_tenant + todas las membresías activas.

    Usado por el frontend para rehidratar localStorage cuando el token fue
    refrescado (lo que puede perder `current_tenant` del lado del cliente) o
    cuando el usuario abrió el dashboard sin pasar por login.
    """
    memberships = list(
        db.execute(
            select(TenantMembership).where(
                TenantMembership.user_id == str(user.id),
                TenantMembership.is_active == True,  # noqa: E712
            )
        ).scalars()
    )
    current = next((m for m in memberships if m.is_owner), memberships[0] if memberships else None)
    current_tenant = None
    if current is not None:
        t = db.get(Tenant, current.tenant_id)
        if t is not None:
            current_tenant = {
                "id": str(current.id),
                "tenant_id": str(t.id),
                "role": current.role.value if hasattr(current.role, "value") else str(current.role),
                "is_owner": bool(current.is_owner),
                "is_active": bool(current.is_active),
                "last_login_at": current.last_login_at,
                "tenant_slug": t.slug,
                "tenant_display_name": t.display_name,
            }
    return {
        "user": UserOut.model_validate(user).model_dump(mode="json"),
        "current_tenant": current_tenant,
        "memberships_count": len(memberships),
    }
