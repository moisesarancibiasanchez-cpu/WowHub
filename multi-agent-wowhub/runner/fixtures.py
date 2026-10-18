"""
Test Fixtures — Request bodies para los 215+ CPs POST/PUT/PATCH
WowHub Multi-Agent System v1.1.0

Genera payloads válidos para los endpoints que requieren body.
Estrategia: fixtures por path (los más comunes) + generador genérico de fallback.

Cada fixture es una funcion que retorna un dict listo para json.dumps.
Las fixtures pueden usar la sesion de auth (token, tenant_id) si esta disponible.
"""

import time
import uuid
import random
from typing import Dict, Any, Optional, Callable
from pathlib import Path
import json

# ----------------------------------------------------------------------------
# Utilidades de generacion de datos
# ----------------------------------------------------------------------------

def _unique_email(prefix: str = "test") -> str:
    return f"{prefix}_{int(time.time() * 1000)}_{random.randint(100, 999)}@test.com"

def _unique_slug(prefix: str = "test") -> str:
    return f"{prefix}-{int(time.time())}-{random.randint(100, 999)}"

def _unique_rut() -> str:
    """Genera un RUT chileno valido para tests."""
    n = random.randint(10000000, 25000000)
    return f"{n}-{random.randint(0, 9)}"


# ----------------------------------------------------------------------------
# Fixtures por path
# Formato: { "method path": callable(context) -> dict }
# ----------------------------------------------------------------------------

_FIXTURES: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]] = {}


def register_fixture(method_path: str):
    """Decorador para registrar un fixture de body."""
    def decorator(fn):
        _FIXTURES[method_path] = fn
        return fn
    return decorator


# ---- Auth ----

@register_fixture("POST /api/v1/auth/register")
def _register(ctx):
    return {
        "email": _unique_email("reg"),
        "password": "Test1234!Secure",
        "full_name": "Test User",
        "business_name": f"Test Biz {random.randint(1000, 9999)}",
        "subdomain": _unique_slug("tenant"),
        "phone": "+56912345678",
    }


@register_fixture("POST /api/v1/auth/login")
def _login(ctx):
    """Para HU_03 (auth) o re-login. Usa credenciales reales si están disponibles."""
    real_email = ctx.get("auth_email", "maria@cafenorte.cl")
    real_password = ctx.get("auth_password", "demo1234")
    return {
        "email": real_email,
        "password": real_password,
    }


@register_fixture("POST /api/v1/auth/refresh")
def _refresh(ctx):
    return {"refresh_token": ctx.get("refresh_token", "fake-refresh-token-for-test")}


@register_fixture("POST /api/v1/auth/forgot-password")
def _forgot(ctx):
    return {"email": _unique_email("forgot")}


@register_fixture("POST /api/v1/auth/reset-password")
def _reset_pw(ctx):
    return {
        "token": "fake-reset-token-12345",
        "new_password": "NewTest1234!Secure",
    }


@register_fixture("POST /api/v1/auth/verify-email")
def _verify_email(ctx):
    return {"token": "fake-verify-token-12345"}


@register_fixture("PATCH /api/v1/auth/me")
def _patch_me(ctx):
    return {"full_name": f"Test Updated {random.randint(1, 999)}"}


# ---- Tenants ----

@register_fixture("POST /api/v1/tenants")
def _create_tenant(ctx):
    return {
        "name": f"Tenant Test {random.randint(1000, 9999)}",
        "slug": _unique_slug("t"),
        "country": "CL",
    }


@register_fixture("PATCH /api/v1/tenants/{tenant_id}")
def _patch_tenant(ctx):
    return {"name": f"Tenant Renamed {random.randint(1, 999)}"}


@register_fixture("POST /api/v1/tenants/{tenant_id}/members")
def _add_member(ctx):
    return {
        "email": _unique_email("member"),
        "role": "staff",
        "full_name": "Test Member",
    }


@register_fixture("POST /api/v1/tenants/{tenant_id}/branches")
def _create_branch(ctx):
    return {
        "name": f"Sucursal Test {random.randint(1, 99)}",
        "address": f"Av. Test {random.randint(100, 9999)}",
        "phone": "+56912345678",
        "is_main": False,
    }


@register_fixture("POST /api/v1/tenants/{tenant_id}/categories")
def _create_category(ctx):
    return {
        "name": f"Categoria Test {random.randint(1, 99)}",
        "color": "#6c5ce7",
        "sort_order": random.randint(0, 100),
    }


@register_fixture("POST /api/v1/tenants/{tenant_id}/products")
def _create_product(ctx):
    return {
        "name": f"Producto Test {random.randint(1, 999)}",
        "description": "Producto generado por auditoria automatica",
        "price": random.randint(500, 50000),
        "category_id": 1,
        "is_active": True,
        "sku": f"SKU-{int(time.time())}",
    }


@register_fixture("POST /api/v1/tenants/{tenant_id}/products/{product_id}/margin/simulate")
def _margin_simulate(ctx):
    return {
        "cost_components": [
            {"name": "Insumo A", "amount": 1000},
            {"name": "Insumo B", "amount": 500},
        ],
        "target_margin": 30.0,
    }


@register_fixture("POST /api/v1/tenants/{tenant_id}/customers")
def _create_customer(ctx):
    return {
        "name": f"Cliente Test {random.randint(1, 9999)}",
        "email": _unique_email("client"),
        "phone": "+56912345678",
        "rut": _unique_rut(),
    }


@register_fixture("POST /api/v1/tenants/{tenant_id}/promotions")
def _create_promotion(ctx):
    return {
        "name": f"Promo Test {random.randint(1, 99)}",
        "type": "percentage",
        "value": 10,
        "is_active": True,
        "starts_at": "2026-01-01T00:00:00Z",
        "ends_at": "2026-12-31T23:59:59Z",
    }


@register_fixture("POST /api/v1/tenants/{tenant_id}/qrs")
def _create_qr(ctx):
    return {
        "name": f"QR Test {random.randint(1, 99)}",
        "type": "table",
        "target_url": "https://test.com/menu",
    }


@register_fixture("PATCH /api/v1/tenants/{tenant_id}/landing")
def _patch_landing(ctx):
    return {
        "headline": f"Test Headline {random.randint(1, 99)}",
        "subheadline": "Test sub",
    }


@register_fixture("POST /api/v1/tenants/{tenant_id}/onboarding/step")
def _onboarding_step(ctx):
    return {
        "step": 1,
        "data": {"restaurant_name": "Test Restaurant"},
    }


# ---- Pedidos ----

@register_fixture("POST /api/v1/tenants/{tenant_id}/orders")
def _create_order(ctx):
    return {
        "items": [
            {
                "product_id": 1,
                "quantity": 1,
                "unit_price": 1000,
            }
        ],
        "channel": "local",
        "table_id": 1,
    }


@register_fixture("POST /api/v1/tenants/{tenant_id}/orders/{order_id}/transition")
def _transition_order(ctx):
    return {"to_state": "EN_PREPARACION"}


@register_fixture("POST /api/v1/tenants/{tenant_id}/orders/{order_id}/apply-discount")
def _apply_discount(ctx):
    return {
        "discount_type": "percentage",
        "value": 10,
    }


# ---- Pagos ----

@register_fixture("POST /api/v1/tenants/{tenant_id}/payments/mercadopago")
def _mp_payment(ctx):
    return {
        "order_id": 1,
        "amount": 1000,
        "token": "fake-mp-token",
    }


@register_fixture("POST /api/v1/tenants/{tenant_id}/payments/manual")
def _manual_payment(ctx):
    return {
        "order_id": 1,
        "amount": 1000,
        "method": "cash",
    }


@register_fixture("POST /api/v1/tenants/{tenant_id}/payments/{payment_id}/confirm")
def _confirm_payment(ctx):
    return {"confirmation_code": f"CONF-{int(time.time())}"}


@register_fixture("POST /api/v1/tenants/{tenant_id}/payments/stripe/intent")
def _stripe_intent(ctx):
    return {
        "order_id": 1,
        "amount": 1000,
        "currency": "CLP",
    }


# ---- Bookings ----

@register_fixture("POST /api/v1/tenants/{tenant_id}/bookings")
def _create_booking(ctx):
    return {
        "customer_name": f"Cliente {random.randint(1, 999)}",
        "customer_phone": "+56912345678",
        "booking_date": "2026-12-31",
        "booking_time": "20:00",
        "party_size": 2,
    }


@register_fixture("POST /api/v1/tenants/{tenant_id}/bookings/web-booking")
def _web_booking(ctx):
    return {
        "name": f"Web {random.randint(1, 999)}",
        "email": _unique_email("web"),
        "phone": "+56912345678",
        "date": "2026-12-31",
        "time": "20:00",
        "party_size": 2,
    }


@register_fixture("POST /api/v1/tenants/{tenant_id}/bookings/availability")
def _booking_availability(ctx):
    return {
        "date": "2026-12-31",
        "party_size": 2,
    }


# ---- Loyalty ----

@register_fixture("POST /api/v1/tenants/{tenant_id}/loyalty/campaigns")
def _create_loyalty_campaign(ctx):
    return {
        "name": f"Loyalty Test {random.randint(1, 99)}",
        "type": "points",
        "points_per_purchase": 10,
        "is_active": True,
    }


@register_fixture("POST /api/v1/tenants/{tenant_id}/loyalty/campaigns/{campaign_id}/tiers")
def _loyalty_tier(ctx):
    return {
        "name": f"Tier {random.randint(1, 9)}",
        "min_points": random.randint(100, 1000),
        "discount_pct": 5,
    }


# ---- Campaigns & Marketing ----

@register_fixture("POST /api/v1/tenants/{tenant_id}/campaigns")
def _create_campaign(ctx):
    return {
        "name": f"Campaign Test {random.randint(1, 99)}",
        "channel": "email",
        "is_active": True,
    }


@register_fixture("POST /api/v1/tenants/{tenant_id}/campaigns/preview")
def _campaign_preview(ctx):
    return {
        "name": "Test Preview",
        "channel": "email",
    }


# ---- Automation ----

@register_fixture("POST /api/v1/automation/preview")
def _automation_preview(ctx):
    return {
        "action_type": "send_email",
        "params": {"to": _unique_email("auto"), "subject": "Test"},
    }


@register_fixture("POST /api/v1/automation/execute")
def _automation_execute(ctx):
    return {
        "action_type": "send_email",
        "params": {"to": _unique_email("auto"), "subject": "Test"},
    }


# ---- Quotes ----

@register_fixture("POST /api/v1/tenants/{tenant_id}/quotes")
def _create_quote(ctx):
    return {
        "customer_name": f"Quote {random.randint(1, 999)}",
        "items": [{"description": "Item test", "quantity": 1, "unit_price": 1000}],
        "valid_until": "2026-12-31",
    }


# ---- Insumos & Recetas ----

@register_fixture("POST /api/v1/tenants/{tenant_id}/insumos")
def _create_insumo(ctx):
    return {
        "name": f"Insumo Test {random.randint(1, 999)}",
        "unit": "kg",
        "cost_per_unit": random.randint(100, 5000),
    }


@register_fixture("POST /api/v1/tenants/{tenant_id}/recetas")
def _create_receta(ctx):
    return {
        "name": f"Receta Test {random.randint(1, 99)}",
        "product_id": 1,
        "components": [
            {"insumo_id": 1, "quantity": 0.5, "unit": "kg"},
        ],
    }


# ---- Marketplace & Plugins ----

@register_fixture("POST /api/v1/marketplace/{slug}/install")
def _install_plugin(ctx):
    return {}


@register_fixture("POST /api/v1/admin/marketplace/")
def _admin_marketplace(ctx):
    return {
        "name": f"Plugin {random.randint(1, 99)}",
        "version": "1.0.0",
    }


# ---- AI ----

@register_fixture("POST /api/v1/ai/chat")
def _ai_chat(ctx):
    return {
        "message": "Test message from auditoria",
        "agent_kind": "general",
    }


@register_fixture("POST /api/v1/ai/marketing/generate")
def _ai_marketing(ctx):
    return {
        "topic": f"Test topic {random.randint(1, 99)}",
        "tone": "professional",
    }


# ---- Sites / Config ----

@register_fixture("PUT /api/v1/sites")
def _put_sites(ctx):
    return {
        "name": f"Test Site {random.randint(1, 99)}",
        "subdomain": _unique_slug("site"),
    }


@register_fixture("PUT /api/v1/admin/site-config/home-theme")
def _admin_theme(ctx):
    return {
        "primary_color": "#6c5ce7",
        "secondary_color": "#00d4a8",
    }


@register_fixture("PATCH /api/v1/admin/site-config")
def _admin_site_config(ctx):
    return {
        "headline": f"Test {random.randint(1, 999)}",
    }


# ---- OCR ----

@register_fixture("POST /api/v1/tenants/{tenant_id}/ocr/receipt")
def _ocr_receipt(ctx):
    return {
        "image_base64": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=",
    }


@register_fixture("POST /api/v1/tenants/{tenant_id}/ocr/payment-proof")
def _ocr_payment(ctx):
    return {
        "image_base64": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=",
    }


# ---- RBAC ----

@register_fixture("POST /api/v1/rbac/policies")
def _rbac_policy(ctx):
    return {
        "name": f"Policy Test {random.randint(1, 99)}",
        "permissions": ["read:products", "write:products"],
    }


@register_fixture("POST /api/v1/rbac/check")
def _rbac_check(ctx):
    return {
        "user_id": 1,
        "permission": "read:products",
    }


# ---- Dashboard ----

@register_fixture("PUT /api/v1/dashboard/layout")
def _dashboard_layout(ctx):
    return {
        "layout": [
            {"id": "kpi-1", "x": 0, "y": 0, "w": 3, "h": 2},
        ],
    }


# ---- Variants & Modifiers ----

@register_fixture("POST /api/v1/tenants/{tenant_id}/products/{product_id}/variants")
def _create_variant(ctx):
    return {
        "name": f"Variant {random.randint(1, 99)}",
        "price_modifier": 0,
        "is_default": True,
    }


@register_fixture("POST /api/v1/tenants/{tenant_id}/products/{product_id}/modifiers")
def _create_modifier(ctx):
    return {
        "name": f"Modifier {random.randint(1, 99)}",
        "type": "single",
    }


@register_fixture("POST /api/v1/tenants/{tenant_id}/modifiers/{modifier_id}/options")
def _create_modifier_option(ctx):
    return {
        "name": f"Option {random.randint(1, 99)}",
        "price_modifier": 100,
    }


# ---- Branch Products ----

@register_fixture("POST /api/v1/tenants/{tenant_id}/branch-products")
def _create_branch_product(ctx):
    return {
        "branch_id": 1,
        "product_id": 1,
        "is_available": True,
    }


# ---- Uploads ----

@register_fixture("POST /api/v1/tenants/{tenant_id}/uploads")
def _create_upload(ctx):
    return {
        "filename": f"test_{random.randint(1, 999)}.jpg",
        "content_type": "image/jpeg",
    }


# ---- Costs ----

@register_fixture("PUT /api/v1/tenants/{tenant_id}/costs")
def _put_costs(ctx):
    return {
        "lines": [
            {"name": "Costo test 1", "amount": 1000, "category": "fijo"},
        ],
    }


@register_fixture("POST /api/v1/tenants/{tenant_id}/costs/pricing-suggestion")
def _pricing_suggestion(ctx):
    return {
        "product_id": 1,
        "target_margin": 30.0,
    }


# ---- Webhooks ----

@register_fixture("POST /api/v1/tenants/{tenant_id}/webhooks")
def _create_webhook(ctx):
    return {
        "url": f"https://test-{random.randint(1, 999)}.com/hook",
        "events": ["order.created", "order.paid"],
    }


# ---- SII ----

@register_fixture("POST /api/v1/tenants/{tenant_id}/sii/validate-rut")
def _sii_rut(ctx):
    return {"rut": _unique_rut()}


@register_fixture("POST /api/v1/tenants/{tenant_id}/sii/export-ventas")
def _sii_export(ctx):
    return {
        "year": 2026,
        "month": 10,
    }


# ---- Dining sessions ----

@register_fixture("POST /api/v1/tenants/{tenant_id}/dining-sessions")
def _create_dining(ctx):
    return {
        "table_id": 1,
        "guests": 2,
    }


@register_fixture("POST /api/v1/tenants/{tenant_id}/dining-sessions/{session_id}/orders")
def _add_to_session(ctx):
    return {
        "items": [{"product_id": 1, "quantity": 1}],
    }


# ---- Public booking flow ----

@register_fixture("POST /api/v1/bookings/t/{slug}/public-check")
def _public_check(ctx):
    return {
        "date": "2026-12-31",
        "time": "20:00",
    }


@register_fixture("POST /api/v1/bookings/t/{slug}/public-create")
def _public_create(ctx):
    return {
        "name": f"Public {random.randint(1, 999)}",
        "phone": "+56912345678",
        "date": "2026-12-31",
        "time": "20:00",
        "party_size": 2,
    }


@register_fixture("POST /api/v1/loyalty/scan")
def _loyalty_scan(ctx):
    return {
        "qr_token": "fake-qr-token-12345",
    }


@register_fixture("POST /api/v1/loyalty/c/{slug}/register")
def _loyalty_register(ctx):
    return {
        "name": f"Loyalty {random.randint(1, 999)}",
        "phone": "+56912345678",
    }


@register_fixture("POST /api/v1/loyalty/c/{slug}/lookup")
def _loyalty_lookup(ctx):
    return {
        "phone": "+56912345678",
    }


@register_fixture("POST /api/v1/public/orders/from-qr/{qr_id}")
def _public_order_qr(ctx):
    return {
        "items": [{"product_id": 1, "quantity": 1}],
    }


# ----------------------------------------------------------------------------
# Generador generico (fallback para endpoints sin fixture especifica)
# ----------------------------------------------------------------------------

_GENERIC_TEMPLATES = {
    "POST": {
        "name": f"Test {uuid.uuid4().hex[:6]}",
        "description": "Auto-generated test payload",
    },
    "PATCH": {
        "name": f"Test {uuid.uuid4().hex[:6]}",
    },
    "PUT": {
        "name": f"Test {uuid.uuid4().hex[:6]}",
    },
}


# ----------------------------------------------------------------------------
# Funcion principal
# ----------------------------------------------------------------------------

def get_body(method: str, path: str, ctx: Optional[Dict[str, Any]] = None, cp_type: str = "F") -> Optional[Dict[str, Any]]:
    """
    Resuelve el request body para un (método, path) dados.

    Args:
        method:  HTTP method (POST, PUT, PATCH)
        path:    URL path del endpoint (con variables ya sustituidas)
        ctx:     Contexto opcional (auth_email, auth_password, etc.)
        cp_type: Tipo de CP: "F" (functional), "S" (security),
                 "N" (negative), "R" (performance). Para N/S se usan
                 payloads que disparan errores esperados.

    Returns:
        Dict con el body, o None si no requiere body / no se puede generar.
    """
    if not method or method.upper() in ("GET", "DELETE", "HEAD", "OPTIONS"):
        return None
    method = method.upper()
    ctx = ctx or {}

    # Para CPs negativos, intentar primero un payload "invalido" conocido
    if cp_type in ("N", "S"):
        invalid = _INVALID_BODIES.get(f"{method} {path}")
        if invalid:
            return invalid(ctx) if callable(invalid) else invalid

    key = f"{method} {path}"
    fixture = _FIXTURES.get(key)
    if fixture:
        try:
            return fixture(ctx)
        except Exception as exc:
            return _GENERIC_TEMPLATES.get(method, {})
    return _GENERIC_TEMPLATES.get(method, {})


# ----------------------------------------------------------------------------
# Invalid bodies para CPs negativos/seguridad
# Disparan 4xx esperado
# ----------------------------------------------------------------------------

_INVALID_BODIES: Dict[str, Any] = {}


def register_invalid(method_path: str, body):
    _INVALID_BODIES[method_path] = body


register_invalid("POST /api/v1/auth/login", {
    "email": "noexiste@invalid.test",
    "password": "wrongpassword",
})
register_invalid("POST /api/v1/auth/login", {  # duplicado: schema inválido
    "email": "not-an-email",
})
register_invalid("POST /api/v1/auth/register", {
    "email": "invalid",
    "password": "123",
})
register_invalid("POST /api/v1/auth/forgot-password", {
    "email": "invalid-email",
})
register_invalid("POST /api/v1/auth/verify-email", {
    "token": "",
})
register_invalid("POST /api/v1/auth/reset-password", {
    "token": "",
    "new_password": "",
})
register_invalid("POST /api/v1/tenants", {
    "name": "",
})
register_invalid("POST /api/v1/tenants/{tenant_id}/bookings", {
    # Falta customer_name, booking_date, etc.
})
register_invalid("POST /api/v1/tenants/{tenant_id}/products", {
    "price": "not-a-number",
})
register_invalid("POST /api/v1/tenants/{tenant_id}/orders", {
    "items": [],
})
register_invalid("POST /api/v1/tenants/{tenant_id}/customers", {
    "email": "not-an-email",
})


def list_fixtures() -> list:
    """Lista de todos los fixtures registrados."""
    return sorted(_FIXTURES.keys())


def save_fixtures_manifest(path: str = None) -> Dict[str, Any]:
    """Guarda un manifest de los fixtures disponibles."""
    manifest = {
        "total_fixtures": len(_FIXTURES),
        "fixtures": list_fixtures(),
        "generic_templates": list(_GENERIC_TEMPLATES.keys()),
    }
    if path:
        Path(path).write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    return manifest
