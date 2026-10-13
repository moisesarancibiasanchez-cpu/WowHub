"""Search API — búsqueda full-text."""
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_membership
from app.models.tenant import TenantMembership
from app.services.search_service import SearchService
from app.services.product_service import ProductService

router = APIRouter(prefix="/tenants/{tenant_id}/search", tags=["search"])


@router.get("/products")
def search_products(
    tenant_id: UUID,
    q: str = Query(..., min_length=2, max_length=200),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    membership: TenantMembership = Depends(get_current_membership),
):
    """Búsqueda full-text en productos del tenant.

    FIX 2026-09-27: este endpoint era alcanzable sin autenticación, por lo que
    un anónimo que conociera el UUID de un tenant obtenía su catálogo completo
    (nombre, SKU, precio, stock). `get_current_membership` resuelve el tenant
    desde el path param y valida la membresía activa (403 si no la tiene).
    """
    svc = SearchService(db)
    products = svc.search_products(tenant_id, q, limit=limit)
    return {
        "query": q,
        "total": len(products),
        "items": [ProductService._to_list_item(p).__dict__ for p in products],
    }
