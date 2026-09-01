"""Tests para HU_02 — LocalStorageMapping."""
from __future__ import annotations

from app.f0_baseline import LocalStorageMapping
from app.f0_baseline.mapping import KEY_TO_MODEL


def test_mapping_uses_existing_models() -> None:
    """TODAS las referencias en KEY_TO_MODEL deben apuntar a modelos existentes.

    El catálogo curado promete 100% de cobertura, así que cualquier modelo
    que falte en `Base.metadata` es un bug que debe romper el test (no un
    80% "razonable" como hacía la versión previa).
    """
    m = LocalStorageMapping()
    rows = m.build_rows()
    from app.database import Base
    declared_tables = {t.name for t in Base.metadata.tables.values()}
    missing = [r for r in rows if r.table not in declared_tables]
    assert not missing, (
        f"{len(missing)}/{len(rows)} modelos no se encontraron en Base.metadata: "
        f"{[(r.model, r.table) for r in missing]}"
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
    # Cada modelo declarado como tenant_scoped DEBE existir en el catálogo
    # y tener tenant_id=True. Si el modelo falta del catálogo, es un bug
    # silencioso que la versión previa se saltaba con `if name in by_model`.
    for model_name in tenant_scoped:
        assert model_name in by_model, (
            f"Modelo tenant-scoped '{model_name}' no está en KEY_TO_MODEL"
        )
        r = by_model[model_name]
        assert r.has_tenant_id is True, (
            f"{model_name} debería tener tenant_id (columna real en la tabla)"
        )


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
