"""HU_03 — RefreshToken: persistencia y rotación de refresh tokens JWT.

Modelo de seguridad:

  * Cada login/registro emite un refresh token y persiste su SHA-256 hash
    en ``refresh_tokens`` (campo ``token_hash``). El JWT en sí es stateless;
    la fila es la fuente de verdad de validez.
  * ``family_id`` agrupa toda la cadena de rotaciones desde el mismo login
    inicial. Si en algún momento un token ya consumido vuelve a presentarse,
    revocamos TODA la familia (heurística de "token robado" — OWASP).
  * ``replaced_by_id`` apunta al siguiente refresh token en la cadena.
    Permite walk forward (forensics) y walk back (rotación inversa).
  * ``tenant_id`` es el tenant activo al emitir el token (puede ser NULL
    para usuarios sin membresías). Se persiste sólo como contexto histórico
    — la autorización efectiva está en ``TenantMembership``.

Rotación (cada POST /refresh):

  1) Lookup por ``token_hash``.
  2) Si no existe → 401 (token no emitido).
  3) Si ``revoked`` → 401.
  4) Si ``used_at is not None`` (token ya consumido) → REVOCAR FAMILIA
     ENTERA + 401. Caso "token robado" / reuso de token.
  5) Si ``expires_at < now`` → 401.
  6) Si todo OK → marcar ``used_at = now``, emitir nuevo par access+refresh,
     crear nueva fila con ``family_id = anterior.family_id`` y
     ``replaced_by_id`` apuntando a esta nueva fila.
"""
from __future__ import annotations

import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import GUID, BaseModel, TenantMixin


class RefreshTokenRevokeReason(str, enum.Enum):
    """Por qué se revocó un refresh token (o familia completa)."""

    ROTATED = "rotated"               # rotación normal (cuando se reemplaza)
    LOGOUT = "logout"                 # logout explícito del usuario
    STOLEN = "stolen"                 # reuso detectado (OWASP family revoke)
    PASSWORD_CHANGED = "pwd_changed"  # cambio de password (revocar familia)
    ADMIN_REVOKE = "admin_revoke"     # admin forzó cierre de sesión
    REPLACED = "replaced"             # cuando una fila es reemplazada por la siguiente


class RefreshToken(BaseModel, TenantMixin):
    """Refresh tokens persistidos (HU_03).

    Tenant_id es NULLABLE porque un usuario puede no tener membresías
    activas al momento del login — eso no debería impedirle obtener un
    refresh token. La migración refleja esto (igual que HU_40 audit_logs).
    """
    __tablename__ = "refresh_tokens"

    # ── Identidad del token ─────────────────────────────────────────────
    # Hash determinista (SHA-256 hex) del refresh token JWT. NO usamos
    # bcrypt porque necesitamos lookup exacto en DB.
    token_hash: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True,
    )
    # jti claim del JWT — para correlación rápida sin decodificar
    jti: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True,
    )

    # ── Familia de rotación ─────────────────────────────────────────────
    # Todos los refresh tokens rotados desde el mismo login comparten
    # family_id. Si alguno se reusa, revocamos TODA la familia.
    family_id: Mapped[str] = mapped_column(
        GUID(), nullable=False, index=True,
    )
    # Apunta al siguiente refresh token en la cadena (id de la fila que
    # reemplazó a esta). NULL si todavía no fue rotada o si es la actual.
    replaced_by_id: Mapped[Optional[str]] = mapped_column(
        GUID(),
        ForeignKey("refresh_tokens.id", ondelete="SET NULL"),
        nullable=True,
    )

    # ── User ────────────────────────────────────────────────────────────
    user_id: Mapped[str] = mapped_column(
        GUID(),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ── Tenant activo al emitir (NULLABLE — ver docstring) ────────────
    # TenantMixin nos da tenant_id NOT NULL por defecto. Lo anulamos para
    # permitir usuarios sin membresías.
    tenant_id: Mapped[Optional[str]] = mapped_column(
        GUID(),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    # ── Lifecycle ──────────────────────────────────────────────────────
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True,
    )
    # Cuándo se consumió este token (al rotarlo). NULL = aún válido.
    used_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    # Si está revocado (logout, stolen, etc.) antes de su expiración
    revoked: Mapped[bool] = mapped_column(default=False, nullable=False, index=True)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    revoked_reason: Mapped[Optional[str]] = mapped_column(
        String(40), nullable=True,
    )

    # ── Contexto de emisión (forensics) ───────────────────────────────
    user_agent: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    ip: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<RefreshToken id={self.id} user_id={self.user_id} "
            f"family={self.family_id} revoked={self.revoked}>"
        )