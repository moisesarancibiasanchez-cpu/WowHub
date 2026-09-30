"""API v1 routers."""
from app.api.v1 import (  # noqa: F401
    auth, branches, categories, customers, landing, products,
    promotions, public, qrs, tenants,
    orders, payments, webhooks, stats, uploads, password,
    i18n, csv, legal, onboarding, audit, bookings,
    branch_products, search,
    analytics, campaigns,
    costs,  # Costos fijos mensuales + cálculo de costo_hora (Fase 2 V8)
    insumos,  # V8 P0.1 — Insumos (materia prima) + Recetas (BOM)
    marketplace,  # HU_45: Marketplace de plugins
    plugins,  # HU_45: Plugin sandbox (RestrictedPython) — /plugins/test
    sii,  # HU_32 — SII Chile (Libro de Ventas + validador RUT)
    webhook_stripe,  # HU_23 — Stripe webhook (público, sin auth)
    audit_chain,  # HU_40 — Audit hash chain (backfill + verify)
)
