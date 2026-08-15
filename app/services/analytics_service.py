"""AnalyticsService — análisis avanzado para el Asistente IA y dashboards.

Cubre:
- Inventario: low_stock, out_of_stock, overstock, dead_stock, top_selling
- Segmentación de clientes: inactive, top, new, vip, all

Todos los métodos reciben `tenant_id` (UUID o str) y devuelven dicts
listos para serializar (con str() aplicado a UUIDs y datetime).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.models.customer import Customer
from app.models.order import Order, OrderItem, OrderStatus
from app.models.product import Product, ProductStatus


class AnalyticsService:
    """Análisis avanzado por tenant."""

    def __init__(self, db: Session):
        self.db = db

    # ──────────────────────────────────────────────────────
    # INVENTARIO
    # ──────────────────────────────────────────────────────
    def inventory(
        self,
        tenant_id: UUID,
        *,
        category: str = "all",  # all | low_stock | out_of_stock | overstock | dead_stock | top_selling
        days_dead: int = 60,
        days_top: int = 30,
        overstock_threshold: int = 100,
        low_stock_threshold: Optional[int] = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        """Devuelve un análisis de inventario segmentado por categoría.

        Categorías:
        - all           → todos los productos activos con track_inventory=True
        - low_stock     → stock > 0 y stock <= low_stock_threshold
        - out_of_stock  → stock == 0
        - overstock     → stock > overstock_threshold
        - dead_stock    → sin ventas (order_items) en los últimos `days_dead` días
        - top_selling   → top N por unidades vendidas en `days_top` días
        """
        tid = str(tenant_id)
        now = datetime.now(timezone.utc)

        base_q = select(Product).where(
            Product.tenant_id == tid,
            Product.track_inventory == True,  # noqa: E712
        )

        # ── all / low / out / overstock ─────────────────────
        if category == "all":
            items = self.db.execute(
                base_q.order_by(Product.stock.asc()).limit(limit)
            ).scalars().all()
        elif category == "low_stock":
            threshold = low_stock_threshold if low_stock_threshold is not None else Product.low_stock_threshold
            # Si threshold viene como int, lo usamos en el WHERE
            if isinstance(threshold, int):
                items = self.db.execute(
                    base_q.where(
                        Product.stock > 0,
                        Product.stock <= threshold,
                    )
                    .order_by(Product.stock.asc())
                    .limit(limit)
                ).scalars().all()
            else:
                # fallback: usar la columna low_stock_threshold
                items = self.db.execute(
                    base_q.where(
                        Product.stock > 0,
                        Product.stock <= Product.low_stock_threshold,
                    )
                    .order_by(Product.stock.asc())
                    .limit(limit)
                ).scalars().all()
        elif category == "out_of_stock":
            items = self.db.execute(
                base_q.where(Product.stock == 0)
                .order_by(Product.updated_at.desc())
                .limit(limit)
            ).scalars().all()
        elif category == "overstock":
            items = self.db.execute(
                base_q.where(Product.stock > overstock_threshold)
                .order_by(Product.stock.desc())
                .limit(limit)
            ).scalars().all()
        elif category == "dead_stock":
            # Productos con track_inventory=True que NO aparecen en order_items
            # en los últimos `days_dead` días.
            since = now - timedelta(days=days_dead)
            sold_product_ids_subq = (
                select(OrderItem.product_id)
                .join(Order, Order.id == OrderItem.order_id)
                .where(
                    Order.tenant_id == tid,
                    Order.created_at >= since,
                    Order.status != OrderStatus.CANCELED,
                )
                .distinct()
            )
            items = self.db.execute(
                base_q.where(~Product.id.in_(sold_product_ids_subq))
                .order_by(Product.updated_at.asc())
                .limit(limit)
            ).scalars().all()
        elif category == "top_selling":
            since = now - timedelta(days=days_top)
            rows = self.db.execute(
                select(
                    Product,
                    func.coalesce(func.sum(OrderItem.quantity), 0).label("units"),
                    func.coalesce(func.sum(OrderItem.total_cents), 0).label("revenue_cents"),
                )
                .join(OrderItem, OrderItem.product_id == Product.id)
                .join(Order, Order.id == OrderItem.order_id)
                .where(
                    Product.tenant_id == tid,
                    Order.tenant_id == tid,
                    Order.created_at >= since,
                    Order.status != OrderStatus.CANCELED,
                )
                .group_by(Product.id)
                .order_by(func.sum(OrderItem.quantity).desc())
                .limit(limit)
            ).all()
            items = [r[0] for r in rows]
            top_meta = {
                str(r[0].id): {
                    "units_sold": int(r[1] or 0),
                    "revenue_cents": int(r[2] or 0),
                }
                for r in rows
            }
        else:
            items = []

        # Resumen
        summary = self._inventory_summary(tid, overstock_threshold=overstock_threshold)

        # Formatear items
        formatted = []
        for p in items:
            entry: dict[str, Any] = {
                "id": str(p.id),
                "sku": p.sku,
                "name": p.name,
                "stock": p.stock,
                "low_stock_threshold": p.low_stock_threshold,
                "price_cents": int(p.price_cents),
                "image_url": p.image_url,
                "status": p.status.value if hasattr(p.status, "value") else str(p.status),
                "is_featured": p.is_featured,
                "sold_count": int(p.sold_count or 0),
                "view_count": int(p.view_count or 0),
            }
            if category == "top_selling":
                meta = top_meta.get(str(p.id), {})
                entry["units_sold"] = meta.get("units_sold", 0)
                entry["revenue_cents"] = meta.get("revenue_cents", 0)
            # Indicador visual
            if p.stock == 0:
                entry["alert"] = "out_of_stock"
            elif p.stock <= p.low_stock_threshold:
                entry["alert"] = "low_stock"
            elif p.stock > overstock_threshold:
                entry["alert"] = "overstock"
            else:
                entry["alert"] = "ok"
            formatted.append(entry)

        return {
            "category": category,
            "tenant_id": tid,
            "summary": summary,
            "count": len(formatted),
            "items": formatted,
            "params": {
                "days_dead": days_dead,
                "days_top": days_top,
                "overstock_threshold": overstock_threshold,
            },
        }

    def _inventory_summary(self, tid: str, *, overstock_threshold: int) -> dict[str, Any]:
        """Cuenta rápida de cada categoría de inventario."""
        products_q = select(Product).where(
            Product.tenant_id == tid,
            Product.track_inventory == True,  # noqa: E712
        )
        all_tracked = self.db.execute(products_q).scalars().all()

        total = len(all_tracked)
        out_of_stock = sum(1 for p in all_tracked if p.stock == 0)
        low_stock = sum(
            1
            for p in all_tracked
            if 0 < p.stock <= (p.low_stock_threshold or 5)
        )
        overstock = sum(1 for p in all_tracked if p.stock > overstock_threshold)
        ok = total - out_of_stock - low_stock - overstock

        return {
            "total_tracked": total,
            "ok": max(ok, 0),
            "out_of_stock": out_of_stock,
            "low_stock": low_stock,
            "overstock": overstock,
        }

    # ──────────────────────────────────────────────────────
    # SEGMENTACIÓN DE CLIENTES
    # ──────────────────────────────────────────────────────
    def customer_segments(
        self,
        tenant_id: UUID,
        *,
        segment: str = "all",  # all | inactive | top | new | vip | no_orders
        days_inactive: int = 60,
        days_new: int = 30,
        top_percentile: float = 0.2,   # top 20% por gasto
        vip_min_orders: int = 5,
        vip_min_spent_cents: int = 50000,  # 50.000 centavos = 500 en moneda local
        limit: int = 100,
    ) -> dict[str, Any]:
        """Devuelve lista de clientes del tenant filtrados por segmento.

        Segmentos:
        - all        → todos los clientes activos
        - inactive   → última compra hace más de `days_inactive` días
                       (o nunca compró)
        - top        → top N% por total gastado
        - new        → creados en los últimos `days_new` días
        - vip        → >= `vip_min_orders` órdenes Y gastaron >= `vip_min_spent_cents`
        - no_orders  → clientes que nunca han comprado
        """
        tid = str(tenant_id)
        now = datetime.now(timezone.utc)

        # Base: clientes activos
        base_q = select(Customer).where(
            Customer.tenant_id == tid,
            Customer.is_active == True,  # noqa: E712
        )

        items: list[Customer] = []

        if segment == "all":
            items = list(
                self.db.execute(
                    base_q.order_by(Customer.total_spent_cents.desc()).limit(limit)
                ).scalars()
            )
        elif segment == "no_orders":
            items = list(
                self.db.execute(
                    base_q.where(Customer.total_orders == 0)
                    .order_by(Customer.created_at.desc())
                    .limit(limit)
                ).scalars()
            )
        elif segment == "new":
            since = now - timedelta(days=days_new)
            items = list(
                self.db.execute(
                    base_q.where(Customer.created_at >= since)
                    .order_by(Customer.created_at.desc())
                    .limit(limit)
                ).scalars()
            )
        elif segment == "vip":
            items = list(
                self.db.execute(
                    base_q.where(
                        Customer.total_orders >= vip_min_orders,
                        Customer.total_spent_cents >= vip_min_spent_cents,
                    )
                    .order_by(Customer.total_spent_cents.desc())
                    .limit(limit)
                ).scalars()
            )
        elif segment == "top":
            # Top N% por total gastado: calculamos el total de clientes activos
            # y luego hacemos una subquery ordenada.
            total_customers = self.db.execute(
                select(func.count()).select_from(
                    base_q.subquery()
                )
            ).scalar() or 0
            top_n = max(1, int(total_customers * top_percentile))
            items = list(
                self.db.execute(
                    base_q.order_by(Customer.total_spent_cents.desc()).limit(top_n)
                ).scalars()
            )
        elif segment == "inactive":
            # Clientes sin orden en los últimos `days_inactive` días
            # o con total_orders == 0 (nunca compraron).
            cutoff = now - timedelta(days=days_inactive)
            # Construimos set de customer_ids que compraron recientemente
            recent_ids_subq = (
                select(Order.customer_id)
                .where(
                    Order.tenant_id == tid,
                    Order.created_at >= cutoff,
                    Order.status != OrderStatus.CANCELED,
                )
                .distinct()
            )
            items = list(
                self.db.execute(
                    base_q.where(
                        ~Customer.id.in_(recent_ids_subq),
                    )
                    .order_by(Customer.last_order_at.asc().nulls_first())
                    .limit(limit)
                ).scalars()
            )
        else:
            items = []

        # Summary
        summary = self._customer_summary(tid, days_inactive=days_inactive, days_new=days_new)

        formatted = []
        for c in items:
            last_order = None
            try:
                if c.last_order_at:
                    last_order = str(c.last_order_at)
            except Exception:
                last_order = None
            formatted.append(
                {
                    "id": str(c.id),
                    "full_name": c.full_name,
                    "email": c.email,
                    "phone": c.phone,
                    "total_orders": int(c.total_orders or 0),
                    "total_spent_cents": int(c.total_spent_cents or 0),
                    "points": int(c.points or 0),
                    "last_order_at": last_order,
                    "accepts_marketing": bool(c.accepts_marketing),
                    "is_active": bool(c.is_active),
                    "tags": list(c.tags or []),
                }
            )

        return {
            "segment": segment,
            "tenant_id": tid,
            "summary": summary,
            "count": len(formatted),
            "items": formatted,
            "params": {
                "days_inactive": days_inactive,
                "days_new": days_new,
                "top_percentile": top_percentile,
                "vip_min_orders": vip_min_orders,
                "vip_min_spent_cents": vip_min_spent_cents,
            },
        }

    def _customer_summary(
        self, tid: str, *, days_inactive: int, days_new: int
    ) -> dict[str, Any]:
        """Resumen rápido de la base de clientes."""
        now = datetime.now(timezone.utc)
        all_active = self.db.execute(
            select(func.count(Customer.id)).where(
                Customer.tenant_id == tid,
                Customer.is_active == True,  # noqa: E712
            )
        ).scalar() or 0

        accepts_marketing = self.db.execute(
            select(func.count(Customer.id)).where(
                Customer.tenant_id == tid,
                Customer.is_active == True,  # noqa: E712
                Customer.accepts_marketing == True,  # noqa: E712
            )
        ).scalar() or 0

        no_orders = self.db.execute(
            select(func.count(Customer.id)).where(
                Customer.tenant_id == tid,
                Customer.total_orders == 0,
            )
        ).scalar() or 0

        vip = self.db.execute(
            select(func.count(Customer.id)).where(
                Customer.tenant_id == tid,
                Customer.total_orders >= 5,
                Customer.total_spent_cents >= 50000,
            )
        ).scalar() or 0

        new_cutoff = now - timedelta(days=days_new)
        new_customers = self.db.execute(
            select(func.count(Customer.id)).where(
                Customer.tenant_id == tid,
                Customer.created_at >= new_cutoff,
            )
        ).scalar() or 0

        inactive_cutoff = now - timedelta(days=days_inactive)
        recent_buyers_subq = (
            select(Order.customer_id)
            .where(
                Order.tenant_id == tid,
                Order.created_at >= inactive_cutoff,
                Order.status != OrderStatus.CANCELED,
            )
            .distinct()
        )
        inactive = self.db.execute(
            select(func.count(Customer.id)).where(
                Customer.tenant_id == tid,
                Customer.is_active == True,  # noqa: E712
                ~Customer.id.in_(recent_buyers_subq),
            )
        ).scalar() or 0

        return {
            "total_active": all_active,
            "accepts_marketing": accepts_marketing,
            "no_orders": no_orders,
            "vip": vip,
            "new": new_customers,
            "inactive": inactive,
        }
