"""Tenant: el "negocio" o "cuenta" SaaS. Contiene todos los datos de un cliente
de WowHub. Tiene muchas membresías, branches, productos, etc."""
import enum
from typing import Optional

from sqlalchemy import Boolean, Enum, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel
from app.models.user import UserRole
from sqlalchemy.dialects.postgresql import UUID
import uuid


class TenantPlan(str, enum.Enum):
    FREE = "free"
    GROW = "grow"
    PRO = "pro"
    BUSINESS = "business"


class TenantStatus(str, enum.Enum):
    TRIAL = "trial"
    ACTIVE = "active"
    PAST_DUE = "past_due"
    CANCELED = "canceled"
    SUSPENDED = "suspended"


class Industry(str, enum.Enum):
    GASTRO = "gastro"               # restaurantes, cafeterías
    RETAIL = "retail"               # tiendas, boutiques
    SERVICES = "services"           # peluquerías, talleres
    BEAUTY = "beauty"               # salones de belleza, estética
    EDUCATION = "education"         # academias, clases
    HEALTH = "health"               # consultas, kinesiología
    OTHER = "other"


class Tenant(BaseModel):
    __tablename__ = "tenants"

    slug: Mapped[str] = mapped_column(String(60), unique=True, nullable=False, index=True)
    legal_name: Mapped[str] = mapped_column(String(200), nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    industry: Mapped[Industry] = mapped_column(
        Enum(Industry, name="industry"),
        default=Industry.OTHER,
        nullable=False,
        index=True,
    )
    plan: Mapped[TenantPlan] = mapped_column(
        Enum(TenantPlan, name="tenant_plan"),
        default=TenantPlan.FREE,
        nullable=False,
    )
    status: Mapped[TenantStatus] = mapped_column(
        Enum(TenantStatus, name="tenant_status"),
        default=TenantStatus.TRIAL,
        nullable=False,
        index=True,
    )
    country: Mapped[str] = mapped_column(String(2), default="CL", nullable=False)  # ISO-3166-1 alpha-2
    locale: Mapped[str] = mapped_column(String(8), default="es-CL", nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="CLP", nullable=False)
    timezone: Mapped[str] = mapped_column(String(60), default="America/Santiago", nullable=False)

    # Métricas de salud (desnormalizadas para dashboards)
    wow_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    health_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    active_branches: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Configuración libre (JSON) — extensible
    settings: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    memberships: Mapped[list["TenantMembership"]] = relationship(  # noqa: F821
        back_populates="tenant",
        cascade="all, delete-orphan",
    )
    branches: Mapped[list["Branch"]] = relationship(  # noqa: F821
        back_populates="tenant",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Tenant {self.slug}>"


class TenantMembership(BaseModel):
    """Relación User <-> Tenant con un rol específico."""
    __tablename__ = "tenant_memberships"
    __table_args__ = (
        # Un user no puede tener dos membresías al mismo tenant
        # (lo manejamos con UniqueConstraint via service)
    )

user_id: Mapped[uuid.UUID] = mapped_column(
    UUID(as_uuid=True),
    ForeignKey("users.id", ondelete="CASCADE"),
    nullable=False,
    index=True,
)
tenant_id: Mapped[uuid.UUID] = mapped_column(
    UUID(as_uuid=True),
    ForeignKey("tenants.id", ondelete="CASCADE"),
    nullable=False,
    index=True,
)

    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="membership_role"),
        default=UserRole.STAFF,
        nullable=False,
    )
    is_owner: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    
    # invited_by: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    invited_by: Mapped[Optional[uuid.UUID]] = mapped_column(
    UUID(as_uuid=True),
    nullable=True,
)
    last_login_at: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)

    user: Mapped["User"] = relationship(  # noqa: F821
        back_populates="memberships",
    )
    tenant: Mapped["Tenant"] = relationship(  # noqa: F821
        back_populates="memberships",
    )
