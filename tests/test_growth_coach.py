"""Tests del Growth Coach (Cap. 19.2 del WowHub AI Core).

Cubre:
1. Schemas Pydantic: validación, defaults, límites.
2. Servicio GrowthCoach: parsing de respuesta del LLM, fallback.
3. Integración con LLM mockeado (success + fallback paths).
4. Endpoint POST /api/v1/ai/growth/analyze: integración E2E.

Las pruebas del LLM mockean `LLMClient.generate` para no depender
del proveedor real. El comportamiento end-to-end real se prueba en
staging con la API key configurada.
"""
from __future__ import annotations

import json
import pytest
from unittest.mock import AsyncMock

from app.schemas.ai import (
    BusinessMemorySnapshot,
    GrowthAnalysisRequest,
    GrowthAnalysisResponse,
    GrowthInsight,
    GrowthInsightCategory,
    GrowthInsightPriority,
    GrowthInsightType,
)
from app.services import llm_client as llm_client_module
from app.services.growth_coach import (
    GrowthCoach,
    TenantContext,
    _GROWTH_SYSTEM_PROMPT,
    _PRIORITY_WEIGHT,
)
from app.services.llm_client import LLMResponse


# ══════════════════════════════════════════════════════════════
# 1) Schemas
# ══════════════════════════════════════════════════════════════
class TestSchemasRequest:
    def test_minimal_request_defaults(self):
        """El request mínimo (vacío) debe usar defaults sensatos."""
        req = GrowthAnalysisRequest()
        assert req.focus == "overview"
        assert req.lookback_days == 30
        assert req.language == "es"
        assert req.max_insights == 8

    def test_full_request_valid(self):
        """Todos los campos explícitos deben validarse."""
        req = GrowthAnalysisRequest(
            focus="sales",
            lookback_days=60,
            language="en",
            max_insights=12,
        )
        assert req.focus == "sales"
        assert req.lookback_days == 60
        assert req.language == "en"
        assert req.max_insights == 12

    @pytest.mark.parametrize("focus", [
        "overview", "sales", "inventory",
        "customers", "promotions", "bookings", "mixed",
    ])
    def test_request_accepts_all_focuses(self, focus):
        """Todos los focuses del Literal deben ser válidos."""
        req = GrowthAnalysisRequest(focus=focus)
        assert req.focus == focus

    def test_request_rejects_unknown_focus(self):
        with pytest.raises(ValueError):
            GrowthAnalysisRequest(focus="no_existe")

    def test_request_rejects_short_lookback(self):
        """lookback_days < 7 debe fallar."""
        with pytest.raises(ValueError):
            GrowthAnalysisRequest(lookback_days=3)

    def test_request_rejects_long_lookback(self):
        """lookback_days > 180 debe fallar."""
        with pytest.raises(ValueError):
            GrowthAnalysisRequest(lookback_days=365)

    def test_request_rejects_few_insights(self):
        """max_insights < 3 debe fallar."""
        with pytest.raises(ValueError):
            GrowthAnalysisRequest(max_insights=1)

    def test_request_rejects_many_insights(self):
        """max_insights > 20 debe fallar."""
        with pytest.raises(ValueError):
            GrowthAnalysisRequest(max_insights=50)

    def test_request_rejects_long_language(self):
        """language > 8 chars debe fallar."""
        with pytest.raises(ValueError):
            GrowthAnalysisRequest(language="es-MX-variant")


class TestSchemasInsight:
    def test_insight_minimal_valid(self):
        ins = GrowthInsight(
            type="opportunity",
            priority="high",
            category="sales",
            title="Subir ticket promedio",
            description="Tus clientes están gastando menos que el mes pasado.",
        )
        assert ins.type == "opportunity"
        assert ins.priority == "high"
        assert ins.evidence == []  # default
        assert ins.recommended_actions == []  # default
        assert ins.linked_module is None
        assert ins.metric_impact_estimate is None
        # id se genera automáticamente
        assert ins.id is not None

    def test_insight_full_valid(self):
        ins = GrowthInsight(
            type="warning",
            priority="urgent",
            category="inventory",
            title="3 productos sin stock",
            description="Tres productos top están sin stock hace 5 días.",
            evidence=["Café latte: stock=0", "Brownie: stock=0"],
            recommended_actions=["Reponer stock", "Pausar promos"],
            linked_module="products",
            metric_impact_estimate="Recuperar ~$2M/mes",
        )
        assert ins.linked_module == "products"
        assert len(ins.evidence) == 2
        assert len(ins.recommended_actions) == 2

    def test_insight_rejects_short_title(self):
        with pytest.raises(ValueError):
            GrowthInsight(
                type="insight", priority="low", category="sales",
                title="abc",  # < 5 chars
                description="Descripción lo suficientemente larga.",
            )

    def test_insight_rejects_long_title(self):
        with pytest.raises(ValueError):
            GrowthInsight(
                type="insight", priority="low", category="sales",
                title="x" * 121,  # > 120 chars
                description="Descripción lo suficientemente larga.",
            )

    def test_insight_rejects_short_description(self):
        with pytest.raises(ValueError):
            GrowthInsight(
                type="insight", priority="low", category="sales",
                title="Título válido",
                description="corta",  # < 10 chars
            )

    def test_insight_rejects_invalid_type(self):
        with pytest.raises(ValueError):
            GrowthInsight(
                type="no_existe", priority="low", category="sales",
                title="Título válido",
                description="Descripción lo suficientemente larga.",
            )

    def test_insight_rejects_invalid_priority(self):
        with pytest.raises(ValueError):
            GrowthInsight(
                type="insight", priority="no_existe", category="sales",
                title="Título válido",
                description="Descripción lo suficientemente larga.",
            )

    def test_insight_rejects_invalid_category(self):
        with pytest.raises(ValueError):
            GrowthInsight(
                type="insight", priority="low", category="no_existe",
                title="Título válido",
                description="Descripción lo suficientemente larga.",
            )


class TestSchemasBusinessMemory:
    def test_snapshot_minimal(self):
        snap = BusinessMemorySnapshot(
            tenant_id="t1",
            tenant_name="Café X",
            tenant_slug="cafe-x",
            lookback_days=30,
        )
        assert snap.tenant_id == "t1"
        assert snap.sales == {}
        assert snap.inventory == {}
        assert snap.customers == {}
        assert snap.promotions == {}
        assert snap.bookings == {}
        assert snap.data_completeness == {}
        # generated_at es auto
        assert snap.generated_at is not None

    def test_snapshot_full(self):
        snap = BusinessMemorySnapshot(
            tenant_id="t1",
            tenant_name="Café X",
            tenant_slug="cafe-x",
            lookback_days=30,
            sales={"total_orders": 12, "total_revenue_cents": 50000},
            inventory={"out_of_stock_count": 2, "out_of_stock": [{"name": "X"}]},
            customers={"total_customers": 30, "inactive_count": 5},
            promotions={"total": 3, "active": 1},
            bookings={"total": 10, "cancellation_rate": 0.1},
            data_completeness={
                "sales": True, "inventory": True,
                "customers": True, "promotions": True, "bookings": True,
            },
        )
        assert snap.sales["total_orders"] == 12
        assert snap.inventory["out_of_stock_count"] == 2
        assert snap.data_completeness["sales"] is True


class TestSchemasResponse:
    def test_response_minimal(self):
        snap = BusinessMemorySnapshot(
            tenant_id="t1", lookback_days=30,
        )
        resp = GrowthAnalysisResponse(
            focus="overview", lookback_days=30, language="es",
            summary="Resumen ejecutivo del estado del negocio.",
            business_memory=snap,
        )
        assert resp.focus == "overview"
        assert resp.fallback is False  # default
        assert resp.fallback_reason is None
        assert resp.model is None
        assert resp.tokens_in is None
        assert resp.tokens_out is None
        assert resp.latency_ms == 0
        assert resp.id is not None
        assert resp.insights == []  # default
        assert resp.generated_at is not None

    def test_response_with_insights(self):
        snap = BusinessMemorySnapshot(
            tenant_id="t1", lookback_days=30,
        )
        ins = GrowthInsight(
            type="warning", priority="high", category="inventory",
            title="Stock bajo detectado",
            description="Tres productos están con stock crítico.",
        )
        resp = GrowthAnalysisResponse(
            focus="inventory", lookback_days=30, language="es",
            summary="Hay problemas de inventario que resolver.",
            insights=[ins],
            business_memory=snap,
            fallback=False,
            model="claude-3-5-sonnet",
            tokens_in=500, tokens_out=400, latency_ms=1200,
        )
        assert len(resp.insights) == 1
        assert resp.tokens_in == 500
        assert resp.tokens_out == 400
        assert resp.latency_ms == 1200


# ══════════════════════════════════════════════════════════════
# 2) Servicio: parsing de la respuesta del LLM
# ══════════════════════════════════════════════════════════════
class TestParseLlmResponse:
    def setup_method(self):
        self.coach = GrowthCoach()
        self.coach.llm = MagicMock() if False else None  # no se usa en parseo

    def test_clean_json(self):
        raw = json.dumps({
            "summary": "Resumen de prueba con suficiente longitud.",
            "insights": [
                {
                    "type": "opportunity",
                    "priority": "high",
                    "category": "sales",
                    "title": "Subir ticket promedio",
                    "description": "Tus clientes están gastando menos.",
                    "evidence": ["Ticket = $15K"],
                    "recommended_actions": ["Combo 2x1"],
                    "linked_module": "promotions",
                    "metric_impact_estimate": "+10%",
                },
            ],
        })
        summary, insights = self.coach._parse_llm_response(
            raw, max_insights=8, focus="overview",
        )
        assert "Resumen de prueba" in summary
        assert len(insights) == 1
        assert insights[0].type == "opportunity"
        assert insights[0].priority == "high"
        assert insights[0].category == "sales"
        assert insights[0].linked_module == "promotions"

    def test_json_in_fences(self):
        """El parser debe tolerar ```json ... ```."""
        raw = (
            "```json\n"
            + json.dumps({
                "summary": "Resumen válido lo suficientemente largo.",
                "insights": [
                    {
                        "type": "warning", "priority": "urgent",
                        "category": "inventory", "title": "Sin stock",
                        "description": "Tres productos sin stock hace días.",
                    },
                ],
            })
            + "\n```"
        )
        summary, insights = self.coach._parse_llm_response(
            raw, max_insights=8, focus="overview",
        )
        assert "Resumen válido" in summary
        assert len(insights) == 1
        assert insights[0].priority == "urgent"

    def test_json_with_bare_fences(self):
        """El parser debe tolerar ``` sin 'json'."""
        raw = (
            "```\n"
            + json.dumps({
                "summary": "Resumen válido lo suficientemente largo.",
                "insights": [],
            })
            + "\n```"
        )
        summary, insights = self.coach._parse_llm_response(
            raw, max_insights=8, focus="overview",
        )
        assert "Resumen válido" in summary
        assert insights == []

    def test_invalid_json_raises_llm_fallback(self):
        """JSON inválido → lanza LLMFallback. El caller activa el fallback."""
        from app.services.llm_client import LLMFallback
        raw = "esto no es json"
        with pytest.raises(LLMFallback):
            self.coach._parse_llm_response(
                raw, max_insights=8, focus="overview",
            )

    def test_missing_insights_field(self):
        """Si falta 'insights' en el JSON, devuelve summary válido + []."""
        raw = json.dumps({"summary": "Resumen lo suficientemente largo."})
        summary, insights = self.coach._parse_llm_response(
            raw, max_insights=8, focus="overview",
        )
        assert "Resumen lo suficientemente largo" in summary
        assert insights == []

    def test_invalid_insight_type_is_fallback_to_insight(self):
        """Insights con type inválido se coaccionan a 'insight' (no se descartan)."""
        raw = json.dumps({
            "summary": "Resumen válido lo suficientemente largo.",
            "insights": [
                {
                    "type": "no_existe", "priority": "high",
                    "category": "sales", "title": "Título válido",
                    "description": "Descripción lo suficientemente larga.",
                },
                {
                    "type": "warning", "priority": "high",
                    "category": "sales", "title": "Título válido 2",
                    "description": "Descripción lo suficientemente larga 2.",
                },
            ],
        })
        summary, insights = self.coach._parse_llm_response(
            raw, max_insights=8, focus="overview",
        )
        # Ambos pasan, pero el primero se coacciona a "insight"
        assert len(insights) == 2
        assert insights[0].type == "insight"
        assert insights[1].type == "warning"

    def test_truncates_to_max_insights(self):
        """Si el LLM devuelve más insights que max_insights, se trunca."""
        insights_list = [
            {
                "type": "insight", "priority": "low",
                "category": "sales", "title": f"Insight número {i}",
                "description": "Descripción lo suficientemente larga.",
            }
            for i in range(15)
        ]
        raw = json.dumps({
            "summary": "Resumen válido lo suficientemente largo.",
            "insights": insights_list,
        })
        summary, insights = self.coach._parse_llm_response(
            raw, max_insights=5, focus="overview",
        )
        assert len(insights) == 5


# ══════════════════════════════════════════════════════════════
# 3) Servicio: TenantContext
# ══════════════════════════════════════════════════════════════
class TestTenantContext:
    def test_has_slug_true(self):
        ctx = TenantContext(tenant_id="t1", slug="cafe", name="C")
        assert ctx.has_slug is True

    def test_has_slug_false(self):
        ctx = TenantContext(tenant_id="t1", slug=None, name="C")
        assert ctx.has_slug is False

    def test_has_slug_empty_string(self):
        ctx = TenantContext(tenant_id="t1", slug="", name="C")
        assert ctx.has_slug is False


# ══════════════════════════════════════════════════════════════
# 4) Servicio: fallback determinístico
# ══════════════════════════════════════════════════════════════
def _empty_memory(lookback: int = 30) -> BusinessMemorySnapshot:
    snap = BusinessMemorySnapshot(
        tenant_id="t1", tenant_name="Test", tenant_slug="t1",
        lookback_days=lookback,
    )
    return snap


def _memory_with_inventory(counts: dict) -> BusinessMemorySnapshot:
    """Crea un memory con sección inventory ya populada."""
    snap = _empty_memory()
    snap.inventory = counts
    snap.data_completeness = {"inventory": bool(counts)}
    return snap


def _memory_with_customers(counts: dict) -> BusinessMemorySnapshot:
    snap = _empty_memory()
    snap.customers = counts
    snap.data_completeness = {"customers": bool(counts)}
    return snap


def _memory_with_promotions(counts: dict) -> BusinessMemorySnapshot:
    snap = _empty_memory()
    snap.promotions = counts
    snap.data_completeness = {"promotions": bool(counts)}
    return snap


def _memory_with_bookings(counts: dict) -> BusinessMemorySnapshot:
    snap = _empty_memory()
    snap.bookings = counts
    snap.data_completeness = {"bookings": bool(counts)}
    return snap


def _req(focus: str = "overview", lookback: int = 30) -> GrowthAnalysisRequest:
    return GrowthAnalysisRequest(focus=focus, lookback_days=lookback)


class TestFallbackAnalyze:
    def setup_method(self):
        self.coach = GrowthCoach()

    def test_empty_data_returns_onboarding_insight(self):
        """Sin datos en ninguna sección → 1 insight informativo."""
        snap = _empty_memory()
        summary, insights = self.coach._fallback_analyze(
            snap, _req(), reason="no_llm",
        )
        assert isinstance(summary, str) and len(summary) >= 10
        assert len(insights) >= 1
        # Es un insight informativo sobre cargar productos
        onb = next(
            (i for i in insights
             if "cargá" in i.description.lower() or "carga" in i.description.lower()),
            None,
        )
        assert onb is not None, f"insights={insights}"

    def test_out_of_stock_urgent_when_ge_3(self):
        """3+ productos sin stock → URGENT."""
        snap = _memory_with_inventory({
            "out_of_stock_count": 5,
            "out_of_stock": [{"name": "Café"}, {"name": "Tostado"}],
        })
        _, insights = self.coach._fallback_analyze(
            snap, _req(focus="inventory"), reason="no_llm",
        )
        # El primer match por priority
        urgent = next((i for i in insights if "sin stock" in i.title.lower()), None)
        assert urgent is not None
        assert urgent.priority == "urgent"
        assert urgent.category == "inventory"
        assert urgent.linked_module == "products"

    def test_out_of_stock_high_when_lt_3(self):
        """1-2 productos sin stock → HIGH (no urgent)."""
        snap = _memory_with_inventory({"out_of_stock_count": 2, "out_of_stock": []})
        _, insights = self.coach._fallback_analyze(
            snap, _req(focus="inventory"), reason="no_llm",
        )
        urgent = next((i for i in insights if "sin stock" in i.title.lower()), None)
        assert urgent is not None
        assert urgent.priority == "high"

    def test_low_stock_medium(self):
        """Stock bajo → MEDIUM."""
        snap = _memory_with_inventory({
            "low_stock_count": 4,
            "low_stock": [{"name": "Leche"}, {"name": "Azúcar"}],
        })
        _, insights = self.coach._fallback_analyze(
            snap, _req(focus="inventory"), reason="no_llm",
        )
        low = next((i for i in insights if "stock bajo" in i.title.lower()), None)
        assert low is not None
        assert low.priority == "medium"

    def test_dead_stock_recommendation(self):
        """3+ dead_stock → RECOMMENDATION con link a promotions."""
        snap = _memory_with_inventory({"dead_stock_count": 4})
        _, insights = self.coach._fallback_analyze(
            snap, _req(), reason="no_llm",
        )
        dead = next(
            (i for i in insights if "60+ días" in i.title or "sin ventas" in i.title.lower()),
            None,
        )
        assert dead is not None
        assert dead.priority == "medium"
        assert dead.category == "inventory"
        assert dead.linked_module == "promotions"

    def test_inactive_customers_high(self):
        """3+ inactivos → HIGH con link a marketing_studio."""
        snap = _memory_with_customers({"inactive_count": 8})
        _, insights = self.coach._fallback_analyze(
            snap, _req(focus="customers"), reason="no_llm",
        )
        inact = next(
            (i for i in insights if "inactivo" in i.title.lower()),
            None,
        )
        assert inact is not None
        assert inact.priority == "high"
        assert inact.category == "customers"
        assert inact.linked_module == "marketing_studio"

    def test_vip_customers_low(self):
        """3+ VIPs → LOW con insight de fidelización."""
        snap = _memory_with_customers({"vip_count": 4})
        _, insights = self.coach._fallback_analyze(
            snap, _req(focus="customers"), reason="no_llm",
        )
        vip = next(
            (i for i in insights if "vip" in i.title.lower()),
            None,
        )
        assert vip is not None
        assert vip.priority == "low"
        assert vip.category == "customers"

    def test_no_promotions_ever_high(self):
        """0 promociones creadas nunca → HIGH invitando a crear la primera."""
        snap = _memory_with_promotions({"total": 0, "active": 0})
        _, insights = self.coach._fallback_analyze(
            snap, _req(focus="promotions"), reason="no_llm",
        )
        no_promo = next(
            (i for i in insights
             if "no tenés promociones" in i.title.lower()
             or "no tenés promos" in i.title.lower()),
            None,
        )
        assert no_promo is not None
        assert no_promo.priority == "high"
        assert no_promo.category == "promotions"
        assert no_promo.linked_module == "promotions"

    def test_promotions_exist_but_none_active_medium(self):
        """Hay promos pero ninguna activa → MEDIUM."""
        snap = _memory_with_promotions({"total": 3, "active": 0})
        _, insights = self.coach._fallback_analyze(
            snap, _req(focus="promotions"), reason="no_llm",
        )
        inact = next(
            (i for i in insights if "ninguna" in i.description.lower()
             or "activar" in i.title.lower()
             or "vencid" in i.title.lower()),
            None,
        )
        assert inact is not None
        assert inact.priority == "medium"
        assert inact.category == "promotions"

    def test_high_cancellation_rate_high(self):
        """Tasa de cancelación > 20% con >=5 reservas → HIGH."""
        snap = _memory_with_bookings({
            "total": 20, "canceled": 8, "cancellation_rate": 0.4,
        })
        _, insights = self.coach._fallback_analyze(
            snap, _req(focus="bookings"), reason="no_llm",
        )
        canc = next(
            (i for i in insights if "cancelaci" in i.title.lower()),
            None,
        )
        assert canc is not None
        assert canc.priority == "high"
        assert canc.category == "bookings"

    def test_fallback_summary_mentions_reason(self):
        """El summary del fallback debe ser informativo (≥10 chars)."""
        snap = _empty_memory()
        summary, _ = self.coach._fallback_analyze(
            snap, _req(), reason="circuit_open",
        )
        assert len(summary) >= 10

    def test_fallback_is_sorted_by_priority_desc(self):
        """El _sort_by_priority debe poner urgent primero."""
        snap = _memory_with_inventory({
            "out_of_stock_count": 5,
            "low_stock_count": 3,
        })
        snap.customers = {"inactive_count": 8}
        snap.data_completeness = {
            "inventory": True, "customers": True,
            "promotions": False, "bookings": False, "sales": False,
        }
        _, insights = self.coach._fallback_analyze(
            snap, _req(), reason="no_llm",
        )
        sorted_insights = self.coach._sort_by_priority(insights)
        # El primero no debe ser low
        if sorted_insights:
            first_w = _PRIORITY_WEIGHT.get(sorted_insights[0].priority, 0)
            last_w = _PRIORITY_WEIGHT.get(sorted_insights[-1].priority, 0)
            assert first_w >= last_w


# ══════════════════════════════════════════════════════════════
# 5) Servicio: integración con LLM (success + fallback)
# ══════════════════════════════════════════════════════════════
class TestAnalyzeWithLlm:
    def setup_method(self):
        # Resetear circuit por si quedó abierto de otro test
        llm_client_module._circuit = llm_client_module.CircuitBreaker(
            fail_threshold=5, reset_seconds=60,
        )

    @pytest.mark.asyncio
    async def test_llm_success_path(self, db_session, monkeypatch):
        """Con LLM mockeado, devuelve fallback=False y el summary del LLM."""
        async def patched_generate(self, messages, **kwargs):
            return LLMResponse(
                content=json.dumps({
                    "summary": "Tu negocio creció 12% este mes vs el anterior.",
                    "insights": [
                        {
                            "type": "opportunity", "priority": "high",
                            "category": "sales", "title": "Crecimiento en ventas",
                            "description": "Las ventas subieron 12% en los últimos 30 días.",
                            "evidence": ["Ingresos: $1.2M", "Hace 30d: $1.07M"],
                            "recommended_actions": ["Mantener el ritmo"],
                            "linked_module": "products",
                        },
                    ],
                }),
                tokens_in=200, tokens_out=180, finish_reason="stop",
            )

        monkeypatch.setattr(
            llm_client_module.LLMClient, "generate", patched_generate,
        )

        ctx = TenantContext(tenant_id="t1", slug="t1", name="Test")
        req = GrowthAnalysisRequest(focus="overview", lookback_days=30)
        coach = GrowthCoach()
        response = await coach.analyze(req, ctx, db_session)
        assert response.fallback is False
        assert "12%" in response.summary
        assert len(response.insights) == 1
        assert response.model is not None
        assert response.tokens_in == 200
        assert response.tokens_out == 180
        assert response.latency_ms >= 0

    @pytest.mark.asyncio
    async def test_llm_fallback_when_circuit_open(
        self, db_session, monkeypatch,
    ):
        """Si el circuit está abierto, devuelve fallback=True con un reason."""
        # Forzar circuit abierto
        llm_client_module._circuit = llm_client_module.CircuitBreaker(
            fail_threshold=1, reset_seconds=9999,
        )
        llm_client_module._circuit.record_failure()

        ctx = TenantContext(tenant_id="t1", slug="t1", name="Test")
        req = GrowthAnalysisRequest(focus="overview", lookback_days=30)
        coach = GrowthCoach()
        response = await coach.analyze(req, ctx, db_session)
        assert response.fallback is True
        assert response.fallback_reason is not None
        assert response.model is None
        # El fallback SIEMPRE devuelve algo útil
        assert response.summary
        assert isinstance(response.summary, str) and len(response.summary) >= 10

    @pytest.mark.asyncio
    async def test_llm_invalid_json_triggers_fallback(
        self, db_session, monkeypatch,
    ):
        """Si el LLM devuelve JSON inválido, se activa el fallback."""
        async def patched_generate(self, messages, **kwargs):
            return LLMResponse(
                content="respuesta que no es json en absoluto",
                tokens_in=10, tokens_out=5, finish_reason="stop",
            )
        monkeypatch.setattr(
            llm_client_module.LLMClient, "generate", patched_generate,
        )

        ctx = TenantContext(tenant_id="t1", slug="t1", name="Test")
        req = GrowthAnalysisRequest(focus="overview", lookback_days=30)
        coach = GrowthCoach()
        response = await coach.analyze(req, ctx, db_session)
        assert response.fallback is True
        # El fallback produce insights determinísticos
        assert len(response.insights) >= 1

    @pytest.mark.asyncio
    async def test_llm_throws_unexpected_uses_fallback(
        self, db_session, monkeypatch,
    ):
        """Si el LLM lanza una excepción inesperada, se activa el fallback."""
        async def patched_generate(self, messages, **kwargs):
            raise RuntimeError("upstream timeout")

        monkeypatch.setattr(
            llm_client_module.LLMClient, "generate", patched_generate,
        )

        ctx = TenantContext(tenant_id="t1", slug="t1", name="Test")
        req = GrowthAnalysisRequest(focus="overview", lookback_days=30)
        coach = GrowthCoach()
        response = await coach.analyze(req, ctx, db_session)
        assert response.fallback is True
        assert "unexpected" in (response.fallback_reason or "").lower()


# ══════════════════════════════════════════════════════════════
# 6) System prompt: invariantes
# ══════════════════════════════════════════════════════════════
class TestSystemPrompt:
    def test_prompt_mentions_no_invention(self):
        assert "NUNCA" in _GROWTH_SYSTEM_PROMPT or "NO inventes" in _GROWTH_SYSTEM_PROMPT

    def test_prompt_mentions_json_format(self):
        assert "JSON" in _GROWTH_SYSTEM_PROMPT

    def test_prompt_mentions_valid_modules(self):
        assert "WowHub" in _GROWTH_SYSTEM_PROMPT
        # Debe mencionar módulos reales
        for mod in ["productos", "promociones", "clientes", "reservas"]:
            assert mod in _GROWTH_SYSTEM_PROMPT, f"missing {mod}"


# ══════════════════════════════════════════════════════════════
# 7) Test de integración: endpoint E2E
# ══════════════════════════════════════════════════════════════
@pytest.fixture
def auth_user_and_tenant(db_session):
    """Crea un user + tenant + membership para tests E2E."""
    from app.models.user import User, UserRole
    from app.models.tenant import Tenant, TenantMembership
    import uuid as _uuid

    user = User(
        id=_uuid.uuid4(),
        email=f"test-{_uuid.uuid4().hex[:8]}@example.com",
        password_hash="fake",
        full_name="Test User",
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()

    tenant = Tenant(
        id=_uuid.uuid4(),
        slug=f"test-{_uuid.uuid4().hex[:8]}",
        legal_name="Café Test SpA",
        display_name="Café Test",
        industry="other",
    )
    db_session.add(tenant)
    db_session.flush()

    membership = TenantMembership(
        id=_uuid.uuid4(),
        user_id=str(user.id),
        tenant_id=str(tenant.id),
        role=UserRole.OWNER,
        is_owner=True,
        is_active=True,
    )
    db_session.add(membership)
    db_session.commit()

    return user, tenant


@pytest.fixture
def auth_headers(client, auth_user_and_tenant):
    """Genera headers con Authorization Bearer y X-Tenant-Id."""
    from app.security import create_access_token
    user, tenant = auth_user_and_tenant
    token = create_access_token(
        subject=str(user.id),
        tenant_id=str(tenant.id),
        role="owner",
    )
    return {
        "Authorization": f"Bearer {token}",
        "X-Tenant-Id": str(tenant.id),
        "Content-Type": "application/json",
    }


class TestEndpointE2E:
    def setup_method(self):
        # Resetear circuit antes de cada test
        llm_client_module._circuit = llm_client_module.CircuitBreaker(
            fail_threshold=5, reset_seconds=60,
        )

    @pytest.mark.asyncio
    async def test_endpoint_401_without_auth(self, client):
        r = client.post(
            "/api/v1/ai/growth/analyze",
            json={"focus": "overview"},
        )
        assert r.status_code == 401

    @pytest.mark.asyncio
    async def test_endpoint_returns_fallback_when_no_llm(
        self, client, auth_headers, monkeypatch,
    ):
        """E2E: el endpoint responde con fallback=True cuando el LLM
        no está configurado."""
        from app.config import settings
        monkeypatch.setattr(settings, "llm_api_key", "")
        llm_client_module._circuit = llm_client_module.CircuitBreaker(
            fail_threshold=5, reset_seconds=60,
        )

        r = client.post(
            "/api/v1/ai/growth/analyze",
            json={"focus": "overview", "lookback_days": 30},
            headers=auth_headers,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["fallback"] is True
        assert data["focus"] == "overview"
        assert data["lookback_days"] == 30
        # El summary es string no-vacío
        assert isinstance(data["summary"], str) and len(data["summary"]) >= 10
        # El business_memory se devuelve completo
        assert "business_memory" in data
        assert data["business_memory"]["lookback_days"] == 30

    @pytest.mark.asyncio
    async def test_endpoint_with_llm_mock(
        self, client, auth_headers, monkeypatch,
    ):
        """E2E: con el LLM mockeado, devuelve fallback=False y model."""
        async def patched_generate(self, messages, **kwargs):
            return LLMResponse(
                content=json.dumps({
                    "summary": "Análisis simulado del LLM de testing.",
                    "insights": [
                        {
                            "type": "recommendation", "priority": "high",
                            "category": "inventory",
                            "title": "Reposición de stock recomendada",
                            "description": "Tres productos están por debajo del stock mínimo.",
                        },
                    ],
                }),
                tokens_in=100, tokens_out=80, finish_reason="stop",
            )

        monkeypatch.setattr(
            llm_client_module.LLMClient, "generate", patched_generate,
        )

        r = client.post(
            "/api/v1/ai/growth/analyze",
            json={"focus": "inventory", "max_insights": 5},
            headers=auth_headers,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["fallback"] is False
        assert "simulado" in data["summary"]
        assert len(data["insights"]) >= 1
        assert data["tokens_in"] == 100
        assert data["model"] is not None

    @pytest.mark.asyncio
    async def test_endpoint_rejects_invalid_focus(
        self, client, auth_headers,
    ):
        r = client.post(
            "/api/v1/ai/growth/analyze",
            json={"focus": "no_existe"},
            headers=auth_headers,
        )
        assert r.status_code == 422

    @pytest.mark.asyncio
    async def test_endpoint_rejects_short_lookback(
        self, client, auth_headers,
    ):
        r = client.post(
            "/api/v1/ai/growth/analyze",
            json={"lookback_days": 2},
            headers=auth_headers,
        )
        assert r.status_code == 422

    @pytest.mark.asyncio
    async def test_endpoint_rejects_many_insights(
        self, client, auth_headers,
    ):
        r = client.post(
            "/api/v1/ai/growth/analyze",
            json={"max_insights": 100},
            headers=auth_headers,
        )
        assert r.status_code == 422

    @pytest.mark.asyncio
    async def test_endpoint_resolves_tenant_in_business_memory(
        self, client, auth_headers, monkeypatch,
    ):
        """E2E: el business_memory incluye el tenant_id resuelto."""
        from app.config import settings
        monkeypatch.setattr(settings, "llm_api_key", "")
        llm_client_module._circuit = llm_client_module.CircuitBreaker(
            fail_threshold=5, reset_seconds=60,
        )

        user, tenant = None, None  # ya inyectados en auth_headers
        r = client.post(
            "/api/v1/ai/growth/analyze",
            json={},
            headers=auth_headers,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        # tenant_id debe ser el del membership
        assert data["business_memory"]["tenant_id"]
        assert data["business_memory"]["lookback_days"] == 30

    @pytest.mark.asyncio
    async def test_endpoint_validates_response_shape(
        self, client, auth_headers, monkeypatch,
    ):
        """E2E: la response tiene el shape exacto del schema."""
        from app.config import settings
        monkeypatch.setattr(settings, "llm_api_key", "")
        llm_client_module._circuit = llm_client_module.CircuitBreaker(
            fail_threshold=5, reset_seconds=60,
        )

        r = client.post(
            "/api/v1/ai/growth/analyze",
            json={"focus": "sales", "lookback_days": 60, "max_insights": 5},
            headers=auth_headers,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        # Top-level keys
        for k in [
            "id", "focus", "lookback_days", "language", "summary",
            "insights", "business_memory", "generated_at",
            "fallback", "tokens_in", "tokens_out", "latency_ms",
        ]:
            assert k in data, f"missing key: {k}"
        # Insight shape (si hay insights)
        for ins in data["insights"]:
            for k in [
                "id", "type", "priority", "category",
                "title", "description",
            ]:
                assert k in ins, f"missing insight key: {k}"
