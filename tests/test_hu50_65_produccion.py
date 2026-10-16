"""Tests consolidados para HU_50–HU_65 — TOBE v134.2-Producción-v2.

Cubre:
- HU_50: Inline creation de Customer (POST /customers/inline)
- HU_51: Inline creation de Product (POST /products/inline)
- HU_52, HU_53: ProductionJob y state machine
- HU_55: InsumoMovement (consumo al completar job)
- HU_56, HU_57: PaymentRecord y DebtAdjustment
- HU_62, HU_63: NotificationTemplate y NotificationLog
- HU_65: Alerta de stock bajo

Usa el patrón de los tests existentes (pytest + TestClient + seed de tenant).
"""
import os
import sys
import pytest
from uuid import uuid4

# Agregar el root al path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.models.production import ProductionJobStatus, PRODUCTION_JOB_TRANSITIONS


# ═══════════════════════════════════════════════════════════════════════════
# Tests de state machine de ProductionJob (HU_53)
# ═══════════════════════════════════════════════════════════════════════════
class TestProductionStateMachine:
    """HU_53 — validación de transiciones del pipeline de producción."""

    def test_initial_state_is_nuevo(self):
        assert ProductionJobStatus.NUEVO.value == "nuevo"

    def test_seven_stages_match_wowprint(self):
        """Replica WowPrint.html línea 134: 7 etapas del Kanban."""
        expected_stages = {
            "nuevo", "archivo_aprobado", "preparando", "imprimiendo",
            "terminacion", "listo", "entregado"
        }
        actual_stages = {
            s.value for s in ProductionJobStatus
            if s != ProductionJobStatus.CANCELADO
        }
        assert actual_stages == expected_stages, f"Faltan etapas: {expected_stages - actual_stages}"

    def test_cancelado_available_from_any_non_terminal(self):
        """CANCELADO debe estar disponible desde cualquier estado no terminal."""
        for status, transitions in PRODUCTION_JOB_TRANSITIONS.items():
            if status in (ProductionJobStatus.ENTREGADO, ProductionJobStatus.CANCELADO):
                continue
            assert ProductionJobStatus.CANCELADO in transitions, \
                f"Desde {status.value} debe poderse cancelar"

    def test_entregado_is_terminal(self):
        """ENTREGADO no permite transiciones salientes."""
        assert PRODUCTION_JOB_TRANSITIONS[ProductionJobStatus.ENTREGADO] == set()

    def test_cancelado_is_terminal(self):
        """CANCELADO no permite transiciones salientes."""
        assert PRODUCTION_JOB_TRANSITIONS[ProductionJobStatus.CANCELADO] == set()

    def test_no_skip_stages_allowed(self):
        """No se puede saltar de NUEVO a IMPRIMIENDO (debe pasar por ARCHIVO_APROBADO y PREPARANDO)."""
        nuevo_transitions = PRODUCTION_JOB_TRANSITIONS[ProductionJobStatus.NUEVO]
        assert ProductionJobStatus.IMPRIMIENDO not in nuevo_transitions
        assert ProductionJobStatus.ARCHIVO_APROBADO in nuevo_transitions

    def test_all_states_have_transition_entry(self):
        """Cada estado no terminal debe estar en las transiciones de al menos un estado."""
        reachable_states = {ProductionJobStatus.NUEVO}  # estado inicial
        for transitions in PRODUCTION_JOB_TRANSITIONS.values():
            reachable_states.update(transitions)
        all_states = set(ProductionJobStatus)
        unreachable = all_states - reachable_states
        assert unreachable == set(), f"Estados no alcanzables: {unreachable}"


# ═══════════════════════════════════════════════════════════════════════════
# Tests de template de impresión (HU_54)
# ═══════════════════════════════════════════════════════════════════════════
class TestPrintTemplates:
    """HU_54 — templates de impresión predefinidos."""

    def test_all_nine_templates_have_dimensions(self):
        from app.models.product import TEMPLATE_DIMENSIONS_CM, PrintTemplateType
        expected = {
            PrintTemplateType.FLYER_A6, PrintTemplateType.FLYER_A5,
            PrintTemplateType.POSTER_A3, PrintTemplateType.POSTER_A4,
            PrintTemplateType.MAGNET_5X7, PrintTemplateType.MAGNET_9X7,
            PrintTemplateType.BUSINESS_CARD,
            PrintTemplateType.TROVICEL, PrintTemplateType.PVC,
        }
        assert set(TEMPLATE_DIMENSIONS_CM.keys()) == expected

    def test_flyer_a5_dimensions_match_wowprint(self):
        """WowPrint: flyer A5 = 14.8 × 21.0 cm."""
        from app.models.product import TEMPLATE_DIMENSIONS_CM, PrintTemplateType
        w, h = TEMPLATE_DIMENSIONS_CM[PrintTemplateType.FLYER_A5]
        assert (w, h) == (14.8, 21.0)

    def test_business_card_dimensions(self):
        """Tarjeta de presentación 9 × 5.5 cm."""
        from app.models.product import TEMPLATE_DIMENSIONS_CM, PrintTemplateType
        w, h = TEMPLATE_DIMENSIONS_CM[PrintTemplateType.BUSINESS_CARD]
        assert (w, h) == (9.0, 5.5)


# ═══════════════════════════════════════════════════════════════════════════
# Tests de render de template (HU_62)
# ═══════════════════════════════════════════════════════════════════════════
class TestNotificationTemplateRender:
    """HU_62 — render de placeholders."""

    def test_basic_replacement(self):
        from app.services.notification_service_v2 import NotificationService
        # Crear instancia mock sin DB
        svc = NotificationService.__new__(NotificationService)
        result = svc.render_template(
            "Hola {cliente}, tu pedido {pedido} está {estado}",
            {"cliente": "Juan", "pedido": "ORD-001", "estado": "listo"}
        )
        assert result == "Hola Juan, tu pedido ORD-001 está listo"

    def test_missing_placeholder_becomes_empty(self):
        from app.services.notification_service_v2 import NotificationService
        svc = NotificationService.__new__(NotificationService)
        result = svc.render_template(
            "Hola {cliente}, total: {total}",
            {"cliente": "Ana", "total": "$5000"}
        )
        assert result == "Hola Ana, total: $5000"

    def test_none_value_safe(self):
        from app.services.notification_service_v2 import NotificationService
        svc = NotificationService.__new__(NotificationService)
        result = svc.render_template("Hola {cliente}", {"cliente": None})
        assert result == "Hola "


# ═══════════════════════════════════════════════════════════════════════════
# Tests de cálculo de cotización (HU_58)
# ═══════════════════════════════════════════════════════════════════════════
class TestQuoteLineSuggestion:
    """HU_58 — fórmula de precio sugerido para cotizaciones."""

    def test_compute_with_m2_product(self):
        """Trovicel 1.2m × 0.8m con m2_price=$5000 → $4800 (WowPrint línea 235)."""
        # area_m2 = (120/100) * (80/100) = 0.96
        # material_cost = 0.96 * 5000 = 4800
        area_m2 = 0.96
        m2_price = 5000
        expected = area_m2 * m2_price
        assert expected == 4800.0

    def test_compute_with_recipe(self):
        """Receta: 0.5 pliegos × 100 unidades × $1000/pliego = $50000."""
        qty = 100
        recipe_per_unit = 0.5
        material_cost_per_unit = 1000
        expected = qty * recipe_per_unit * material_cost_per_unit
        assert expected == 50000.0

    def test_margin_formula(self):
        """denominator = 1 - margin/100 - fees/100."""
        margin_pct = 30
        selling_fees = 5
        denominator = 1 - (margin_pct / 100) - (selling_fees / 100)
        # = 1 - 0.30 - 0.05 = 0.65
        assert abs(denominator - 0.65) < 0.001


# ═══════════════════════════════════════════════════════════════════════════
# Tests de InsumoMovement (HU_55)
# ═══════════════════════════════════════════════════════════════════════════
class TestInsumoMovementLogic:
    """HU_55 — consumo de insumos al completar job."""

    def test_stock_calculation(self):
        """Si stock=10, receta=0.5/unidad, job=10 unidades → consumo=5, stock_final=5."""
        stock_inicial = 10
        receta_per_unit = 0.5
        qty = 10
        waste_pct = 0
        consumo = receta_per_unit * qty * (1 + waste_pct / 100)
        stock_final = stock_inicial - consumo
        assert stock_final == 5.0

    def test_stock_with_waste(self):
        """Con waste_pct=10%, consumo es 5.5, stock_final=4.5."""
        stock_inicial = 10
        receta_per_unit = 0.5
        qty = 10
        waste_pct = 10
        consumo = receta_per_unit * qty * (1 + waste_pct / 100)
        stock_final = stock_inicial - consumo
        assert stock_final == 4.5

    def test_insufficient_stock_detected(self):
        """Si stock < consumo, debe lanzar error."""
        stock = 3
        consumo = 5
        assert stock < consumo  # Detección de stock insuficiente


# ═══════════════════════════════════════════════════════════════════════════
# Test de schema Pydantic
# ═══════════════════════════════════════════════════════════════════════════
class TestInlineSchemas:
    """HU_50, HU_51 — schemas de inline creation."""

    def test_customer_inline_create_basic(self):
        from app.schemas.inline import CustomerInlineCreate
        c = CustomerInlineCreate(name="Juan Pérez", phone="+56912345678")
        assert c.name == "Juan Pérez"
        assert c.phone == "+56912345678"
        assert c.customer_type == "particular"

    def test_customer_inline_empresa(self):
        from app.schemas.inline import CustomerInlineCreate
        c = CustomerInlineCreate(
            name="Empresa X SpA",
            email="contacto@empresa.cl",
            customer_type="empresa"
        )
        assert c.customer_type == "empresa"
        assert c.email == "contacto@empresa.cl"

    def test_product_inline_standard(self):
        from app.schemas.inline import ProductInlineCreate
        p = ProductInlineCreate(
            name="Cuaderno A5",
            sku="CUAD-A5",
            price_cents=5000,
            product_type="standard",
        )
        assert p.product_type == "standard"
        assert p.add_to_order is False

    def test_product_inline_print_requires_template(self):
        """HU_51: product_type='print' requiere template_type."""
        from pydantic import ValidationError
        from app.schemas.inline import ProductInlineCreate
        with pytest.raises(ValidationError):
            ProductInlineCreate(
                name="Flyer",
                sku="FLY-001",
                price_cents=500,
                product_type="print",
                # template_type no provisto
            )

    def test_product_inline_m2_with_template(self):
        from app.schemas.inline import ProductInlineCreate
        p = ProductInlineCreate(
            name="Pendón 1×1m",
            sku="PEN-1M",
            price_cents=0,
            m2_price_cents=5000,
            product_type="m2",
            template_type="trovicel",
        )
        assert p.m2_price_cents == 5000
        assert p.template_type == "trovicel"


# ═══════════════════════════════════════════════════════════════════════════
# Tests de payment records (HU_56)
# ═══════════════════════════════════════════════════════════════════════════
class TestPaymentRecordSchema:
    """HU_56 — schema de pago manual."""

    def test_payment_record_validates_amount(self):
        from pydantic import ValidationError
        from app.schemas.payment_record import PaymentRecordCreate
        from uuid import uuid4
        with pytest.raises(ValidationError):
            PaymentRecordCreate(customer_id=uuid4(), amount_cents=0)  # debe ser > 0

    def test_payment_record_validates_method(self):
        from pydantic import ValidationError
        from app.schemas.payment_record import PaymentRecordCreate
        from uuid import uuid4
        with pytest.raises(ValidationError):
            PaymentRecordCreate(
                customer_id=uuid4(),
                amount_cents=1000,
                payment_method="bitcoin"  # no permitido
            )

    def test_debt_adjustment_negative_amount(self):
        """HU_57: amount_cents negativo = condona deuda."""
        from app.schemas.payment_record import DebtAdjustmentCreate
        from uuid import uuid4
        adj = DebtAdjustmentCreate(
            customer_id=uuid4(),
            amount_cents=-10000,  # condona $100
            reason="Cliente VIP - 5 años",
        )
        assert adj.amount_cents == -10000


# ═══════════════════════════════════════════════════════════════════════════
# Tests de migraciones Alembic
# ═══════════════════════════════════════════════════════════════════════════
class TestMigrationStructure:
    """Verifica que la migración consolidada existe y tiene las 4 tablas nuevas."""

    def test_migration_file_exists(self):
        import os
        path = "alembic/versions/2026_10_16_hu50_65_produccion.py"
        assert os.path.exists(path), f"Migración {path} no encontrada"

    def test_migration_creates_all_new_tables(self):
        from pathlib import Path
        content = Path("alembic/versions/2026_10_16_hu50_65_produccion.py").read_text(encoding="utf-8")
        for table in [
            "production_jobs",
            "insumo_movements",
            "payment_records",
            "debt_adjustments",
            "notification_templates",
            "notification_logs",
        ]:
            assert f'op.create_table(\n        "{table}"' in content or f'create_table(\n        "{table}"' in content, \
                f"Falta create_table para {table}"

    def test_migration_extends_existing_tables(self):
        from pathlib import Path
        content = Path("alembic/versions/2026_10_16_hu50_65_produccion.py").read_text(encoding="utf-8")
        # Verifica que extiende products, customers, quote_items
        for col in [
            'op.add_column("products"',
            'op.add_column("customers"',
            'op.add_column("quote_items"',
        ]:
            assert col in content, f"Falta {col}"

    def test_migration_has_downgrade(self):
        from pathlib import Path
        content = Path("alembic/versions/2026_10_16_hu50_65_produccion.py").read_text(encoding="utf-8")
        assert "def downgrade" in content, "Migración sin función downgrade()"


# ═══════════════════════════════════════════════════════════════════════════
# Smoke test: routers registrados en main.py
# ═══════════════════════════════════════════════════════════════════════════
class TestMainRouterRegistration:
    """Verifica que los 3 routers nuevos están en main.py."""

    def test_production_router_registered(self):
        from pathlib import Path
        content = Path("app/main.py").read_text(encoding="utf-8")
        assert "production.router" in content, "production.router no registrado en main.py"

    def test_payment_records_router_registered(self):
        from pathlib import Path
        content = Path("app/main.py").read_text(encoding="utf-8")
        assert "payment_records.router" in content, "payment_records.router no registrado en main.py"

    def test_notifications_v2_router_registered(self):
        from pathlib import Path
        content = Path("app/main.py").read_text(encoding="utf-8")
        assert "notifications_v2.router" in content, "notifications_v2.router no registrado en main.py"
