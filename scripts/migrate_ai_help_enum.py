"""Migración idempotente: agregar el valor 'help' al enum ai_agent_kind.

¿Por qué existe este script?
- SQLAlchemy `Enum(AgentKind, name="ai_agent_kind")` crea el tipo en
  PostgreSQL con solo los valores que conoce al momento de
  `create_all`. Si el tipo ya existe (deploys previos), `create_all`
  NO lo altera.
- En SQLite, los enums se almacenan como VARCHAR, no requieren migración.

Este script:
1. Detecta el motor (PostgreSQL vs SQLite).
2. En Postgres, hace `ALTER TYPE ai_agent_kind ADD VALUE IF NOT EXISTS 'help'`.
3. Es idempotente: si 'help' ya existe, no hace nada.

Uso:
    python -m scripts.migrate_ai_help_enum
    # o como parte del entrypoint antes de `Base.metadata.create_all`.
"""
from __future__ import annotations

import logging
import os
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("migrate.ai_help")


def _is_postgres(engine) -> bool:
    return engine.dialect.name in ("postgresql", "postgres")


def _enum_values_postgres(conn, enum_name: str) -> set[str]:
    """Devuelve los valores actuales del enum en PostgreSQL."""
    from sqlalchemy import text
    sql = text(
        """
        SELECT e.enumlabel
        FROM pg_type t
        JOIN pg_enum e ON t.oid = e.enumtypid
        WHERE t.typname = :name
        ORDER BY e.enumsortorder
        """
    )
    rows = conn.execute(sql, {"name": enum_name}).fetchall()
    return {r[0] for r in rows}


def run() -> int:
    # Mismo bootstrap que entrypoint.sh
    os.environ.setdefault("APP_ENV", "production")
    from app.database import engine  # noqa: WPS433
    from app.models.ai import AgentKind  # noqa: WPS433

    target_value = AgentKind.HELP.value  # "help"
    enum_name = "ai_agent_kind"

    if not _is_postgres(engine):
        log.info("Motor no es PostgreSQL (es %s). No requiere ALTER TYPE.",
                 engine.dialect.name)
        return 0

    with engine.begin() as conn:
        existing = _enum_values_postgres(conn, enum_name)
        if not existing:
            # El tipo aún no existe. create_all lo creará con todos los
            # valores de AgentKind (incluyendo 'help'). No hacemos nada.
            log.info("Enum %s no existe aún. create_all lo creará completo.",
                     enum_name)
            return 0
        if target_value in existing:
            log.info("Enum %s ya contiene '%s'. Nada que hacer.",
                     enum_name, target_value)
            return 0
        # Postgres requiere que ALTER TYPE ADD VALUE esté fuera de
        # una transacción en algunas versiones. Usamos AUTOCOMMIT.
        from sqlalchemy import text
        conn.execution_options(isolation_level="AUTOCOMMIT")
        try:
            conn.execute(text(
                f"ALTER TYPE {enum_name} ADD VALUE IF NOT EXISTS '{target_value}'"
            ))
            log.info("✔ ALTER TYPE %s ADD VALUE '%s' ejecutado.",
                     enum_name, target_value)
        except Exception as e:  # noqa: BLE001
            log.exception("Error agregando '%s' al enum %s: %s",
                          target_value, enum_name, e)
            return 1
        return 0


if __name__ == "__main__":
    sys.exit(run())
