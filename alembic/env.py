"""
Alembic env.py — F1.3 (≈ HU_06).

Adaptado del template default de ``alembic init`` para que use:
  - ``app.database.Base.metadata`` como ``target_metadata`` (autogenerate).
  - ``app.config.settings.database_url`` como URL de conexión (respeta
    la misma variable de entorno / .env que el resto del proyecto).

Cualquier modelo nuevo en ``app/models/`` se importará vía
``app.models`` (PEP 562 lazy) para que SQLAlchemy lo registre en
``Base.metadata`` antes del autogenerate.

Modos:
  - Offline: ``alembic upgrade head --sql`` (genera SQL sin conectar).
  - Online: conexión real a la DB definida en ``DATABASE_URL``.
"""
from __future__ import annotations

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import engine_from_config, pool

from alembic import context

# ── Path setup: agregar la raíz del proyecto al sys.path ─────────────────
# Alembic ejecuta este archivo desde /workspace/wowhub, pero si se invoca
# desde otro CWD (e.g. desde un script en scripts/), necesitamos asegurar
# que ``app.*`` sea importable.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


# ── Config object de Alembic ─────────────────────────────────────────────
config = context.config

# Logging — solo si el config file existe (no en tests donde a veces se omite)
if config.config_file_name is not None:
    fileConfig(config.config_file_name)


# ── Override de la URL desde settings ────────────────────────────────────
# Prioridad:
#   1. Variable de entorno DATABASE_URL (si está seteada en el shell).
#   2. ``app.config.settings.database_url`` (Pydantic settings + .env).
# Esto permite que CI y tests overrideen la DB sin tocar el alembic.ini.
def _resolve_database_url() -> str:
    env_url = os.environ.get("DATABASE_URL")
    if env_url:
        return env_url
    from app.config import settings
    return settings.database_url


config.set_main_option("sqlalchemy.url", _resolve_database_url())


# ── Target metadata para autogenerate ────────────────────────────────────
# Importar ``app.models`` y ``app.database`` DESPUÉS de fijar el sys.path
# para evitar ImportError cuando se ejecuta ``alembic`` desde otro CWD.
from app.database import Base  # noqa: E402

# Importar los modelos para que SQLAlchemy los registre en Base.metadata.
# Si añadís un modelo nuevo a ``app/models/``, agregalo al import abajo
# (o importalo explícitamente en tu código antes de correr autogenerate).
import app.models  # noqa: E402,F401
from app.models import (  # noqa: E402,F401
    user, tenant, branch, category, product, customer,
    promotion, qr, landing, order,
    site_config,
    loyalty_pass,
    automation,
    business_costs,
    insumo,
)

target_metadata = Base.metadata


# ── Funciones run_migrations_* (default de Alembic, adaptadas) ───────────


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    Configures the context with just a URL and not an Engine.
    Calls to context.execute() here emit the given string to the
    script output.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        # Útil cuando el schema no es el default ('public')
        # include_schemas=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine and associate
    a connection with the context.
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # render_as_batch=True  # para SQLite ALTER TABLE support
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
