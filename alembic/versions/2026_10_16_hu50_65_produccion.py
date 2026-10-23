"""Migración consolidada HU_50–HU_65 — TOBE v134.2-Producción-v2

Crea:
  - production_jobs (HU_52, HU_53)
  - insumo_movements (HU_55)
  - payment_records + debt_adjustments (HU_56, HU_57)
  - notification_templates + notification_logs (HU_62, HU_63)

Extiende (additive only, NO modifica columnas existentes):
  - products: + product_type, template_type, m2_price_cents (HU_51, HU_54)
  - customers: + customer_type, marketing_*_status, current_debt_cents (HU_50)
  - quote_items: + template_type, width_cm, height_cm, faces, etc. (HU_54, HU_58)
  - orders: + relationship production_jobs (FK agregada via relationship)

Operación: ADITIVA. 100% backward-compatible con datos existentes.

Idempotencia (FIX 2026-10-21)
-----------------------------
Esta migración es la ÚNICA del proyecto que combina ``op.create_table`` con
``op.add_column``. Eso la hacía vulnerable al defecto del bootstrap que
detecta DBs "legacy" (creadas con ``Base.metadata.create_all()``): el
bootstrap las daba por aplicadas sólo porque las 6 tablas existían, y sellaba
la DB en ``head`` **sin ejecutar nunca los 15 ADD COLUMN**. Resultado en
producción: ``column products.product_type does not exist``.

A partir de este commit cada operación está protegida:
  - ``op.create_table``  → se omite si la tabla ya existe (``_create_table``).
  - ``op.add_column``    → se omite si la columna ya existe (guard
    ``if not _has_column(...)`` en cada llamada).
  - ``op.create_index``  → se omite si el índice ya existe.

En una DB donde la migración ya estaba aplicada, Alembic no la vuelve a
ejecutar (la revisión ya quedó en ``alembic_version``): este cambio sólo
afecta a DBs donde estaba PARCIALMENTE aplicada, donde antes fallaba con
``DuplicateTable`` y dejaba el esquema a medias.

``down_revision`` y el contenido funcional NO cambian.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

# revision identifiers
revision = "2026_10_16_hu50_65"
down_revision = "2026_10_07_0002"
branch_labels = None
depends_on = None


# ── Helpers idempotentes ──────────────────────────────────────────────────
def _has_table(table: str) -> bool:
    """True si la tabla ya existe en la DB destino."""
    return sa.inspect(op.get_bind()).has_table(table)


def _has_column(table: str, column: str) -> bool:
    """True si la columna ya existe en la tabla indicada."""
    insp = sa.inspect(op.get_bind())
    if not insp.has_table(table):
        return False
    return any(c["name"] == column for c in insp.get_columns(table))


def _create_table(table: str, *columns, **kwargs) -> None:
    """``op.create_table`` idempotente: no falla si la tabla ya existe."""
    if _has_table(table):
        return
    op.create_table(table, *columns, **kwargs)


def _create_index(name: str, table: str, cols: list[str]) -> None:
    """``op.create_index`` idempotente: no falla si el índice ya existe."""
    if not _has_table(table):
        return
    insp = sa.inspect(op.get_bind())
    if any(i["name"] == name for i in insp.get_indexes(table)):
        return
    op.create_index(name, table, cols)


def upgrade() -> None:
    # ═══════════════════════════════════════════════════════════════════════
    # 1. PRODUCTION JOBS (HU_52, HU_53)
    # ═══════════════════════════════════════════════════════════════════════
    _create_table(
        "production_jobs",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", PG_UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        # Relaciones
        sa.Column("order_id", PG_UUID(as_uuid=True), sa.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("order_item_id", PG_UUID(as_uuid=True), sa.ForeignKey("order_items.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("product_id", PG_UUID(as_uuid=True), sa.ForeignKey("products.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("product_snapshot", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("customer_id", PG_UUID(as_uuid=True), sa.ForeignKey("customers.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("customer_name", sa.String(200), nullable=True),
        # Cantidades
        sa.Column("quantity", sa.Integer, nullable=False, server_default="1"),
        sa.Column("completed_qty", sa.Integer, nullable=False, server_default="0"),
        # Medidas
        sa.Column("width_cm", sa.Float, nullable=True),
        sa.Column("height_cm", sa.Float, nullable=True),
        # Pipeline (7 etapas + cancelado)
        sa.Column("status", sa.String(20), nullable=False, server_default="nuevo", index=True),
        sa.Column("priority", sa.String(20), nullable=False, server_default="normal"),
        # Fechas
        sa.Column("due_date", sa.DateTime, nullable=True, index=True),
        sa.Column("delivered_at", sa.DateTime, nullable=True),
        # Archivo
        sa.Column("file_url", sa.String(500), nullable=True),
        sa.Column("file_status", sa.String(20), nullable=False, server_default="pending"),
        # Texto
        sa.Column("notes", sa.Text, nullable=True),
        # Costos
        sa.Column("estimated_cost_cents", sa.Integer, nullable=False, server_default="0"),
        sa.Column("actual_cost_cents", sa.Integer, nullable=False, server_default="0"),
        # Lock optimista
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
    )
    _create_index("ix_production_jobs_tenant_status", "production_jobs", ["tenant_id", "status"])
    _create_index("ix_production_jobs_tenant_due", "production_jobs", ["tenant_id", "due_date"])

    # ═══════════════════════════════════════════════════════════════════════
    # 2. INSUMO MOVEMENTS (HU_55)
    # ═══════════════════════════════════════════════════════════════════════
    _create_table(
        "insumo_movements",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", PG_UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now(), index=True),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("insumo_id", PG_UUID(as_uuid=True), sa.ForeignKey("insumos.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("type", sa.String(20), nullable=False, index=True),
        sa.Column("quantity", sa.Float, nullable=False),
        sa.Column("balance_after", sa.Float, nullable=False),
        sa.Column("production_job_id", PG_UUID(as_uuid=True), sa.ForeignKey("production_jobs.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("order_id", PG_UUID(as_uuid=True), sa.ForeignKey("orders.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("unit_cost_cents_at_move", sa.Integer, nullable=False, server_default="0"),
        sa.Column("total_cost_cents", sa.Integer, nullable=False, server_default="0"),
    )

    # ═══════════════════════════════════════════════════════════════════════
    # 3. PAYMENT RECORDS + DEBT ADJUSTMENTS (HU_56, HU_57)
    # ═══════════════════════════════════════════════════════════════════════
    _create_table(
        "payment_records",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", PG_UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("customer_id", PG_UUID(as_uuid=True), sa.ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("order_id", PG_UUID(as_uuid=True), sa.ForeignKey("orders.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("amount_cents", sa.Integer, nullable=False),
        sa.Column("payment_method", sa.String(20), nullable=False, server_default="cash"),
        sa.Column("reference", sa.String(100), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("order_total_cents", sa.Integer, nullable=False, server_default="0"),
        sa.Column("order_paid_cents", sa.Integer, nullable=False, server_default="0"),
        sa.Column("order_debt_cents", sa.Integer, nullable=False, server_default="0"),
    )
    _create_index("ix_payment_records_tenant_created", "payment_records", ["tenant_id", "created_at"])

    _create_table(
        "debt_adjustments",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", PG_UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("customer_id", PG_UUID(as_uuid=True), sa.ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("order_id", PG_UUID(as_uuid=True), sa.ForeignKey("orders.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("amount_cents", sa.Integer, nullable=False),
        sa.Column("reason", sa.String(200), nullable=False),
        sa.Column("adjusted_by_user_id", PG_UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
    )

    # ═══════════════════════════════════════════════════════════════════════
    # 4. NOTIFICATION TEMPLATES + LOGS (HU_62, HU_63)
    # ═══════════════════════════════════════════════════════════════════════
    _create_table(
        "notification_templates",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", PG_UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("event", sa.String(40), nullable=False),
        sa.Column("channel", sa.String(20), nullable=False),
        sa.Column("template_body", sa.Text, nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true(), index=True),
        sa.UniqueConstraint("tenant_id", "event", "channel", name="uq_notif_tpl_tenant_event_channel"),
    )

    _create_table(
        "notification_logs",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", PG_UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("customer_id", PG_UUID(as_uuid=True), sa.ForeignKey("customers.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("order_id", PG_UUID(as_uuid=True), sa.ForeignKey("orders.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("channel", sa.String(20), nullable=False),
        sa.Column("event", sa.String(40), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending", index=True),
        sa.Column("content_rendered", sa.Text, nullable=True),
        sa.Column("error_message", sa.String(500), nullable=True),
        sa.Column("sent_at", sa.DateTime, nullable=True, index=True),
    )

    # ═══════════════════════════════════════════════════════════════════════
    # 5. EXTENSIÓN ADITIVA A TABLAS EXISTENTES (HU_50, HU_51, HU_54, HU_58)
    # ═══════════════════════════════════════════════════════════════════════
    # Products (HU_51, HU_52, HU_54)
    if not _has_column("products", "product_type"):
        op.add_column("products", sa.Column("product_type", sa.String(30), nullable=False, server_default="standard"))
    if not _has_column("products", "template_type"):
        op.add_column("products", sa.Column("template_type", sa.String(30), nullable=True))
    if not _has_column("products", "m2_price_cents"):
        op.add_column("products", sa.Column("m2_price_cents", sa.Integer, nullable=False, server_default="0"))
    _create_index("ix_products_product_type", "products", ["product_type"])

    # Customers (HU_50, HU_56, HU_57)
    if not _has_column("customers", "customer_type"):
        op.add_column("customers", sa.Column("customer_type", sa.String(20), nullable=False, server_default="particular"))
    if not _has_column("customers", "marketing_email_status"):
        op.add_column("customers", sa.Column("marketing_email_status", sa.String(20), nullable=False, server_default="pending"))
    if not _has_column("customers", "marketing_whatsapp_status"):
        op.add_column("customers", sa.Column("marketing_whatsapp_status", sa.String(20), nullable=False, server_default="pending"))
    if not _has_column("customers", "current_debt_cents"):
        op.add_column("customers", sa.Column("current_debt_cents", sa.Integer, nullable=False, server_default="0"))
    _create_index("ix_customers_customer_type", "customers", ["customer_type"])

    # QuoteItems (HU_54, HU_58)
    if not _has_column("quote_items", "template_type"):
        op.add_column("quote_items", sa.Column("template_type", sa.String(30), nullable=True))
    if not _has_column("quote_items", "width_cm"):
        op.add_column("quote_items", sa.Column("width_cm", sa.Float, nullable=True))
    if not _has_column("quote_items", "height_cm"):
        op.add_column("quote_items", sa.Column("height_cm", sa.Float, nullable=True))
    if not _has_column("quote_items", "faces"):
        op.add_column("quote_items", sa.Column("faces", sa.Integer, nullable=False, server_default="1"))
    if not _has_column("quote_items", "suggested_price_cents"):
        op.add_column("quote_items", sa.Column("suggested_price_cents", sa.Integer, nullable=False, server_default="0"))
    if not _has_column("quote_items", "cost_unit_cents"):
        op.add_column("quote_items", sa.Column("cost_unit_cents", sa.Integer, nullable=False, server_default="0"))
    if not _has_column("quote_items", "pack_qty"):
        op.add_column("quote_items", sa.Column("pack_qty", sa.Integer, nullable=True))
    if not _has_column("quote_items", "pack_size"):
        op.add_column("quote_items", sa.Column("pack_size", sa.Integer, nullable=True))


def _drop_column(table: str, column: str) -> None:
    """``op.drop_column`` idempotente: no falla si la columna no existe.

    Antes de dropear la columna elimina los índices que la referencian:
    SQLite rechaza ``DROP COLUMN`` si existe un índice sobre ella
    ("error in index ... after drop column: no such column").
    """
    if not _has_table(table) or not _has_column(table, column):
        return
    insp = sa.inspect(op.get_bind())
    for idx in insp.get_indexes(table):
        idx_cols = set(idx.get("column_names") or [])
        if column in idx_cols:
            op.drop_index(idx["name"], table)
    op.drop_column(table, column)


def _drop_index(name: str, table: str) -> None:
    """``op.drop_index`` idempotente: no falla si el índice no existe."""
    if not _has_table(table):
        return
    insp = sa.inspect(op.get_bind())
    if not any(i["name"] == name for i in insp.get_indexes(table)):
        return
    op.drop_index(name, table)


def _drop_table(table: str) -> None:
    """``op.drop_table`` idempotente: no falla si la tabla no existe."""
    if not _has_table(table):
        return
    op.drop_table(table)


def downgrade() -> None:
    # Drop in reverse order
    _drop_column("quote_items", "pack_size")
    _drop_column("quote_items", "pack_qty")
    _drop_column("quote_items", "cost_unit_cents")
    _drop_column("quote_items", "suggested_price_cents")
    _drop_column("quote_items", "faces")
    _drop_column("quote_items", "height_cm")
    _drop_column("quote_items", "width_cm")
    _drop_column("quote_items", "template_type")

    _drop_index("ix_customers_customer_type", "customers")
    _drop_column("customers", "current_debt_cents")
    _drop_column("customers", "marketing_whatsapp_status")
    _drop_column("customers", "marketing_email_status")
    _drop_column("customers", "customer_type")

    _drop_index("ix_products_product_type", "products")
    _drop_column("products", "m2_price_cents")
    _drop_column("products", "template_type")
    _drop_column("products", "product_type")

    _drop_table("notification_logs")
    _drop_table("notification_templates")
    _drop_table("debt_adjustments")
    _drop_index("ix_payment_records_tenant_created", "payment_records")
    _drop_table("payment_records")
    _drop_table("insumo_movements")
    _drop_index("ix_production_jobs_tenant_due", "production_jobs")
    _drop_index("ix_production_jobs_tenant_status", "production_jobs")
    _drop_table("production_jobs")
