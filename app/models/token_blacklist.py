"""HU_03 — TokenBlacklist: revocación de access tokens JWT.

Limitaciones del modelo:

  * JWT es stateless — sin blacklist, un token robado es válido hasta ``exp``.
  * Para revocación inmediata (logout, admin kill-session) necesitamos una
    fuente de verdad centralizada: este modelo.
  * Las filas tienen ``expires_at`` igual al ``exp`` del JWT. Una vez
    pasado ese momento la fila puede purgarse sin perder nada (el JWT ya
    está expirado y ``jwt.decode`` lo rechazaría de todas formas).

Estrategia de limpieza:

  * Recomendamos un cron diario que ejecute
    ``DELETE FROM token_blacklist WHERE expires_at < NOW()``
    para mantener la tabla pequeña. En V0.2.1 esto queda como TODO
    operacional; la lógica de la app filtra por ``expires_at`` así que
    aunque la tabla crezca, la verificación sigue siendo O(log N) por ``jti``.

Verificación:

  * ``get_current_user`` (deps.py) hace una sola query:
    ``SELECT 1 FROM token_blacklist WHERE jti = :jti AND expires_at > now()``
    Si encuentra fila → 401.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import GUID, BaseModel


class TokenBlacklist(BaseModel):
    """Access tokens JWT revocados antes de su expiración natural (HU_03).

    NO usa TenantMixin (es cross-tenant por naturaleza — un user de varios
    tenants puede revocar su sesión sin importar a qué tenant pertenezca).

    IMPORTANTE: el índice compuesto ``ix_token_blacklist_jti_exp`` ya
    cubre la columna ``jti`` (prefijo izquierdo). NO agregamos un
    índice separado en ``jti`` para evitar duplicación que rompe
    ``create_all`` (SQLite rechaza nombres duplicados).
    """
    __tablename__ = "token_blacklist"
    __table_args__ = (
        # El índice compuesto cubre ``jti`` (prefijo izquierdo) y ``expires_at``.
        # Usado por ``_is_jti_blacklisted`` en deps.py.
        Index("ix_token_blacklist_jti_exp", "jti", "expires_at"),
        Index("ix_token_blacklist_user", "user_id", "revoked_at"),
        Index("ix_token_blacklist_expires", "expires_at"),
    )

    # jti claim del JWT revocado (único por token)
    jti: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False,
    )

    # user_id (para audit + forensics)
    user_id: Mapped[Optional[str]] = mapped_column(
        GUID(),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
    )

    # Tipo de token revocado (siempre 'access' hoy;预留 para futuro 'refresh' si lo movemos)
    token_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="access",
    )

    # Cuándo y por qué
    revoked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
    )
    # ``exp`` del JWT — las filas pueden purgarse después de este momento.
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
    )
    reason: Mapped[str] = mapped_column(
        String(40), nullable=False, default="logout",
    )

    # Contexto opcional
    ip: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<TokenBlacklist jti={self.jti} reason={self.reason}>"