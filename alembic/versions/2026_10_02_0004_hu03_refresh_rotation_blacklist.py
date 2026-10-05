"""HU_03 â€” refresh_tokens + token_blacklist.

Revision ID: 2026_10_02_0004
Revises: 2026_10_02_0003
Create Date: 2026-10-02

Contexto
--------
HU_03 endurezió el flujo de auth con tres piezas:

1. **Refresh tokens persistidos con rotación**. Cada ``POST /refresh``
   emite un refresh NUEVO y marca el anterior como ``used_at = now``.
   Si alguien presenta un token ya consumido (``used_at is not null``)
   se revoca la familia entera (heurística OWASP family-revoke).

2. **Blacklist de access tokens**. Cada JWT access lleva un claim
   ``jti`` (UUID v4). En ``POST /logout`` (o admin kill-session)
   se agrega el ``jti`` a ``token_blacklist`` con ``expires_at = exp``.
   ``get_current_user`` consulta la tabla y rechaza tokens revocados
   aunque sean técnicamente válidos.

3. **TTL de access token reducido** (config separado).

Schema
------
* ``refresh_tokens``: 1 fila por refresh token emitido. ``family_id``
  agrupa la cadena de rotaciones desde el mismo login.
* ``token_blacklist``: 1 fila por access token revocado. Cleanup
  recomendado: ``DELETE WHERE expires_at < NOW()``.

Tipos
-----
* ``id UUID`` (no CHAR(32) â€” patrón validado en 2026_09_30_0001).
* FK a ``users.id`` (UUID en PG).
* ``tenant_id UUID NULLABLE`` en ``refresh_tokens`` (un user puede
  no tener membresías activas al autenticarse â€” patrón idéntico a
  HU_40 v1.1 / audit_logs.tenant_id).

Idempotencia
------------
* ``CREATE TABLE IF NOT EXISTS``.
* ``CREATE INDEX IF NOT EXISTS``.
"""
from __future__ import annotations

import logging

from alembic import op
from sqlalchemy import text

revision = "2026_10_02_0004"
down_revision = "2026_10_02_0003"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")


# â”€â”€ DDL validada contra PostgreSQL real de Railway â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
_DDL_REFRESH_TOKENS = """
CREATE TABLE IF NOT EXISTS refresh_tokens (
    id UUID NOT NULL PRIMARY KEY,
    user_id UUID NOT NULL,
    tenant_id UUID,
    token_hash VARCHAR(64) NOT NULL,
    jti VARCHAR(64) NOT NULL,
    family_id UUID NOT NULL,
    replaced_by_id UUID,
    issued_at TIMESTAMP WITH TIME ZONE NOT NULL,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    used_at TIMESTAMP WITH TIME ZONE,
    revoked BOOLEAN NOT NULL DEFAULT FALSE,
    revoked_at TIMESTAMP WITH TIME ZONE,
    revoked_reason VARCHAR(40),
    user_agent VARCHAR(500),
    ip VARCHAR(64),
    note TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_refresh_tokens_user
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT fk_refresh_tokens_tenant
        FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE,
    CONSTRAINT fk_refresh_tokens_replaced_by
        FOREIGN KEY (replaced_by_id) REFERENCES refresh_tokens(id) ON DELETE SET NULL,
    CONSTRAINT uq_refresh_tokens_token_hash UNIQUE (token_hash),
    CONSTRAINT uq_refresh_tokens_jti UNIQUE (jti)
)
"""

_DDL_TOKEN_BLACKLIST = """
CREATE TABLE IF NOT EXISTS token_blacklist (
    id UUID NOT NULL PRIMARY KEY,
    jti VARCHAR(64) NOT NULL,
    user_id UUID,
    token_type VARCHAR(20) NOT NULL DEFAULT 'access',
    revoked_at TIMESTAMP WITH TIME ZONE NOT NULL,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    reason VARCHAR(40) NOT NULL DEFAULT 'logout',
    ip VARCHAR(64),
    user_agent VARCHAR(500),
    note TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_token_blacklist_user
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT uq_token_blacklist_jti UNIQUE (jti)
)
"""

# â”€â”€ Ándices â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
_IDX_REFRESH_USER = (
    "CREATE INDEX IF NOT EXISTS ix_refresh_tokens_user "
    "ON refresh_tokens (user_id)"
)
_IDX_REFRESH_FAMILY = (
    "CREATE INDEX IF NOT EXISTS ix_refresh_tokens_family "
    "ON refresh_tokens (family_id)"
)
_IDX_REFRESH_TENANT = (
    "CREATE INDEX IF NOT EXISTS ix_refresh_tokens_tenant "
    "ON refresh_tokens (tenant_id)"
)
_IDX_REFRESH_EXPIRES = (
    "CREATE INDEX IF NOT EXISTS ix_refresh_tokens_expires "
    "ON refresh_tokens (expires_at)"
)
_IDX_REFRESH_REVOKED = (
    "CREATE INDEX IF NOT EXISTS ix_refresh_tokens_revoked "
    "ON refresh_tokens (revoked)"
)

_IDX_BLACKLIST_JTI_EXP = (
    "CREATE INDEX IF NOT EXISTS ix_token_blacklist_jti_exp "
    "ON token_blacklist (jti, expires_at)"
)
_IDX_BLACKLIST_USER = (
    "CREATE INDEX IF NOT EXISTS ix_token_blacklist_user "
    "ON token_blacklist (user_id, revoked_at)"
)
_IDX_BLACKLIST_EXPIRES = (
    "CREATE INDEX IF NOT EXISTS ix_token_blacklist_expires "
    "ON token_blacklist (expires_at)"
)


def upgrade() -> None:
    """Crea las 2 tablas + 8 índices (todos IF NOT EXISTS, idempotente)."""
    op.execute(text(_DDL_REFRESH_TOKENS))
    op.execute(text(_DDL_TOKEN_BLACKLIST))

    op.execute(text(_IDX_REFRESH_USER))
    op.execute(text(_IDX_REFRESH_FAMILY))
    op.execute(text(_IDX_REFRESH_TENANT))
    op.execute(text(_IDX_REFRESH_EXPIRES))
    op.execute(text(_IDX_REFRESH_REVOKED))

    op.execute(text(_IDX_BLACKLIST_JTI_EXP))
    op.execute(text(_IDX_BLACKLIST_USER))
    op.execute(text(_IDX_BLACKLIST_EXPIRES))

    logger.info(
        "hu03_refresh_rotation_blacklist: 2 tablas + 8 índices creados OK"
    )


def downgrade() -> None:
    """Drop de los índices y las tablas (orden importa por FK)."""
    # Blacklist primero (no depende de refresh_tokens)
    op.execute(text("DROP INDEX IF EXISTS ix_token_blacklist_expires"))
    op.execute(text("DROP INDEX IF EXISTS ix_token_blacklist_user"))
    op.execute(text("DROP INDEX IF EXISTS ix_token_blacklist_jti_exp"))
    op.execute(text("DROP TABLE IF EXISTS token_blacklist"))

    # refresh_tokens después (tiene FK self-referential en replaced_by_id)
    op.execute(text("DROP INDEX IF EXISTS ix_refresh_tokens_revoked"))
    op.execute(text("DROP INDEX IF EXISTS ix_refresh_tokens_expires"))
    op.execute(text("DROP INDEX IF EXISTS ix_refresh_tokens_tenant"))
    op.execute(text("DROP INDEX IF EXISTS ix_refresh_tokens_family"))
    op.execute(text("DROP INDEX IF EXISTS ix_refresh_tokens_user"))
    op.execute(text("DROP TABLE IF EXISTS refresh_tokens"))