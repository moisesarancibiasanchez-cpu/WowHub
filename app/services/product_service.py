"""ProductService — CRUD de productos y helpers para listados públicos.

Fase 3 (V8): las respuestas (`ProductOut`, `ProductListItem`) ahora
incluyen los campos derivados de pricing:
  - `cost_real_cents`        (insumos + mano de obra)
  - `suggested_price_cents`  (precio sugerido por margen objetivo)
  - `current_margin_pct`     (margen actual del precio cargado)
  - `target_margin_pct`      (margen objetivo del tenant, opcional)
  - `cost_hour_used_cents`   (costo_hora usado en el cálculo)
  - `health` / `health_message` (healthy / warning / danger / unknown)
"""
from typing import Optional
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError
from app.models.product import Product, ProductStatus
from app.schemas.product import ProductCreate, ProductUpdate, ProductListItem
from app.schemas.common import Page
from app.services.product_pricing import (
    ProductPricing,
    compute_for_product,
)


def _to_uuid(v) -> Optional[UUID]:
    """Coerce str|UUID|None a UUID|None."""
    if v is None or isinstance(v, UUID):
        return v
    return UUID(str(v))


class ProductService:
    def __init__(self, db: Session):
        self.db = db

    # ── Pricing context ────────────────────────────────────
    def _pricing_for(self, tenant_id) -> tuple[int, Optional[int]]:
        """Lee cost_hour + target_margin del tenant (1 query liviana).

        Devuelve (0, None) si el tenant no tiene BusinessCosts aún.
        """
        from app.models.business_costs import BusinessCosts
        bc = self.db.execute(
            select(BusinessCosts).where(BusinessCosts.tenant_id == str(tenant_id))
        ).scalar_one_or_none()
        if not bc:
            return 0, None
        return int(bc.cost_hour_cents or 0), (
            int(bc.target_margin_pct) if bc.target_margin_pct is not None else None
        )

    def _pricing(self, product: Product) -> ProductPricing:
        cost_hour, target = self._pricing_for(product.tenant_id)
        return compute_for_product(
            product,
            cost_hour_cents=cost_hour,
            target_margin_pct=target,
        )

    # ── Scoped (tenant) ────────────────────────────────
    def list(
        self,
        tenant_id: UUID,
        *,
        page: int = 1,
        page_size: int = 20,
        search: Optional[str] = None,
        status: Optional[ProductStatus] = None,
        category_id: Optional[UUID] = None,
        is_featured: Optional[bool] = None,
        order_by: str = "position",
    ) -> Page[ProductListItem]:
        page, page_size = max(1, page), max(1, min(200, page_size))
        offset = (page - 1) * page_size

        q = select(Product).where(Product.tenant_id == str(tenant_id))
        if search:
            like = f"%{search.lower()}%"
            q = q.where(or_(
                func.lower(Product.name).like(like),
                func.lower(Product.sku).like(like),
                func.lower(Product.short_description).like(like),
            ))
        if status:
            q = q.where(Product.status == status)
        if category_id:
            q = q.where(Product.category_id == str(category_id))
        if is_featured is not None:
            q = q.where(Product.is_featured == is_featured)

        # total
        total = self.db.execute(
            select(func.count()).select_from(q.subquery())
        ).scalar() or 0

        order_col = {
            "position": Product.position,
            "name": Product.name,
            "price": Product.price_cents,
            "created": Product.created_at,
            "sold": Product.sold_count,
        }.get(order_by, Product.position)
        q = q.order_by(order_col.asc(), Product.created_at.desc())
        q = q.offset(offset).limit(page_size)

        products = list(self.db.execute(q).scalars())
        # Fase 3: poblar derivados de pricing en el listado para que el
        # dashboard muestre Costo real / Margen / Salud sin pedir el
        # detalle de cada producto. N+1 aceptable en este listado (≤ 200
        # filas por página y la query de BusinessCosts es 1 por fila, no
        # por producto — ver `_pricing_for`).
        items = [self.to_list_item_with_pricing(p) for p in products]
        return Page.build(items, total, page, page_size)

    def get(self, tenant_id: UUID, product_id: UUID) -> Product:
        p = self.db.get(Product, product_id)
        if not p or p.tenant_id != tenant_id:
            raise NotFoundError("Producto")
        return p

    def get_by_slug(self, tenant_id: UUID, slug: str) -> Product:
        p = self.db.execute(
            select(Product).where(
                Product.tenant_id == str(tenant_id),
                Product.slug == slug,
            )
        ).scalar_one_or_none()
        if not p:
            raise NotFoundError("Producto")
        return p

    def create(self, tenant_id: UUID, payload: ProductCreate) -> Product:
        # unicidad sku y slug por tenant
        self._check_unique(tenant_id, sku=payload.sku, slug=payload.slug)
        data = payload.model_dump()
        data["tenant_id"] = str(tenant_id)
        if data.get("category_id"):
            data["category_id"] = str(data["category_id"])
        p = Product(**data)
        self.db.add(p)
        self.db.commit()
        self.db.refresh(p)
        return p

    def update(self, product: Product, payload: ProductUpdate) -> Product:
        data = payload.model_dump(exclude_unset=True)
        if "sku" in data or "slug" in data:
            new_sku = data.get("sku", product.sku)
            new_slug = data.get("slug", product.slug)
            if new_sku != product.sku or new_slug != product.slug:
                self._check_unique(UUID(product.tenant_id), sku=new_sku, slug=new_slug, exclude_id=product.id)
        for k, v in data.items():
            if k == "category_id" and v is not None:
                v = str(v)
            setattr(product, k, v)
        self.db.commit()
        self.db.refresh(product)
        return product

    def delete(self, product: Product) -> None:
        self.db.delete(product)
        self.db.commit()

    def increment_view(self, product: Product) -> None:
        product.view_count += 1
        self.db.commit()

    # ── Internals ──────────────────────────────────────
    def _check_unique(
        self, tenant_id: UUID, *, sku: str, slug: str, exclude_id: Optional[UUID] = None
    ) -> None:
        q = select(Product).where(
            Product.tenant_id == str(tenant_id),
            or_(Product.sku == sku, Product.slug == slug),
        )
        if exclude_id:
            q = q.where(Product.id != exclude_id)
        existing = self.db.execute(q).scalar_one_or_none()
        if existing:
            if existing.sku == sku:
                raise ConflictError(f"SKU '{sku}' ya existe en este tenant")
            raise ConflictError(f"slug '{slug}' ya existe en este tenant")

    @staticmethod
    def _to_list_item(p: Product) -> ProductListItem:
        on_sale = bool(p.compare_at_cents and p.compare_at_cents > p.price_cents)
        discount_pct = None
        if on_sale and p.compare_at_cents and p.compare_at_cents > 0:
            discount_pct = int(round((1 - p.price_cents / p.compare_at_cents) * 100))
        return ProductListItem(
            id=p.id,
            tenant_id=_to_uuid(p.tenant_id),
            sku=p.sku,
            name=p.name,
            slug=p.slug,
            short_description=p.short_description,
            category_id=_to_uuid(p.category_id),
            price_cents=p.price_cents,
            compare_at_cents=p.compare_at_cents,
            image_url=p.image_url,
            status=p.status,
            is_featured=p.is_featured,
            position=p.position,
            stock=p.stock,
            track_inventory=p.track_inventory,
            on_sale=on_sale,
            discount_pct=discount_pct,
            production_time_min=int(p.production_time_min or 0),
        )

    def to_out(self, p: Product):
        # Reuso del método list_item + datos completos
        from app.schemas.product import ProductOut
        on_sale = bool(p.compare_at_cents and p.compare_at_cents > p.price_cents)
        discount_pct = None
        if on_sale and p.compare_at_cents and p.compare_at_cents > 0:
            discount_pct = int(round((1 - p.price_cents / p.compare_at_cents) * 100))

        # Fase 3: derivados de pricing (lee BusinessCosts del tenant).
        pricing = self._pricing(p)

        return ProductOut(
            id=p.id,
            tenant_id=_to_uuid(p.tenant_id),
            sku=p.sku,
            name=p.name,
            slug=p.slug,
            short_description=p.short_description,
            description=p.description,
            category_id=_to_uuid(p.category_id),
            price_cents=p.price_cents,
            compare_at_cents=p.compare_at_cents,
            cost_cents=p.cost_cents,
            production_time_min=int(p.production_time_min or 0),
            track_inventory=p.track_inventory,
            stock=p.stock,
            low_stock_threshold=p.low_stock_threshold,
            image_url=p.image_url,
            gallery=p.gallery or [],
            tags=p.tags or [],
            status=p.status,
            is_featured=p.is_featured,
            position=p.position,
            view_count=p.view_count,
            sold_count=p.sold_count,
            created_at=p.created_at,
            updated_at=p.updated_at,
            on_sale=on_sale,
            discount_pct=discount_pct,
            cost_real_cents=pricing.cost_real_cents,
            suggested_price_cents=pricing.suggested_price_cents,
            current_margin_pct=pricing.current_margin_pct,
            target_margin_pct=pricing.target_margin_pct,
            cost_hour_used_cents=pricing.cost_hour_used_cents,
            health=pricing.health,
            health_message=pricing.health_message,
        )

    def to_list_item_with_pricing(self, p: Product) -> ProductListItem:
        """Variante de _to_list_item que incluye los derivados Fase 3.

        Usada en el listado del dashboard para que la tabla muestre
        Costo real / Margen / Salud sin obligar al front a pedir el
        detalle de cada producto.
        """
        item = self._to_list_item(p)
        pricing = self._pricing(p)
        item.cost_real_cents = pricing.cost_real_cents
        item.current_margin_pct = pricing.current_margin_pct
        item.target_margin_pct = pricing.target_margin_pct
        item.health = pricing.health
        item.health_message = pricing.health_message
        return item
