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
)
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
