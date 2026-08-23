"""Endpoints de Costos (BusinessCosts).

  GET    /tenants/{id}/costs              → Config editada (con defaults)
  PUT    /tenants/{id}/costs              → Update + recálculo
  GET    /tenants/{id}/costs/breakdown    → Totales por sección + costo_hora
  GET    /tenants/{id}/costs/fields-meta  → Lista canónica de campos (para UI)
  POST   /tenants/{id}/costs/pricing-suggestion
                                          → Sugerencia de precio para un producto

Todos requieren membresía activa al tenant.
"""
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_tenant_for_membership
from app.models.tenant import Tenant
from app.schemas.business_costs import (
    BusinessCostsBreakdown,
    BusinessCostsRead,
    BusinessCostsUpdate,
    PricingSuggestionRequest,
    PricingSuggestionResponse,
)
from app.services.costs_service import COST_FIELDS_META, CostsService


router = APIRouter(prefix="/tenants/{tenant_id}/costs", tags=["costs"])


@router.get("", response_model=BusinessCostsRead)
def get_costs(
    tenant: Tenant = Depends(get_tenant_for_membership),
    db: Session = Depends(get_db),
):
    """Lee la config de costos del tenant. Si no existe, la crea con defaults."""
    return CostsService(db).get_for_tenant(tenant.id)


@router.put("", response_model=BusinessCostsRead)
def put_costs(
    payload: BusinessCostsUpdate,
    tenant: Tenant = Depends(get_tenant_for_membership),
    db: Session = Depends(get_db),
):
    """Actualiza la config completa y recalcula costo_hora + total fijo."""
    return CostsService(db).update_for_tenant(tenant.id, payload)


@router.get("/breakdown", response_model=BusinessCostsBreakdown)
def get_breakdown(
    tenant: Tenant = Depends(get_tenant_for_membership),
    db: Session = Depends(get_db),
):
    """Totales por sección (Personal / Básicos / Otros) + costo_hora."""
    return CostsService(db).breakdown(tenant.id)


@router.get("/fields-meta")
def get_fields_meta():
    """Metadata estática de los 14+2 campos. Cacheable (inmutable por release)."""
    return {"fields": COST_FIELDS_META}


@router.post("/pricing-suggestion", response_model=PricingSuggestionResponse)
def pricing_suggestion(
    payload: PricingSuggestionRequest,
    current_price_cents: int | None = None,
    tenant: Tenant = Depends(get_tenant_for_membership),
    db: Session = Depends(get_db),
):
    """Calcula costo_real + precio_sugerido para un producto.

    Body:
      {
        "material_cost_cents": 2500,   // insumos
        "production_time_min": 15,     // tiempo de producción
        "target_margin_pct": 30        // opcional, override del tenant default
      }
    Query `?current_price_cents=4990` para que devuelva también el margen
    actual (útil para mostrar "tu margen actual vs. el objetivo").
    """
    return CostsService(db).pricing_suggestion(
        tenant.id, payload, current_price_cents=current_price_cents
    )
