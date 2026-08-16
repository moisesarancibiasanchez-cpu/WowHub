"""AuthService — registro, login, refresh, cambio de tenant activo."""
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import (
    ConflictError, NotFoundError, UnauthorizedError, ForbiddenError,
)
from app.models.tenant import Industry, Tenant, TenantMembership, TenantStatus
from app.models.user import User, UserRole
from app.schemas.auth import UserCreate
from app.security import (
    create_access_token, create_refresh_token, decode_token,
    hash_password, verify_password,
)
from app.config import settings


class AuthService:
    def __init__(self, db: Session):
        self.db = db

    # ── Registro ────────────────────────────────────────
    def register(self, payload: UserCreate) -> tuple[User, Optional[Tenant], TenantMembership]:
        # 1) Verificar email único
        existing = self.db.execute(
            select(User).where(User.email == payload.email.lower())
        ).scalar_one_or_none()
        if existing:
            raise ConflictError("Email ya registrado")

        # 2) Crear user
        user = User(
            email=payload.email.lower(),
            password_hash=hash_password(payload.password),
            full_name=payload.full_name,
            phone=payload.phone,
        )
        self.db.add(user)
        self.db.flush()

        # 3) Crear tenant si corresponde
        tenant: Optional[Tenant] = None
        membership: Optional[TenantMembership] = None

        if payload.create_tenant:
            if not payload.tenant_slug or not payload.tenant_legal_name:
                raise ConflictError("create_tenant=true requiere tenant_slug y tenant_legal_name")
            # slug único
            slug_taken = self.db.execute(
                select(Tenant).where(Tenant.slug == payload.tenant_slug)
            ).scalar_one_or_none()
            if slug_taken:
                raise ConflictError(f"slug '{payload.tenant_slug}' ya existe")

            tenant = Tenant(
                slug=payload.tenant_slug,
                legal_name=payload.tenant_legal_name,
                display_name=payload.tenant_legal_name,
                industry=Industry(payload.tenant_industry) if payload.tenant_industry else Industry.OTHER,
                status=TenantStatus.TRIAL,
            )
            self.db.add(tenant)
            self.db.flush()

            membership = TenantMembership(
                user_id=str(user.id),
                tenant_id=str(tenant.id),
                role=UserRole.OWNER,
                is_owner=True,
                is_active=True,
            )
            self.db.add(membership)
        try:
            self.db.commit()
        except IntegrityError as e:
            self.db.rollback()
            raise ConflictError(f"Conflicto de integridad: {e.orig}") from e

        self.db.refresh(user)
        if tenant:
            self.db.refresh(tenant)
        if membership:
            self.db.refresh(membership)
        return user, tenant, membership

    # ── Login ───────────────────────────────────────────
    def login(self, email: str, password: str) -> tuple[User, Optional[TenantMembership], list[TenantMembership]]:
        user = self.db.execute(
            select(User).where(User.email == email.lower())
        ).scalar_one_or_none()
        if not user or not user.is_active:
            raise UnauthorizedError("Credenciales inválidas")
        if not verify_password(password, user.password_hash):
            raise UnauthorizedError("Credenciales inválidas")

        memberships = list(
            self.db.execute(
                select(TenantMembership).where(
                    TenantMembership.user_id == str(user.id),
                    TenantMembership.is_active == True,  # noqa: E712
                )
            ).scalars()
        )
        if not memberships:
            return user, None, []

        # Por default el primer OWNER, o el primero
        current = next((m for m in memberships if m.is_owner), memberships[0])
        current.last_login_at = datetime.now(timezone.utc).isoformat()
        self.db.commit()
        return user, current, memberships

    # ── Refresh ─────────────────────────────────────────
    def refresh(self, refresh_token: str) -> tuple[User, Optional[TenantMembership]]:
        try:
            payload = decode_token(refresh_token)
        except ValueError as e:
            raise UnauthorizedError(str(e))
        if payload.get("type") != "refresh":
            raise UnauthorizedError("Token inválido (no es refresh)")
        user_id = payload.get("sub")
        user = self.db.get(User, UUID(user_id))
        if not user or not user.is_active:
            raise UnauthorizedError("Usuario no encontrado")
        # mantener tenant activo
        tid = payload.get("tid")
        current = None
        if tid:
            current = self.db.execute(
                select(TenantMembership).where(
                    TenantMembership.user_id == str(user.id),
                    TenantMembership.tenant_id == str(tid),
                )
            ).scalar_one_or_none()
        return user, current

    # ── Switch tenant ───────────────────────────────────
    def switch_tenant(self, user: User, tenant_id: UUID) -> TenantMembership:
        m = self.db.execute(
            select(TenantMembership).where(
                TenantMembership.user_id == str(user.id),
                TenantMembership.tenant_id == str(tenant_id),
                TenantMembership.is_active == True,  # noqa: E712
            )
        ).scalar_one_or_none()
        if not m:
            raise ForbiddenError("No tienes acceso a este tenant")
        return m

    # ── Tokens ──────────────────────────────────────────
    def issue_tokens(self, user: User, current: Optional[TenantMembership]) -> tuple[str, str, int]:
        if current and current.tenant_id is not None:
            tid = current.tenant_id
            tenant_id = tid if isinstance(tid, UUID) else UUID(str(tid))
        else:
            tenant_id = None
        role = current.role.value if current else user.default_role.value
        # SUPERADMIN: incluimos is_superuser como claim del access token
        # para que `require_superuser` no necesite consultar la BD.
        access = create_access_token(
            user.id,
            tenant_id=tenant_id,
            role=role,
            extra_claims={"is_superuser": bool(getattr(user, "is_superuser", False))},
        )
        refresh = create_refresh_token(user.id)
        # Reusar info del tenant en el refresh para mantener contexto tras refresh
        if current:
            from app.security import jwt
            from datetime import timedelta
            # regenerar refresh con tid + is_superuser
            now = datetime.now(timezone.utc)
            payload = {
                "sub": str(user.id),
                "tid": str(current.tenant_id),
                "role": current.role.value,
                "is_superuser": bool(getattr(user, "is_superuser", False)),
                "iat": int(now.timestamp()),
                "exp": int((now + timedelta(days=settings.jwt_refresh_ttl_days)).timestamp()),
                "type": "refresh",
            }
            refresh = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
        ttl = settings.jwt_access_ttl_minutes * 60
        return access, refresh, ttl
