"""Production API — Kanban de producción (HU_52, HU_53, HU_55)."""
from __future__ import annotations
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.core.security import requires_permission
from app.database import get_db
from app.deps import get_current_membership
from app.models.production import ProductionJobStatus
from app.models.tenant import TenantMembership
from app.schemas.inline import (
    ProductionJobOut, ProductionJobMove, KanbanBoard, KanbanColumn
)
from app.services.production_service import ProductionService


router = APIRouter(prefix="/tenants/{tenant_id}/production", tags=["production"])


@router.get("/kanban", response_model=KanbanBoard)
def get_kanban(
    tenant_id: UUID,
    statuses: Optional[str] = Query(None, description="Comma-separated status filter"),
    membership: TenantMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    """HU_52 — Tablero Kanban con jobs agrupados por status."""
    svc = ProductionService(db)
    status_filter = None
    if statuses:
        status_filter = [ProductionJobStatus(s.strip()) for s in statuses.split(",")]
    data = svc.list_for_kanban(tenant_id, status_filter)
    return data


@router.get("/jobs/{job_id}", response_model=ProductionJobOut)
def get_job(
    tenant_id: UUID,
    job_id: UUID,
    membership: TenantMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    """Detalle de un ProductionJob."""
    return ProductionService(db).get(tenant_id, job_id)


@router.post("/jobs/{job_id}/move", response_model=ProductionJobOut)
@requires_permission("production", "write")
def move_job(
    tenant_id: UUID,
    job_id: UUID,
    payload: ProductionJobMove,
    membership: TenantMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    """HU_53 — transicionar un job a otro estado con validación de state machine."""
    return ProductionService(db).move(tenant_id, job_id, payload.new_status, payload.notes)


@router.get("/low-stock")
def low_stock_insumos(
    tenant_id: UUID,
    membership: TenantMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    """HU_65 — lista de insumos bajo stock mínimo."""
    from app.models.insumo import Insumo
    from sqlalchemy import select

    rows = db.execute(
        select(Insumo).where(
            Insumo.tenant_id == str(tenant_id),
            Insumo.is_active == True,  # noqa: E712
            Insumo.min_stock.isnot(None),
            Insumo.stock <= Insumo.min_stock,
        ).order_by(Insumo.stock)
    ).scalars()
    return [
        {
            "id": str(r.id),
            "name": r.name,
            "stock": r.stock,
            "min_stock": r.min_stock,
            "unit": r.unit,
            "shortage": (r.min_stock or 0) - r.stock,
        }
        for r in rows
    ]
