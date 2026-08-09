"""AuditLog: registro inmutable de acciones para compliance y debugging."""
from typing import Optional

from sqlalchemy import JSON, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel, TenantMixin


class AuditLog(BaseModel, TenantMixin):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_tenant_action", "tenant_id", "action"),
        Index("ix_audit_tenant_actor", "tenant_id", "actor_user_id"),
        Index("ix_audit_tenant_created", "tenant_id", "created_at"),
    )

    actor_user_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    actor_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    action: Mapped[str] = mapped_column(String(80), nullable=False)  # user.login, product.create, etc.
    resource_type: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)  # product, order, etc.
    resource_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)

    method: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    ip: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    status_code: Mapped[Optional[int]] = mapped_column(String(4), nullable=True)
    extra: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
