"""CSV API — import/export de productos y clientes."""
from uuid import UUID

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.database import get_db
from app.deps import get_current_membership
from app.models.tenant import Tenant, TenantMembership
from app.services.csv_service import CsvService

router = APIRouter(prefix="/tenants/{tenant_id}/csv", tags=["csv"])


@router.get("/products/export", response_class=PlainTextResponse)
def export_products(
    tenant_id: UUID,
    membership: TenantMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    """Exporta productos a CSV."""
    csv_content = CsvService(db).export_products(tenant_id)
    return PlainTextResponse(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=productos-{tenant_id}.csv"},
    )


@router.post("/products/import")
async def import_products(
    tenant_id: UUID,
    request: Request,
    membership: TenantMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    """Importa productos desde CSV (body = texto CSV)."""
    tenant = db.get(Tenant, tenant_id)
    if not tenant:
        raise NotFoundError("Tenant")
    csv_content = (await request.body()).decode("utf-8")
    result = CsvService(db).import_products(tenant, csv_content)
    return result


@router.get("/customers/export", response_class=PlainTextResponse)
def export_customers(
    tenant_id: UUID,
    membership: TenantMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    csv_content = CsvService(db).export_customers(tenant_id)
    return PlainTextResponse(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=clientes-{tenant_id}.csv"},
    )
