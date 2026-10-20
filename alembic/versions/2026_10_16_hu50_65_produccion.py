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
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

# revision identifiers
revision = "2026_10_16_hu50_65"
down_revision = "2026_10_07_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ═══════════════════════════════════════════════════════════════════════
    # 1. PRODUCTION JOBS (HU_52, HU_53)
    # ═══════════════════════════════════════════════════════════════════════
    op.create_table(
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
    op.create_index("ix_production_jobs_tenant_status", "production_jobs", ["tenant_id", "status"])
    op.create_index("ix_production_jobs_tenant_due", "production_jobs", ["tenant_id", "due_date"])

    # ═══════════════════════════════════════════════════════════════════════
    # 2. INSUMO MOVEMENTS (HU_55)
    # ═══════════════════════════════════════════════════════════════════════
    op.create_table(
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
    op.create_table(
        "payment_records",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", PG_UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now(), index=True),
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
    op.create_index("ix_payment_records_tenant_created", "payment_records", ["tenant_id", "created_at"])

    op.create_table(
        "debt_adjustments",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", PG_UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now(), index=True),
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
    op.create_table(
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

    op.create_table(
        "notification_logs",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", PG_UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now(), index=True),
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
    op.add_column("products", sa.Column("product_type", sa.String(30), nullable=False, server_default="standard"))
    op.add_column("products", sa.Column("template_type", sa.String(30), nullable=True))
    op.add_column("products", sa.Column("m2_price_cents", sa.Integer, nullable=False, server_default="0"))
    op.create_index("ix_products_product_type", "products", ["product_type"])

    # Customers (HU_50, HU_56, HU_57)
    op.add_column("customers", sa.Column("customer_type", sa.String(20), nullable=False, server_default="particular"))
    op.add_column("customers", sa.Column("marketing_email_status", sa.String(20), nullable=False, server_default="pending"))
    op.add_column("customers", sa.Column("marketing_whatsapp_status", sa.String(20), nullable=False, server_default="pending"))
    op.add_column("customers", sa.Column("current_debt_cents", sa.Integer, nullable=False, server_default="0"))
    op.create_index("ix_customers_customer_type", "customers", ["customer_type"])

    # QuoteItems (HU_54, HU_58)
    op.add_column("quote_items", sa.Column("template_type", sa.String(30), nullable=True))
    op.add_column("quote_items", sa.Column("width_cm", sa.Float, nullable=True))
    op.add_column("quote_items", sa.Column("height_cm", sa.Float, nullable=True))
    op.add_column("quote_items", sa.Column("faces", sa.Integer, nullable=False, server_default="1"))
    op.add_column("quote_items", sa.Column("suggested_price_cents", sa.Integer, nullable=False, server_default="0"))
    op.add_column("quote_items", sa.Column("cost_unit_cents", sa.Integer, nullable=False, server_default="0"))
    op.add_column("quote_items", sa.Column("pack_qty", sa.Integer, nullable=True))
    op.add_column("quote_items", sa.Column("pack_size", sa.Integer, nullable=True))


def downgrade() -> None:
    # Drop in reverse order
    op.drop_column("quote_items", "pack_size")
    op.drop_column("quote_items", "pack_qty")
    op.drop_column("quote_items", "cost_unit_cents")
    op.drop_column("quote_items", "suggested_price_cents")
    op.drop_column("quote_items", "faces")
    op.drop_column("quote_items", "height_cm")
    op.drop_column("quote_items", "width_cm")
    op.drop_column("quote_items", "template_type")

    op.drop_index("ix_customers_customer_type", "customers")
    op.drop_column("customers", "current_debt_cents")
    op.drop_column("customers", "marketing_whatsapp_status")
    op.drop_column("customers", "marketing_email_status")
    op.drop_column("customers", "customer_type")

    op.drop_index("ix_products_product_type", "products")
    op.drop_column("products", "m2_price_cents")
    op.drop_column("products", "template_type")
    op.drop_column("products", "product_type")

    op.drop_table("notification_logs")
    op.drop_table("notification_templates")
    op.drop_table("debt_adjustments")
    op.drop_index("ix_payment_records_tenant_created", "payment_records")
    op.drop_table("payment_records")
    op.drop_table("insumo_movements")
    op.drop_index("ix_production_jobs_tenant_due", "production_jobs")
    op.drop_index("ix_production_jobs_tenant_status", "production_jobs")
    op.drop_table("production_jobs")
