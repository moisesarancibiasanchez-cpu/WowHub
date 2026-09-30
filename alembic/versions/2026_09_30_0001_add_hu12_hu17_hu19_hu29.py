"""add HU_12 / HU_17 / HU_19 / HU_29 tables (idempotente)

Revision ID: 2026_09_30_0001
Revises: 2026_09_27_0001
Create Date: 2026-09-30

Contexto
--------
Esta migración crea las tablas de 4 features nuevas del backlog:

  - HU_12 (Productos con variantes y modificadores):
      product_variants
      modifiers
      modifier_options
      product_modifier_groups

  - HU_17 (Línea de tiempo del pedido):
      order_events

  - HU_19 (Mesero virtual con cuenta dividida):
      dining_sessions
      dining_session_items

  - HU_29 (Dashboard de lealtad con tiers):
      loyalty_tiers
      + columna nueva `customer_passes.current_tier_id`

Diseño
------
Idempotente: usa CREATE TABLE IF NOT EXISTS y CREATE INDEX IF NOT EXISTS,
igual que la migración previa 2026_09_27_0001. Eso permite reaplicarla en
una DB donde ``Base.metadata.create_all()`` ya creó las tablas (escenario
real en Railway producción + tests de bootstrap).

La columna ``customer_passes.current_tier_id`` se agrega con ALTER TABLE
… ADD COLUMN IF NOT EXISTS para no romper customer_passes pre-existentes
(es nullable, así que es backwards-compatible).

Cross-DB
--------
Esta migración está escrita para correr tanto en PostgreSQL (producción
Railway) como en SQLite (tests). PostgreSQL 9.5+ soporta
``ALTER TABLE … ADD COLUMN IF NOT EXISTS``. SQLite >= 3.35.0 también
(la versión de los runners de CI suele ser 3.40+).
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = "2026_09_30_0001"
down_revision = "2026_09_27_0001"
branch_labels = None
depends_on = None


# ── Helpers ───────────────────────────────────────────────
_UUID = "UUID"  # el dialecto de SQLAlchemy lo convierte a CHAR(36) en SQLite


def _uuid_fk_clause() -> str:
    """Para FKs, en SQLite el GUID se almacena como CHAR(36)."""
    return _UUID


# ── HU_12 ─────────────────────────────────────────────────
_DDL_PRODUCT_VARIANTS = f"""
CREATE TABLE IF NOT EXISTS product_variants (
    id {_UUID} NOT NULL,
    tenant_id {_UUID} NOT NULL,
    product_id {_UUID} NOT NULL,
    sku VARCHAR(80) NOT NULL,
    name VARCHAR(200) NOT NULL,
    price_cents INTEGER NOT NULL DEFAULT 0,
    cost_cents INTEGER,
    stock INTEGER NOT NULL DEFAULT 0,
    track_inventory BOOLEAN NOT NULL DEFAULT FALSE,
    image_url VARCHAR(500),
    sort_order INTEGER NOT NULL DEFAULT 0,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    attributes JSON NOT NULL DEFAULT '{{}}',
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE,
    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE,
    UNIQUE (tenant_id, sku)
)
"""

_DDL_MODIFIERS = f"""
CREATE TABLE IF NOT EXISTS modifiers (
    id {_UUID} NOT NULL,
    tenant_id {_UUID} NOT NULL,
    product_id {_UUID} NOT NULL,
    name VARCHAR(120) NOT NULL,
    type VARCHAR(16) NOT NULL DEFAULT 'single',
    required BOOLEAN NOT NULL DEFAULT FALSE,
    sort_order INTEGER NOT NULL DEFAULT 0,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    description TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE,
    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
)
"""

_DDL_MODIFIER_OPTIONS = f"""
CREATE TABLE IF NOT EXISTS modifier_options (
    id {_UUID} NOT NULL,
    modifier_id {_UUID} NOT NULL,
    name VARCHAR(120) NOT NULL,
    price_delta_cents INTEGER NOT NULL DEFAULT 0,
    is_default BOOLEAN NOT NULL DEFAULT FALSE,
    sort_order INTEGER NOT NULL DEFAULT 0,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY (modifier_id) REFERENCES modifiers(id) ON DELETE CASCADE
)
"""

_DDL_PRODUCT_MODIFIER_GROUPS = f"""
CREATE TABLE IF NOT EXISTS product_modifier_groups (
    id {_UUID} NOT NULL,
    tenant_id {_UUID} NOT NULL,
    product_id {_UUID} NOT NULL,
    modifier_id {_UUID} NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE,
    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE,
    FOREIGN KEY (modifier_id) REFERENCES modifiers(id) ON DELETE CASCADE,
    UNIQUE (product_id, modifier_id)
)
"""


# ── HU_17 ─────────────────────────────────────────────────
_DDL_ORDER_EVENTS = f"""
CREATE TABLE IF NOT EXISTS order_events (
    id {_UUID} NOT NULL,
    tenant_id {_UUID} NOT NULL,
    order_id {_UUID} NOT NULL,
    event_type VARCHAR(32) NOT NULL DEFAULT 'status_change',
    payload JSON NOT NULL DEFAULT '{{}}',
    actor_user_id {_UUID},
    message TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE
)
"""


# ── HU_19 ─────────────────────────────────────────────────
_DDL_DINING_SESSIONS = f"""
CREATE TABLE IF NOT EXISTS dining_sessions (
    id {_UUID} NOT NULL,
    tenant_id {_UUID} NOT NULL,
    branch_id {_UUID} NOT NULL,
    table_id {_UUID},
    table_label VARCHAR(60) NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'open',
    opened_at TIMESTAMP WITH TIME ZONE NOT NULL,
    closed_at TIMESTAMP WITH TIME ZONE,
    total_cents INTEGER NOT NULL DEFAULT 0,
    paid_cents INTEGER NOT NULL DEFAULT 0,
    tip_cents INTEGER NOT NULL DEFAULT 0,
    customer_count INTEGER NOT NULL DEFAULT 1,
    server_user_id {_UUID},
    notes TEXT,
    extra JSON NOT NULL DEFAULT '{{}}',
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE,
    FOREIGN KEY (branch_id) REFERENCES branches(id) ON DELETE CASCADE
)
"""

_DDL_DINING_SESSION_ITEMS = f"""
CREATE TABLE IF NOT EXISTS dining_session_items (
    id {_UUID} NOT NULL,
    session_id {_UUID} NOT NULL,
    order_item_id {_UUID} NOT NULL,
    assigned_to VARCHAR(80),
    share_cents INTEGER,
    notes VARCHAR(300),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY (session_id) REFERENCES dining_sessions(id) ON DELETE CASCADE,
    FOREIGN KEY (order_item_id) REFERENCES order_items(id) ON DELETE CASCADE
)
"""


# ── HU_29 ─────────────────────────────────────────────────
_DDL_LOYALTY_TIERS = f"""
CREATE TABLE IF NOT EXISTS loyalty_tiers (
    id {_UUID} NOT NULL,
    tenant_id {_UUID} NOT NULL,
    campaign_id {_UUID} NOT NULL,
    name VARCHAR(60) NOT NULL,
    min_stamps INTEGER NOT NULL DEFAULT 0,
    discount_pct FLOAT NOT NULL DEFAULT 0.0,
    perks JSON NOT NULL DEFAULT '{{}}',
    sort_order INTEGER NOT NULL DEFAULT 0,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    color VARCHAR(7),
    icon VARCHAR(60),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE,
    FOREIGN KEY (campaign_id) REFERENCES loyalty_campaigns(id) ON DELETE CASCADE,
    UNIQUE (campaign_id, name),
    UNIQUE (campaign_id, min_stamps)
)
"""


# ── Índices idempotentes ──────────────────────────────────
_INDEX_STATEMENTS = (
    # HU_12
    "CREATE INDEX IF NOT EXISTS ix_product_variants_product_id "
    "ON product_variants (product_id)",
    "CREATE INDEX IF NOT EXISTS ix_product_variants_sku "
    "ON product_variants (sku)",
    "CREATE INDEX IF NOT EXISTS ix_product_variants_product_active "
    "ON product_variants (product_id, is_active)",
    "CREATE INDEX IF NOT EXISTS ix_modifiers_product_id "
    "ON modifiers (product_id)",
    "CREATE INDEX IF NOT EXISTS ix_modifiers_product_active "
    "ON modifiers (product_id, is_active)",
    "CREATE INDEX IF NOT EXISTS ix_modifier_options_modifier_id "
    "ON modifier_options (modifier_id)",
    "CREATE INDEX IF NOT EXISTS ix_product_modifier_groups_product_id "
    "ON product_modifier_groups (product_id)",
    "CREATE INDEX IF NOT EXISTS ix_product_modifier_groups_modifier_id "
    "ON product_modifier_groups (modifier_id)",
    "CREATE INDEX IF NOT EXISTS ix_pmg_tenant_product "
    "ON product_modifier_groups (tenant_id, product_id)",
    # HU_17
    "CREATE INDEX IF NOT EXISTS ix_order_events_order_id "
    "ON order_events (order_id)",
    "CREATE INDEX IF NOT EXISTS ix_order_events_event_type "
    "ON order_events (event_type)",
    "CREATE INDEX IF NOT EXISTS ix_order_events_actor_user_id "
    "ON order_events (actor_user_id)",
    "CREATE INDEX IF NOT EXISTS ix_order_events_order_when "
    "ON order_events (order_id, created_at)",
    "CREATE INDEX IF NOT EXISTS ix_order_events_tenant_type "
    "ON order_events (tenant_id, event_type)",
    # HU_19
    "CREATE INDEX IF NOT EXISTS ix_dining_sessions_branch_id "
    "ON dining_sessions (branch_id)",
    "CREATE INDEX IF NOT EXISTS ix_dining_sessions_table_id "
    "ON dining_sessions (table_id)",
    "CREATE INDEX IF NOT EXISTS ix_dining_sessions_status "
    "ON dining_sessions (status)",
    "CREATE INDEX IF NOT EXISTS ix_dining_sessions_server_user_id "
    "ON dining_sessions (server_user_id)",
    "CREATE INDEX IF NOT EXISTS ix_dining_sessions_branch_status "
    "ON dining_sessions (tenant_id, branch_id, status)",
    "CREATE INDEX IF NOT EXISTS ix_dining_sessions_opened "
    "ON dining_sessions (branch_id, opened_at)",
    "CREATE INDEX IF NOT EXISTS ix_dsi_session "
    "ON dining_session_items (session_id)",
    "CREATE INDEX IF NOT EXISTS ix_dsi_order_item "
    "ON dining_session_items (order_item_id)",
    # HU_29
    "CREATE INDEX IF NOT EXISTS ix_loyalty_tiers_campaign_id "
    "ON loyalty_tiers (campaign_id)",
    "CREATE INDEX IF NOT EXISTS ix_loyalty_tiers_campaign_sort "
    "ON loyalty_tiers (campaign_id, sort_order)",
    "CREATE INDEX IF NOT EXISTS ix_customer_passes_current_tier_id "
    "ON customer_passes (current_tier_id)",
)


def upgrade() -> None:
    # ── 1. Crear tablas (idempotente) ──────────────────────
    op.execute(text(_DDL_PRODUCT_VARIANTS))
    op.execute(text(_DDL_MODIFIERS))
    op.execute(text(_DDL_MODIFIER_OPTIONS))
    op.execute(text(_DDL_PRODUCT_MODIFIER_GROUPS))
    op.execute(text(_DDL_ORDER_EVENTS))
    op.execute(text(_DDL_DINING_SESSIONS))
    op.execute(text(_DDL_DINING_SESSION_ITEMS))
    op.execute(text(_DDL_LOYALTY_TIERS))

    # ── 2. Columna nueva en customer_passes (HU_29) ───────
    # ADD COLUMN IF NOT EXISTS: PostgreSQL 9.6+ y SQLite 3.35.0+.
    # Si la columna ya existe (escenario re-aplicación o DB legacy),
    # la cláusula IF NOT EXISTS evita el DuplicateColumn / duplicate.
    op.execute(text(
        "ALTER TABLE customer_passes ADD COLUMN IF NOT EXISTS "
        "current_tier_id UUID"
    ))

    # ── 3. Índices (idempotentes) ──────────────────────────
    for idx_sql in _INDEX_STATEMENTS:
        op.execute(text(idx_sql))


def downgrade() -> None:
    # 1) Borrar columna nueva (sin IF EXISTS en SQLite < 3.35, pero
    #    los DROP COLUMN en SQLite recrean la tabla — suficiente para
    #    tests/CI). En Postgres usamos IF EXISTS.
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(text("ALTER TABLE customer_passes DROP COLUMN IF EXISTS current_tier_id"))
        op.execute(text("DROP INDEX IF EXISTS ix_customer_passes_current_tier_id"))

    # 2) Borrar índices y tablas (idempotente)
    for idx in (
        "ix_loyalty_tiers_campaign_sort",
        "ix_loyalty_tiers_campaign_id",
        "ix_dsi_order_item",
        "ix_dsi_session",
        "ix_dining_sessions_opened",
        "ix_dining_sessions_branch_status",
        "ix_dining_sessions_server_user_id",
        "ix_dining_sessions_status",
        "ix_dining_sessions_table_id",
        "ix_dining_sessions_branch_id",
        "ix_order_events_tenant_type",
        "ix_order_events_order_when",
        "ix_order_events_actor_user_id",
        "ix_order_events_event_type",
        "ix_order_events_order_id",
        "ix_pmg_tenant_product",
        "ix_product_modifier_groups_modifier_id",
        "ix_product_modifier_groups_product_id",
        "ix_modifier_options_modifier_id",
        "ix_modifiers_product_active",
        "ix_modifiers_product_id",
        "ix_product_variants_product_active",
        "ix_product_variants_sku",
        "ix_product_variants_product_id",
    ):
        if bind.dialect.name == "postgresql":
            op.execute(text(f"DROP INDEX IF EXISTS {idx}"))

    op.execute(text("DROP TABLE IF EXISTS loyalty_tiers"))
    op.execute(text("DROP TABLE IF EXISTS dining_session_items"))
    op.execute(text("DROP TABLE IF EXISTS dining_sessions"))
    op.execute(text("DROP TABLE IF EXISTS order_events"))
    op.execute(text("DROP TABLE IF EXISTS product_modifier_groups"))
    op.execute(text("DROP TABLE IF EXISTS modifier_options"))
    op.execute(text("DROP TABLE IF EXISTS modifiers"))
    op.execute(text("DROP TABLE IF EXISTS product_variants"))
