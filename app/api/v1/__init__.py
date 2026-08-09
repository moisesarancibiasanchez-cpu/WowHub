"""API v1 routers."""
from app.api.v1 import (  # noqa: F401
    auth, branches, categories, customers, landing, products,
    promotions, public, qrs, tenants,
    orders, payments, webhooks, stats, uploads, password,
    i18n, csv, legal, onboarding, audit, bookings,
    branch_products, search,
)
