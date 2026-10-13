"""Stats API — analíticas para el dashboard."""
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_membership
from app.models.tenant import TenantMembership
from app.schemas.stats import OverviewResponse
from app.services.stats_service import StatsService

router = APIRouter(prefix="/tenants/{tenant_id}/stats", tags=["stats"])


@router.get("/overview", response_model=OverviewResponse)
def get_overview(
    tenant_id: UUID,
    days: int = Query(30, ge=1, le=365),
    membership: TenantMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    """Dashboard overview: ventas, productos top, QRs top, series temporales."""
    data = StatsService(db).overview(tenant_id, days=days)
    return OverviewResponse(**data)
