"""Analytics API — análisis avanzado para el Asistente IA y dashboards.

Endpoints:
- GET /tenants/{tenant_id}/analytics/inventory        → análisis de inventario segmentado
- GET /tenants/{tenant_id}/analytics/customer-segments → segmentación de clientes
"""
from typing import Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_tenant_for_membership
from app.models.tenant import Tenant
from app.schemas.analytics import (
    CustomerSegmentResponse,
    InventoryResponse,
)
from app.services.analytics_service import AnalyticsService

router = APIRouter(
    prefix="/tenants/{tenant_id}/analytics",
    tags=["analytics"],
)


@router.get("/inventory", response_model=InventoryResponse)
def get_inventory_analytics(
    tenant: Tenant = Depends(get_tenant_for_membership),
    db: Session = Depends(get_db),
    category: Literal["all", "low_stock", "out_of_stock", "overstock", "dead_stock", "top_selling"] = Query(
        "all",
        description="Categoría de inventario a analizar.",
    ),
    days_dead: int = Query(60, ge=1, le=365, description="Días sin ventas para considerar 'dead stock'."),
    days_top: int = Query(30, ge=1, le=365, description="Ventana para 'top_selling'."),
    overstock_threshold: int = Query(100, ge=1, description="Stock por encima del cual se considera 'overstock'."),
    low_stock_threshold: Optional[int] = Query(
        None, ge=0, description="Override del umbral de low stock (si no se da, usa el del producto).",
    ),
    limit: int = Query(50, ge=1, le=500),
):
    """Análisis de inventario segmentado.

    Devuelve un resumen (`summary`) con conteos por categoría y la lista
    de productos (`items`) con metadatos relevantes para el Asistente IA.
    """
    data = AnalyticsService(db).inventory(
        tenant.id,
        category=category,
        days_dead=days_dead,
        days_top=days_top,
        overstock_threshold=overstock_threshold,
        low_stock_threshold=low_stock_threshold,
        limit=limit,
    )
    return data


@router.get("/customer-segments", response_model=CustomerSegmentResponse)
def get_customer_segments(
    tenant: Tenant = Depends(get_tenant_for_membership),
    db: Session = Depends(get_db),
    segment: Literal["all", "inactive", "top", "new", "vip", "no_orders"] = Query(
        "all",
        description="Segmento de clientes a devolver.",
    ),
    days_inactive: int = Query(60, ge=1, le=365, description="Días sin comprar = inactivo."),
    days_new: int = Query(30, ge=1, le=365, description="Ventana para considerar 'nuevo'."),
    top_percentile: float = Query(0.2, ge=0.01, le=1.0,
                                  description="Percentil para el segmento 'top'."),
    vip_min_orders: int = Query(5, ge=1, description="Mínimo de órdenes para 'vip'."),
    vip_min_spent_cents: int = Query(50000, ge=0,
                                     description="Mínimo de gasto (centavos) para 'vip'."),
    limit: int = Query(100, ge=1, le=500),
):
    """Segmentación de clientes del tenant.

    Devuelve `summary` con conteos rápidos por categoría y la lista de
    clientes que cumplen el criterio (`items`).
    """
    data = AnalyticsService(db).customer_segments(
        tenant.id,
        segment=segment,
        days_inactive=days_inactive,
        days_new=days_new,
        top_percentile=top_percentile,
        vip_min_orders=vip_min_orders,
        vip_min_spent_cents=vip_min_spent_cents,
        limit=limit,
    )
    return data
