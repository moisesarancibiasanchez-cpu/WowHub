"""App principal FastAPI — incluye API, UI server-rendered, y redirect de QR."""
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.v1 import auth, branches, categories, customers, landing, products, promotions, public, qrs, tenants
from app.config import settings
from app.database import SessionLocal, init_db
from app.models.qr import QrCode, QrTarget
from app.services.qr_service import QrService

logging.basicConfig(level=settings.log_level)
logger = logging.getLogger("wowhub")

BASE_DIR = Path(__file__).parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Inicializando base de datos...")
    init_db()
    logger.info(f"WowHub arrancado — env={settings.app_env}, db={settings.database_url}")
    yield
    # Shutdown
    logger.info("WowHub cerrando.")


app = FastAPI(
    title="WowHub API",
    description=(
        "Plataforma SaaS modular para PyMEs en LATAM.\n\n"
        "Esta API cubre las 4 features del MVP: **Página**, **Catálogo**, **QR** y **Promociones**, "
        "sobre una arquitectura multi-tenant."
    ),
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# API v1
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


# ── Rutas de UI (server-rendered) ────────────────────
@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def home(request: Request):
    return templates.TemplateResponse(request, "home.html", {"settings": settings})


@app.get("/login", response_class=HTMLResponse, include_in_schema=False)
def login_page(request: Request):
    return templates.TemplateResponse(request, "auth/login.html", {"settings": settings})


@app.get("/register", response_class=HTMLResponse, include_in_schema=False)
def register_page(request: Request):
    return templates.TemplateResponse(request, "auth/register.html", {"settings": settings})


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


# ── Páginas públicas por tenant ──────────────────────
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


# ── Redirect de QR (short_code → destino) ────────────
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
        # métricas
        svc.record_scan(qr)

        # Resolver destino
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


# ── Manejadores de error ─────────────────────────────
@app.exception_handler(StarletteHTTPException)
async def http_error_handler(request: Request, exc: StarletteHTTPException):
    if request.url.path.startswith("/api/"):
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    return templates.TemplateResponse(
        request,
        "public/404.html" if exc.status_code == 404 else "public/error.html",
        {"settings": settings, "detail": exc.detail, "status": exc.status_code},
        status_code=exc.status_code,
    )


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok", "version": "0.1.0", "env": settings.app_env}
