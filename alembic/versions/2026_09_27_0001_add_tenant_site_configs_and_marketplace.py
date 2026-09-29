"""add tenant_site_configs + marketplace tables

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
   ``app/models/marketplace.py`` pero NO estaban en la migración inicial, por
   lo que ``alembic upgrade head`` sobre una base limpia no creaba el
   Marketplace (sólo lo creaba ``Base.metadata.create_all``).

3. ``users.default_role`` — el default en el modelo era ``OWNER`` y el registro
   nunca lo asignaba, así que todo usuario autogistrado quedaba con rol de
   plataforma. El fix del modelo está en ``app/models/user.py``; esta
   migración normaliza las filas existentes que quedaron en OWNER sin
   membresía OWNER/ADMIN activa.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import select
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "2026_09_27_0001"
down_revision = "f2efb29e03b1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. tenant_site_configs ──────────────────────────────
    op.create_table(
        "tenant_site_configs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("nombre_sitio", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("eslogan", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("logo_url", sa.String(length=500), nullable=False, server_default=""),
        sa.Column("brand_color", sa.String(length=20), nullable=False, server_default="#0f172a"),
        sa.Column("mensaje_principal", sa.Text(), nullable=False, server_default=""),
        sa.Column("imagen_hero_url", sa.String(length=500), nullable=False, server_default=""),
        sa.Column("bookings_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("orders_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("loyalty_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("public_menu_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("web_booking_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], ondelete="CASCADE", name="fk_tenant_site_configs_tenant_id"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", name="uq_tenant_site_configs_tenant_id"),
    )
    op.create_index("ix_tenant_site_configs_tenant_id", "tenant_site_configs", ["tenant_id"])

    # ── 2. marketplace_plugins (espejo de app/models/marketplace.py) ──
    op.create_table(
        "marketplace_plugins",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("slug", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("version", sa.String(length=20), nullable=True, server_default="1.0.0"),
        sa.Column("category", sa.String(length=50), nullable=False),
        sa.Column("pip_package", sa.String(length=255), nullable=True),
        sa.Column("git_url", sa.String(length=500), nullable=True),
        sa.Column("install_script", sa.Text(), nullable=True),
        sa.Column("config_schema", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_featured", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_paid", sa.Boolean(), nullable=True, server_default=sa.false()),
        sa.Column("price_monthly_usd", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("installs", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("rating", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("published_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )
    op.create_index("ix_marketplace_plugins_slug", "marketplace_plugins", ["slug"])
    op.create_index("ix_marketplace_plugins_category", "marketplace_plugins", ["category"])
    op.create_index("ix_marketplace_plugins_is_active", "marketplace_plugins", ["is_active"])

    # ── 3. plugin_subscriptions ──────────────────────────────
    op.create_table(
        "plugin_subscriptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("plugin_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=True, server_default="active"),
        sa.Column("config", sa.Text(), nullable=True),
        sa.Column("installed_at", sa.DateTime(), nullable=False),
        sa.Column("canceled_at", sa.DateTime(), nullable=True),
        sa.Column("revenue_share_70_to_developer", sa.Boolean(), nullable=True, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["plugin_id"], ["marketplace_plugins.id"]),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "plugin_id", name="uq_tenant_plugin"),
    )
    op.create_index("ix_plugin_subscriptions_tenant_id", "plugin_subscriptions", ["tenant_id"])
    op.create_index("ix_plugin_subscriptions_plugin_id", "plugin_subscriptions", ["plugin_id"])

    # ── 4. normalizar default_role de usuarios sin OWNER ──
    # FIX 2026-09-29: la versión anterior usaba `u.id::text` y `is_active = true`
    # en SQL raw, que funciona en PostgreSQL pero rompe en SQLite (driver de
    # tests/CI y desarrollo local). Se reescribe con SQLAlchemy core, que es
    # cross-database. Como `users.id` y `tenant_memberships.user_id` son del
    # mismo tipo (CHAR(36) en SQLite, UUID en Postgres) la comparación directa
    # funciona sin cast.
    bind = op.get_bind()
    inspector = sa.inspect(bind)
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
    op.drop_index("ix_plugin_subscriptions_plugin_id", table_name="plugin_subscriptions")
    op.drop_index("ix_plugin_subscriptions_tenant_id", table_name="plugin_subscriptions")
    op.drop_table("plugin_subscriptions")

    op.drop_index("ix_marketplace_plugins_is_active", table_name="marketplace_plugins")
    op.drop_index("ix_marketplace_plugins_category", table_name="marketplace_plugins")
    op.drop_index("ix_marketplace_plugins_slug", table_name="marketplace_plugins")
    op.drop_table("marketplace_plugins")

    op.drop_index("ix_tenant_site_configs_tenant_id", table_name="tenant_site_configs")
    op.drop_table("tenant_site_configs")
