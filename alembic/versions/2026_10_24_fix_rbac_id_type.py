"""FIX — alinear el tipo de ``rbac_policies`` / ``rbac_groupings`` con el ORM.

Revision ID: 2026_10_24_fix_rbac_id_type
Revises: 2026_10_23_fix_enum_labels
Create Date: 2026-10-24

Contexto
--------
El botón "⚡ Recalcular RFM" del dashboard respondía HTTP 403::

    Permiso denegado: role:OWNER no puede 'write' sobre 'customer'

    POST /api/v1/tenants/{tenant_id}/customers/rfm/recalculate

El usuario es OWNER del tenant, así que el permiso debería existir. La
causa raíz NO está en la matriz de permisos sino en el ESQUEMA:

``alembic/versions/2026_09_30_0003_rbac_casbin.py`` creó las dos tablas con
DDL crudo::

    CREATE TABLE IF NOT EXISTS rbac_policies (
        id CHAR(32) NOT NULL PRIMARY KEY,
        created_at TIMESTAMP NOT NULL,
        ...
    )

Pero el ORM no usa CHAR(32) en PostgreSQL:

- ``app/models/base.py`` define ``GUID``, un ``TypeDecorator`` que en
  PostgreSQL se materializa como **UUID nativo** y que
  ``process_bind_param`` devuelve como ``uuid.UUID``.
- ``TimestampMixin`` declara ``server_default=func.now()`` para
  ``created_at`` / ``updated_at``, pero el DDL crudo los creó NOT NULL
  **sin DEFAULT**.

Resultado en la DB de producción (PostgreSQL):

1. El INSERT del seed intenta escribir un UUID nativo en una columna
   ``char(32)`` → ``column "id" is of type character but expression is of
   type uuid``.
2. Además, ``created_at`` es NOT NULL sin DEFAULT y el INSERT del ORM la
   omite (SQLAlchemy confía en el ``server_default``) → violación de
   NOT NULL.

Ambos errores abortan la transacción, así que **las N policies se
revierten juntas**: la tabla ``rbac_policies`` queda VACÍA. Casbin no
entrega ninguna policy al enforcer y ``enforce()`` devuelve False para
todos los roles → HTTP 403 en los 26 endpoints protegidos por
``requires_permission`` (clientes, productos, pedidos, promociones,
categorías, sucursales, pagos, producción, RFM...).

El único que escapaba era ``superadmin`` (tiene su propio bypass).

Fix (ADITIVO, idempotente, NO destructivo)
-------------------------------------------
- ``rbac_policies.id`` y ``rbac_groupings.id``: ``CHAR(32)`` → ``uuid``.
  La conversión usa el cast de entrada de PostgreSQL, que acepta tanto
  la forma con guiones como los 32 hex sin guiones; ``rtrim`` quita el
  relleno de ``CHAR``.
- ``created_at`` / ``updated_at``: ``SET DEFAULT now()`` para que coincidan
  con el ``server_default`` del modelo.

Ningún DROP, ningún borrado de filas, ninguna pérdida de datos: sólo se
alinea el tipo y el default de columnas existentes.

Idempotencia
------------
Antes de alterar nada se consulta el tipo real y el default real de cada
columna (``information_schema.columns``). Si ya son correctos, no se hace
nada. La migración se puede aplicar las veces que haga falta.

Reversible
----------
El ``downgrade`` es un no-op documentado: volver a ``CHAR(32)`` restauraría
exactamente el estado roto que hace que el seed falle y que Casbin
deniegue todo. Es un cambio de tipo, no un borrado de datos, pero
deshacerlo solo puede empeorar el sistema.
"""
from __future__ import annotations

import logging

from alembic import op
from sqlalchemy import text

revision = "2026_10_24_fix_rbac_id_type"
down_revision = "2026_10_23_fix_enum_labels"
branch_labels = None
depends_on = None


logger = logging.getLogger("alembic.runtime.migration")


TABLES: tuple[str, ...] = ("rbac_policies", "rbac_groupings")
TIMESTAMP_COLUMNS: tuple[str, ...] = ("created_at", "updated_at")


def _column_type(bind, table: str, column: str) -> str | None:
    """Tipo real de la columna (``None`` si no existe la columna)."""
    row = bind.execute(
        text(
            """
            SELECT data_type
            FROM information_schema.columns
            WHERE table_name = :t AND column_name = :c
            """
        ),
        {"t": table, "c": column},
    ).first()
    return row[0] if row else None


def _column_length(bind, table: str, column: str) -> int | None:
    """Longitud del tipo de la columna (``None`` si no aplica)."""
    row = bind.execute(
        text(
            """
            SELECT character_maximum_length
            FROM information_schema.columns
            WHERE table_name = :t AND column_name = :c
            """
        ),
        {"t": table, "c": column},
    ).first()
    return row[0] if row else None


def _column_has_default(bind, table: str, column: str) -> bool:
    """True si la columna tiene DEFAULT en la DB."""
    row = bind.execute(
        text(
            """
            SELECT column_default
            FROM information_schema.columns
            WHERE table_name = :t AND column_name = :c
            """
        ),
        {"t": table, "c": column},
    ).first()
    return bool(row and row[0])


def upgrade() -> None:
    """Alinea ``id`` a uuid y agrega los DEFAULT de los timestamps."""
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        # En SQLite el propio ORM usa CHAR(32) para GUID: no hay drift.
        logger.info("SQLite: GUID ya es CHAR(32) — no-op")
        return

    for table in TABLES:
        if bind.execute(
            text(
                """
                SELECT 1 FROM information_schema.tables
                WHERE table_name = :t
                """
            ),
            {"t": table},
        ).first() is None:
            logger.info("%s: la tabla no existe — se omite", table)
            continue

        # ── 1. id: CHAR(32) → uuid ───────────────────────────────────────
        data_type = _column_type(bind, table, "id")
        length = _column_length(bind, table, "id")
        if data_type is None:
            logger.info("%s.id: no existe — se omite", table)
        elif data_type == "uuid":
            logger.info("%s.id: ya es uuid — OK", table)
        elif data_type in ("character", "character varying") and length == 32:
            op.execute(
                text(
                    f'ALTER TABLE "{table}" ALTER COLUMN "id" TYPE uuid '
                    f'USING rtrim("id")::uuid'
                )
            )
            logger.info("%s.id: CHAR(32) → uuid OK", table)
        else:
            logger.warning(
                "%s.id: tipo %s(%s) inesperado — no se toca", table, data_type, length
            )

        # ── 2. created_at / updated_at: DEFAULT now() ────────────────────
        for column in TIMESTAMP_COLUMNS:
            if _column_type(bind, table, column) is None:
                continue
            if _column_has_default(bind, table, column):
                logger.info("%s.%s: ya tiene DEFAULT — OK", table, column)
                continue
            op.execute(
                text(
                    f'ALTER TABLE "{table}" ALTER COLUMN "{column}" '
                    f"SET DEFAULT now()"
                )
            )
            logger.info("%s.%s: DEFAULT now() agregado", table, column)


def downgrade() -> None:
    """No-op documentado.

    Revertir el tipo de ``id`` a ``CHAR(32)`` restauraría el estado roto:
    el seed de policies volvería a fallar y Casbin volvería a denegar
    todas las operaciones a todos los roles. No es un borrado de datos,
    pero deshacerlo solo puede empeorar el sistema.
    """
    logger.warning(
        "downgrade no implementado: revertir 'id' a CHAR(32) reintroduciría "
        "el fallo del seed de RBAC y los 403 de permisos."
    )
