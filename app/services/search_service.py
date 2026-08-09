"""SearchService — búsqueda full-text en productos (PostgreSQL tsvector + fallback SQLite LIKE)."""
import logging
from typing import Optional
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.product import Product, ProductStatus

logger = logging.getLogger("wowhub.search")


class SearchService:
    def __init__(self, db: Session):
        self.db = db

    def search_products(
        self, tenant_id: UUID, query: str, *,
        limit: int = 20, status_filter: Optional[ProductStatus] = ProductStatus.ACTIVE,
    ) -> list[Product]:
        """Búsqueda full-text en productos.

        En PostgreSQL usa tsvector (configurado en migración).
        En SQLite usa LIKE case-insensitive (fallback).
        """
        if not query or len(query.strip()) < 2:
            return []

        q = query.strip().lower()
        from app.config import settings

        if not settings.is_sqlite:
            # PostgreSQL: usar tsvector con plainto_tsquery
            from sqlalchemy import text
            sql = text("""
                SELECT p.* FROM products p,
                to_tsvector('simple', coalesce(p.name,'') || ' ' || coalesce(p.short_description,'') || ' ' || coalesce(p.description,'') || ' ' || array_to_string(coalesce(p.tags, ARRAY[]::text[]), ' '))
                AS document
                WHERE p.tenant_id = :tenant_id
                AND to_tsvector('simple', coalesce(p.name,'') || ' ' || coalesce(p.short_description,'') || ' ' || coalesce(p.description,'') || ' ' || array_to_string(coalesce(p.tags, ARRAY[]::text[]), ' '))
                @@ plainto_tsquery('simple', :query)
                ORDER BY ts_rank(document, plainto_tsquery('simple', :query)) DESC
                LIMIT :limit
            """)
            result = self.db.execute(sql, {"tenant_id": str(tenant_id), "query": query, "limit": limit})
            return [r[0] for r in result]

        # SQLite fallback: LIKE
        like = f"%{q}%"
        stmt = select(Product).where(
            Product.tenant_id == str(tenant_id),
            or_(
                func.lower(Product.name).like(like),
                func.lower(Product.short_description).like(like),
                func.lower(Product.sku).like(like),
            )
        )
        if status_filter:
            stmt = stmt.where(Product.status == status_filter)
        stmt = stmt.limit(limit)
        return list(self.db.execute(stmt).scalars())
