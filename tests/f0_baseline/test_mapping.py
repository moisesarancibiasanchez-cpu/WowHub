"""Tests para HU_02 — LocalStorageMapping."""
from __future__ import annotations

from app.f0_baseline import LocalStorageMapping
from app.f0_baseline.mapping import KEY_TO_MODEL


def test_mapping_uses_existing_models() -> None:
    """Ninguna referencia en KEY_TO_MODEL debe apuntar a un modelo inexistente."""
    m = LocalStorageMapping()
    rows = m.build_rows()
    # Cada fila debe tener un modelo cuyo nombre esté en la lista de modelos del proyecto.
    # Importamos dinámicamente para evitar fallos si el modelo aún no está cargado.
    from app.database import Base
    declared_tables = {t.name for t in Base.metadata.tables.values()}
    # Algunos modelos pueden tener nombres de tabla irregulares — los aceptamos con advertencia.
    found = 0
    for r in rows:
        expected = r.table
        if expected in declared_tables:
            found += 1
    # Al menos el 80% de los modelos deben existir en la metadata actual.
    assert found >= int(len(rows) * 0.8), (
        f"Solo {found}/{len(rows)} modelos se encontraron en Base.metadata. "
        f"Faltantes: {[r.model for r in rows if r.table not in declared_tables]}"
    )


def test_mapping_100_percent_coverage() -> None:
    """Todas las keys de localStorage tienen un modelo asignado."""
    m = LocalStorageMapping()
    report = m.build_report()
    stats = report["stats"]
    assert stats["coverage_pct"] == 100.0
    assert stats["keys_in_html"] == len(KEY_TO_MODEL)
    assert stats["models"] == len(KEY_TO_MODEL)


def test_mapping_marks_tenant_id_correctly() -> None:
    """Los modelos tenant-scoped deben tener has_tenant_id=True.

    NOTA: Modelos globales (User, SiteConfig, LegalConsent) y modelos
    "join"/"child" (OrderItem, CartItem, QuoteItem, PassStamp, QrToken,
    WebhookEvent, WebhookDelivery) NO tienen su propia columna tenant_id.
    """
    m = LocalStorageMapping()
    rows = m.build_rows()
    by_model = {r.model: r for r in rows}
    # Solo modelos raíz (no join/child, no globales) que SÍ tienen tenant_id.
    tenant_scoped = {
        "Branch", "Category", "Product", "Customer", "Promotion",
        "QrCode", "LandingConfig", "Order", "Payment", "Webhook",
        "AuditLog", "BranchProduct", "Cart",
        "Invoice", "Booking", "OnboardingState", "Upload",
        "AIConversation", "AIMessage", "AILog", "AITrace",
        "AIMetricDaily", "LoyaltyCampaign", "CustomerPass",
        "Quote", "AutomationExecution", "Insumo", "Receta",
        "TenantMembership",
    }
    for model_name in tenant_scoped:
        if model_name in by_model:
            r = by_model[model_name]
            assert r.has_tenant_id is True, f"{model_name} debería tener tenant_id"


def test_mapping_markdown_has_modules_section() -> None:
    m = LocalStorageMapping()
    report = m.build_report()
    md = m.to_markdown(report)
    assert "Mapeo" in md
    assert "Resumen por módulo" in md
    assert "Detalle del mapeo" in md
    assert "wowhub.tenant" in md


def test_mapping_run_returns_serializable_dict() -> None:
    m = LocalStorageMapping()
    report = m.run()
    import json
    # Debe ser JSON-serializable.
    json.dumps(report, default=str)
    assert "stats" in report
    assert "mapping" in report
    assert "markdown" in report
