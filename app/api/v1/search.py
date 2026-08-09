"""Search API — búsqueda full-text."""
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.search_service import SearchService
from app.services.product_service import ProductService

router = APIRouter(prefix="/tenants/{tenant_id}/search", tags=["search"])


@router.get("/products")
def search_products(
    tenant_id: UUID,
    q: str = Query(..., min_length=2, max_length=200),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Búsqueda full-text en productos del tenant."""
    svc = SearchService(db)
    products = svc.search_products(tenant_id, q, limit=limit)
    return {
        "query": q,
        "total": len(products),
        "items": [ProductService._to_list_item(p).__dict__ for p in products],
    }
