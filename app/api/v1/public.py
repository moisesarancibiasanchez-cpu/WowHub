"""Public endpoints — SIN auth. Catálogo, landing, redirect de QR."""
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.errors import NotFoundError, ValidationError
from app.database import get_db
from app.models.landing import LandingConfig
from app.models.order import OrderSource
from app.models.product import Product, ProductStatus
from app.models.promotion import Promotion
from app.models.qr import QrCode, QrTarget
from app.models.tenant import Tenant
from app.services.order_service import OrderService
from app.services.qr_service import QrService
from app.services.product_service import ProductService

router = APIRouter(prefix="/public", tags=["public"])


# ── Media pública del tenant ───────────────────────────────────────────
# El 2026-09-27 se desmontó el montaje público `/storage` por seguridad
# (exponía los archivos de TODOS los tenants sin autenticación). Pero las
# imágenes que el tenant sube desde el dashboard se guardaban con la URL
# `/storage/{tenant_id}/{archivo}`, que en producción NO existe → el hero,
# el logo y las fotos de producto de la landing no cargaban (404).
#
# La URL que sirve el contenido real es autenticada
# (`/api/v1/tenants/{tid}/uploads/{uid}/content`), así que la landing
# pública no podía usarla.
#
# Solución: un endpoint público POR SLUG que sólo sirve los uploads de uso
# público de ese tenant, más la reescritura de las URLs en el borde
# público. La URL guardada en la DB puede ser de las dos formas:
#   - /api/v1/tenants/{tid}/uploads/{uid}/content   (formato nuevo)
#   - .../storage/{tid}/{archivo}                   (formato legacy)
_PUBLIC_MEDIA_PURPOSES = frozenset({
    "landing_hero",
    "landing_logo",
    "product_image",
    "promotion",
    "promotion_image",
    # FIX V2.014 — el logo de la campaña de fidelización se sube desde el
    # dashboard (admin_loyalty.html) y se muestra en la tarjeta del
    # cliente, que es una página PÚBLICA sin sesión: sin esta entrada la
    # URL autenticada devolvía 401 y el logo no cargaba.
    "loyalty_campaign_logo",
})

_MEDIA_CONTENT_RE = re.compile(
    r"/api/v1/tenants/(?P<tenant>[0-9a-fA-F-]{36})"
    r"/uploads/(?P<upload>[0-9a-fA-F-]{36})/content"
)
_STORAGE_RE = re.compile(
    r"/storage/(?P<tenant>[0-9a-fA-F-]{36})/(?P<file>[^/?#]+)"
)


def _find_public_upload(url: str, tenant: Tenant, db: Session):
    """Devuelve el Upload público al que apunta ``url`` (o ``None``)."""
    from app.models.upload import Upload

    if not url:
        return None

    upload = None
    match = _MEDIA_CONTENT_RE.search(url)
    if match:
        upload = db.execute(
            select(Upload).where(Upload.id == match.group("upload"))
        ).scalar_one_or_none()
    else:
        match = _STORAGE_RE.search(url)
        if match:
            upload = db.execute(
                select(Upload).where(
                    Upload.tenant_id == str(tenant.id),
                    Upload.stored_filename == match.group("file"),
                )
            ).scalars().first()

    if upload is None:
        return None
    if str(upload.tenant_id) != str(tenant.id):
        return None
    if (upload.purpose or "") not in _PUBLIC_MEDIA_PURPOSES:
        return None
    return upload


def _public_media_url(url: Optional[str], tenant: Tenant, db: Session, slug: str):
    """Reescribe una URL de upload a la ruta pública por slug.

    Si la URL no apunta a un upload público de este tenant, se devuelve
    tal cual (por ejemplo, una URL externa).
    """
    if not url:
        return url
    upload = _find_public_upload(url, tenant, db)
    if upload is None:
        return url
    return f"/api/v1/public/t/{slug}/media/{upload.id}"



# ── Resolver tenant por slug ──────────────────────────
def _resolve_tenant(slug: str, db: Session) -> Tenant:
    t = db.execute(select(Tenant).where(Tenant.slug == slug)).scalar_one_or_none()
    if not t or not t.is_active:
        from app.core.errors import NotFoundError
        raise NotFoundError("Tenant")
    return t


@router.get("/t/{slug}/media/{upload_id}")
def public_tenant_media(
    slug: str,
    upload_id: UUID,
    db: Session = Depends(get_db),
):
    """Sirve una imagen PÚBLICA del tenant (hero, logo, foto de producto).

    FIX V2.012 — sin este endpoint las imágenes de la landing no cargaban:
    la URL guardada apuntaba a `/storage/...`, que ya no está montado en
    producción por seguridad (2026-09-27).

    Sólo se sirven uploads cuyo ``purpose`` es de uso público y que
    pertenecen a ESTE tenant. Cualquier otro archivo responde 404 (y no
    403: no se revela la existencia de recursos ajenos).
    """
    from fastapi import HTTPException

    from app.models.upload import Upload

    t = _resolve_tenant(slug, db)
    upload = db.execute(
        select(Upload).where(Upload.id == str(upload_id))
    ).scalar_one_or_none()
    if not upload or str(upload.tenant_id) != str(t.id):
        raise HTTPException(status_code=404, detail="Archivo no encontrado")
    if (upload.purpose or "") not in _PUBLIC_MEDIA_PURPOSES:
        raise HTTPException(status_code=404, detail="Archivo no encontrado")

    storage_dir = Path(settings.storage_dir)
    base_dir = (storage_dir / str(t.id)).resolve()
    candidate = (base_dir / upload.stored_filename).resolve()
    try:
        # Path traversal: el archivo debe quedar dentro de storage/{tenant_id}/
        candidate.relative_to(base_dir)
    except ValueError:
        raise HTTPException(status_code=400, detail="Ruta de archivo inválida")

    if not candidate.is_file():
        raise HTTPException(status_code=404, detail="Archivo no encontrado en disco")

    return FileResponse(
        candidate,
        media_type=upload.content_type or "application/octet-stream",
        headers={"Cache-Control": "public, max-age=3600"},
    )


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
            "logo_url": (
                _public_media_url(landing.logo_url, t, db, slug)
                if landing else None
            ),
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
    # FIX V2.012 — reescribe la URL de la foto de producto a la ruta
    # pública por slug (antes apuntaba a /storage, que no existe en prod).
    for item in result.items:
        if item.image_url:
            item.image_url = _public_media_url(item.image_url, t, db, slug)
    return result


@router.get("/t/{slug}/products/{product_slug}")
def public_product(slug: str, product_slug: str, db: Session = Depends(get_db)):
    t = _resolve_tenant(slug, db)
    svc = ProductService(db)
    p = svc.get_by_slug(t.id, product_slug)
    svc.increment_view(p)
    out = svc.to_out(p)
    if out.image_url:
        out.image_url = _public_media_url(out.image_url, t, db, slug)
    return out


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
            "image_url": _public_media_url(p.image_url, t, db, slug),
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
    """Configuración de la landing pública del tenant.

    FIX V2.012 — se devuelve una COPIA (dict) en lugar del objeto ORM: las
    URLs de hero/logo/favicon/seo_image se reescriben a la ruta pública por
    slug. Mutar el objeto ORM marcaría la fila como sucia y el siguiente
    commit de la sesión guardaría la URL reescrita en la DB.
    """
    t = _resolve_tenant(slug, db)
    cfg = db.query(LandingConfig).filter(LandingConfig.tenant_id == str(t.id)).first()
    if not cfg:
        return None

    data = {
        "id": str(cfg.id),
        "tenant_id": str(cfg.tenant_id),
        "hero_title": cfg.hero_title,
        "hero_subtitle": cfg.hero_subtitle,
        "hero_image_url": _public_media_url(cfg.hero_image_url, t, db, slug),
        "hero_cta_text": cfg.hero_cta_text,
        "hero_cta_url": cfg.hero_cta_url,
        "brand_color": cfg.brand_color,
        "accent_color": cfg.accent_color,
        "logo_url": _public_media_url(cfg.logo_url, t, db, slug),
        "favicon_url": _public_media_url(cfg.favicon_url, t, db, slug),
        "contact_whatsapp": cfg.contact_whatsapp,
        "contact_phone": cfg.contact_phone,
        "contact_email": cfg.contact_email,
        "contact_address": cfg.contact_address,
        "social_instagram": cfg.social_instagram,
        "social_facebook": cfg.social_facebook,
        "social_tiktok": cfg.social_tiktok,
        "show_categories": cfg.show_categories,
        "show_featured_products": cfg.show_featured_products,
        "show_promotions": cfg.show_promotions,
        "show_branches": cfg.show_branches,
        "show_contact": cfg.show_contact,
        "seo_title": cfg.seo_title,
        "seo_description": cfg.seo_description,
        "seo_image_url": _public_media_url(cfg.seo_image_url, t, db, slug),
        "custom_css": cfg.custom_css,
        "extra_blocks": cfg.extra_blocks,
    }
    return data


# ════════════════════════════════════════════════════════════════════════
# HU_16 — Pedidos desde QR (flujo público, sin auth)
# ════════════════════════════════════════════════════════════════════════
class QROrderItem(BaseModel):
    """Item de la orden QR (sin auth)."""
    product_id: UUID = Field(..., description="UUID del producto")
    quantity: int = Field(1, ge=1, le=99)


class QROrderCreate(BaseModel):
    """Body de POST /public/orders/from-qr/{qr_id}."""
    items: list[QROrderItem] = Field(..., min_length=1, description="Líneas del pedido")
    customer_phone: Optional[str] = Field(None, max_length=40)
    customer_name: Optional[str] = Field(None, max_length=200)
    notes: Optional[str] = Field(None, max_length=1000)


@router.post("/orders/from-qr/{qr_id}", status_code=201)
def public_create_order_from_qr(
    qr_id: UUID,
    payload: QROrderCreate,
    db: Session = Depends(get_db),
):
    """Crea un pedido en estado RECIBIDO a partir de un QR público.

    Flujo típico: el cliente escanea el QR de la mesa/catálogo y la página
    pública llama a este endpoint con los productos seleccionados. Sin auth
    (igual que el resto de ``/public/*``). El ``source`` del pedido se setea
    a ``"qr"`` para que el dashboard Kanban lo agrupe en el canal correcto.

    Validaciones:
    - El QR debe existir y estar activo.
    - El QR debe tener ``branch_id`` (mesa/sucursal física) para asignar el
      pedido. Si no, igual creamos el pedido pero sin branch (no es bloqueante).
    - Todos los productos deben pertenecer al mismo tenant del QR.
    - Devuelve el ``order_id`` y ``order_number`` para que el cliente pueda
      mostrarlo en la confirmación.
    """
    qr = db.get(QrCode, qr_id)
    if not qr:
        raise NotFoundError("QR")
    if not qr.is_active:
        raise ValidationError("Este QR está inactivo. Escanea uno vigente.")

    tenant = db.get(Tenant, qr.tenant_id)
    if not tenant or not tenant.is_active:
        raise NotFoundError("Negocio")

    # Construir items resolviendo productos (OrderService.create valida
    # pertenencia al tenant).
    items_payload = [
        {"product_id": it.product_id, "quantity": it.quantity, "options": {}}
        for it in payload.items
    ]

    try:
        order = OrderService(db).create(
            tenant,
            items=items_payload,
            customer_phone=payload.customer_phone,
            customer_name=payload.customer_name,
            notes=payload.notes,
            source=OrderSource.QR.value,
            qr_code_id=qr.id,
        )
        # Si el QR tenía branch_id, lo asignamos explícitamente al pedido
        # (OrderService.create() siempre lo deja en None hoy).
        if qr.branch_id:
            order.branch_id = str(qr.branch_id)
        # Incrementar el contador de conversiones del QR (el QR "convirtió"
        # cuando generó un pedido).
        qr.conversion_count += 1
        db.commit()
        db.refresh(order)
        return {
            "order_id": str(order.id),
            "order_number": order.number,
            "status": order.status.value if hasattr(order.status, "value") else order.status,
            "total_cents": order.total_cents,
            "currency": order.currency,
            "tenant_id": str(order.tenant_id),
            "source": order.source.value if hasattr(order.source, "value") else order.source,
        }
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        # Re-raise para que FastAPI lo serialice como 400/422 según corresponda.
        raise
