"""Product endpoints.

Fase 3 (V8): el listado y el detalle ahora incluyen los derivados
de pricing (costo real, margen, salud). Hay además un endpoint
``GET /products/{id}/pricing`` que devuelve el breakdown completo
para alimentar la calculadora del modal de edición.

HU_11 — Endpoints dedicados de margen y simulación:
  * ``GET  /products/{id}/margin``             → margen actual
  * ``POST /products/{id}/margin/simulate``    → simula cambio de costo
"""
from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

# HU_38 — RBAC granular con Casbin. Importamos el decorator para proteger
# los endpoints sensibles (delete, write) según la matriz del usuario.
from app.core.security import requires_permission
from app.database import get_db
from app.deps import get_current_membership, get_tenant_for_membership
from app.models.product import ProductStatus
from app.models.tenant import Tenant
from app.models.tenant import TenantMembership
from app.schemas.common import Page
from app.schemas.product import (
    ProductCreate,
    ProductOut,
    ProductUpdate,
    ProductListItem,
    MarginOut,
    MarginSimulateIn,
    MarginSimulateOut,
)
from app.services.product_pricing import (
    ProductPricing,
    compute_for_product,
    compute_margin_pct,
    compute_real_cost,
    compute_suggested_price,
    health_for_margin,
    health_message,
)
from app.services.product_service import ProductService

router = APIRouter(prefix="/tenants/{tenant_id}/products", tags=["products"])


# ── HU_11 — helper local para armar MarginOut ─────────────
def _build_margin_out(p, pricing: ProductPricing) -> MarginOut:
    """Arma un MarginOut desde un Product + ProductPricing.

    Centraliza el cálculo de `margin_cents` para que tanto el GET
    como el POST /simulate devuelvan exactamente la misma forma.
    """
    price = int(p.price_cents or 0)
    real = int(pricing.cost_real_cents or 0)
    return MarginOut(
        product_id=p.id,
        cost_cents=int(p.cost_cents or 0),
        cost_real_cents=real,
        price_cents=price,
        margin_cents=price - real,
        margin_pct=pricing.current_margin_pct,
        target_margin_pct=pricing.target_margin_pct,
        suggested_price_cents=int(pricing.suggested_price_cents or 0),
        cost_hour_used_cents=int(pricing.cost_hour_used_cents or 0),
        health=pricing.health,
        health_message=pricing.health_message,
    )


@router.get("", response_model=Page[ProductListItem])
def list_products(
    tenant: Tenant = Depends(get_tenant_for_membership),
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    search: str | None = None,
    status: ProductStatus | None = None,
    category_id: UUID | None = None,
    is_featured: bool | None = None,
    order_by: str = Query("position", pattern="^(position|name|price|created|sold)$"),
):
    return ProductService(db).list(
        tenant.id,
        page=page,
        page_size=page_size,
        search=search,
        status=status,
        category_id=category_id,
        is_featured=is_featured,
        order_by=order_by,
    )


@router.post("", response_model=ProductOut, status_code=201)
@requires_permission("product", "write")
def create_product(
    payload: ProductCreate,
    tenant: Tenant = Depends(get_tenant_for_membership),
    db: Session = Depends(get_db),
    # HU_38 — membership explícito para que el decorator RBAC pueda
    # resolver el rol del usuario contra Casbin. FastAPI cachea la
    # dependencia dentro del request (mismo callable que
    # ``get_tenant_for_membership``), sin DB extra.
    membership: TenantMembership = Depends(get_current_membership),
):
    """HU_38 — crear producto requiere ``product.write``.

    Roles permitidos (matriz default seed): OWNER, ADMIN, STAFF.
    VIEWER y CASHIER quedan fuera por falta de policy.
    """
    p = ProductService(db).create(tenant.id, payload)
    return ProductService(db).to_out(p)


@router.get("/{product_id}", response_model=ProductOut)
def get_product(
    product_id: UUID,
    tenant: Tenant = Depends(get_tenant_for_membership),
    db: Session = Depends(get_db),
    increment_view: bool = False,
):
    svc = ProductService(db)
    p = svc.get(tenant.id, product_id)
    if increment_view:
        svc.increment_view(p)
    return svc.to_out(p)


@router.get("/{product_id}/pricing", response_model=ProductOut)
def get_product_pricing(
    product_id: UUID,
    tenant: Tenant = Depends(get_tenant_for_membership),
    db: Session = Depends(get_db),
):
    """Devuelve el producto con todos los derivados de pricing (Fase 3).

    Útil para la calculadora del modal: la UI puede pedirla cada vez
    que el usuario cambia `cost_cents`, `production_time_min` o
    `price_cents` y mostrar el resultado en vivo.
    """
    svc = ProductService(db)
    p = svc.get(tenant.id, product_id)
    return svc.to_out(p)


# ── HU_11 — Margen actual ────────────────────────────────
@router.get("/{product_id}/margin", response_model=MarginOut)
def get_product_margin(
    product_id: UUID,
    tenant: Tenant = Depends(get_tenant_for_membership),
    db: Session = Depends(get_db),
):
    """HU_11 — Devuelve el margen actual del producto.

    Lee el producto + ``BusinessCosts`` del tenant (si existe) y
    devuelve el desglose:

    - ``cost_cents``     → costo de insumos cargado
    - ``cost_real_cents``→ costo real (insumos + mano de obra)
    - ``price_cents``    → precio de venta
    - ``margin_cents``   → ``price - cost_real``
    - ``margin_pct``     → porcentaje de margen
    - ``suggested_price_cents`` → según margen objetivo del tenant
    - ``health``         → clasificación (healthy/warning/danger/unknown)

    RBAC: solo requiere acceso al tenant (read via membership).
    No expone ni modifica datos, por eso NO usa ``@requires_permission``.
    """
    svc = ProductService(db)
    p = svc.get(tenant.id, product_id)
    cost_hour, target = svc._pricing_for(p.tenant_id)
    pricing = compute_for_product(
        p,
        cost_hour_cents=cost_hour,
        target_margin_pct=target,
    )
    return _build_margin_out(p, pricing)


# ── HU_11 — Simulación de cambio de costo ─────────────────
@router.post("/{product_id}/margin/simulate", response_model=MarginSimulateOut)
def simulate_product_margin(
    product_id: UUID,
    payload: MarginSimulateIn,
    tenant: Tenant = Depends(get_tenant_for_membership),
    db: Session = Depends(get_db),
):
    """HU_11 — Simula un cambio en el costo de insumos y proyecta el margen.

    Recibe ``{"new_cost_cents": <int>}`` y devuelve dos snapshots:

    - ``current``  → margen vigente (igual a ``GET /margin``).
    - ``projected_*`` → margen si el producto tuviera
      ``cost_cents = new_cost_cents``.

    La mano de obra y el costo_hora del tenant se mantienen: el
    simulador solo varía el componente materiales. El producto NO
    se modifica en la DB (es un what-if puro).

    RBAC: solo requiere acceso al tenant (read via membership).
    """
    svc = ProductService(db)
    p = svc.get(tenant.id, product_id)
    cost_hour, target = svc._pricing_for(p.tenant_id)

    # Snapshot actual (reusa la misma lógica del GET /margin)
    current_pricing = compute_for_product(
        p,
        cost_hour_cents=cost_hour,
        target_margin_pct=target,
    )
    current = _build_margin_out(p, current_pricing)

    # Proyección con el nuevo costo de insumos
    projected_real = compute_real_cost(
        payload.new_cost_cents,
        int(p.production_time_min or 0),
        int(cost_hour or 0),
    )
    price = int(p.price_cents or 0)
    projected_margin_pct = compute_margin_pct(price, projected_real)
    projected_margin_cents = price - projected_real

    # Precio sugerido + health proyectado (mismo patrón que compute_for_product)
    if target is None or target <= 0:
        projected_suggested = 0
        projected_health = "unknown" if projected_margin_pct is None else (
            "healthy" if projected_margin_pct >= 0 else "danger"
        )
        projected_msg: Optional[str] = None
    else:
        projected_suggested = compute_suggested_price(projected_real, target)
        projected_health = health_for_margin(projected_margin_pct, target)
        projected_msg = health_message(
            projected_health,
            current_margin_pct=projected_margin_pct,
            target_margin_pct=target,
            suggested_price_cents=projected_suggested,
            price_cents=price,
        )

    return MarginSimulateOut(
        current=current,
        projected_cost_cents=payload.new_cost_cents,
        projected_cost_real_cents=projected_real,
        projected_margin_cents=projected_margin_cents,
        projected_margin_pct=projected_margin_pct,
        projected_suggested_price_cents=projected_suggested,
        projected_health=projected_health,
        projected_health_message=projected_msg,
    )


@router.patch("/{product_id}", response_model=ProductOut)
@requires_permission("product", "write")
def update_product(
    product_id: UUID,
    payload: ProductUpdate,
    tenant: Tenant = Depends(get_tenant_for_membership),
    db: Session = Depends(get_db),
    # HU_38 — ver create_product. Mismo patrón de inyección explícita.
    membership: TenantMembership = Depends(get_current_membership),
):
    """HU_38 — actualizar producto requiere ``product.write``."""
    svc = ProductService(db)
    p = svc.get(tenant.id, product_id)
    p = svc.update(p, payload)
    return svc.to_out(p)


@router.delete("/{product_id}", status_code=204)
@requires_permission("product", "delete")
def delete_product(
    product_id: UUID,
    tenant: Tenant = Depends(get_tenant_for_membership),
    db: Session = Depends(get_db),
    # HU_38 — ver create_product. Mismo patrón de inyección explícita.
    membership: TenantMembership = Depends(get_current_membership),
):
    """HU_38 — eliminar producto requiere ``product.delete``.

    Roles permitidos (matriz default seed): OWNER, ADMIN.
    STAFF y VIEWER quedan fuera (sin policy de delete en el seed).
    Esto cierra el hueco donde cualquier miembro del tenant podía
    borrar productos antes de HU_38.
    """
    svc = ProductService(db)
    p = svc.get(tenant.id, product_id)
    svc.delete(p)
