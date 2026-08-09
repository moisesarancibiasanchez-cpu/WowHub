"""StatsService — analíticas y métricas para el dashboard."""
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.models.order import Order, OrderItem, OrderStatus
from app.models.product import Product
from app.models.promotion import Promotion
from app.models.qr import QrCode
from app.models.tenant import Tenant


class StatsService:
    def __init__(self, db: Session):
        self.db = db

    def overview(self, tenant_id: UUID, days: int = 30) -> dict:
        """Dashboard overview: ventas, órdenes, productos top, QRs top."""
        now = datetime.now(timezone.utc)
        since = now - timedelta(days=days)

        # Métricas de órdenes (últimos `days` días)
        orders = self.db.execute(
            select(
                func.count(Order.id).label("total_orders"),
                func.coalesce(func.sum(Order.total_cents), 0).label("total_revenue_cents"),
                func.coalesce(func.sum(Order.discount_cents), 0).label("total_discount_cents"),
                func.count(case((Order.status == OrderStatus.DELIVERED, 1))).label("delivered"),
                func.count(case((Order.status == OrderStatus.CANCELED, 1))).label("canceled"),
                func.count(case((Order.status == OrderStatus.PENDING, 1))).label("pending"),
            ).where(
                Order.tenant_id == str(tenant_id),
                Order.created_at >= since,
            )
        ).one()

        # AOV (Average Order Value)
        aov_cents = 0
        if orders.total_orders and orders.total_orders > 0:
            aov_cents = int(orders.total_revenue_cents / orders.total_orders)

        # Top 5 productos (por revenue)
        top_products = self.db.execute(
            select(
                Product.id,
                Product.name,
                Product.sku,
                Product.image_url,
                func.coalesce(func.sum(OrderItem.total_cents), 0).label("revenue_cents"),
                func.coalesce(func.sum(OrderItem.quantity), 0).label("units_sold"),
            )
            .join(OrderItem, OrderItem.product_id == Product.id)
            .join(Order, Order.id == OrderItem.order_id)
            .where(
                Order.tenant_id == str(tenant_id),
                Order.created_at >= since,
                Order.status != OrderStatus.CANCELED,
            )
            .group_by(Product.id, Product.name, Product.sku, Product.image_url)
            .order_by(func.sum(OrderItem.total_cents).desc())
            .limit(5)
        ).all()

        # Top 5 QRs
        top_qrs = self.db.execute(
            select(
                QrCode.id,
                QrCode.label,
                QrCode.short_code,
                QrCode.scan_count,
                QrCode.unique_scans,
                QrCode.conversion_count,
            )
            .where(QrCode.tenant_id == str(tenant_id))
            .order_by(QrCode.scan_count.desc())
            .limit(5)
        ).all()

        # Promociones activas
        active_promos = self.db.execute(
            select(func.count(Promotion.id)).where(
                Promotion.tenant_id == str(tenant_id),
                Promotion.is_active == True,  # noqa: E712
            )
        ).scalar() or 0

        # Total productos
        total_products = self.db.execute(
            select(func.count(Product.id)).where(Product.tenant_id == str(tenant_id))
        ).scalar() or 0

        # Series temporales (últimos 7 días, agrupados por día)
        daily = self.db.execute(
            select(
                func.date(Order.created_at).label("day"),
                func.count(Order.id).label("orders"),
                func.coalesce(func.sum(Order.total_cents), 0).label("revenue_cents"),
            )
            .where(
                Order.tenant_id == str(tenant_id),
                Order.created_at >= now - timedelta(days=7),
                Order.status != OrderStatus.CANCELED,
            )
            .group_by(func.date(Order.created_at))
            .order_by(func.date(Order.created_at))
        ).all()

        return {
            "period_days": days,
            "orders": {
                "total": orders.total_orders or 0,
                "pending": orders.pending or 0,
                "delivered": orders.delivered or 0,
                "canceled": orders.canceled or 0,
            },
            "revenue": {
                "total_cents": int(orders.total_revenue_cents or 0),
                "discount_cents": int(orders.total_discount_cents or 0),
                "aov_cents": aov_cents,
            },
            "catalog": {
                "total_products": total_products,
                "active_promotions": active_promos,
            },
            "top_products": [
                {
                    "id": str(r.id), "name": r.name, "sku": r.sku,
                    "image_url": r.image_url, "revenue_cents": int(r.revenue_cents),
                    "units_sold": int(r.units_sold),
                } for r in top_products
            ],
            "top_qrs": [
                {
                    "id": str(r.id), "label": r.label, "short_code": r.short_code,
                    "scan_count": r.scan_count, "unique_scans": r.unique_scans,
                    "conversion_count": r.conversion_count,
                } for r in top_qrs
            ],
            "daily_series": [
                {
                    "day": str(r.day),
                    "orders": r.orders,
                    "revenue_cents": int(r.revenue_cents),
                } for r in daily
            ],
        }
