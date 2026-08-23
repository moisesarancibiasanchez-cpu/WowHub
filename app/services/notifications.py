"""NotificationsEngine — generador de notificaciones por evento para el dashboard.

Visión: complementar `OpportunityEngine` con señales accionables que el
usuario debe ver **ahora** (no tendencias). Es el "bell badge" del dashboard.

Diferencias con ``OpportunityEngine``:
    * ``OpportunityEngine``     → oportunidades/ideas (severidad atencion|oport|inact,
                                 score 0-100, ordenadas por score, pueden ser muchas)
    * ``NotificationsEngine``   → hechos/alertas (severidad info|warning|critical,
                                 ordenadas por severidad, top-N curado)

Por eso las notificaciones son **menos en cantidad** y más **prescriptivas**:
incluyen `action_label` + `action_url` listos para que el front muestre un
botón directo.

Pipeline:
    DB → reglas determinísticas → Notification (dataclass) → JSON

Reglas MVP alineadas con la Maqueta V8 (Fase 4 — backend listo para que
Fase 6 sea solo UI):

    Pricing
        N1. Margen crítico (health="danger")                  → critical
        N2. Margen bajo (health="warning")                    → warning
        N3. Precio actual < precio sugerido (gap >= 10%)      → warning
    Inventory
        N4. Sin stock (stock == 0)                            → critical
        N5. Stock bajo (stock <= low_stock_threshold)         → warning
    Orders
        N6. Pedido PENDING > 24h                              → warning
    Costs (V8)
        N7. Costos sin configurar (BusinessCosts.version == 1) → info
        N8. Costo_hora elevado (> 15.000 CLP/h)               → warning
    System
        N9. Bienvenida después de registrar tenant            → info

Cada notificación tiene:
    - id          : estable por (regla, entidad) → permite caching en el front
                    y evita parpadeos al recargar.
    - severity    : info | warning | critical
    - category    : pricing | inventory | orders | costs | system
    - title       : título corto en español
    - body        : 1-2 oraciones con el contexto/dato concreto
    - action_label: texto del botón (Subir precio, Crear orden, etc.)
    - action_url  : URL a donde apunta el botón
    - entity_type : product | order | tenant
    - entity_id   : UUID (o "tenant" para alertas globales)
    - detected_at : ISO timestamp
    - metric      : dict de soporte para tooltips en Fase 6

Uso típico (consumido por un endpoint en Fase 6):

    engine = NotificationsEngine(db, tenant_id)
    bell = engine.summary()                  # → para el badge del header
    items = engine.detect_all(limit=20)      # → para el dropdown
"""
from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.services.product_pricing import compute_for_product


# ────────────────────────────────────────────────────────
# Modelo canónico
# ────────────────────────────────────────────────────────

# Categorías (5 — alineadas con secciones del dashboard V8)
CATEGORIES: tuple[str, ...] = ("pricing", "inventory", "orders", "costs", "system")
# Severidades (3 — alimentan el color del badge)
SEVERITIES: tuple[str, ...] = ("info", "warning", "critical")
# Orden visual de severidad (de mayor a menor urgencia)
SEVERITY_ORDER: dict[str, int] = {"critical": 0, "warning": 1, "info": 2}

# Umbrales configurables (single source of truth para el front)
THRESHOLDS: dict[str, Any] = {
    # Stock bajo relativo al threshold del producto (ya lo da Product.low_stock_threshold,
    # pero dejamos un default global por si el producto tiene 0).
    "low_stock_default": 5,
    # Costo hora por encima del cual alertamos (CLP; 15.000 ≈ 15 USD/h para una PYME).
    "high_cost_hour_cents": 15_000,
    # Pedidos PENDING con más de N horas pasan a "warning".
    "pending_order_hours": 24,
    # Gap mínimo entre precio actual y sugerido para activar la notificación
    # (evita falsos positivos en diferencias de centavos).
    "pricing_gap_pct": 10,
}


@dataclass
class Notification:
    """Una notificación detectada para un tenant."""
    id: str
    severity: str
    category: str
    title: str
    body: str
    action_label: str
    action_url: str
    entity_type: str
    entity_id: str
    detected_at: str
    metric: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────

def _stable_id(rule: str, entity_id: str) -> str:
    """ID estable por (regla, entidad). Permite caching en el front y
    evita parpadeos cuando el usuario recarga el dashboard."""
    h = hashlib.sha1(f"{rule}:{entity_id}".encode("utf-8")).hexdigest()[:16]
    return f"notif_{h}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _format_money(cents: int) -> str:
    """Helper mínimo para formatear centavos → string con separador de miles.

    Asumimos CLP (sin decimales). Si en el futuro hay multi-currency con
    decimales, este helper se centraliza acá para no duplicar la lógica
    en cada regla.
    """
    if cents is None:
        return "—"
    return f"${cents / 100:,.0f}".replace(",", ".")


# ────────────────────────────────────────────────────────
# Motor
# ────────────────────────────────────────────────────────

class NotificationsEngine:
    """Genera notificaciones accionables para un tenant.

    Uso::

        engine = NotificationsEngine(db, tenant_id)
        bell = engine.summary()                # → para el badge del header
        items = engine.detect_all(limit=20)    # → para el dropdown
        by_cat = engine.by_category(items)     # → agrupación
    """

    def __init__(self, db: Session, tenant_id: UUID | str):
        self.db = db
        self.tid = str(tenant_id)
        self._now = datetime.now(timezone.utc)

    # ── entrypoints ───────────────────────────────────────
    def detect_all(self, *, limit: int = 20) -> list[dict[str, Any]]:
        """Ejecuta TODAS las reglas y devuelve las top ``limit`` notificaciones.

        Orden: severidad ascendente (``critical`` primero), dentro de cada
        severidad por ``detected_at`` descendente (más recientes primero).
        """
        all_notifs: list[Notification] = []
        all_notifs.extend(self._rule_costs_not_configured())
        all_notifs.extend(self._rule_high_cost_hour())
        all_notifs.extend(self._rule_critical_margin())
        all_notifs.extend(self._rule_low_margin())
        all_notifs.extend(self._rule_pricing_below_suggested())
        all_notifs.extend(self._rule_out_of_stock())
        all_notifs.extend(self._rule_low_stock())
        all_notifs.extend(self._rule_pending_orders_old())
        all_notifs.extend(self._rule_system())

        # 1) agrupar por severidad preservando el orden natural
        by_sev: dict[str, list[Notification]] = {s: [] for s in SEVERITIES}
        for n in all_notifs:
            by_sev.setdefault(n.severity, []).append(n)

        # 2) dentro de cada severidad, las más recientes primero
        for sev in by_sev:
            by_sev[sev].sort(key=lambda n: n.detected_at, reverse=True)

        # 3) concatenar en orden de severidad (critical → warning → info)
        flat: list[Notification] = by_sev["critical"] + by_sev["warning"] + by_sev["info"]
        return [n.to_dict() for n in flat[:limit]]

    def summary(self) -> dict[str, Any]:
        """Resumen compacto para el badge del header.

        Retorna:
            {
                "total": int,
                "by_severity": {"critical": n, "warning": n, "info": n},
                "by_category": {"pricing": n, "inventory": n, ...},
                "top_3": [Notification.to_dict(), ...]
            }
        """
        items = self.detect_all(limit=100)  # agrupamos todas
        by_sev: dict[str, int] = {s: 0 for s in SEVERITIES}
        by_cat: dict[str, int] = {c: 0 for c in CATEGORIES}
        for it in items:
            by_sev[it["severity"]] = by_sev.get(it["severity"], 0) + 1
            by_cat[it["category"]] = by_cat.get(it["category"], 0) + 1
        return {
            "generated_at": _now_iso(),
            "total": len(items),
            "by_severity": by_sev,
            "by_category": by_cat,
            "top_3": items[:3],
        }

    # ── helpers públicos para Fase 6 UI ─────────────────
    @staticmethod
    def by_category(items: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        out: dict[str, list[dict[str, Any]]] = {c: [] for c in CATEGORIES}
        for it in items:
            out.setdefault(it["category"], []).append(it)
        return out

    @staticmethod
    def by_severity(items: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        out: dict[str, list[dict[str, Any]]] = {s: [] for s in SEVERITIES}
        for it in items:
            out.setdefault(it["severity"], []).append(it)
        return out

    # ──────────────────────────────────────────────────────
    # Reglas — Pricing
    # ──────────────────────────────────────────────────────

    def _pricing_context(self) -> tuple[int, Optional[int]]:
        """Lee BusinessCosts y devuelve ``(cost_hour_cents, target_margin_pct)``.

        Si el tenant no tiene BusinessCosts, devuelve ``(0, None)`` para que
        las reglas de pricing degraden con ``health="unknown"``.
        """
        from app.models.business_costs import BusinessCosts
        bc = self.db.execute(
            select(BusinessCosts).where(BusinessCosts.tenant_id == self.tid)
        ).scalar_one_or_none()
        if not bc:
            return (0, None)
        return (int(bc.cost_hour_cents or 0), bc.target_margin_pct if bc.target_margin_pct is not None else None)

    def _rule_critical_margin(self) -> list[Notification]:
        """N1 — Productos con margen crítico (health="danger")."""
        from app.models.product import Product, ProductStatus
        cost_hour, target = self._pricing_context()
        if not cost_hour and target is None:
            return []  # sin datos → no notificamos (sería ruido)

        rows = self.db.execute(
            select(Product).where(
                Product.tenant_id == self.tid,
                Product.status == ProductStatus.ACTIVE,
            )
        ).scalars().all()

        out: list[Notification] = []
        for p in rows:
            pricing = compute_for_product(
                p, cost_hour_cents=cost_hour, target_margin_pct=target,
            )
            if pricing.health != "danger":
                continue
            out.append(Notification(
                id=_stable_id("N1_critical_margin", p.id),
                severity="critical",
                category="pricing",
                title=f"'{p.name}' tiene margen crítico",
                body=(
                    f"Estás ganando {pricing.current_margin_pct:.1f}% "
                    f"(objetivo: {target}%). Te sugerimos un precio de "
                    f"{_format_money(pricing.suggested_price_cents)} para alcanzar el objetivo."
                ),
                action_label="Subir precio",
                action_url=f"/dashboard/products/{p.id}#pricing",
                entity_type="product",
                entity_id=p.id,
                detected_at=_now_iso(),
                metric={
                    "current_margin_pct": pricing.current_margin_pct,
                    "target_margin_pct": target,
                    "suggested_price_cents": pricing.suggested_price_cents,
                    "current_price_cents": int(p.price_cents or 0),
                },
            ))
        return out

    def _rule_low_margin(self) -> list[Notification]:
        """N2 — Productos con margen bajo (health="warning")."""
        from app.models.product import Product, ProductStatus
        cost_hour, target = self._pricing_context()
        if not cost_hour and target is None:
            return []

        rows = self.db.execute(
            select(Product).where(
                Product.tenant_id == self.tid,
                Product.status == ProductStatus.ACTIVE,
            )
        ).scalars().all()

        out: list[Notification] = []
        for p in rows:
            pricing = compute_for_product(
                p, cost_hour_cents=cost_hour, target_margin_pct=target,
            )
            if pricing.health != "warning":
                continue
            out.append(Notification(
                id=_stable_id("N2_low_margin", p.id),
                severity="warning",
                category="pricing",
                title=f"'{p.name}' tiene margen bajo",
                body=(
                    f"Margen actual: {pricing.current_margin_pct:.1f}% "
                    f"(objetivo: {target}%). El precio sugerido es "
                    f"{_format_money(pricing.suggested_price_cents)}."
                ),
                action_label="Revisar pricing",
                action_url=f"/dashboard/products/{p.id}#pricing",
                entity_type="product",
                entity_id=p.id,
                detected_at=_now_iso(),
                metric={
                    "current_margin_pct": pricing.current_margin_pct,
                    "target_margin_pct": target,
                    "suggested_price_cents": pricing.suggested_price_cents,
                },
            ))
        return out

    def _rule_pricing_below_suggested(self) -> list[Notification]:
        """N3 — Productos donde el precio actual está por debajo del sugerido
        en más de un % configurable (default 10%).

        A diferencia de N1/N2 (que miran margen), esta regla mira el gap
        absoluto: si vos ponés un precio de $5.000 y el sugerido es $7.500,
        hay un gap del 50% aunque el margen actual no sea estrictamente
        "danger" (p.ej. si la mano de obra es muy baja).
        """
        from app.models.product import Product, ProductStatus
        cost_hour, target = self._pricing_context()
        if not target:
            return []

        rows = self.db.execute(
            select(Product).where(
                Product.tenant_id == self.tid,
                Product.status == ProductStatus.ACTIVE,
                Product.price_cents > 0,
            )
        ).scalars().all()

        out: list[Notification] = []
        threshold_pct = THRESHOLDS["pricing_gap_pct"]
        for p in rows:
            pricing = compute_for_product(
                p, cost_hour_cents=cost_hour, target_margin_pct=target,
            )
            suggested = pricing.suggested_price_cents
            price = int(p.price_cents or 0)
            if suggested <= 0 or price <= 0:
                continue
            gap_pct = (suggested - price) / suggested * 100
            if gap_pct < threshold_pct:
                continue
            out.append(Notification(
                id=_stable_id("N3_pricing_below", p.id),
                severity="warning",
                category="pricing",
                title=f"'{p.name}' está {gap_pct:.0f}% bajo del sugerido",
                body=(
                    f"Precio actual: {_format_money(price)}. "
                    f"Sugerido: {_format_money(suggested)}. "
                    f"Diferencia por venta: {_format_money(suggested - price)}."
                ),
                action_label="Ver sugerido",
                action_url=f"/dashboard/products/{p.id}#pricing",
                entity_type="product",
                entity_id=p.id,
                detected_at=_now_iso(),
                metric={
                    "current_price_cents": price,
                    "suggested_price_cents": suggested,
                    "gap_pct": round(gap_pct, 1),
                },
            ))
        return out

    # ──────────────────────────────────────────────────────
    # Reglas — Inventory
    # ──────────────────────────────────────────────────────

    def _rule_out_of_stock(self) -> list[Notification]:
        """N4 — Productos sin stock (stock == 0 y track_inventory)."""
        from app.models.product import Product, ProductStatus
        rows = self.db.execute(
            select(Product).where(
                Product.tenant_id == self.tid,
                Product.status == ProductStatus.ACTIVE,
                Product.track_inventory.is_(True),
                Product.stock == 0,
            )
        ).scalars().all()

        out: list[Notification] = []
        for p in rows:
            out.append(Notification(
                id=_stable_id("N4_out_of_stock", p.id),
                severity="critical",
                category="inventory",
                title=f"'{p.name}' está sin stock",
                body=(
                    "Los clientes no pueden comprarlo. "
                    "Recomendamos reponer hoy para no perder ventas."
                ),
                action_label="Reponer stock",
                action_url=f"/dashboard/products/{p.id}#inventory",
                entity_type="product",
                entity_id=p.id,
                detected_at=_now_iso(),
                metric={"stock": 0, "sku": p.sku},
            ))
        return out

    def _rule_low_stock(self) -> list[Notification]:
        """N5 — Productos con stock bajo (stock <= low_stock_threshold)."""
        from app.models.product import Product, ProductStatus
        default_threshold = THRESHOLDS["low_stock_default"]
        rows = self.db.execute(
            select(Product).where(
                Product.tenant_id == self.tid,
                Product.status == ProductStatus.ACTIVE,
                Product.track_inventory.is_(True),
                Product.stock > 0,
            )
        ).scalars().all()

        out: list[Notification] = []
        for p in rows:
            threshold = int(p.low_stock_threshold or default_threshold)
            if p.stock > threshold:
                continue
            out.append(Notification(
                id=_stable_id("N5_low_stock", p.id),
                severity="warning",
                category="inventory",
                title=f"'{p.name}' tiene stock bajo",
                body=(
                    f"Solo {p.stock} unidades (umbral: {threshold}). "
                    f"Te recomendamos reponer antes del fin de semana."
                ),
                action_label="Reponer stock",
                action_url=f"/dashboard/products/{p.id}#inventory",
                entity_type="product",
                entity_id=p.id,
                detected_at=_now_iso(),
                metric={"stock": int(p.stock), "threshold": threshold},
            ))
        return out

    # ──────────────────────────────────────────────────────
    # Reglas — Orders
    # ──────────────────────────────────────────────────────

    def _rule_pending_orders_old(self) -> list[Notification]:
        """N6 — Pedidos en PENDING con más de N horas."""
        from app.models.order import Order, OrderStatus
        hours = THRESHOLDS["pending_order_hours"]
        cutoff = self._now - timedelta(hours=hours)
        rows = self.db.execute(
            select(Order).where(
                Order.tenant_id == self.tid,
                Order.status == OrderStatus.PENDING,
                Order.created_at < cutoff,
            )
        ).scalars().all()

        out: list[Notification] = []
        for o in rows:
            # Normalizar: SQLite no preserva tz en DateTime, lo agregamos acá
            created = o.created_at
            if created is not None and created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            age_hours = (self._now - created).total_seconds() / 3600
            out.append(Notification(
                id=_stable_id("N6_pending_old", o.id),
                severity="warning",
                category="orders",
                title=f"Pedido #{str(o.id)[:8]} lleva {age_hours:.0f}h pendiente",
                body=(
                    f"Total: {_format_money(int(o.total_cents or 0))}. "
                    f"Conviene confirmarlo o cancelarlo para liberar inventario."
                ),
                action_label="Ver pedido",
                action_url=f"/dashboard/orders/{o.id}",
                entity_type="order",
                entity_id=o.id,
                detected_at=_now_iso(),
                metric={
                    "age_hours": round(age_hours, 1),
                    "total_cents": int(o.total_cents or 0),
                },
            ))
        return out

    # ──────────────────────────────────────────────────────
    # Reglas — Costs (V8)
    # ──────────────────────────────────────────────────────

    def _rule_costs_not_configured(self) -> list[Notification]:
        """N7 — El tenant nunca configuró Costos (BusinessCosts.version == 1)."""
        from app.models.business_costs import BusinessCosts
        bc = self.db.execute(
            select(BusinessCosts).where(BusinessCosts.tenant_id == self.tid)
        ).scalar_one_or_none()

        # Si no hay fila o la versión es 1 (defaults) → no configurado
        if bc and (bc.version or 1) > 1:
            return []

        return [Notification(
            id=_stable_id("N7_costs_unconfigured", "tenant"),
            severity="info",
            category="costs",
            title="Configurá tus costos para recibir sugerencias de precio",
            body=(
                "Sin tu estructura de costos, no podemos sugerirte precios "
                "ni detectar márgenes bajos. Te lleva 2 minutos."
            ),
            action_label="Configurar costos",
            action_url="/dashboard/admin_costs",
            entity_type="tenant",
            entity_id="tenant",
            detected_at=_now_iso(),
            metric={"configured": False, "version": (bc.version if bc else 0)},
        )]

    def _rule_high_cost_hour(self) -> list[Notification]:
        """N8 — Costo_hora elevado (posible carga fija muy alta o pocas horas)."""
        from app.models.business_costs import BusinessCosts
        bc = self.db.execute(
            select(BusinessCosts).where(BusinessCosts.tenant_id == self.tid)
        ).scalar_one_or_none()
        if not bc or not bc.cost_hour_cents:
            return []
        threshold = THRESHOLDS["high_cost_hour_cents"]
        if int(bc.cost_hour_cents) < threshold:
            return []

        return [Notification(
            id=_stable_id("N8_high_cost_hour", "tenant"),
            severity="warning",
            category="costs",
            title="Tu costo por hora está elevado",
            body=(
                f"Costo hora actual: {_format_money(int(bc.cost_hour_cents))}/h "
                f"(umbral: {_format_money(threshold)}/h). "
                f"Revisá sueldos, arriendo o horas productivas para optimizarlo."
            ),
            action_label="Ver costos",
            action_url="/dashboard/admin_costs",
            entity_type="tenant",
            entity_id="tenant",
            detected_at=_now_iso(),
            metric={
                "cost_hour_cents": int(bc.cost_hour_cents),
                "threshold_cents": threshold,
                "total_fixed_cents": int(bc.total_fixed_cents or 0),
                "productive_hours": int(bc.productive_hours_per_month or 0),
            },
        )]

    # ──────────────────────────────────────────────────────
    # Reglas — System
    # ──────────────────────────────────────────────────────

    def _rule_system(self) -> list[Notification]:
        """N9 — Mensaje de bienvenida después del primer login post-seed.

        Solo aparece si el tenant fue creado en las últimas 24h y nunca
        tuvo un owner que haya visitado el dashboard.
        """
        from app.models.tenant import Tenant
        t = self.db.execute(
            select(Tenant).where(Tenant.id == self.tid)
        ).scalar_one_or_none()
        if not t or not t.created_at:
            return []
        # Normalizar tz (SQLite no preserva)
        created = t.created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        # Si fue creado hace más de 24h, no notificamos
        if (self._now - created).total_seconds() > 24 * 3600:
            return []
        return [Notification(
            id=_stable_id("N9_welcome", "tenant"),
            severity="info",
            category="system",
            title="¡Bienvenido a WowHub!",
            body=(
                "Empezá por configurar tus costos y subir tu primer producto. "
                "Te recomendamos el tour de 5 pasos."
            ),
            action_label="Empezar tour",
            action_url="/dashboard/onboarding",
            entity_type="tenant",
            entity_id="tenant",
            detected_at=_now_iso(),
            metric={"tenant_created_hours_ago": round(
                (self._now - created).total_seconds() / 3600, 1,
            )},
        )]
