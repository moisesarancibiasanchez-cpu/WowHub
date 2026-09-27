"""Marketplace API — plugin ecosystem (HU_45).

Tenant endpoints (require JWT auth via headers):
  GET  /marketplace/                        → list active plugins
  GET  /marketplace/{slug}                  → plugin detail
  POST /marketplace/{slug}/install           → subscribe tenant
  POST /marketplace/{slug}/uninstall         → cancel subscription
  GET  /marketplace/my-plugins              → tenant's installed plugins
  PATCH /marketplace/my-plugins/{slug}/config → update plugin config

Admin endpoints (require superuser):
  POST   /admin/marketplace/                 → publish plugin
  PATCH  /admin/marketplace/{id}            → update plugin
  DELETE /admin/marketplace/{id}            → remove plugin
  POST   /admin/marketplace/seed             → seed 5 example plugins
"""
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.deps import get_current_user, get_current_membership, require_superuser
from app.models.tenant import TenantMembership
from app.models.user import User
from app.models.marketplace import MarketplacePlugin, PluginSubscription
from app.schemas.marketplace import (
    MarketplacePluginCreate, MarketplacePluginUpdate, MarketplacePluginResponse,
    PluginSubscriptionCreate, PluginSubscriptionUpdate, PluginSubscriptionResponse,
    MarketplaceListResponse,
)
from app.core.errors import NotFoundError

router = APIRouter(tags=["marketplace"])

# ─────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────

def _get_plugin_by_slug(db: Session, slug: str) -> MarketplacePlugin:
    p = db.query(MarketplacePlugin).filter(
        MarketplacePlugin.slug == slug,
        MarketplacePlugin.is_active == True,
    ).first()
    if not p:
        raise NotFoundError(f"Plugin '{slug}' not found or inactive")
    return p


def _get_subscription(db: Session, tenant_id: UUID, plugin_id: UUID) -> Optional[PluginSubscription]:
    return db.query(PluginSubscription).filter(
        PluginSubscription.tenant_id == tenant_id,
        PluginSubscription.plugin_id == plugin_id,
        PluginSubscription.status == "active",
    ).first()


def _require_tenant(request: Request, db: Session, user: User = Depends(get_current_user)) -> User:
    """Ensure the request has a tenant context."""
    tenant_id = request.headers.get("x-tenant-id") or getattr(request.state, "tenant_id", None)
    if not tenant_id:
        # Try via membership
        membership = db.query(TenantMembership).filter(
            TenantMembership.user_id == str(user.id)
        ).first()
        if not membership:
            raise HTTPException(status_code=401, detail="No tenant context")
    return user


# ─────────────────────────────────────────────────────────────────
# Tenant endpoints
# ─────────────────────────────────────────────────────────────────

@router.get("/", response_model=MarketplaceListResponse)
def list_marketplace_plugins(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    category: Optional[str] = Query(None, description="Filter by category"),
    search: Optional[str] = Query(None, description="Search name/description"),
    page: int = Query(1, ge=1),
    per_page: int = Query(12, ge=1, le=100),
):
    """List all active marketplace plugins with pagination and filters."""
    q = db.query(MarketplacePlugin).filter(MarketplacePlugin.is_active == True)

    if category:
        q = q.filter(MarketplacePlugin.category == category)

    if search:
        pattern = f"%{search}%"
        q = q.filter(
            (MarketplacePlugin.name.ilike(pattern)) |
            (MarketplacePlugin.description.ilike(pattern))
        )

    total = q.count()
    pages = (total + per_page - 1) // per_page if total > 0 else 1
    items = q.order_by(
        MarketplacePlugin.is_featured.desc(),
        MarketplacePlugin.installs.desc(),
    ).offset((page - 1) * per_page).limit(per_page).all()

    return MarketplaceListResponse(
        items=[MarketplacePluginResponse.model_validate(p) for p in items],
        total=total,
        page=page,
        per_page=per_page,
        pages=pages,
    )


@router.get("/{slug}", response_model=MarketplacePluginResponse)
def get_marketplace_plugin(
    slug: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get details for a specific plugin."""
    plugin = _get_plugin_by_slug(db, slug)
    return MarketplacePluginResponse.model_validate(plugin)


@router.post("/{slug}/install", response_model=PluginSubscriptionResponse, status_code=201)
def install_plugin(
    slug: str,
    body: Optional[PluginSubscriptionCreate] = None,
    request: Request = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Install a plugin for the current tenant (creates subscription)."""
    plugin = _get_plugin_by_slug(db, slug)

    # Resolve tenant_id from header or state
    tenant_id_str = request.headers.get("x-tenant-id") if request else None
    if not tenant_id_str:
        membership = db.query(TenantMembership).filter(
            TenantMembership.user_id == str(user.id)
        ).first()
        if not membership:
            raise HTTPException(status_code=400, detail="No tenant found for user")
        tenant_id = UUID(membership.tenant_id)
    else:
        tenant_id = UUID(tenant_id_str)

    # Check if already subscribed
    existing = _get_subscription(db, tenant_id, plugin.id)
    if existing:
        raise HTTPException(status_code=409, detail="Plugin already installed")

    config_json = body.config if body else None
    sub = PluginSubscription(
        tenant_id=tenant_id,
        plugin_id=plugin.id,
        status="active",
        config=config_json,
        revenue_share_70_to_developer=True,
    )
    db.add(sub)

    # Increment install count
    plugin.installs = (plugin.installs or 0) + 1

    db.commit()
    db.refresh(sub)
    return PluginSubscriptionResponse.model_validate(sub)


@router.post("/{slug}/uninstall", status_code=204)
def uninstall_plugin(
    slug: str,
    request: Request = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Uninstall a plugin for the current tenant (marks subscription canceled)."""
    plugin = _get_plugin_by_slug(db, slug)

    tenant_id_str = request.headers.get("x-tenant-id") if request else None
    if not tenant_id_str:
        membership = db.query(TenantMembership).filter(
            TenantMembership.user_id == str(user.id)
        ).first()
        if not membership:
            raise HTTPException(status_code=400, detail="No tenant found for user")
        tenant_id = UUID(membership.tenant_id)
    else:
        tenant_id = UUID(tenant_id_str)

    sub = _get_subscription(db, tenant_id, plugin.id)
    if not sub:
        raise HTTPException(status_code=404, detail="Plugin not installed")

    sub.status = "canceled"
    sub.canceled_at = datetime.now(timezone.utc)
    db.commit()


@router.get("/my-plugins", response_model=list[PluginSubscriptionResponse])
def my_plugins(
    request: Request = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List plugins installed for the current tenant."""
    tenant_id_str = request.headers.get("x-tenant-id") if request else None
    if not tenant_id_str:
        membership = db.query(TenantMembership).filter(
            TenantMembership.user_id == str(user.id)
        ).first()
        if not membership:
            return []
        tenant_id = UUID(membership.tenant_id)
    else:
        tenant_id = UUID(tenant_id_str)

    subs = db.query(PluginSubscription).options(
        joinedload(PluginSubscription.__dict__.get('plugin', None) if hasattr(PluginSubscription, 'plugin') else None)
    ).filter(
        PluginSubscription.tenant_id == tenant_id,
        PluginSubscription.status == "active",
    ).all()

    # Manually eager-load plugin
    plugin_ids = [sub.plugin_id for sub in subs]
    plugins_map = {
        p.id: p for p in db.query(MarketplacePlugin).filter(
            MarketplacePlugin.id.in_(plugin_ids)
        ).all()
    }

    result = []
    for sub in subs:
        resp = PluginSubscriptionResponse.model_validate(sub)
        resp.plugin = MarketplacePluginResponse.model_validate(plugins_map.get(sub.plugin_id))
        result.append(resp)
    return result


@router.patch("/my-plugins/{slug}/config", response_model=PluginSubscriptionResponse)
def update_plugin_config(
    slug: str,
    body: PluginSubscriptionUpdate,
    request: Request = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Update the configuration for an installed plugin."""
    plugin = _get_plugin_by_slug(db, slug)

    tenant_id_str = request.headers.get("x-tenant-id") if request else None
    if not tenant_id_str:
        membership = db.query(TenantMembership).filter(
            TenantMembership.user_id == str(user.id)
        ).first()
        if not membership:
            raise HTTPException(status_code=400, detail="No tenant found for user")
        tenant_id = UUID(membership.tenant_id)
    else:
        tenant_id = UUID(tenant_id_str)

    sub = _get_subscription(db, tenant_id, plugin.id)
    if not sub:
        raise HTTPException(status_code=404, detail="Plugin not installed")

    if body.config is not None:
        sub.config = body.config
    if body.status is not None:
        sub.status = body.status
        if body.status == "canceled":
            sub.canceled_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(sub)

    resp = PluginSubscriptionResponse.model_validate(sub)
    resp.plugin = MarketplacePluginResponse.model_validate(plugin)
    return resp


# ─────────────────────────────────────────────────────────────────
# Admin endpoints
# ─────────────────────────────────────────────────────────────────

admin_router = APIRouter(prefix="/admin/marketplace", tags=["marketplace-admin"])


@admin_router.post("/", response_model=MarketplacePluginResponse, status_code=201)
def admin_create_plugin(
    body: MarketplacePluginCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_superuser),
):
    """Publish a new marketplace plugin. Requires superadmin."""
    existing = db.query(MarketplacePlugin).filter(
        MarketplacePlugin.slug == body.slug
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"Plugin with slug '{body.slug}' already exists")

    plugin = MarketplacePlugin(
        name=body.name,
        slug=body.slug,
        description=body.description,
        version=body.version,
        category=body.category,
        pip_package=body.pip_package,
        git_url=body.git_url,
        install_script=body.install_script,
        config_schema=body.config_schema,
        is_active=body.is_active,
        is_featured=body.is_featured,
        is_paid=body.is_paid,
        price_monthly_usd=body.price_monthly_usd,
        published_by=user.id,
    )
    db.add(plugin)
    db.commit()
    db.refresh(plugin)
    return MarketplacePluginResponse.model_validate(plugin)


@admin_router.patch("/{plugin_id}", response_model=MarketplacePluginResponse)
def admin_update_plugin(
    plugin_id: UUID,
    body: MarketplacePluginUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_superuser),
):
    """Update a marketplace plugin. Requires superadmin."""
    plugin = db.get(MarketplacePlugin, plugin_id)
    if not plugin:
        raise HTTPException(status_code=404, detail="Plugin not found")

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(plugin, field, value)

    db.commit()
    db.refresh(plugin)
    return MarketplacePluginResponse.model_validate(plugin)


@admin_router.delete("/{plugin_id}", status_code=204)
def admin_delete_plugin(
    plugin_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_superuser),
):
    """Remove a marketplace plugin. Requires superadmin."""
    plugin = db.get(MarketplacePlugin, plugin_id)
    if not plugin:
        raise HTTPException(status_code=404, detail="Plugin not found")

    db.delete(plugin)
    db.commit()


class SeedResult(BaseModel):
    created: int
    message: str


@admin_router.post("/seed", response_model=SeedResult)
def admin_seed_plugins(
    db: Session = Depends(get_db),
    user: User = Depends(require_superuser),
):
    """Seed 5 example marketplace plugins. Requires superadmin."""
    from app.seed import seed_marketplace_plugins as _seed_fn
    created = _seed_fn(db)
    return SeedResult(created=created, message=f"Seeded {created} plugins")
