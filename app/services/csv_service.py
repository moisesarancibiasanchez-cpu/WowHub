"""CsvService — import/export CSV para productos y clientes."""
import csv
import io
import logging
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.errors import ValidationError
from app.models.customer import Customer
from app.models.product import Product, ProductStatus
from app.models.tenant import Tenant
from app.services.product_service import ProductService

logger = logging.getLogger("wowhub.csv")


class CsvService:
    def __init__(self, db: Session):
        self.db = db

    # ── Export Products ─────────────────────────────────
    def export_products(self, tenant_id: UUID) -> str:
        products = self.db.query(Product).filter(Product.tenant_id == str(tenant_id)).all()
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "sku", "name", "slug", "short_description", "category_id",
            "price_cents", "compare_at_cents", "cost_cents", "stock",
            "track_inventory", "status", "is_featured", "image_url", "tags",
        ])
        for p in products:
            writer.writerow([
                p.sku, p.name, p.slug, p.short_description or "",
                p.category_id or "", p.price_cents, p.compare_at_cents or "",
                p.cost_cents or "", p.stock, "true" if p.track_inventory else "false",
                p.status.value, "true" if p.is_featured else "false",
                p.image_url or "", ",".join(p.tags or []),
            ])
        return output.getvalue()

    # ── Import Products ────────────────────────────────
    def import_products(self, tenant: Tenant, csv_content: str) -> dict:
        reader = csv.DictReader(io.StringIO(csv_content))
        required = {"sku", "name", "slug", "price_cents"}
        if not required.issubset(set(reader.fieldnames or [])):
            raise ValidationError(f"Faltan columnas requeridas: {required - set(reader.fieldnames or [])}")

        svc = ProductService(self.db)
        created = 0
        errors: list[dict] = []
        for i, row in enumerate(reader, start=2):  # start=2 para considerar header
            try:
                from app.schemas.product import ProductCreate
                payload = ProductCreate(
                    sku=row["sku"].strip(),
                    name=row["name"].strip(),
                    slug=row["slug"].strip(),
                    short_description=row.get("short_description", "").strip() or None,
                    description=None,
                    price_cents=int(row["price_cents"]),
                    compare_at_cents=int(row["compare_at_cents"]) if row.get("compare_at_cents") else None,
                    cost_cents=int(row["cost_cents"]) if row.get("cost_cents") else None,
                    track_inventory=str(row.get("track_inventory", "false")).lower() == "true",
                    stock=int(row.get("stock", 0)),
                    low_stock_threshold=int(row.get("low_stock_threshold", 5)),
                    image_url=row.get("image_url", "").strip() or None,
                    tags=[t.strip() for t in (row.get("tags", "") or "").split(",") if t.strip()],
                    status=row.get("status", "active") if row.get("status") in [s.value for s in ProductStatus] else "draft",
                    is_featured=str(row.get("is_featured", "false")).lower() == "true",
                )
                svc.create(tenant.id, payload)
                created += 1
            except Exception as e:
                errors.append({"row": i, "sku": row.get("sku", "?"), "error": str(e)})
        return {"created": created, "errors": errors, "total_rows": i - 1 if created + len(errors) > 0 else 0}

    # ── Export Customers ───────────────────────────────
    def export_customers(self, tenant_id: UUID) -> str:
        customers = self.db.query(Customer).filter(Customer.tenant_id == str(tenant_id)).all()
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "full_name", "email", "phone", "address", "city",
            "total_orders", "total_spent_cents", "points",
            "tags", "accepts_marketing", "is_active",
        ])
        for c in customers:
            writer.writerow([
                c.full_name, c.email or "", c.phone or "", c.address or "",
                c.city or "", c.total_orders, c.total_spent_cents, c.points,
                ",".join(c.tags or []), "true" if c.accepts_marketing else "false",
                "true" if c.is_active else "false",
            ])
        return output.getvalue()
