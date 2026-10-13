"""HU_45 — Plugin runtime: columnas ``install_log`` y ``hooks``.

Revision ID: 2026_10_07_0002
Revises: 2026_10_07_0001
Create Date: 2026-10-07

Contexto
--------
Hasta ahora ``install_script`` y ``config_schema`` se almacenaban en
``marketplace_plugins`` pero nunca se ejecutaban ni validaban. Esta
migración agrega dos columnas a ``plugin_subscriptions`` para soportar
el runtime:

  - ``install_log TEXT NULL`` — JSON con el resultado de la última
    ejecución de ``install_script`` (output, error, duration_ms,
    hooks_count). Se actualiza en cada install/reinstall.

  - ``hooks TEXT NULL`` — JSON: ``{event_name: source_code}`` mapea
    cada evento del ciclo de vida (p.ej. ``on_order_created``) al
    source del hook registrado por el plugin. El dispatcher
    (``app/services/plugin_hooks.py``) compila + ejecuta este source
    cuando se dispara el evento.

Idempotencia cross-DB
---------------------
Mismo patrón que ``2026_10_07_0001`` (RFM):
  - PostgreSQL: ``ALTER TABLE ... ADD COLUMN IF NOT EXISTS`` (PG 9.6+).
  - SQLite: try/except silencioso porque ``ALTER TABLE ADD COLUMN``
    NO soporta ``IF NOT EXISTS``.

Ambas columnas son ``NULL`` (sin default) porque:
  - Para tenants existentes sin install_script en su plugin, el log
    queda en NULL hasta el primer install/reinstall.
  - Para tenants con plugins sin hooks, ``hooks`` queda en NULL.

Tipos alineados con ``app/models/marketplace.py``: ``Text`` (sin
límite duro, los hooks pueden ser medianos).
"""
from __future__ import annotations

import logging

from alembic import op
from sqlalchemy import text
from sqlalchemy.exc import OperationalError, ProgrammingError

logger = logging.getLogger("alembic.runtime.migration")

revision = "2026_10_07_0002"
down_revision = "2026_10_07_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    # ── install_log ──────────────────────────────────────────────────────────
    if dialect == "postgresql":
        op.execute(text(
            "ALTER TABLE plugin_subscriptions "
            "ADD COLUMN IF NOT EXISTS install_log TEXT"
        ))
    else:
        try:
            op.execute(text(
                "ALTER TABLE plugin_subscriptions ADD COLUMN install_log TEXT"
            ))
        except (OperationalError, ProgrammingError) as e:
            logger.info(
                "plugin_subscriptions.install_log ya existe o no se pudo "
                "agregar (esperado en SQLite con tabla legacy): %s", e,
            )

    # ── hooks ───────────────────────────────────────────────────────────────
    if dialect == "postgresql":
        op.execute(text(
            "ALTER TABLE plugin_subscriptions "
            "ADD COLUMN IF NOT EXISTS hooks TEXT"
        ))
    else:
        try:
            op.execute(text(
                "ALTER TABLE plugin_subscriptions ADD COLUMN hooks TEXT"
            ))
        except (OperationalError, ProgrammingError) as e:
            logger.info(
                "plugin_subscriptions.hooks ya existe o no se pudo "
                "agregar (esperado en SQLite con tabla legacy): %s", e,
            )


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == "postgresql":
        op.execute(text(
            "ALTER TABLE plugin_subscriptions "
            "DROP COLUMN IF EXISTS hooks"
        ))
        op.execute(text(
            "ALTER TABLE plugin_subscriptions "
            "DROP COLUMN IF EXISTS install_log"
        ))
    else:
        for col in ("install_log", "hooks"):
            try:
                op.execute(text(
                    f"ALTER TABLE plugin_subscriptions DROP COLUMN {col}"
                ))
            except (OperationalError, ProgrammingError) as e:
                logger.info(
                    "plugin_subscriptions.%s no se pudo quitar: %s", col, e,
                )