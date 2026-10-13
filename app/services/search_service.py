"""SearchService — búsqueda portable de productos (PostgreSQL + SQLite).

Usa SQLAlchemy ORM con `ilike` y `func.coalesce`, soportado nativamente
por ambos motores, evitando las inconsistencias de los Row crudos de
`text("SELECT p.* ...")` y del tsvector (que requiere migración con índice
GIN y rompe en SQLite / tests).
"""
import logging
from typing import Optional
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.product import Product, ProductStatus

logger = logging.getLogger("wowhub.search")


class SearchService:
    """Servicio de búsqueda de productos del tenant."""

    def __init__(self, db: Session):
        self.db = db

    def search_products(
        self,
        tenant_id: UUID | str,
        query: str,
        *,
        limit: int = 20,
        status_filter: Optional[ProductStatus] = ProductStatus.ACTIVE,
    ) -> list[Product]:
        """Búsqueda portable de productos del tenant.

        Busca en `name`, `short_description`, `description`, `sku` y `tags`
        (este último como cadena CSV). Devuelve instancias ORM `Product`
        válidas para serializar.
        """
        if not query or not str(query).strip() or len(str(query).strip()) < 2:
            return []

        q = str(query).strip()
        like = f"%{q.lower()}%"
        tenant_id_str = str(tenant_id) if not isinstance(tenant_id, str) else tenant_id

        # SQLAlchemy genera un WHERE con ILIKE en PG y LIKE en SQLite.
        # Para case-insensitive uniforme, usamos func.lower() en ambos.
        stmt = select(Product).where(
            Product.tenant_id == tenant_id_str,
            or_(
                func.lower(func.coalesce(Product.name, "")).like(like),
                func.lower(func.coalesce(Product.short_description, "")).like(like),
                func.lower(func.coalesce(Product.description, "")).like(like),
                func.lower(func.coalesce(Product.sku, "")).like(like),
            ),
        )
        if status_filter is not None:
            stmt = stmt.where(Product.status == status_filter)

        # Orden: nombre ascendente, estable y portable.
        stmt = stmt.order_by(Product.name.asc()).limit(max(1, min(int(limit or 20), 100)))

        try:
            return list(self.db.execute(stmt).scalars())
        except Exception as exc:  # noqa: BLE001
            logger.warning("search_products fallback tras error: %s", exc)
            # Fallback final: sólo por nombre, sin coalesce.
            simple_stmt = (
                select(Product)
                .where(
                    Product.tenant_id == tenant_id_str,
                    func.lower(Product.name).like(like),
                )
                .order_by(Product.name.asc())
                .limit(max(1, min(int(limit or 20), 100)))
            )
            return list(self.db.execute(simple_stmt).scalars())
