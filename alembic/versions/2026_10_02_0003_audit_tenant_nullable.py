"""HU_40 v1.1 — audit_logs.tenant_id NULLABLE para eventos de sistema.

Revision ID: 2026_10_02_0003
Revises: 2026_10_02_0002
Create Date: 2026-10-02

Contexto
--------
HU_40 inicial asume que todo audit log pertenece a un tenant. Esto funciona
para impersonación de superadmin (siempre hay tenant del impersonated user),
pero NO cubre eventos globales del sistema:

  - ``auth.register`` sin ``create_tenant`` (no hay tenant todavía)
  - ``auth.login`` de un user sin membresías activas (no hay tenant actual)
  - ``auth.logout`` (token ya fue descartado, no hay tenant)
  - ``auth.password_forgot`` (request anónimo, no hay tenant)
  - ``auth.password_reset`` (token one-shot, no hay sesión)
  - ``auth.email_verified`` (no hay sesión)
  - ``auth.email_verification_sent`` (no hay sesión)

Cambio
------
``ALTER TABLE audit_logs ALTER COLUMN tenant_id DROP NOT NULL``.

Idempotencia
------------
- PG: ``ALTER COLUMN ... DROP NOT NULL`` es idempotente (segunda corrida
  no falla, sólo re-aplica la constraint ``NOT NULL`` que ya no existe).
- SQLite: SQLite NO soporta ``DROP NOT NULL`` directamente. El path es
  recreate-table. Sin embargo, en SQLite el modelo actual de tests ya
  crea la columna como nullable (el ``Base.metadata.create_all`` lee el
  schema del modelo, no de una migración previa). Por lo tanto, la rama
  SQLite es un no-op (la columna ya es nullable en el schema recreado).

Migración de datos
------------------
No requiere backfill: las filas existentes tienen ``tenant_id NOT NULL``
y siguen siendo válidas; sólo permitimos NULL para nuevos inserts.
"""
from __future__ import annotations

import logging

from alembic import op
from sqlalchemy import text

revision = "2026_10_02_0003"
down_revision = "2026_10_02_0002"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(text("ALTER TABLE audit_logs ALTER COLUMN tenant_id DROP NOT NULL"))
        logger.info("audit_tenant_nullable: tenant_id es NULLABLE en PostgreSQL")
        return
    # SQLite: la columna ya se crea NULLABLE en tests (Base.metadata.create_all
    # usa el schema Python). En runtime, los deployments con SQLite son de
    # testing — el path producción es PG.
    logger.info(
        "audit_tenant_nullable: dialect=%s — no se aplica DROP NOT NULL "
        "(SQLite tests crean la columna con el schema Python directamente)",
        bind.dialect.name,
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        # No podemos volver a NOT NULL si ya hay filas con NULL. Si la tabla
        # está vacía o no tiene NULL, el ALTER funciona. Si tiene NULL,
        # falla — el caller debe limpiar primero.
        try:
            op.execute(text("ALTER TABLE audit_logs ALTER COLUMN tenant_id SET NOT NULL"))
            logger.info("audit_tenant_nullable.downgrade: tenant_id es NOT NULL")
        except Exception as exc:
            logger.warning(
                "audit_tenant_nullable.downgrade: no se pudo volver a NOT NULL "
                "(probablemente hay filas con tenant_id NULL): %s",
                exc,
            )