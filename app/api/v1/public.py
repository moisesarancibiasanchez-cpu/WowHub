"""Public endpoints — SIN auth. Catálogo, landing, redirect de QR."""
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.landing import LandingConfig
from app.models.product import Product, ProductStatus
from app.models.promotion import Promotion
from app.models.qr import QrCode, QrTarget
from app.models.tenant import Tenant
from app.services.qr_service import QrService
from app.services.product_service import ProductService

router = APIRouter(prefix="/public", tags=["public"])


# ── Resolver tenant por slug ──────────────────────────
def _resolve_tenant(slug: str, db: Session) -> Tenant:
    t = db.execute(select(Tenant).where(Tenant.slug == slug)).scalar_one_or_none()
    if not t or not t.is_active:
        from app.core.errors import NotFoundError
        raise NotFoundError("Tenant")
    return t


@router.get("/t/{slug}/profile")
def public_profile(slug: str, db: Session = Depends(get_db)):
    """Datos públicos del tenant (logo, nombre, contacto)."""
    t = _resolve_tenant(slug, db)
    landing = db.query(LandingConfig).filter(LandingConfig.tenant_id == str(t.id)).first()
    return {
        "slug": t.slug,
        "display_name": t.display_name,
        "industry": t.industry.value,
        "country": t.country,
        "locale": t.locale,
        "currency": t.currency,
        "branding": {
            "brand_color": landing.brand_color if landing else "#7c5cff",
            "accent_color": landing.accent_color if landing else "#00d4a8",
            "logo_url": landing.logo_url if landing else None,
        } if landing else None,
    }


@router.get("/t/{slug}/catalog")
def public_catalog(
    slug: str,
    db: Session = Depends(get_db),
    category: str | None = None,
    search: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(24, ge=1, le=100),
):
    t = _resolve_tenant(slug, db)
    svc = ProductService(db)
    result = svc.list(
        t.id,
        page=page,
        page_size=page_size,
        search=search,
        status=ProductStatus.ACTIVE,
        category_id=UUID(category) if category else None,
        is_featured=None,
        order_by="position",
    )
    return result


@router.get("/t/{slug}/products/{product_slug}")
def public_product(slug: str, product_slug: str, db: Session = Depends(get_db)):
    t = _resolve_tenant(slug, db)
    svc = ProductService(db)
    p = svc.get_by_slug(t.id, product_slug)
    svc.increment_view(p)
    return svc.to_out(p)


@router.get("/t/{slug}/promotions")
def public_promotions(slug: str, db: Session = Depends(get_db)):
    t = _resolve_tenant(slug, db)
    now = datetime.now(timezone.utc)
    items = list(db.execute(
        select(Promotion).where(
            Promotion.tenant_id == str(t.id),
            Promotion.is_active == True,  # noqa: E712
            Promotion.is_public == True,  # noqa: E712
        ).order_by(Promotion.priority.desc())
    ).scalars())
    out = []
    for p in items:
        if p.starts_at and p.starts_at.replace(tzinfo=timezone.utc) > now:
            continue
        if p.ends_at and p.ends_at.replace(tzinfo=timezone.utc) < now:
            continue
        if p.usage_limit and p.used_count >= p.usage_limit:
            continue
        out.append({
            "id": str(p.id),
            "name": p.name,
            "description": p.description,
            "code": p.code,
            "promo_type": p.promo_type.value,
            "discount_type": p.discount_type.value,
            "discount_value": p.discount_value,
            "badge_text": p.badge_text,
            "color": p.color,
            "image_url": p.image_url,
        })
    return out


@router.get("/t/{slug}/categories")
def public_categories(slug: str, db: Session = Depends(get_db)):
    from app.models.category import Category
    t = _resolve_tenant(slug, db)
    return list(db.execute(
        select(Category).where(
            Category.tenant_id == str(t.id),
            Category.is_active == True,  # noqa: E712
        ).order_by(Category.position, Category.name)
    ).scalars())


@router.get("/t/{slug}/branches")
def public_branches(slug: str, db: Session = Depends(get_db)):
    from app.models.branch import Branch
    t = _resolve_tenant(slug, db)
    return list(db.execute(
        select(Branch).where(
            Branch.tenant_id == str(t.id),
            Branch.is_active == True,  # noqa: E712
        ).order_by(Branch.is_main.desc(), Branch.name)
    ).scalars())


@router.get("/t/{slug}/landing")
def public_landing(slug: str, db: Session = Depends(get_db)):
    t = _resolve_tenant(slug, db)
    cfg = db.query(LandingConfig).filter(LandingConfig.tenant_id == str(t.id)).first()
    if not cfg:
        return None
    return cfg
