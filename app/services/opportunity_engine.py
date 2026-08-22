"""OpportunityEngine — motor de detección de oportunidades (Fase 3 del plan).

Visión: ver `user_input_files/oportunidades.pdf`.

Pipeline:
    DATOS → ANÁLISIS (AnalyticsService) → DETECCIÓN (este módulo)
          → OPORTUNIDAD (estructura normalizada con score)
          → Recomendación → Acción

Cada oportunidad tiene:
    - id          : uuid (estable por entidad+regla, para que el front pueda
                   cachear y evitar parpadeos al recargar)
    - category    : una de las 6 categorías del PDF
                     (rentabilidad | inventario | clientes | ventas
                      | marketing | operacion)
    - severity    : estado de la card (.opp-card--atencion|--oport|--inact)
    - title       : título corto en español
    - body        : 1-2 oraciones con el contexto/dato concreto
    - score       : 0-100 (Impacto × Urgencia × Confianza) — PDF p.3
    - band        : high (>=70) | medium (40-69) | low (<40) — color del badge
    - action_label: texto del botón (Ver producto, Crear orden, etc.)
    - action_url  : URL a donde apunta el botón
    - entity_type : product | customer | order
    - entity_id   : UUID de la entidad afectada
    - detected_at : ISO timestamp (caching key)

Reglas MVP implementadas (las más accionables del PDF):
    R1. Stock bajo              → categoría=inventario,   severity=atencion
    R2. Producto sin rotación   → categoría=inventario,   severity=atencion
    R3. Sobre-stock             → categoría=inventario,   severity=oport
    R4. Cliente inactivo        → categoría=clientes,     severity=inact
    R5. Cliente nuevo sin compra→ categoría=clientes,     severity=oport
    R6. Producto top con poca rotación inversa
                                 → categoría=ventas,      severity=oport
       (producto top + muchos días sin venta = algo cambió)

Cada regla produce 0..N oportunidades (top N por severidad/score).
Las oportunidades se ordenan por score desc y se truncan a `limit`.
"""
from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.services.analytics_service import AnalyticsService


# ────────────────────────────────────────────────────────
# Modelo canónico de oportunidad
# ────────────────────────────────────────────────────────

# Categorías del PDF (6)
CATEGORIES = ("rentabilidad", "inventario", "clientes", "ventas", "marketing", "operacion")
# Severidades / estados visuales
SEVERITIES = ("atencion", "oport", "inact")
# Bandas del score
BANDS = ("high", "medium", "low")


@dataclass
class Opportunity:
    """Una oportunidad detectada para un tenant."""
    id: str
    category: str
    severity: str
    title: str
    body: str
    score: int
    band: str
    action_label: str
    action_url: str
    entity_type: str
    entity_id: str
    detected_at: str
    # Métrica de soporte (opcional, la inyectamos para que el front la muestre)
    metric: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────

def _band_from_score(score: int) -> str:
    if score >= 70:
        return "high"
    if score >= 40:
        return "medium"
    return "low"


def _stable_id(rule: str, entity_id: str) -> str:
    """ID estable por (regla, entidad). Permite caching en el front."""
    h = hashlib.sha1(f"{rule}:{entity_id}".encode("utf-8")).hexdigest()[:16]
    return f"opp_{h}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _score(impact: int, urgency: int, confidence: int) -> int:
    """OpportunityScore = Impacto × Urgencia × Confianza (PDF p.3).
    Cada factor va 0-100. El score final es la media geométrica truncada
    para que el resultado también caiga en 0-100 (más interpretable)."""
    if impact <= 0 or urgency <= 0 or confidence <= 0:
        return 0
    # Media geométrica: raíz cúbica del producto
    score = round((impact * urgency * confidence) ** (1 / 3))
    return max(0, min(100, score))


# ────────────────────────────────────────────────────────
# Motor
# ────────────────────────────────────────────────────────

class OpportunityEngine:
    """Detecta oportunidades para un tenant usando AnalyticsService.

    Uso:
        engine = OpportunityEngine(db, tenant_id)
        opps = engine.detect(limit=12)
        brief = engine.daily_brief()
    """

    def __init__(self, db: Session, tenant_id: UUID | str):
        self.db = db
        self.tid = str(tenant_id)
        self.analytics = AnalyticsService(db)
        self._now = datetime.now(timezone.utc)

    # ── entrypoint ────────────────────────────────────────
    def detect(self, *, limit: int = 12) -> list[dict[str, Any]]:
        """Ejecuta TODAS las reglas y devuelve las top `limit` oportunidades."""
        all_opps: list[Opportunity] = []
        all_opps.extend(self._rule_low_stock())
        all_opps.extend(self._rule_dead_stock())
        all_opps.extend(self._rule_overstock())
        all_opps.extend(self._rule_inactive_customers())
        all_opps.extend(self._rule_new_customers_no_orders())
        all_opps.extend(self._rule_top_seller_falling())

        # Ordenar por score desc, truncar
        all_opps.sort(key=lambda o: o.score, reverse=True)
        top = all_opps[:limit]
        return [o.to_dict() for o in top]

    def daily_brief(self) -> dict[str, Any]:
        """Resumen ejecutivo del día: stats + oportunidades agrupadas por categoría."""
        opps = self.detect(limit=20)  # agrupamos todas
        by_category: dict[str, int] = {c: 0 for c in CATEGORIES}
        for o in opps:
            by_category[o.category] = by_category.get(o.category, 0) + 1

        # Stats principales
        products_active = self._count_active_products()
        sales_today = self._sales_today_cents()
        orders_today = self._orders_today_count()
        margin_pct = self._avg_margin_pct() or 0

        return {
            "generated_at": _now_iso(),
            "stats": {
                "products_active": products_active,
                "sales_today_cents": sales_today,
                "orders_today": orders_today,
                "margin_pct": round(margin_pct, 1),
            },
            "opportunities_total": len(opps),
            "opportunities_by_category": by_category,
            "top_3": opps[:3],
        }

    # ──────────────────────────────────────────────────────
    # R1: Stock bajo (app.css:8 equivalente a "stock <= threshold")
    # ──────────────────────────────────────────────────────
    def _rule_low_stock(self) -> list[Opportunity]:
        result = self.analytics.inventory(
            self.tid, category="low_stock", limit=10
        )
        opps: list[Opportunity] = []
        for item in result.get("items", []):
            stock = item.get("stock", 0)
            threshold = item.get("low_stock_threshold", 5) or 5
            # Urgencia alta si stock == 1 (casi quiebre)
            urgency = 90 if stock <= 1 else 70
            # Impacto: depende del precio (proxy de valor)
            price_cents = item.get("price_cents", 0)
            impact = min(100, 30 + (price_cents // 1000))  # +1 por cada $10
            confidence = 95  # regla determinística
            score = _score(impact, urgency, confidence)

            name = item.get("name", "Producto")
            opps.append(Opportunity(
                id=_stable_id("R1_low_stock", item["id"]),
                category="inventario",
                severity="atencion",
                title=f"'{name}' tiene stock bajo",
                body=(
                    f"Solo {stock} unidades. A tu ritmo de ventas te quedan "
                    f"aproximadamente {max(1, stock)}-{max(2, stock + 1)} días "
                    f"de inventario. Recomendamos reponer hoy."
                ),
                score=score,
                band=_band_from_score(score),
                action_label="Crear orden de compra",
                action_url=f"/dashboard/products/{item['id']}",
                entity_type="product",
                entity_id=item["id"],
                detected_at=_now_iso(),
                metric={"stock": stock, "threshold": threshold, "price_cents": price_cents},
            ))
        return opps

    # ──────────────────────────────────────────────────────
    # R2: Producto sin rotación (dead_stock)
    # ──────────────────────────────────────────────────────
    def _rule_dead_stock(self) -> list[Opportunity]:
        result = self.analytics.inventory(
            self.tid, category="dead_stock", days_dead=30, limit=10
        )
        opps: list[Opportunity] = []
        for item in result.get("items", []):
            stock = item.get("stock", 0)
            price_cents = item.get("price_cents", 0)
            capital_inmovilizado = stock * price_cents
            # Impacto alto si hay mucho capital inmovilizado
            impact = min(100, 40 + (capital_inmovilizado // 5000))
            urgency = 50  # no es urgente inmediato pero sí importante
            confidence = 80
            score = _score(impact, urgency, confidence)
            name = item.get("name", "Producto")
            opps.append(Opportunity(
                id=_stable_id("R2_dead_stock", item["id"]),
                category="inventario",
                severity="atencion",
                title=f"'{name}' lleva 30+ días sin venderse",
                body=(
                    f"Tienes {stock} unidades en stock sin rotación. "
                    f"Capital inmovilizado: ${capital_inmovilizado / 100:,.0f}. "
                    f"Considera una promoción o campaña de reactivación."
                ),
                score=score,
                band=_band_from_score(score),
                action_label="Crear promoción",
                action_url=f"/dashboard/promotions?product_id={item['id']}",
                entity_type="product",
                entity_id=item["id"],
                detected_at=_now_iso(),
                metric={
                    "stock": stock,
                    "days_without_sales": 30,
                    "capital_inmovilizado_cents": capital_inmovilizado,
                },
            ))
        return opps

    # ──────────────────────────────────────────────────────
    # R3: Sobre-stock
    # ──────────────────────────────────────────────────────
    def _rule_overstock(self) -> list[Opportunity]:
        result = self.analytics.inventory(
            self.tid, category="overstock", overstock_threshold=100, limit=10
        )
        opps: list[Opportunity] = []
        for item in result.get("items", []):
            stock = item.get("stock", 0)
            price_cents = item.get("price_cents", 0)
            capital_inmovilizado = stock * price_cents
            impact = min(100, 35 + (capital_inmovilizado // 8000))
            urgency = 40
            confidence = 75
            score = _score(impact, urgency, confidence)
            name = item.get("name", "Producto")
            opps.append(Opportunity(
                id=_stable_id("R3_overstock", item["id"]),
                category="inventario",
                severity="oport",
                title=f"'{name}' tiene sobre-stock",
                body=(
                    f"{stock} unidades ({capital_inmovilizado / 100:,.0f} en capital). "
                    f"Recomendamos liberar stock con una promo antes que se deprecie."
                ),
                score=score,
                band=_band_from_score(score),
                action_label="Crear promoción",
                action_url=f"/dashboard/promotions?product_id={item['id']}",
                entity_type="product",
                entity_id=item["id"],
                detected_at=_now_iso(),
                metric={"stock": stock, "capital_inmovilizado_cents": capital_inmovilizado},
            ))
        return opps

    # ──────────────────────────────────────────────────────
    # R4: Clientes inactivos (60+ días sin comprar)
    # ──────────────────────────────────────────────────────
    def _rule_inactive_customers(self) -> list[Opportunity]:
        result = self.analytics.customer_segments(
            self.tid, segment="inactive", days_inactive=60, limit=25
        )
        items = result.get("items", [])
        if not items:
            return []
        opps: list[Opportunity] = []
        # Una oportunidad RESUMEN + link a la lista completa
        n = len(items)
        avg_spent = sum(int(c.get("total_spent_cents") or 0) for c in items) / max(n, 1)
        impact = min(100, 50 + int(avg_spent / 5000))
        urgency = 55
        confidence = 70
        score = _score(impact, urgency, confidence)
        opps.append(Opportunity(
            id=_stable_id("R4_inactive", "summary"),
            category="clientes",
            severity="inact",
            title=f"{n} clientes pueden ser reactivados",
            body=(
                f"Llevan más de 60 días sin comprar. "
                f"Gasto histórico promedio: ${avg_spent / 100:,.0f}. "
                f"Una campaña de reactivación podría recuperar parte de ese valor."
            ),
            score=score,
            band=_band_from_score(score),
            action_label="Crear campaña",
            action_url="/dashboard/customers?segment=inactive",
            entity_type="customer",
            entity_id="summary",
            detected_at=_now_iso(),
            metric={"count": n, "avg_spent_cents": int(avg_spent)},
        ))
        # Top 3 más valiosos individualmente
        for c in sorted(items, key=lambda x: -(x.get("total_spent_cents") or 0))[:3]:
            spent = int(c.get("total_spent_cents") or 0)
            impact_i = min(100, 30 + spent // 5000)
            score_i = _score(impact_i, 55, 70)
            opps.append(Opportunity(
                id=_stable_id("R4_inactive", c["id"]),
                category="clientes",
                severity="inact",
                title=f"'{c.get('full_name', 'Cliente')}' no compra hace 60+ días",
                body=(
                    f"Histórico: {c.get('total_orders', 0)} órdenes, "
                    f"${spent / 100:,.0f} gastados. "
                    f"Buen candidato para una promo personalizada."
                ),
                score=score_i,
                band=_band_from_score(score_i),
                action_label="Ver cliente",
                action_url=f"/dashboard/customers/{c['id']}",
                entity_type="customer",
                entity_id=c["id"],
                detected_at=_now_iso(),
                metric={"total_orders": c.get("total_orders", 0), "total_spent_cents": spent},
            ))
        return opps

    # ──────────────────────────────────────────────────────
    # R5: Clientes nuevos sin segunda compra
    # ──────────────────────────────────────────────────────
    def _rule_new_customers_no_orders(self) -> list[Opportunity]:
        result = self.analytics.customer_segments(
            self.tid, segment="no_orders", limit=10
        )
        items = result.get("items", [])
        # Filtrar a los realmente NUEVOS (últimos 30 días)
        from datetime import timedelta
        cutoff = self._now - timedelta(days=30)
        # Customer model no tiene last_order_at en el summary, pero sí created_at
        # En este MVP usamos todos los "no_orders" como señal (no segunda compra nunca)
        if not items:
            return []
        n = len(items)
        impact = 60
        urgency = 65
        confidence = 60
        score = _score(impact, urgency, confidence)
        opps: list[Opportunity] = []
        opps.append(Opportunity(
            id=_stable_id("R5_new_no_orders", "summary"),
            category="clientes",
            severity="oport",
            title=f"{n} clientes nuevos aún no compran",
            body=(
                "Un email de bienvenida con un cupón de primera compra tiene "
                "tasas de conversión del 15-25% en LATAM. Es una de las acciones "
                "con mejor ROI del ciclo de vida del cliente."
            ),
            score=score,
            band=_band_from_score(score),
            action_label="Crear campaña de bienvenida",
            action_url="/dashboard/campaigns/new?audience=new_customers",
            entity_type="customer",
            entity_id="summary",
            detected_at=_now_iso(),
            metric={"count": n},
        ))
        return opps

    # ──────────────────────────────────────────────────────
    # R6: Producto top con señal de caída (best sellers que ya no rotan)
    # ──────────────────────────────────────────────────────
    def _rule_top_seller_falling(self) -> list[Opportunity]:
        # Top selling de los últimos 30 días
        top = self.analytics.inventory(
            self.tid, category="top_selling", days_top=30, limit=5
        )
        if not top.get("items"):
            return []
        # Buscar los que NO aparecen en top de últimos 7 días
        recent = self.analytics.inventory(
            self.tid, category="top_selling", days_top=7, limit=20
        )
        recent_ids = {i["id"] for i in recent.get("items", [])}
        opps: list[Opportunity] = []
        for item in top.get("items", []):
            if item["id"] in recent_ids:
                continue
            units_30 = item.get("units_sold", 0)
            if units_30 < 5:
                continue  # volumen bajo, no relevante
            impact = min(100, 50 + units_30 * 2)
            urgency = 70
            confidence = 60
            score = _score(impact, urgency, confidence)
            name = item.get("name", "Producto")
            opps.append(Opportunity(
                id=_stable_id("R6_top_falling", item["id"]),
                category="ventas",
                severity="oport",
                title=f"'{name}' está perdiendo tracción",
                body=(
                    f"Vendía {units_30} unidades/mes pero en los últimos 7 días "
                    f"no registra ventas. Posible cambio de tendencia o de temporada. "
                    f"Conviene revisar precio y stock."
                ),
                score=score,
                band=_band_from_score(score),
                action_label="Ver producto",
                action_url=f"/dashboard/products/{item['id']}",
                entity_type="product",
                entity_id=item["id"],
                detected_at=_now_iso(),
                metric={"units_30d": units_30},
            ))
        return opps

    # ──────────────────────────────────────────────────────
    # Helpers de stats para el Daily Brief
    # ──────────────────────────────────────────────────────
    def _count_active_products(self) -> int:
        from app.models.product import Product, ProductStatus
        from sqlalchemy import select, func
        n = self.db.execute(
            select(func.count(Product.id)).where(
                Product.tenant_id == self.tid,
                Product.status == ProductStatus.ACTIVE,
            )
        ).scalar() or 0
        return int(n)

    def _sales_today_cents(self) -> int:
        from app.models.order import Order, OrderStatus
        from sqlalchemy import select, func
        from datetime import timedelta
        start = self._now.replace(hour=0, minute=0, second=0, microsecond=0)
        total = self.db.execute(
            select(func.coalesce(func.sum(Order.total_cents), 0)).where(
                Order.tenant_id == self.tid,
                Order.created_at >= start,
                Order.status != OrderStatus.CANCELED,
            )
        ).scalar() or 0
        return int(total)

    def _orders_today_count(self) -> int:
        from app.models.order import Order, OrderStatus
        from sqlalchemy import select, func
        from datetime import timedelta
        start = self._now.replace(hour=0, minute=0, second=0, microsecond=0)
        n = self.db.execute(
            select(func.count(Order.id)).where(
                Order.tenant_id == self.tid,
                Order.created_at >= start,
                Order.status != OrderStatus.CANCELED,
            )
        ).scalar() or 0
        return int(n)

    def _avg_margin_pct(self) -> Optional[float]:
        """Margen promedio = avg( (price - cost) / price ) sobre productos activos.
        Si no hay costos, devuelve None (el daily_brief lo trata como 0)."""
        from app.models.product import Product, ProductStatus
        from sqlalchemy import select
        try:
            rows = self.db.execute(
                select(Product.price_cents, Product.cost_cents).where(
                    Product.tenant_id == self.tid,
                    Product.status == ProductStatus.ACTIVE,
                    Product.cost_cents.isnot(None),
                    Product.cost_cents > 0,
                    Product.price_cents > 0,
                )
            ).all()
        except Exception:
            return None
        if not rows:
            return None
        margins = []
        for price, cost in rows:
            try:
                p = float(price)
                c = float(cost)
                if p > 0:
                    margins.append(max(0.0, (p - c) / p * 100))
            except (TypeError, ValueError):
                continue
        if not margins:
            return None
        return sum(margins) / len(margins)
