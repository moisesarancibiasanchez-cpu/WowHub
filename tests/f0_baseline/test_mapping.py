"""Tests para HU_02 — LocalStorageMapping."""
from __future__ import annotations

from app.f0_baseline import LocalStorageMapping
from app.f0_baseline.mapping import KEY_TO_MODEL
from app.f0_baseline.router import INTERNAL_MODELS_ALLOWLIST, _catalog_diff


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


# ─────────────────────────────────────────────────────────────────────
# Detección de modelos huérfanos (no catalogados).
# Cierra el punto débil §3.7 del análisis de Fase 1.
# ─────────────────────────────────────────────────────────────────────


def test_no_orphan_models_in_metadata() -> None:
    """Detecta modelos en ``app.models`` que no están en ``KEY_TO_MODEL``.

    Si un dev añade un modelo nuevo a ``app/models/`` y olvida crear
    su entrada en ``KEY_TO_MODEL``, este test falla con la lista de
    huérfanos. La allowlist ``INTERNAL_MODELS_ALLOWLIST`` exime a los
    modelos "internos" (Tenant, User, AuthToken, etc.) que no se siembran
    en localStorage.

    Si añades un modelo de UI que SÍ debe estar en localStorage pero
    no quieres romper este test, **debes** añadir su entrada en
    ``KEY_TO_MODEL`` (no en la allowlist).
    """
    diff = _catalog_diff()
    assert diff["orphan_models"] == [], (
        f"Modelos en app.models sin entrada en KEY_TO_MODEL: "
        f"{diff['orphan_models']}. Añádelos a KEY_TO_MODEL o a "
        f"INTERNAL_MODELS_ALLOWLIST (solo si NO se siembran en localStorage)."
    )


def test_no_catalog_only_entries() -> None:
    """Detecta entradas del catálogo sin modelo físico en metadata.

    Si ``KEY_TO_MODEL`` referencia un modelo que no existe en
    ``Base.metadata``, este test falla. Sería un bug grave: el
    endpoint /f0/hu02 mentiría sobre la cobertura.
    """
    diff = _catalog_diff()
    assert diff["catalog_only"] == [], (
        f"Entradas en KEY_TO_MODEL sin modelo en Base.metadata: "
        f"{diff['catalog_only']}. Borra la entrada o crea el modelo."
    )


def test_allowlist_is_a_frozenset() -> None:
    """La allowlist debe ser inmutable para que no se modifique por accidente."""
    assert isinstance(INTERNAL_MODELS_ALLOWLIST, frozenset), (
        "INTERNAL_MODELS_ALLOWLIST debe ser frozenset, no set/list"
    )
    # Debe tener al menos Tenant y User (modelos raíz de SaaS).
    assert "Tenant" in INTERNAL_MODELS_ALLOWLIST
    assert "User" in INTERNAL_MODELS_ALLOWLIST


def test_catalog_diff_includes_table_map() -> None:
    """El diff debe incluir el mapeo modelo→tabla para auditoría."""
    diff = _catalog_diff()
    assert "metadata_table_map" in diff
    assert isinstance(diff["metadata_table_map"], dict)
    # Cada modelo del catálogo que tenga tabla física debe aparecer.
    for model_name, table_name in diff["metadata_table_map"].items():
        assert model_name in {meta["model"] for meta in KEY_TO_MODEL.values()}
        assert isinstance(table_name, str)
        assert table_name  # no vacío
