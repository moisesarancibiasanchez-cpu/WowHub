"""TenantService — gestión de tenants y membresías."""
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError
from app.models.tenant import Tenant, TenantMembership
from app.models.user import User, UserRole
from app.schemas.tenant import TenantCreate, TenantUpdate, TenantMembershipCreate, TenantMembershipUpdate


class TenantService:
    def __init__(self, db: Session):
        self.db = db

    def create(self, owner: User, payload: TenantCreate) -> Tenant:
        # slug único
        existing = self.db.execute(
            select(Tenant).where(Tenant.slug == payload.slug)
        ).scalar_one_or_none()
        if existing:
            raise ConflictError(f"slug '{payload.slug}' ya existe")

        tenant = Tenant(**payload.model_dump())
        self.db.add(tenant)
        self.db.flush()

        # Membresía owner
        m = TenantMembership(
            user_id=str(owner.id),
            tenant_id=str(tenant.id),
            role=UserRole.OWNER,
            is_owner=True,
            is_active=True,
        )
        self.db.add(m)
        self.db.commit()
        self.db.refresh(tenant)
        return tenant

    def get(self, tenant_id: UUID) -> Tenant:
        t = self.db.get(Tenant, tenant_id)
        if not t:
            raise NotFoundError("Tenant")
        return t

    def get_by_slug(self, slug: str) -> Tenant:
        t = self.db.execute(
            select(Tenant).where(Tenant.slug == slug)
        ).scalar_one_or_none()
        if not t:
            raise NotFoundError("Tenant")
        return t

    def update(self, tenant: Tenant, payload: TenantUpdate) -> Tenant:
        data = payload.model_dump(exclude_unset=True)
        for k, v in data.items():
            setattr(tenant, k, v)
        self.db.commit()
        self.db.refresh(tenant)
        return tenant

    # ── Membresías ─────────────────────────────────────
    def list_members(self, tenant: Tenant) -> list[TenantMembership]:
        return list(self.db.execute(
            select(TenantMembership).where(TenantMembership.tenant_id == str(tenant.id))
        ).scalars())

    def add_member(
        self, tenant: Tenant, payload: TenantMembershipCreate
    ) -> TenantMembership:
        # Resolver user
        user: Optional[User] = None
        if payload.user_id:
            user = self.db.get(User, payload.user_id)
        elif payload.email:
            user = self.db.execute(
                select(User).where(User.email == payload.email.lower())
            ).scalar_one_or_none()
        if not user:
            raise NotFoundError("Usuario a invitar")
        # ¿ya es miembro?
        existing = self.db.execute(
            select(TenantMembership).where(
                TenantMembership.user_id == str(user.id),
                TenantMembership.tenant_id == str(tenant.id),
            )
        ).scalar_one_or_none()
        if existing:
            raise ConflictError("El usuario ya es miembro del tenant")
        m = TenantMembership(
            user_id=str(user.id),
            tenant_id=str(tenant.id),
            role=payload.role,
            is_owner=False,
            is_active=True,
        )
        self.db.add(m)
        self.db.commit()
        self.db.refresh(m)
        return m

    def update_member(
        self, tenant: Tenant, membership_id: UUID, payload: TenantMembershipUpdate
    ) -> TenantMembership:
        m = self.db.get(TenantMembership, membership_id)
        if not m or m.tenant_id != tenant.id:
            raise NotFoundError("Membresía")
        if m.is_owner and payload.role and payload.role != UserRole.OWNER:
            raise ConflictError("No se puede cambiar el rol del owner")
        if payload.role is not None:
            m.role = payload.role
        if payload.is_active is not None:
            m.is_active = payload.is_active
        self.db.commit()
        self.db.refresh(m)
        return m
