"""add tenant_site_configs + marketplace tables (idempotente)

Revision ID: 2026_09_27_0001
Revises: f2efb29e03b1
Create Date: 2026-09-27

Contexto
--------
Esta migración cierra tres huecos de esquema detectados en la auditoría del
2026-09-27:

1. ``tenant_site_configs`` — el modelo `TenantSiteConfig` fue eliminado en el
   commit 9163349 ("duplicate table conflict") porque usaba ``site_configs``,
   que colisionaba con la tabla global ``site_config``. El modelo volvió con
   el nombre de tabla ``tenant_site_configs`` (distinto del singular global) y
   este script crea la tabla de verdad. Sin ella, el router
   ``/tenants/{tid}/site-config`` falla en runtime.

2. ``marketplace_plugins`` y ``plugin_subscriptions`` — los modelos existen en
   ``app/models/marketplace.py`` y la versión pre-9163349 ya los creaba con
   ``Base.metadata.create_all()``. En una DB legacy de producción esas dos
   tablas YA EXISTEN; sólo falta ``tenant_site_configs``. Esta migración usa
   ``CREATE TABLE IF NOT EXISTS`` y ``CREATE INDEX IF NOT EXISTS`` para ser
   idempotente: crea lo que falte y respeta lo que ya esté.

3. ``users.default_role`` — el default en el modelo era ``OWNER`` y el registro
   nunca lo asignaba, así que todo usuario autogistrado quedaba con rol de
   plataforma. El fix del modelo está en ``app/models/user.py``; esta
   migración normaliza las filas existentes que quedaron en OWNER sin
   membresía OWNER/ADMIN activa.

FIX 2026-09-29 (producción Railway)
-----------------------------------
La versión anterior usaba ``op.create_table(...)`` (de Alembic) que emite un
``CREATE TABLE`` sin ``IF NOT EXISTS``. Eso falla con
``psycopg.errors.DuplicateTable`` cuando la tabla ya existe — situación
real en Railway, donde ``marketplace_plugins`` y ``plugin_subscriptions``
fueron creadas por el ``create_all()`` de la versión pre-9163349.

La reescritura usa ``op.execute(text("CREATE TABLE IF NOT EXISTS ..."))``
y ``CREATE INDEX IF NOT EXISTS``. Es portable a PostgreSQL y SQLite
(los tests del bootstrap usan SQLite). Alembic trata la ejecución exitosa
como migración aplicada: ``alembic_version`` se actualiza a esta revisión
incluso si las tablas ya existían.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import select, text
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "2026_09_27_0001"
down_revision = "f2efb29e03b1"
branch_labels = None
depends_on = None


# ── Helpers ────────────────────────────────────────────────────────────
# Usamos SQL crudo con IF NOT EXISTS porque Alembic no expone
# ``create_table(if_not_exists=True)`` para PostgreSQL en 1.13.x. Es la
# forma más portable cross-DB. PostgreSQL acepta CREATE TABLE IF NOT EXISTS
# desde 9.1; SQLite desde 3.3.0.
_PG_UUID = "UUID"


def _uuid_type_sql() -> str:
    """Devuelve el tipo de columna para IDs UUID, portable cross-DB.

    PostgreSQL tiene ``UUID`` nativo. SQLite no: ahí las columnas se
    almacenan como TEXT. El ``Base.metadata.create_all`` ya hace esto bien
    (CHAR(36) en SQLite, UUID en Postgres). Como nosotros trabajamos con
    el esquema lógico (lo que la app ve), basta con declarar UUID — el
    dialecto de SQLAlchemy hace la conversión cuando se necesite.

    Para esta migración manual usamos ``UUID`` directamente: el deploy de
    Railway apunta a Postgres, y los tests usan SQLite en cuyo caso
    Alembic interpreta la columna como CHAR(36) automáticamente (es lo que
    hace ``postgresql.UUID(as_uuid=True)`` cuando el dialect es SQLite).
    """
    return _PG_UUID


# ── DDL de las 3 tablas (idempotente) ────────────────────────────────
# Mantenemos los DDL alineados 1-a-1 con lo que declara ``Base.metadata``
# en ``app/models/tenant_site_config.py`` y ``app/models/marketplace.py``
# (verificado durante la auditoría del 2026-09-27). Si esos modelos
# cambian, hay que actualizar este script también.

_DDL_TENANT_SITE_CONFIGS = f"""
CREATE TABLE IF NOT EXISTS tenant_site_configs (
    id {_uuid_type_sql()} NOT NULL,
    tenant_id {_uuid_type_sql()} NOT NULL,
    nombre_sitio VARCHAR(120) NOT NULL DEFAULT '',
    eslogan VARCHAR(200) NOT NULL DEFAULT '',
    logo_url VARCHAR(500) NOT NULL DEFAULT '',
    brand_color VARCHAR(20) NOT NULL DEFAULT '#0f172a',
    mensaje_principal TEXT NOT NULL DEFAULT '',
    imagen_hero_url VARCHAR(500) NOT NULL DEFAULT '',
    bookings_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    orders_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    loyalty_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    public_menu_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    web_booking_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    PRIMARY KEY (id),
    UNIQUE (tenant_id),
    FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE
)
"""

_DDL_MARKETPLACE_PLUGINS = f"""
CREATE TABLE IF NOT EXISTS marketplace_plugins (
    id {_uuid_type_sql()} NOT NULL,
    name VARCHAR(100) NOT NULL,
    slug VARCHAR(100) NOT NULL,
    description TEXT,
    version VARCHAR(20) DEFAULT '1.0.0',
    category VARCHAR(50) NOT NULL,
    pip_package VARCHAR(255),
    git_url VARCHAR(500),
    install_script TEXT,
    config_schema TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    is_featured BOOLEAN NOT NULL DEFAULT FALSE,
    is_paid BOOLEAN DEFAULT FALSE,
    price_monthly_usd INTEGER DEFAULT 0,
    installs INTEGER DEFAULT 0,
    rating INTEGER DEFAULT 0,
    published_by {_uuid_type_sql()},
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    PRIMARY KEY (id),
    UNIQUE (slug)
)
"""

_DDL_PLUGIN_SUBSCRIPTIONS = f"""
CREATE TABLE IF NOT EXISTS plugin_subscriptions (
    id {_uuid_type_sql()} NOT NULL,
    tenant_id {_uuid_type_sql()} NOT NULL,
    plugin_id {_uuid_type_sql()} NOT NULL,
    status VARCHAR(20) DEFAULT 'active',
    config TEXT,
    installed_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    canceled_at TIMESTAMP WITHOUT TIME ZONE,
    revenue_share_70_to_developer BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    PRIMARY KEY (id),
    UNIQUE (tenant_id, plugin_id),
    FOREIGN KEY (tenant_id) REFERENCES tenants(id),
    FOREIGN KEY (plugin_id) REFERENCES marketplace_plugins(id)
)
"""

# Índices — alineados con ``op.create_index`` que usaba la versión previa.
_IDX_STATEMENTS = (
    "CREATE INDEX IF NOT EXISTS ix_tenant_site_configs_tenant_id "
    "ON tenant_site_configs (tenant_id)",
    "CREATE INDEX IF NOT EXISTS ix_marketplace_plugins_slug "
    "ON marketplace_plugins (slug)",
    "CREATE INDEX IF NOT EXISTS ix_marketplace_plugins_category "
    "ON marketplace_plugins (category)",
    "CREATE INDEX IF NOT EXISTS ix_marketplace_plugins_is_active "
    "ON marketplace_plugins (is_active)",
    "CREATE INDEX IF NOT EXISTS ix_plugin_subscriptions_tenant_id "
    "ON plugin_subscriptions (tenant_id)",
    "CREATE INDEX IF NOT EXISTS ix_plugin_subscriptions_plugin_id "
    "ON plugin_subscriptions (plugin_id)",
)


def upgrade() -> None:
    # ── 1. tenant_site_configs ──────────────────────────────
    op.execute(text(_DDL_TENANT_SITE_CONFIGS))

    # ── 2. marketplace_plugins ──────────────────────────────
    op.execute(text(_DDL_MARKETPLACE_PLUGINS))

    # ── 3. plugin_subscriptions ─────────────────────────────
    op.execute(text(_DDL_PLUGIN_SUBSCRIPTIONS))

    # ── 4. índices (idempotentes) ──────────────────────────
    for idx_sql in _IDX_STATEMENTS:
        op.execute(text(idx_sql))

    # ── 5. normalizar default_role de usuarios sin OWNER ──
    # FIX 2026-09-29: la versión anterior usaba `u.id::text` y `is_active = true`
    # en SQL raw, que funciona en PostgreSQL pero rompe en SQLite (driver de
    # tests/CI y desarrollo local). Se reescribe con SQLAlchemy core, que es
    # cross-database. Como `users.id` y `tenant_memberships.user_id` son del
    # mismo tipo (CHAR(36) en SQLite, UUID en Postgres) la comparación directa
    # funciona sin cast.
    bind = op.get_bind()
    users_table = sa.Table("users", sa.MetaData(), autoload_with=bind)
    tm_table = sa.Table("tenant_memberships", sa.MetaData(), autoload_with=bind)

    # Subquery: hay AL MENOS una membresia activa OWNER/ADMIN del usuario?
    has_owner_membership = (
        select(tm_table.c.id)
        .where(
            tm_table.c.user_id == users_table.c.id,
            tm_table.c.is_active.is_(True),
            sa.or_(
                tm_table.c.is_owner.is_(True),
                tm_table.c.role.in_(("OWNER", "ADMIN")),
            ),
        )
        .exists()
    )
    bind.execute(
        sa.update(users_table)
        .where(users_table.c.default_role == "OWNER", ~has_owner_membership)
        .values(default_role="STAFF")
    )


def downgrade() -> None:
    # El downgrade elimina los índices y las tablas. Como pueden estar
    # parcialmente pre-existentes (caso legacy), usamos IF EXISTS.
    for idx in (
        "ix_plugin_subscriptions_plugin_id",
        "ix_plugin_subscriptions_tenant_id",
        "ix_marketplace_plugins_is_active",
        "ix_marketplace_plugins_category",
        "ix_marketplace_plugins_slug",
        "ix_tenant_site_configs_tenant_id",
    ):
        op.execute(text(f"DROP INDEX IF EXISTS {idx}"))

    op.execute(text("DROP TABLE IF EXISTS plugin_subscriptions"))
    op.execute(text("DROP TABLE IF EXISTS marketplace_plugins"))
    op.execute(text("DROP TABLE IF EXISTS tenant_site_configs"))