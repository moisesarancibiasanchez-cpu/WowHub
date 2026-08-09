"""Modelo base y mixins compartidos."""
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CHAR, DateTime, TypeDecorator, func
from sqlalchemy.orm import Mapped, mapped_column, declared_attr

from app.database import Base


class GUID(TypeDecorator):
    """Tipo UUID portable:
    - Postgres: usa UUID nativo
    - SQLite: almacena como CHAR(32) (hex sin guiones) y lo convierte
      transparentemente al modelo.
    """
    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            from sqlalchemy.dialects.postgresql import UUID as PG_UUID
            return dialect.type_descriptor(PG_UUID(as_uuid=True))
        return dialect.type_descriptor(CHAR(32))

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        if isinstance(value, UUID):
            uuid_obj = value
        else:
            try:
                uuid_obj = UUID(str(value))
            except (TypeError, ValueError, AttributeError):
                # Si llega un valor no-uuid-like, lo dejamos pasar tal cual;
                # SQLAlchemy reportará el error apropiado.
                return value
        if dialect.name == "postgresql":
            return uuid_obj
        return uuid_obj.hex

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        if isinstance(value, UUID):
            return value
        return UUID(str(value))


class TimestampMixin:
    """created_at / updated_at con default server-side."""
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class BaseModel(Base, TimestampMixin):
    """Modelo base con id UUID v4 y timestamps."""
    __abstract__ = True

    id: Mapped[UUID] = mapped_column(
        GUID(),
        primary_key=True,
        default=uuid4,
        server_default=None,
    )

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} id={self.id}>"


class TenantMixin:
    """Mixin para entidades que pertenecen a un tenant (multi-tenant)."""
    @declared_attr
    def tenant_id(cls):  # noqa: N805
        from sqlalchemy import ForeignKey
        from sqlalchemy import String
        return mapped_column(
            GUID(),
            ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )

