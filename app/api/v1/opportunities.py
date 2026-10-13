"""Opportunities API — motor de oportunidades para el dashboard y la IA.

Endpoints:
- GET /tenants/{tenant_id}/opportunities             → lista priorizada de oportunidades
- GET /tenants/{tenant_id}/opportunities/daily-brief → resumen ejecutivo (Daily Brief)

Visión: ver `user_input_files/oportunidades.pdf` — sección "El Ciclo de Inteligencia"
y la categoría de Oportunidades en el dashboard.
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_tenant_for_membership
from app.models.tenant import Tenant
from app.services.opportunity_engine import OpportunityEngine

router = APIRouter(
    prefix="/tenants/{tenant_id}/opportunities",
    tags=["opportunities"],
)


@router.get("")
def list_opportunities(
    tenant: Tenant = Depends(get_tenant_for_membership),
    db: Session = Depends(get_db),
    limit: int = Query(12, ge=1, le=50, description="Máximo de oportunidades a devolver."),
    category: Optional[str] = Query(
        None,
        description=(
            "Filtrar por una de las 6 categorías: "
            "rentabilidad | inventario | clientes | ventas | marketing | operacion"
        ),
    ),
):
    """Devuelve las oportunidades detectadas para este tenant, ordenadas por
    OpportunityScore (Impacto × Urgencia × Confianza) descendente.

    Cada oportunidad incluye:
      - `id` estable (cacheable)
      - `category`, `severity` (atencion | oport | inact)
      - `title`, `body` (texto en español, listo para mostrar)
      - `score` (0-100) y `band` (high | medium | low)
      - `action_label`, `action_url` (botón contextual)
      - `entity_type`, `entity_id` (para deep-link o acciones programáticas)
    """
    engine = OpportunityEngine(db, tenant.id)
    opps = engine.detect(limit=limit)
    if category:
        opps = [o for o in opps if o.get("category") == category]
    return {
        "count": len(opps),
        "tenant_id": str(tenant.id),
        "opportunities": opps,
    }


@router.get("/daily-brief")
def get_daily_brief(
    tenant: Tenant = Depends(get_tenant_for_membership),
    db: Session = Depends(get_db),
):
    """Devuelve el WowHub Daily Brief: stats del día + oportunidades agrupadas.

    Estructura del PDF (p. 14): "Buenos días — tu negocio hoy — WowHub detectó N oportunidades"
    """
    engine = OpportunityEngine(db, tenant.id)
    brief = engine.daily_brief()
    return {"tenant_id": str(tenant.id), **brief}
