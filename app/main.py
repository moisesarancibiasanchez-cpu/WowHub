"""App principal FastAPI — incluye API, UI server-rendered, y redirect de QR."""
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.v1 import (
    auth, branches, categories, customers, landing, products, promotions, public, qrs, tenants,
    orders, payments, webhooks, stats, uploads, password,
    i18n, csv, legal, onboarding, audit, bookings,
    branch_products, search,
    site_config,
    ai, admin_ai, superadmin,
    loyalty,
    analytics, campaigns,
    automation,  # Automation Manager™ (Cap. 19.3)
    opportunities,  # Opportunity Engine (Fase 3 del plan, ver oportunidades.pdf)
    quotes,  # Cotizaciones (Quotes) — Gestión interna
    costs,  # Costos fijos mensuales + cálculo de costo_hora (Fase 2 V8)
    notifications,  # Notifications Engine API (Fase 5) — bell badge + lista
)
from app.models.user import UserRole
from app.config import settings
from app.core.audit_middleware import AuditMiddleware
from app.core.security import RateLimitMiddleware
from app.database import SessionLocal, init_db
from app.models.qr import QrCode, QrTarget
from app.services.qr_service import QrService
from app.services.site_config_service import SiteConfigService

logging.basicConfig(level=settings.log_level)
logger = logging.getLogger("wowhub")

BASE_DIR = Path(__file__).parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"
STORAGE_DIR = Path(settings.storage_path)
STORAGE_DIR.mkdir(parents=True, exist_ok=True)

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# ── Detección de i18n en templates ───────────────────────
from app.services.i18n_service import I18nService  # noqa: E402


def _t(context: dict, key: str, default: str = "") -> str:
    """Helper de traducción para templates Jinja2 (inyectado como global)."""
    request = context.get("request")
    lang = "es"
    if request is not None:
        lang = I18nService.detect_lang(request.headers.get("accept-language"))
    return I18nService.t(lang, key, default)


templates.env.globals["_t"] = _t

# Exponer el objeto settings completo para que los templates puedan usar
# `{{ settings.* }}` directamente.
templates.env.globals["settings"] = settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Inicializando base de datos...")
    init_db()
    logger.info(f"WowHub arrancado — env={settings.app_env}, db={settings.database_url}")
    yield
    # Shutdown
    logger.info("WowHub cerrando.")


# Determinar tipo de base de datos
_db_kind = "postgres" if "postgresql" in (settings.database_url or "") else "sqlite"

app = FastAPI(
    title="WowHub API",
    description=(
        "Plataforma SaaS modular para PyMEs en LATAM.\n\n"
        "Stack: **FastAPI + SQLAlchemy + Pydantic + Jinja2** sobre arquitectura multi-tenant.\n\n"
        "Esta API cubre: **Página**, **Catálogo**, **QR**, **Promociones**, "
        "**Pedidos**, **Pagos**, **Email**, **Reservas**, **Inventario multi-sucursal**, "
        "**Auditoría**, **Webhooks**, **Estadísticas**, **Multi-idioma (es/en/pt)** y más."
    ),
    version="0.2.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# ── Middlewares ──────────────────────────────────────────
# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rate limit
if getattr(settings, "rate_limit_enabled", True):
    app.add_middleware(RateLimitMiddleware)

# Audit log
if getattr(settings, "audit_enabled", True):
    app.add_middleware(AuditMiddleware)

# Static & storage
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.mount("/storage", StaticFiles(directory=str(STORAGE_DIR)), name="storage")

# ── API v1 ───────────────────────────────────────────────
app.include_router(auth.router, prefix="/api/v1")
app.include_router(tenants.router, prefix="/api/v1")
app.include_router(tenants.membership_router, prefix="/api/v1")
app.include_router(branches.router, prefix="/api/v1")
app.include_router(categories.router, prefix="/api/v1")
app.include_router(products.router, prefix="/api/v1")
app.include_router(customers.router, prefix="/api/v1")
app.include_router(promotions.router, prefix="/api/v1")
app.include_router(qrs.router, prefix="/api/v1")
app.include_router(landing.router, prefix="/api/v1")
app.include_router(public.router, prefix="/api/v1")
# Nuevas rutas (v0.2.0)
app.include_router(orders.router, prefix="/api/v1")
app.include_router(payments.tenant_router, prefix="/api/v1")
app.include_router(payments.public_router, prefix="/api/v1")
app.include_router(webhooks.router, prefix="/api/v1")
app.include_router(stats.router, prefix="/api/v1")
app.include_router(uploads.router, prefix="/api/v1")
app.include_router(password.router, prefix="/api/v1")
app.include_router(i18n.router, prefix="/api/v1")
app.include_router(csv.router, prefix="/api/v1")
app.include_router(legal.router, prefix="/api/v1")
app.include_router(onboarding.router, prefix="/api/v1")
app.include_router(audit.router, prefix="/api/v1")
app.include_router(bookings.router, prefix="/api/v1")
app.include_router(branch_products.router, prefix="/api/v1")
app.include_router(search.router, prefix="/api/v1")
app.include_router(site_config.router, prefix="/api/v1")
app.include_router(ai.router, prefix="/api/v1")
app.include_router(admin_ai.router, prefix="/api/v1")
app.include_router(superadmin.router, prefix="/api/v1")
# Loyalty Pass (Fase 1 y 2)
app.include_router(loyalty.owner_router, prefix="/api/v1")
app.include_router(loyalty.pos_router, prefix="/api/v1")
app.include_router(loyalty.public_router, prefix="/api/v1")
# Bookings Fase 2 (público)
app.include_router(bookings.public_router, prefix="/api/v1")
# Analytics + Campaigns (alimentan al Asistente IA)
app.include_router(analytics.router, prefix="/api/v1")
app.include_router(campaigns.router, prefix="/api/v1")
# Automation Manager™ (Cap. 19.3) — ejecuta acciones del Growth Coach
app.include_router(automation.router, prefix="/api/v1")
# Opportunity Engine (Fase 3) — oportunidades priorizadas para el dashboard
app.include_router(opportunities.router, prefix="/api/v1")
# Cotizaciones (Quotes) — owner + público
app.include_router(quotes.router, prefix="/api/v1")
app.include_router(quotes.public_router, prefix="/api/v1")
# Costos (BusinessCosts) — fuente de verdad de costo_hora y precio sugerido
app.include_router(costs.router, prefix="/api/v1")
# Notifications (Fase 5) — bell badge del dashboard (summary + lista)
app.include_router(notifications.router, prefix="/api/v1")


# ── Rutas de UI (server-rendered) ────────────────────────
@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def home(request: Request):
    """Portada: renderiza home.html (tema dark) o home_pro.html (tema pro)
    según la configuración global SiteConfig.home_theme."""
    with SessionLocal() as db:
        theme = SiteConfigService(db).get_theme()
    template = "home_pro.html" if theme == "pro" else "home.html"
    return templates.TemplateResponse(
        request, template, {"settings": settings, "site_theme": theme}
    )


@app.get("/login", response_class=HTMLResponse, include_in_schema=False)
def login_page(request: Request):
    return templates.TemplateResponse(request, "auth/login.html", {"settings": settings})


# ── Alias legacy: /dashboard/login → /login ──────────────────────
# Los guards de admin_ai y superadmin redirigen a /dashboard/login?reason=...
# preservando compatibilidad con URLs antiguas. 301 = canonical a /login.
@app.get("/dashboard/login", include_in_schema=False)
def login_dashboard_alias(request: Request):
    """Alias legacy: /dashboard/login → /login (preserva reason y next)."""
    qs = request.url.query
    target = "/login" + (f"?{qs}" if qs else "")
    return RedirectResponse(url=target, status_code=301)


@app.get("/register", response_class=HTMLResponse, include_in_schema=False)
def register_page(request: Request):
    return templates.TemplateResponse(request, "auth/register.html", {"settings": settings})


@app.get("/forgot-password", response_class=HTMLResponse, include_in_schema=False)
def forgot_password_page(request: Request):
    return templates.TemplateResponse(request, "auth/forgot_password.html", {"settings": settings})


@app.get("/reset-password", response_class=HTMLResponse, include_in_schema=False)
def reset_password_page(request: Request, token: str = ""):
    return templates.TemplateResponse(
        request, "auth/reset_password.html", {"settings": settings, "token": token}
    )


@app.get("/dashboard", response_class=HTMLResponse, include_in_schema=False)
def dashboard_page(request: Request):
    return templates.TemplateResponse(request, "dashboard/index.html", {"settings": settings})


@app.get("/dashboard/products", response_class=HTMLResponse, include_in_schema=False)
def dashboard_products(request: Request):
    return templates.TemplateResponse(request, "dashboard/products.html", {"settings": settings})


@app.get("/dashboard/promotions", response_class=HTMLResponse, include_in_schema=False)
def dashboard_promotions(request: Request):
    return templates.TemplateResponse(request, "dashboard/promotions.html", {"settings": settings})


@app.get("/dashboard/qrs", response_class=HTMLResponse, include_in_schema=False)
def dashboard_qrs(request: Request):
    return templates.TemplateResponse(request, "dashboard/qrs.html", {"settings": settings})


@app.get("/dashboard/customers", response_class=HTMLResponse, include_in_schema=False)
def dashboard_customers(request: Request):
    return templates.TemplateResponse(request, "dashboard/customers.html", {"settings": settings})


@app.get("/dashboard/landing", response_class=HTMLResponse, include_in_schema=False)
def dashboard_landing(request: Request):
    return templates.TemplateResponse(request, "dashboard/landing.html", {"settings": settings})


@app.get("/dashboard/site", response_class=HTMLResponse, include_in_schema=False)
def dashboard_site(request: Request):
    """Admin UI: cambiar tema de la portada (dark | pro)."""
    return templates.TemplateResponse(request, "dashboard/site.html", {"settings": settings})


# Nuevas páginas de dashboard (v0.2.0)
@app.get("/dashboard/orders", response_class=HTMLResponse, include_in_schema=False)
def dashboard_orders(request: Request):
    return templates.TemplateResponse(request, "dashboard/orders.html", {"settings": settings})


@app.get("/dashboard/payments", response_class=HTMLResponse, include_in_schema=False)
def dashboard_payments(request: Request):
    return templates.TemplateResponse(request, "dashboard/payments.html", {"settings": settings})


@app.get("/dashboard/stats", response_class=HTMLResponse, include_in_schema=False)
def dashboard_stats(request: Request):
    return templates.TemplateResponse(request, "dashboard/stats.html", {"settings": settings})


@app.get("/dashboard/webhooks", response_class=HTMLResponse, include_in_schema=False)
def dashboard_webhooks(request: Request):
    return templates.TemplateResponse(request, "dashboard/webhooks.html", {"settings": settings})


@app.get("/dashboard/ai", response_class=HTMLResponse, include_in_schema=False)
def dashboard_ai(request: Request):
    """Chat con el asistente IA de WowHub.

    FIX bug reportado: "Conversar con la IA → no envía a ninguna
    page funcional, queda todo en blanco".

    El problema: la página /dashboard/ai extendía dashboard/base.html,
    que SIEMPRE incluye _ai_panel.html. La dash_content de ai.html
    también era un ai-sidebar → había DOS paneles AI en la misma
    vista, y el main quedaba visualmente vacío.

    Solución:
      1) Esta ruta pasa `hide_ai_panel=True` para que base.html NO
         incluya el panel derecho (porque la página ES el chat).
      2) ai.html renderiza el chat como contenido principal.
      3) ai.js lee `?context=opportunities` y auto-envía el primer
         mensaje del usuario con contexto de oportunidades.
    """
    context = request.query_params.get("context", "").strip()
    return templates.TemplateResponse(
        request, "dashboard/ai.html",
        {"settings": settings, "hide_ai_panel": True, "ai_context": context},
    )


@app.get("/dashboard/marketing", response_class=HTMLResponse, include_in_schema=False)
def dashboard_marketing_studio(request: Request):
    """Marketing Studio (Fase 7): UI dedicada para generar copy de marketing
    contextual al tenant. Usa POST /api/v1/ai/marketing/generate y muestra
    las variantes generadas con copy-to-clipboard.
    """
    return templates.TemplateResponse(
        request, "dashboard/admin_marketing.html",
        {"settings": settings, "body_class": "route-marketing"},
    )


@app.get("/admin/ai", response_class=HTMLResponse, include_in_schema=False)
def admin_ai_page(request: Request):
    """Dashboard admin del AI Core: logs, métricas, trazas, circuit.
    Requiere rol OWNER o ADMIN — si no, redirige a /dashboard/login."""
    from app.database import SessionLocal
    from app.security import decode_token

    token = request.cookies.get("access_token") or request.cookies.get("wowhub_access_token")
    auth_header = request.headers.get("authorization", "")
    if not token and auth_header.lower().startswith("bearer "):
        token = auth_header.split(" ", 1)[1].strip()
    if not token:
        return RedirectResponse(url="/dashboard/login?reason=admin_auth", status_code=302)

    try:
        payload = decode_token(token)
    except Exception:
        return RedirectResponse(url="/dashboard/login?reason=admin_auth", status_code=302)

    user_id = payload.get("sub")
    if not user_id:
        return RedirectResponse(url="/dashboard/login?reason=admin_auth", status_code=302)

    with SessionLocal() as db:
        from app.models.user import User
        user = db.get(User, user_id)
        if not user:
            return RedirectResponse(url="/dashboard/login?reason=admin_auth", status_code=302)
        role = getattr(user, "default_role", None) or getattr(user, "role", None)
        if role not in (UserRole.OWNER, UserRole.ADMIN):
            return RedirectResponse(
                url="/dashboard?reason=admin_forbidden",
                status_code=302,
            )

    return templates.TemplateResponse(
        request,
        "dashboard/admin_ai.html",
        {"settings": settings, "user_role": role.value},
    )


# ── Alias de backward compat ──────────────────────────────
# La doc antigua (v1.0 de CANONICAL_WOWHUB.md) y algunos bookmarks pueden
# apuntar a /dashboard/admin/ai. Redirigimos 301 a la ruta canónica /admin/ai
# para evitar el 404 que reportaban los usuarios.
@app.get("/dashboard/admin/ai", include_in_schema=False)
def admin_ai_legacy_alias():
    """Alias legacy: /dashboard/admin/ai → /admin/ai (deprecated)."""
    return RedirectResponse(url="/admin/ai", status_code=301)


# ── SUPERADMIN (UI) ──────────────────────────────────────────────
@app.get("/admin/superadmin", response_class=HTMLResponse, include_in_schema=False)
def superadmin_page(request: Request):
    """Panel de plataforma para SUPERADMIN: KPIs, tiendas, usuarios, auditoría.

    Guard server-side:
    - Si no hay sesión → redirige a /dashboard/login?reason=superadmin_auth
    - Si hay sesión pero no es superuser → redirige a /dashboard?reason=superadmin_forbidden
    """
    from app.database import SessionLocal
    from app.security import decode_token

    token = request.cookies.get("access_token") or request.cookies.get("wowhub_access_token")
    auth_header = request.headers.get("authorization", "")
    if not token and auth_header.lower().startswith("bearer "):
        token = auth_header.split(" ", 1)[1].strip()
    if not token:
        return RedirectResponse(
            url="/dashboard/login?reason=superadmin_auth", status_code=302
        )

    try:
        payload = decode_token(token)
    except Exception:
        return RedirectResponse(
            url="/dashboard/login?reason=superadmin_auth", status_code=302
        )

    user_id = payload.get("sub")
    if not user_id:
        return RedirectResponse(
            url="/dashboard/login?reason=superadmin_auth", status_code=302
        )

    with SessionLocal() as db:
        from app.models.user import User
        user = db.get(User, user_id)
        if not user:
            return RedirectResponse(
                url="/dashboard/login?reason=superadmin_auth", status_code=302
            )
        # Doble check: claim del JWT + DB
        is_su_jwt = bool(payload.get("is_superuser"))
        is_su_db = bool(getattr(user, "is_superuser", False))
        if not (is_su_jwt or is_su_db):
            return RedirectResponse(
                url="/dashboard?reason=superadmin_forbidden",
                status_code=302,
            )
        user_email = user.email
        user_name = user.full_name

    return templates.TemplateResponse(
        request,
        "dashboard/superadmin.html",
        {
            "settings": settings,
            "user_role": "superuser",
            "user_email": user_email,
            "user_name": user_name,
        },
    )


# ── Loyalty Pass (UI) ─────────────────────────────────────
@app.get("/dashboard/loyalty", response_class=HTMLResponse, include_in_schema=False)
def dashboard_loyalty(request: Request):
    """Panel del dueño: crear campañas, ver métricas, generar QR del mostrador."""
    return templates.TemplateResponse(
        request, "dashboard/admin_loyalty.html",
        {"settings": settings, "body_class": "route-loyalty"},
    )


@app.get("/dashboard/loyalty/scanner", response_class=HTMLResponse, include_in_schema=False)
def dashboard_loyalty_scanner(request: Request):
    """Escáner del POS: cámara + QR del mostrador + resultado del scan."""
    return templates.TemplateResponse(
        request, "dashboard/admin_scanner.html",
        {"settings": settings, "body_class": "route-loyalty-scanner"},
    )


# ── Bookings Fase 2 (UI) ─────────────────────────────────
@app.get("/dashboard/bookings", response_class=HTMLResponse, include_in_schema=False)
def dashboard_bookings(request: Request):
    """Panel del dueño: agenda de reservas con KPIs, filtros y acciones."""
    return templates.TemplateResponse(
        request, "dashboard/admin_bookings.html",
        {"settings": settings, "body_class": "route-bookings"},
    )


@app.api_route("/u/{slug}/reservar", methods=["GET", "HEAD"],
               response_class=HTMLResponse, include_in_schema=False)
def public_booking_page(slug: str, request: Request):
    """Landing público: el cliente elige horario y reserva sin login."""
    from app.models.tenant import Tenant
    with SessionLocal() as db:
        t = db.execute(select(Tenant).where(Tenant.slug == slug)).scalar_one_or_none()
        if not t or not t.is_active:
            return templates.TemplateResponse(
                request, "public/404.html",
                {"settings": settings, "slug": slug},
                status_code=404,
            )
        tenant_name = t.display_name or t.legal_name or slug
    return templates.TemplateResponse(
        request, "public/booking.html",
        {"settings": settings, "slug": slug, "tenant_name": tenant_name},
    )


# ── Cotizaciones (UI owner) ─────────────────────────────────
@app.get("/dashboard/quotes", response_class=HTMLResponse, include_in_schema=False)
def dashboard_quotes(request: Request):
    """Panel del dueño: cotizaciones con KPIs, filtros, modal de crear/editar."""
    return templates.TemplateResponse(
        request, "dashboard/quotes.html",
        {"settings": settings, "body_class": "route-quotes"},
    )


# ── Vista pública de cotización (token) ─────────────────────
@app.get("/quote/{token}", response_class=HTMLResponse, include_in_schema=False)
def public_quote_page(token: str, request: Request):
    """El cliente abre la cotización por su token único (sin login)."""
    tenant_name = ""
    try:
        with SessionLocal() as db:
            from app.models.quote import Quote
            q = db.execute(
                select(Quote).where(Quote.public_token == token)
            ).scalar_one_or_none()
            if q:
                from app.models.tenant import Tenant
                t = db.get(Tenant, q.tenant_id)
                if t:
                    tenant_name = t.display_name or t.legal_name or t.slug
    except Exception:
        pass
    return templates.TemplateResponse(
        request, "public/quote.html",
        {"settings": settings, "token": token, "tenant_name": tenant_name},
    )


# ── Inventario (UI owner) ──────────────────────────────────
@app.get("/dashboard/inventory", response_class=HTMLResponse, include_in_schema=False)
def dashboard_inventory(request: Request):
    """Panel del dueño: stock por sucursal con alertas de reposición."""
    return templates.TemplateResponse(
        request, "dashboard/inventory.html",
        {"settings": settings, "body_class": "route-inventory"},
    )


# ── Costos (UI owner) — Fase 2 V8 ──────────────────────────
@app.get("/dashboard/costs", response_class=HTMLResponse, include_in_schema=False)
def dashboard_costs(request: Request):
    """Panel del dueño: configuración de costos fijos mensuales + cálculo de
    costo/hora. Es la fuente de verdad para el motor de precios sugerido."""
    return templates.TemplateResponse(
        request, "dashboard/costs.html",
        {"settings": settings, "body_class": "route-costs"},
    )


# ── Notificaciones (UI owner) — Fase 6 ─────────────────────
@app.get("/dashboard/notifications", response_class=HTMLResponse, include_in_schema=False)
def dashboard_notifications(request: Request):
    """Centro de notificaciones: lista completa con filtros por severidad
    y categoría. Alimentado por GET /api/v1/tenants/{tid}/notifications
    (mismo motor que el bell badge del header)."""
    return templates.TemplateResponse(
        request, "dashboard/notifications.html",
        {"settings": settings, "body_class": "route-notifications"},
    )


# ── Pipeline de Pedidos (UI owner) ─────────────────────────
@app.get("/dashboard/pipeline", response_class=HTMLResponse, include_in_schema=False)
def dashboard_pipeline(request: Request):
    """Panel del dueño: Kanban de pedidos por estado (PENDING → DELIVERED)."""
    return templates.TemplateResponse(
        request, "dashboard/pipeline.html",
        {"settings": settings, "body_class": "route-pipeline"},
    )


# ── Páginas públicas por tenant ──────────────────────────
@app.get("/u/{slug}", response_class=HTMLResponse, include_in_schema=False)
def public_landing_page(slug: str, request: Request):
    """Landing pública del tenant."""
    with SessionLocal() as db:
        from app.models.tenant import Tenant
        t = db.execute(select(Tenant).where(Tenant.slug == slug)).scalar_one_or_none()
        if not t or not t.is_active:
            return templates.TemplateResponse(
                request, "public/404.html", {"settings": settings, "slug": slug}, status_code=404
            )
    return templates.TemplateResponse(request, "public/landing.html", {"settings": settings, "slug": slug})


@app.get("/u/{slug}/catalogo", response_class=HTMLResponse, include_in_schema=False)
def public_catalog_page(slug: str, request: Request):
    return templates.TemplateResponse(request, "public/catalog.html", {"settings": settings, "slug": slug})


# ── Landing público de fidelización ────────────────────────
@app.get("/loyalty/{slug}", response_class=HTMLResponse, include_in_schema=False)
def public_loyalty_page(slug: str, request: Request):
    """Landing público: el cliente se registra y obtiene su pase."""
    from app.services.loyalty_pass_service import get_active_campaign_by_slug
    with SessionLocal() as db:
        campaign = get_active_campaign_by_slug(db, slug)
        if not campaign:
            return templates.TemplateResponse(
                request, "public/404.html",
                {"settings": settings, "slug": slug, "detail": "Sin campaña activa"},
                status_code=404,
            )
        # Resolver tenant por tenant_id (no hay relationship en el modelo)
        from app.models.tenant import Tenant
        tenant = db.get(Tenant, campaign.tenant_id)
        tenant_name = (tenant.display_name or tenant.legal_name or tenant.slug) if tenant else slug
    return templates.TemplateResponse(
        request, "public/loyalty.html",
        {
            "settings": settings,
            "slug": slug,
            "tenant_name": tenant_name,
            "campaign": {
                "id": str(campaign.id),
                "name": campaign.name,
                "reward_label": campaign.reward_label,
                "stamps_required": campaign.stamps_required,
                "primary_color": campaign.primary_color,
                "text_color": campaign.text_color,
            },
        },
    )


# ── Alias canónico: /u/{slug}/tarjeta → /loyalty/{slug} ─────
# Para consistencia con el resto de URLs públicas (/u/{slug},
# /u/{slug}/catalogo, /u/{slug}/reservar), /u/{slug}/tarjeta es
# la ruta preferida. /loyalty/{slug} se mantiene por retro-compat.
# Soporta GET (navegador) y HEAD (probe de capability en landing).
@app.api_route("/u/{slug}/tarjeta", methods=["GET", "HEAD"],
               response_class=HTMLResponse, include_in_schema=False)
def public_loyalty_alias(slug: str, request: Request):
    return public_loyalty_page(slug, request)


# ── Páginas legales (términos, privacidad, cookies) ─────
@app.get("/legal/terms", response_class=HTMLResponse, include_in_schema=False)
def legal_terms_page(request: Request):
    return templates.TemplateResponse(request, "legal/terms.html", {"settings": settings})


@app.get("/legal/privacy", response_class=HTMLResponse, include_in_schema=False)
def legal_privacy_page(request: Request):
    return templates.TemplateResponse(request, "legal/privacy.html", {"settings": settings})


@app.get("/legal/cookies", response_class=HTMLResponse, include_in_schema=False)
def legal_cookies_page(request: Request):
    return templates.TemplateResponse(request, "legal/cookies.html", {"settings": settings})


# ── Mock checkout de pagos (entorno de desarrollo) ────────
@app.get("/pay/mock/{payment_id}", response_class=HTMLResponse, include_in_schema=False)
def mock_checkout(payment_id: str, request: Request):
    """Página mock de pago para entornos sin MercadoPago real configurado."""
    return templates.TemplateResponse(
        request, "payments/mock_checkout.html",
        {"settings": settings, "payment_id": payment_id},
    )


# ── Redirect de QR (short_code → destino) ────────────────
@app.get("/r/{short_code}")
def qr_redirect(short_code: str):
    """Resuelve un QR por short_code y redirige al destino configurado."""
    with SessionLocal() as db:
        svc = QrService(db)
        try:
            qr = svc.get_by_code(short_code)
        except Exception:
            return RedirectResponse(url="/", status_code=302)
        if not qr.is_active:
            return RedirectResponse(url="/", status_code=302)
        svc.record_scan(qr)

        slug = None
        with SessionLocal() as db2:
            from app.models.tenant import Tenant
            t = db2.get(Tenant, qr.tenant_id)
            if t:
                slug = t.slug

        if not slug:
            return RedirectResponse(url="/", status_code=302)

        if qr.target_type == QrTarget.CATALOG:
            return RedirectResponse(url=f"/u/{slug}/catalogo?qr={qr.short_code}", status_code=302)
        if qr.target_type == QrTarget.LANDING:
            return RedirectResponse(url=f"/u/{slug}?qr={qr.short_code}", status_code=302)
        if qr.target_type == QrTarget.PRODUCT and qr.target_id:
            from app.models.product import Product
            p = db2.get(Product, qr.target_id)
            if p:
                return RedirectResponse(url=f"/u/{slug}/catalogo?product={p.slug}&qr={qr.short_code}", status_code=302)
        if qr.target_type == QrTarget.CATEGORY and qr.target_id:
            from app.models.category import Category
            c = db2.get(Category, qr.target_id)
            if c:
                return RedirectResponse(url=f"/u/{slug}/catalogo?category={c.slug}&qr={qr.short_code}", status_code=302)
        if qr.target_type == QrTarget.EXTERNAL_URL and qr.external_url:
            return RedirectResponse(url=qr.external_url, status_code=302)
        return RedirectResponse(url=f"/u/{slug}?qr={qr.short_code}", status_code=302)


# ── PWA, sitemap, robots ─────────────────────────────────
@app.get("/manifest.json", include_in_schema=False)
def pwa_manifest():
    return {
        "name": "WowHub",
        "short_name": "WowHub",
        "description": "Plataforma SaaS modular para PyMEs en LATAM",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#0b1220",
        "theme_color": "#06b6d4",
        "icons": [
            {"src": "/static/icons/icon-192.png", "sizes": "192x192", "type": "image/png"},
            {"src": "/static/icons/icon-512.png", "sizes": "512x512", "type": "image/png"},
        ],
    }


@app.get("/sw.js", include_in_schema=False)
def service_worker():
    sw_path = STATIC_DIR / "sw.js"
    if sw_path.exists():
        return FileResponse(sw_path, media_type="application/javascript")
    # Fallback mínimo
    return PlainTextResponse(
        "self.addEventListener('install',e=>self.skipWaiting());"
        "self.addEventListener('fetch',e=>{});"
    )


@app.get("/robots.txt", include_in_schema=False)
def robots_txt():
    base = settings.public_base_url or "https://wowhub.app"
    return PlainTextResponse(
        f"User-agent: *\nAllow: /\nSitemap: {base}/sitemap.xml\n"
    )


@app.get("/sitemap.xml", include_in_schema=False)
def sitemap_xml():
    base = settings.public_base_url or "https://wowhub.app"
    urls = [
        f"{base}/",
        f"{base}/login",
        f"{base}/register",
        f"{base}/legal/terms",
        f"{base}/legal/privacy",
        f"{base}/legal/cookies",
    ]
    body = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "".join(f"  <url><loc>{u}</loc></url>\n" for u in urls)
        + "</urlset>\n"
    )
    return HTMLResponse(body, media_type="application/xml")


# ── Manejadores de error ─────────────────────────────────
@app.exception_handler(StarletteHTTPException)
async def http_error_handler(request: Request, exc: StarletteHTTPException):
    if request.url.path.startswith("/api/"):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    return templates.TemplateResponse(
        request,
        "public/404.html" if exc.status_code == 404 else "public/error.html",
        {"settings": settings, "detail": exc.detail, "status": exc.status_code},
        status_code=exc.status_code,
    )


@app.get("/health", tags=["meta"])
def health():
    return {
        "status": "ok",
        "version": "0.2.0",
        "env": settings.app_env,
        "db": _db_kind,
        "service": "wowhub-api",
    }
