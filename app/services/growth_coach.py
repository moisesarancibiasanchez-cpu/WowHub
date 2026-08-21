"""Growth Coach — WowHub AI Core™ (Cap. 19.2).

Análisis proactivo de la "Memoria de Negocio" (ventas, inventario,
clientes, promociones, reservas) que devuelve insights accionables.
A diferencia del Marketing Studio (que genera copy), el Growth Coach
genera RECOMENDACIONES a partir de los datos del tenant.

Pipeline:
1. `GrowthCoach.analyze(req, tenant_ctx, db)` recibe un
   `GrowthAnalysisRequest` validado por Pydantic.
2. Recolecta la "Memoria de Negocio" consultando:
   - StatsService.overview() → ventas + top productos
   - AnalyticsService.inventory() → stock bajo, sin stock, top selling
   - AnalyticsService.customer_segments() → inactivos, top, nuevos, VIP
   - Direct queries → promociones, reservas (count, activas, top)
3. Construye un system prompt especializado en análisis de negocio
   (no el genérico de los sub-agentes ni el de marketing) + user prompt
   con el focus pedido.
4. Llama al LLM con `temperature=0.4` (baja creatividad, alta
   consistencia) y `max_tokens` adaptado a `max_insights`.
5. Parsea la respuesta. El LLM DEBE devolver JSON con
   `{"summary": "...", "insights": [{"type","priority","category",
   "title","description","evidence","recommended_actions",
   "linked_module","metric_impact_estimate"}]}`.
6. Si el LLM falla (circuit abierto, key faltante, JSON inválido) →
   usa análisis determinístico (`_fallback_analyze`) basado en reglas
   que SIEMPRE produce insights útiles a partir de los datos
   disponibles. Garantiza que la UI nunca rompa.

Diseño clave (lecciones aprendidas del Marketing Studio):
- Los datos del negocio se leen UNA vez y se inyectan YA ESTRUCTURADOS
  al prompt. NUNCA se le pide al LLM que invente cifras.
- El response incluye `business_memory` (snapshot) para que la UI/debug
  vean exactamente qué datos usó.
- Los insights se devuelven ordenados por `priority` desc
  (urgent → high → medium → low).
- El fallback es SEMPRE útil: si hay 5 productos sin stock, el insight
  "Tienes 5 productos sin stock que requieren reposición" aparece
  incluso si el LLM está caído.

Tests: `tests/test_growth_coach.py`.
"""
from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.schemas.ai import (
    BusinessMemorySnapshot,
    GrowthAnalysisRequest,
    GrowthAnalysisResponse,
    GrowthInsight,
    GrowthInsightCategory,
    GrowthInsightPriority,
    GrowthInsightType,
)
from app.services.analytics_service import AnalyticsService
from app.services.llm_client import (
    LLMClient,
    LLMFallback,
    LLMMessage,
    get_circuit,
)
from app.services.stats_service import StatsService

logger = logging.getLogger("wowhub.ai.growth_coach")


# ── System prompt (NO es el genérico de los sub-agentes) ──────────
# Especializado en análisis de negocio: prioriza ACCIÓN CONCRETA sobre
# creatividad. Output JSON ESTRICTO para que el parseo sea robusto.
_GROWTH_SYSTEM_PROMPT = """Eres un analista de negocio experto para WowHub, una plataforma SaaS para
pequeños negocios latinoamericanos (restaurantes, cafeterías, barberías,
tiendas, servicios). Tu trabajo es ANALIZAR DATOS REALES del negocio y
devolver INSIGHTS ACCIONABLES en formato JSON.

DATOS DE ENTRADA: vas a recibir un objeto `business_memory` con 5
secciones (sales, inventory, customers, promotions, bookings). Cada
sección puede estar VACÍA si no hay datos — NUNCA inventes cifras.

REGLAS OBLIGATORIAS:
1. SOLO USA CIFRAS DEL SNAPSHOT. Si el snapshot dice "no data" en una
   sección, NO generes insights sobre esa sección. Di que no hay datos.
2. PRIORIZA ACCIÓN CONCRETA. Cada insight debe tener 1-5 acciones
   que el dueño del negocio pueda hacer hoy (no "considera", "evalúa"
   genérico — "Crear promo 2x1 para el producto X", "Enviar WhatsApp
   a los 8 clientes inactivos", etc.).
3. NO inventes módulos, rutas, endpoints ni features. SOLO menciona
   módulos que EXISTEN en WowHub: productos, promociones, clientes,
   reservas, campanas, marketing_studio, configuracion. NO inventes.
4. NO incluyas URLs, links, ni "consultar con soporte" si no es un
   insight específico sobre un problema que requiere soporte humano.
5. PRIORIDADES: usa "urgent" solo para riesgos reales (out_of_stock
   de productos top, cancelaciones masivas). "high" para oportunidades
   concretas. "medium" para mejoras incrementales. "low" para info.
6. CATEGORÍAS VÁLIDAS (deben coincidir exactamente):
   - "sales"        → insights sobre ingresos, ticket, tendencias
   - "inventory"    → insights sobre stock, productos
   - "customers"    → insights sobre segmentos, retención, lealtad
   - "promotions"   → insights sobre promos activas, frecuencia
   - "bookings"     → insights sobre reservas, cancelaciones
   - "operations"   → insights sobre horarios, sucursales, branding
7. TIPOS VÁLIDOS (deben coincidir exactamente):
   - "opportunity"   → oportunidad de crecer
   - "warning"       → alerta que requiere atención
   - "anomaly"       → comportamiento fuera de patrón
   - "recommendation"→ acción concreta
   - "insight"       → observación informativa
8. EVIDENCIA: cada insight DEBE tener 1-5 items en `evidence` que
   reproduzcan CIFRAS LITERALES del snapshot (no las parafrasees).
9. IMPACTO ESTIMADO: si lo incluís, que sea APROXIMADO
   (ej. "+10-15% ingresos", "recuperar 8 clientes"). NO prometas
   cifras exactas ni absolutas.
10. IDIOMA: responde en el idioma del campo `language` del request.
    Default: español neutro.
11. Devuelve un MÁXIMO de `max_insights` insights, ordenados por
    prioridad descendente (urgent → low).
12. Devuelve EXACTAMENTE el JSON pedido. NO uses bloques ```json ni
    ``` ni texto antes o después.

FORMATO DE SALIDA (JSON ESTRICTO, sin fences):
{
  "summary": "Resumen ejecutivo de 1-3 oraciones sobre el estado del negocio.",
  "insights": [
    {
      "type": "opportunity|warning|anomaly|recommendation|insight",
      "priority": "urgent|high|medium|low",
      "category": "sales|inventory|customers|promotions|bookings|operations",
      "title": "Título corto y accionable (5-120 chars)",
      "description": "Descripción de 1-3 oraciones (10-1000 chars)",
      "evidence": ["dato1 del snapshot", "dato2 del snapshot"],
      "recommended_actions": ["Acción 1", "Acción 2", "Acción 3"],
      "linked_module": "products|promotions|customers|bookings|campaigns|marketing_studio|null",
      "metric_impact_estimate": "+10-15% ingresos | null"
    }
  ]
}

Si NO hay datos en el snapshot (tenant nuevo), devuelve un solo
insight informativo de tipo "insight" recomendando cargar productos/
clientes primero. NO inventes cifras.
"""


# ── Mapeo de prioridad a peso numérico (para ordenar) ────────────
_PRIORITY_WEIGHT = {
    GrowthInsightPriority.URGENT: 4,
    GrowthInsightPriority.HIGH: 3,
    GrowthInsightPriority.MEDIUM: 2,
    GrowthInsightPriority.LOW: 1,
}


@dataclass
class TenantContext:
    """Contexto del tenant (reutilizado del patrón de marketing_studio)."""
    tenant_id: str
    slug: Optional[str] = None
    name: Optional[str] = None
    public_base_url: Optional[str] = None

    @property
    def has_slug(self) -> bool:
        return bool(self.slug)


class GrowthCoach:
    """Servicio principal del Growth Coach (Cap. 19.2)."""

    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self.llm = llm_client or LLMClient()

    # ── Entry point ────────────────────────────────────────
    async def analyze(
        self,
        req: GrowthAnalysisRequest,
        tenant_ctx: TenantContext,
        db: Session,
    ) -> GrowthAnalysisResponse:
        """Pipeline completo: gather → LLM (o fallback) → response."""
        t0 = time.monotonic()
        # 1. Recolectar Memoria de Negocio
        memory = self._gather_business_memory(db, tenant_ctx, req.lookback_days)

        # 2. Intentar LLM
        try:
            messages = self._build_messages(req, memory)
            resp = await self.llm.generate(
                messages,
                temperature=0.4,
                max_tokens=min(200 + req.max_insights * 200, 4096),
            )
            summary, insights = self._parse_llm_response(
                resp.content,
                max_insights=req.max_insights,
                focus=req.focus,
            )
            latency = int((time.monotonic() - t0) * 1000)
            return GrowthAnalysisResponse(
                focus=req.focus,
                lookback_days=req.lookback_days,
                language=req.language,
                summary=summary,
                insights=self._sort_by_priority(insights)[: req.max_insights],
                business_memory=memory,
                fallback=False,
                model=self.llm.model,
                tokens_in=resp.tokens_in,
                tokens_out=resp.tokens_out,
                latency_ms=latency,
            )
        except LLMFallback as e:
            reason = getattr(e, "code", "fallback")
            logger.warning("Growth Coach: LLM fallback (%s) — usando reglas", reason)
        except Exception as e:  # noqa: BLE001
            reason = f"unexpected:{type(e).__name__}"
            logger.exception("Growth Coach: error inesperado — usando reglas: %s", e)
            # Reset circuit en errores inesperados
            try:
                get_circuit().record_failure()
            except Exception:
                pass

        # 3. Fallback determinístico
        summary, insights = self._fallback_analyze(memory, req, reason)
        latency = int((time.monotonic() - t0) * 1000)
        return GrowthAnalysisResponse(
            focus=req.focus,
            lookback_days=req.lookback_days,
            language=req.language,
            summary=summary,
            insights=self._sort_by_priority(insights)[: req.max_insights],
            business_memory=memory,
            fallback=True,
            fallback_reason=reason,
            model=None,
            tokens_in=None,
            tokens_out=None,
            latency_ms=latency,
        )

    # ── 1. Recolectar Memoria de Negocio ────────────────────
    def _gather_business_memory(
        self,
        db: Session,
        tenant_ctx: TenantContext,
        lookback_days: int,
    ) -> BusinessMemorySnapshot:
        """Lee los 5 dominios del negocio y devuelve un snapshot."""
        tid = str(tenant_ctx.tenant_id)
        sales = self._gather_sales(db, tid, lookback_days)
        inventory = self._gather_inventory(db, tid)
        customers = self._gather_customers(db, tid)
        promotions = self._gather_promotions(db, tid, lookback_days)
        bookings = self._gather_bookings(db, tid, lookback_days)
        data_completeness = {
            "sales": bool(sales),
            "inventory": bool(inventory.get("total_products")),
            "customers": bool(customers.get("total_customers")),
            "promotions": "total" in promotions,
            "bookings": "total" in bookings,
        }
        return BusinessMemorySnapshot(
            tenant_id=tid,
            tenant_name=tenant_ctx.name,
            tenant_slug=tenant_ctx.slug,
            lookback_days=lookback_days,
            sales=sales,
            inventory=inventory,
            customers=customers,
            promotions=promotions,
            bookings=bookings,
            data_completeness=data_completeness,
        )

    def _gather_sales(self, db: Session, tid: str, lookback_days: int) -> dict[str, Any]:
        try:
            stats = StatsService(db).overview(UUID(tid), days=lookback_days)
            return {
                "total_orders": stats.get("total_orders", 0),
                "total_revenue_cents": stats.get("total_revenue_cents", 0),
                "total_discount_cents": stats.get("total_discount_cents", 0),
                "delivered": stats.get("delivered", 0),
                "canceled": stats.get("canceled", 0),
                "pending": stats.get("pending", 0),
                "aov_cents": stats.get("aov_cents", 0),
                "top_products": stats.get("top_products", [])[:5],
                "lookback_days": lookback_days,
            }
        except Exception as e:  # noqa: BLE001
            logger.warning("gather_sales failed: %s", e)
            return {"lookback_days": lookback_days, "error": str(e)}

    def _gather_inventory(self, db: Session, tid: str) -> dict[str, Any]:
        try:
            ana = AnalyticsService(db)
            low = ana.inventory(UUID(tid), category="low_stock", limit=20)
            out = ana.inventory(UUID(tid), category="out_of_stock", limit=20)
            top = ana.inventory(UUID(tid), category="top_selling", limit=5)
            dead = ana.inventory(UUID(tid), category="dead_stock", days_dead=60, limit=10)
            summary = ana._inventory_summary(tid, overstock_threshold=100)
            return {
                "low_stock": low.get("items", []),
                "out_of_stock": out.get("items", []),
                "top_selling": top.get("items", []),
                "dead_stock": dead.get("items", []),
                "total_products": summary.get("total_products", 0),
                "low_stock_count": summary.get("low_stock", 0),
                "out_of_stock_count": summary.get("out_of_stock", 0),
                "overstock_count": summary.get("overstock", 0),
                "dead_stock_count": summary.get("dead_stock", 0),
            }
        except Exception as e:  # noqa: BLE001
            logger.warning("gather_inventory failed: %s", e)
            return {"error": str(e)}

    def _gather_customers(self, db: Session, tid: str) -> dict[str, Any]:
        try:
            ana = AnalyticsService(db)
            segs = ana.customer_segments(UUID(tid))
            return {
                "total_customers": segs.get("total_customers", 0),
                "segments": {
                    "new": segs.get("new", []),
                    "vip": segs.get("vip", []),
                    "top": segs.get("top", []),
                    "inactive": segs.get("inactive", []),
                },
                "inactive_count": len(segs.get("inactive", [])),
                "vip_count": len(segs.get("vip", [])),
                "new_count": len(segs.get("new", [])),
            }
        except Exception as e:  # noqa: BLE001
            logger.warning("gather_customers failed: %s", e)
            return {"error": str(e)}

    def _gather_promotions(self, db: Session, tid: str, lookback_days: int) -> dict[str, Any]:
        try:
            # Import local para evitar ciclos
            from app.models.promotion import Promotion
            total = db.execute(
                select(func.count(Promotion.id)).where(Promotion.tenant_id == tid)
            ).scalar() or 0
            # active: según status si existe; si no, contamos las vigentes
            active_q = db.execute(
                select(func.count(Promotion.id)).where(
                    Promotion.tenant_id == tid,
                    Promotion.is_active == True,  # noqa: E712
                )
            )
            active = active_q.scalar() or 0
            return {
                "total": int(total),
                "active": int(active),
                "lookback_days": lookback_days,
            }
        except Exception as e:  # noqa: BLE001
            logger.warning("gather_promotions failed: %s", e)
            return {"lookback_days": lookback_days, "error": str(e)}

    def _gather_bookings(self, db: Session, tid: str, lookback_days: int) -> dict[str, Any]:
        try:
            from app.models.booking import Booking
            total = db.execute(
                select(func.count(Booking.id)).where(Booking.tenant_id == tid)
            ).scalar() or 0
            # Conteo por status si la columna existe
            try:
                canceled = db.execute(
                    select(func.count(Booking.id)).where(
                        Booking.tenant_id == tid,
                        Booking.status.in_(["canceled", "cancelled", "no_show"]),
                    )
                ).scalar() or 0
            except Exception:
                canceled = 0
            return {
                "total": int(total),
                "canceled": int(canceled),
                "cancellation_rate": (int(canceled) / int(total)) if int(total) > 0 else 0.0,
                "lookback_days": lookback_days,
            }
        except Exception as e:  # noqa: BLE001
            logger.warning("gather_bookings failed: %s", e)
            return {"lookback_days": lookback_days, "error": str(e)}

    # ── 2. Construir mensajes para el LLM ──────────────────
    def _build_messages(
        self,
        req: GrowthAnalysisRequest,
        memory: BusinessMemorySnapshot,
    ) -> list[LLMMessage]:
        focus_label = {
            "overview": "vista 360 del negocio",
            "sales": "ventas e ingresos",
            "inventory": "inventario y stock",
            "customers": "clientes y segmentos",
            "promotions": "promociones y campañas",
            "bookings": "reservas y agenda",
            "mixed": "todas las áreas (1-2 insights por categoría)",
        }.get(req.focus, req.focus)
        user_prompt = (
            f"Generá un análisis con foco en **{focus_label}** para los últimos "
            f"**{req.lookback_days} días**. Idioma: **{req.language}**. "
            f"Máximo de insights: **{req.max_insights}**.\n\n"
            f"## Memoria de Negocio (snapshot de los datos del tenant)\n\n"
            f"```json\n{json.dumps(self._memory_to_llm_dict(memory), indent=2, ensure_ascii=False, default=str)}\n```\n\n"
            f"## Secciones con datos\n\n"
            f"{self._data_completeness_summary(memory)}\n\n"
            f"Devolvé EXCLUSIVAMENTE el JSON pedido. NO uses bloques ```json, "
            f"NO agregues texto antes ni después."
        )
        return [
            LLMMessage(role="system", content=_GROWTH_SYSTEM_PROMPT),
            LLMMessage(role="user", content=user_prompt),
        ]

    def _memory_to_llm_dict(self, memory: BusinessMemorySnapshot) -> dict[str, Any]:
        """Convierte el snapshot a un dict limpio para el prompt (sin Pydantic)."""
        return {
            "tenant": {
                "id": memory.tenant_id,
                "name": memory.tenant_name,
                "slug": memory.tenant_slug,
                "lookback_days": memory.lookback_days,
            },
            "sales": memory.sales,
            "inventory": memory.inventory,
            "customers": memory.customers,
            "promotions": memory.promotions,
            "bookings": memory.bookings,
            "data_completeness": memory.data_completeness,
        }

    def _data_completeness_summary(self, memory: BusinessMemorySnapshot) -> str:
        lines = []
        for section, has_data in memory.data_completeness.items():
            mark = "✅ tiene datos" if has_data else "⚠️ sin datos"
            lines.append(f"- **{section}**: {mark}")
        return "\n".join(lines) if lines else "(sin datos)"

    # ── 3. Parsear respuesta del LLM ───────────────────────
    def _parse_llm_response(
        self,
        raw: str,
        *,
        max_insights: int,
        focus: str,
    ) -> tuple[str, list[GrowthInsight]]:
        """Parsea la respuesta del LLM. Tolerante a fences y texto alrededor."""
        if not raw or not raw.strip():
            raise LLMFallback("Respuesta vacía del LLM", code="empty")
        text = raw.strip()
        # Quitar fences ```json ... ``` o ``` ... ```
        fence_re = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE | re.MULTILINE)
        text = fence_re.sub("", text).strip()
        # Intentar parseo JSON directo
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            # Intentar extraer el primer {...} balanceado
            m = re.search(r"\{.*\}", text, re.DOTALL)
            if not m:
                raise LLMFallback("LLM no devolvió JSON válido", code="invalid_json")
            try:
                data = json.loads(m.group(0))
            except json.JSONDecodeError as e:
                raise LLMFallback(f"JSON inválido: {e}", code="invalid_json")

        if not isinstance(data, dict):
            raise LLMFallback("JSON raíz no es objeto", code="invalid_shape")

        summary = (data.get("summary") or "").strip()
        if not summary:
            summary = "Análisis generado por el Growth Coach."

        raw_insights = data.get("insights") or []
        if not isinstance(raw_insights, list):
            raw_insights = []

        insights: list[GrowthInsight] = []
        for i, item in enumerate(raw_insights[: max_insights * 2]):  # pequeño margen
            try:
                ins = self._coerce_insight(item, idx=i + 1)
                if ins is not None:
                    insights.append(ins)
            except Exception as e:  # noqa: BLE001
                logger.debug("Insight descartado por parse error: %s | %s", e, item)
                continue
            if len(insights) >= max_insights:
                break

        return summary, insights

    def _coerce_insight(
        self,
        item: Any,
        *,
        idx: int,
    ) -> GrowthInsight | None:
        """Coacciona un dict del LLM a un GrowthInsight."""
        if not isinstance(item, dict):
            return None
        # type con fallback
        t = str(item.get("type") or "insight").lower()
        if t not in {"opportunity", "warning", "anomaly", "recommendation", "insight"}:
            t = "insight"
        # priority con fallback
        p = str(item.get("priority") or "medium").lower()
        if p not in {"urgent", "high", "medium", "low"}:
            p = "medium"
        # category con fallback
        c = str(item.get("category") or "operations").lower()
        if c not in {"sales", "inventory", "customers", "promotions", "bookings", "operations"}:
            c = "operations"
        title = str(item.get("title") or "").strip()
        if len(title) < 5:
            title = f"Insight {idx}"
        title = title[:120]
        description = str(item.get("description") or "").strip()
        if len(description) < 10:
            description = "Recomendación generada por el Growth Coach."
        description = description[:1000]
        evidence_raw = item.get("evidence") or []
        if not isinstance(evidence_raw, list):
            evidence_raw = []
        evidence = [str(e) for e in evidence_raw if e is not None][:8]
        actions_raw = item.get("recommended_actions") or []
        if not isinstance(actions_raw, list):
            actions_raw = []
        actions = [str(a) for a in actions_raw if a is not None][:8]
        linked_module = item.get("linked_module")
        if linked_module is not None:
            linked_module = str(linked_module)[:64] or None
        impact = item.get("metric_impact_estimate")
        if impact is not None:
            impact = str(impact)[:120] or None
        return GrowthInsight(
            type=t,
            priority=p,
            category=c,
            title=title,
            description=description,
            evidence=evidence,
            recommended_actions=actions,
            linked_module=linked_module,
            metric_impact_estimate=impact,
        )

    # ── 4. Fallback determinístico ─────────────────────────
    def _fallback_analyze(
        self,
        memory: BusinessMemorySnapshot,
        req: GrowthAnalysisRequest,
        reason: str,
    ) -> tuple[str, list[GrowthInsight]]:
        """Análisis basado en reglas cuando el LLM no está disponible.

        SIEMPRE devuelve insights útiles basados en los datos que
        existen. Si casi no hay datos, devuelve un insight informativo
        invitando a cargar productos/clientes.
        """
        insights: list[GrowthInsight] = []
        any_data = any(memory.data_completeness.values())

        # ── Inventory: stock bajo / sin stock (URGENT) ────────
        out_n = int(memory.inventory.get("out_of_stock_count", 0))
        if out_n > 0:
            names = [
                (i.get("name") if isinstance(i, dict) else None) or "(sin nombre)"
                for i in memory.inventory.get("out_of_stock", [])[:5]
            ]
            insights.append(GrowthInsight(
                type=GrowthInsightType.WARNING,
                priority=GrowthInsightPriority.URGENT if out_n >= 3 else GrowthInsightPriority.HIGH,
                category=GrowthInsightCategory.INVENTORY,
                title=f"{out_n} producto{'s' if out_n != 1 else ''} sin stock",
                description=(
                    f"Tenés {out_n} productos sin stock que probablemente están "
                    f"generando pérdida de ventas. Reposición prioritaria."
                ),
                evidence=[f"Sin stock: {', '.join(names)}"] if names else [f"out_of_stock_count={out_n}"],
                recommended_actions=[
                    "Ir a Productos y reponer los más vendidos primero",
                    "Contactar proveedores para reposición urgente",
                    "Pausar o ajustar la promoción activa sobre estos productos",
                ],
                linked_module="products",
                metric_impact_estimate="Recuperar ventas perdidas por falta de stock",
            ))

        # ── Inventory: stock bajo (HIGH) ──────────────────────
        low_n = int(memory.inventory.get("low_stock_count", 0))
        if low_n > 0:
            insights.append(GrowthInsight(
                type=GrowthInsightType.WARNING,
                priority=GrowthInsightPriority.MEDIUM,
                category=GrowthInsightCategory.INVENTORY,
                title=f"{low_n} producto{'s' if low_n != 1 else ''} con stock bajo",
                description=(
                    f"Hay {low_n} productos con stock bajo que se quedarán sin "
                    f"inventario pronto si no se reponen. Planificá reposición."
                ),
                evidence=[f"low_stock_count={low_n}"],
                recommended_actions=[
                    "Revisar la lista de stock bajo en Productos",
                    "Hacer un pedido de reposición esta semana",
                ],
                linked_module="products",
                metric_impact_estimate="Evitar roturas de stock en los próximos 7-14 días",
            ))

        # ── Inventory: dead stock (MEDIUM) ───────────────────
        dead_n = int(memory.inventory.get("dead_stock_count", 0))
        if dead_n >= 3:
            insights.append(GrowthInsight(
                type=GrowthInsightType.RECOMMENDATION,
                priority=GrowthInsightPriority.MEDIUM,
                category=GrowthInsightCategory.INVENTORY,
                title=f"{dead_n} productos sin ventas en 60+ días",
                description=(
                    f"Detectamos {dead_n} productos sin ventas recientes. "
                    f"可以考虑 crear una promo para liquidarlos o archivarlos."
                ),
                evidence=[f"dead_stock_count={dead_n}"],
                recommended_actions=[
                    "Crear una promoción con descuento agresivo para estos productos",
                    "Archivar los productos que no son estratégicos",
                ],
                linked_module="promotions",
                metric_impact_estimate="Liberar capital de trabajo inmovilizado",
            ))

        # ── Customers: inactivos (HIGH) ──────────────────────
        inactive_n = int(memory.customers.get("inactive_count", 0))
        if inactive_n >= 3:
            insights.append(GrowthInsight(
                type=GrowthInsightType.OPPORTUNITY,
                priority=GrowthInsightPriority.HIGH,
                category=GrowthInsightCategory.CUSTOMERS,
                title=f"{inactive_n} clientes inactivos para reactivar",
                description=(
                    f"Tenés {inactive_n} clientes que no compran hace tiempo. "
                    f"Una campaña de reactivación podría recuperar ventas."
                ),
                evidence=[f"inactive_count={inactive_n}"],
                recommended_actions=[
                    "Crear un segmento 'Inactivos' en Campañas",
                    "Enviar un WhatsApp con promo personalizada",
                    "Usar Marketing Studio para redactar el copy de la campaña",
                ],
                linked_module="marketing_studio",
                metric_impact_estimate=f"Reactivar entre {max(1, inactive_n // 4)} y {max(2, inactive_n // 2)} clientes",
            ))

        # ── Customers: VIP (OPPORTUNITY) ─────────────────────
        vip_n = int(memory.customers.get("vip_count", 0))
        if vip_n >= 3:
            insights.append(GrowthInsight(
                type=GrowthInsightType.INSIGHT,
                priority=GrowthInsightPriority.LOW,
                category=GrowthInsightCategory.CUSTOMERS,
                title=f"{vip_n} clientes VIP: fidelizálos",
                description=(
                    f"Tenés {vip_n} clientes VIP. Mantenerlos engaged es más "
                    f"barato que conseguir nuevos. Considerá un beneficio exclusivo."
                ),
                evidence=[f"vip_count={vip_n}"],
                recommended_actions=[
                    "Crear una promo exclusiva para VIPs",
                    "Enviar un agradecimiento personalizado",
                ],
                linked_module="campaigns",
                metric_impact_estimate="Aumentar retención de clientes de alto valor",
            ))

        # ── Promotions: sin promos activas (RECOMMENDATION) ──
        promos_total = int(memory.promotions.get("total", 0))
        promos_active = int(memory.promotions.get("active", 0))
        if promos_total == 0:
            insights.append(GrowthInsight(
                type=GrowthInsightType.OPPORTUNITY,
                priority=GrowthInsightPriority.HIGH,
                category=GrowthInsightCategory.PROMOTIONS,
                title="No tenés promociones creadas",
                description=(
                    "Las promociones son una de las palancas más efectivas para "
                    "aumentar ventas y mover stock. Crea tu primera promo."
                ),
                evidence=["promotions.total=0"],
                recommended_actions=[
                    "Crear una promo 2x1 o con descuento en un producto top",
                    "Usar Marketing Studio para redactar el copy de la promo",
                    "Activar la promo por 7-14 días y medir impacto",
                ],
                linked_module="promotions",
                metric_impact_estimate="+10-20% en ventas durante la vigencia",
            ))
        elif promos_active == 0 and promos_total > 0:
            insights.append(GrowthInsight(
                type=GrowthInsightType.RECOMMENDATION,
                priority=GrowthInsightPriority.MEDIUM,
                category=GrowthInsightCategory.PROMOTIONS,
                title="Ninguna promoción activa",
                description=(
                    f"Tenés {promos_total} promociones creadas pero ninguna activa. "
                    f"Activá una para empezar a generar impacto."
                ),
                evidence=[f"promotions.active=0 de un total de {promos_total}"],
                recommended_actions=[
                    "Ir a Promociones y activar una existente",
                    "Crear una nueva promo alineada con productos top",
                ],
                linked_module="promotions",
            ))

        # ── Sales: comparación con período previo (ANOMALY) ──
        sales = memory.sales or {}
        total_rev = int(sales.get("total_revenue_cents", 0))
        if total_rev == 0 and not any_data:
            # tenant realmente nuevo
            insights.append(GrowthInsight(
                type=GrowthInsightType.INSIGHT,
                priority=GrowthInsightPriority.HIGH,
                category=GrowthInsightCategory.OPERATIONS,
                title="Tu tienda todavía no tiene datos",
                description=(
                    "Para activar el Growth Coach necesitás datos del negocio. "
                    "Empezá cargando productos, clientes y haciendo tus primeras ventas."
                ),
                evidence=["snapshot sin datos en ninguna sección"],
                recommended_actions=[
                    "Ir a Productos y cargar tu catálogo",
                    "Registrar tu primer cliente en Clientes",
                    "Hacer una venta de prueba para activar las métricas",
                ],
                linked_module="products",
            ))

        # ── Bookings: cancelaciones (WARNING) ────────────────
        cancel_rate = float(memory.bookings.get("cancellation_rate", 0.0))
        if cancel_rate > 0.20 and memory.bookings.get("total", 0) >= 5:
            insights.append(GrowthInsight(
                type=GrowthInsightType.WARNING,
                priority=GrowthInsightPriority.HIGH,
                category=GrowthInsightCategory.BOOKINGS,
                title=f"Tasa de cancelación de reservas: {int(cancel_rate * 100)}%",
                description=(
                    f"Cerca de 1 de cada {int(1 / max(cancel_rate, 0.01))} reservas se cancela. "
                    f"Podrías recuperar ingresos con recordatorios o política de seña."
                ),
                evidence=[
                    f"total reservas: {memory.bookings.get('total', 0)}",
                    f"canceladas: {memory.bookings.get('canceled', 0)}",
                ],
                recommended_actions=[
                    "Activar recordatorios automáticos 24h antes de la reserva",
                    "Considerar una seña o política de cancelación",
                    "Revisar la configuración de sucursales y horarios",
                ],
                linked_module="bookings",
            ))

        # ── Sales: top products (insight) ────────────────────
        top_prods = sales.get("top_products") or []
        if top_prods:
            tp = top_prods[0]
            name = tp.get("name") if isinstance(tp, dict) else None
            if name:
                insights.append(GrowthInsight(
                    type=GrowthInsightType.INSIGHT,
                    priority=GrowthInsightPriority.LOW,
                    category=GrowthInsightCategory.SALES,
                    title=f"Tu producto estrella: {name}",
                    description=(
                        f"El producto más vendido en los últimos {req.lookback_days} días "
                        f"es '{name}'. Asegurate de tener stock y considerá crear "
                        f"un combo o una variante premium."
                    ),
                    evidence=[
                        f"top product: {name} (revenue_cents={tp.get('revenue_cents', 0)}, "
                        f"units_sold={tp.get('units_sold', 0)})"
                    ],
                    recommended_actions=[
                        "Verificar stock de este producto",
                        "Crear un combo con productos complementarios",
                    ],
                    linked_module="products",
                ))

        # Si no generamos nada, devolver un insight informativo
        if not insights:
            insights.append(GrowthInsight(
                type=GrowthInsightType.INSIGHT,
                priority=GrowthInsightPriority.LOW,
                category=GrowthInsightCategory.OPERATIONS,
                title="Sin insights accionables por ahora",
                description=(
                    "Con los datos actuales no detectamos oportunidades críticas. "
                    "Seguimos acumulando información; volvé a consultar en unos días."
                ),
                evidence=["fallback sin insights generados"],
                recommended_actions=[
                    "Revisar el dashboard de Resumen para métricas generales",
                ],
                linked_module=None,
            ))

        # Summary genérico basado en el motivo
        if reason in ("not_configured", "circuit_open"):
            summary = (
                f"Análisis generado con datos reales (motor de IA no disponible). "
                f"Se detectaron {len(insights)} insight{'s' if len(insights) != 1 else ''} "
                f"accionables sobre tu negocio en los últimos {req.lookback_days} días."
            )
        else:
            summary = (
                f"Análisis generado en modo de respaldo. "
                f"Se identificaron {len(insights)} insight{'s' if len(insights) != 1 else ''} "
                f"a partir de la Memoria de Negocio."
            )
        return summary, insights

    # ── Helpers ────────────────────────────────────────────
    def _sort_by_priority(
        self,
        insights: list[GrowthInsight],
    ) -> list[GrowthInsight]:
        """Ordena por prioridad desc (urgent → low), manteniendo orden estable."""
        return sorted(
            insights,
            key=lambda i: -_PRIORITY_WEIGHT.get(i.priority, 0),
        )
