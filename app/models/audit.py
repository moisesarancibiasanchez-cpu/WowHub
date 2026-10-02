"""AuditLog: registro inmutable de acciones para compliance y debugging."""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import GUID, BaseModel, TenantMixin


def _utcnow_microsecond() -> datetime:
    """Default Python-side para ``created_at`` con precisión de microsegundo.

    Heredamos ``TimestampMixin.created_at`` con ``server_default=func.now()``,
    pero eso da precisión de **segundo** en SQLite (``CURRENT_TIMESTAMP``),
    lo que rompe el orden del hash chain cuando hay varios inserts en el
    mismo segundo (p.ej. tests, webhooks en ráfaga). En PostgreSQL
    ``func.now()`` ya devuelve microsegundos, pero tener el default
    Python-side hace el comportamiento uniforme y robusto entre dialectos.

    El modelo sigue aceptando ``server_default`` para migraciones existentes
    en PG (el default Python toma precedencia al hacer INSERT desde la app).
    """
    return datetime.now(timezone.utc)


class AuditLog(BaseModel, TenantMixin):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_tenant_action", "tenant_id", "action"),
        Index("ix_audit_tenant_actor", "tenant_id", "actor_user_id"),
        Index("ix_audit_tenant_created", "tenant_id", "created_at"),
        # HU_40 — hash chain: walk cronológico para verify-chain.
        Index("ix_audit_tenant_created_id", "tenant_id", "created_at", "id"),
        Index("ix_audit_prev_hash", "prev_hash"),
        Index("ix_audit_current_hash", "current_hash"),
    )

    # HU_40 — created_at con default Python-side microsegundo (ver docstring).
    # Sobrescribe el server_default heredado de TimestampMixin sólo para esta
    # tabla; el resto de modelos sigue usando ``func.now()``.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow_microsecond,
        server_default=func.now(),
        nullable=False,
    )

    # HU_40 v1.1 (2026-10-02) — ``tenant_id`` es NULLABLE para auditoría de
    # eventos de sistema que no pertenecen a ningún tenant (login, logout,
    # password reset, email verification, register sin ``create_tenant``).
    # Mantenemos la FK a ``tenants.id`` y el index para queries cross-tenant.
    # El superadmin list query usa ``tenant_id IS NULL OR tenant_id = X``
    # para incluir eventos globales. La migración de NOT NULL → NULL se
    # gestiona en la migración ``2026_10_02_0003_audit_tenant_nullable``.
    tenant_id: Mapped[Optional[str]] = mapped_column(
        GUID(),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
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

    # ── HU_40 — Hash Chain (SHA-256) ────────────────────────────────
    # ``prev_hash``    = hash del registro anterior en la cadena (o "" para
    #                    el primer registro). Cadena por tenant.
    # ``current_hash`` = SHA-256(prev_hash || canonical_json(payload)).
    # Si el cálculo del hash falla, ambos quedan en NULL (ver ``audit_service.log``)
    # y la cadena puede regenerarse con ``POST /api/v1/audit/backfill-chain``.
    prev_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    current_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
