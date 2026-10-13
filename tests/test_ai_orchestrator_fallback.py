"""Tests del fallback del orquestador (LLM caído → respuesta pre-canned)."""
import pytest
from uuid import uuid4

from app.config import settings
from app.services.ai_orchestrator import AIOrchestrator, _is_repetitive_response
from app.services.llm_client import LLMError, LLMFallback, get_circuit
from app.services.ai_agents import (
    get_agent, heuristic_route, list_sub_agents,
)


# ── Heuristic router ────────────────────────────────
class TestHeuristicRouter:
    def test_marketing_keywords(self):
        assert heuristic_route("quiero crear una promo del 20%") == "marketing"
        # "producto" ahora también es keyword de marketplace, así que usamos
        # otra palabra clave de marketing para evitar ambigüedad.
        assert heuristic_route("dame un copy para mi anuncio") == "marketing"

    def test_growth_keywords(self):
        assert heuristic_route("¿cómo van mis ventas?") == "growth"
        assert heuristic_route("mi ticket promedio está bajo") == "growth"

    def test_automation_keywords(self):
        assert heuristic_route("quiero automatizar el email de cumpleaños") == "automation"
        assert heuristic_route("reactivar clientes inactivos") == "automation"

    def test_marketplace_keywords(self):
        assert heuristic_route("cómo mejoro el precio de mi producto") == "marketplace"
        assert heuristic_route("mi stock está bajo") == "marketplace"

    def test_fallback_marketing(self):
        # Sin keywords → marketing por default
        assert heuristic_route("hola") == "marketing"


# ── Sub-agent fallbacks ─────────────────────────────
class TestSubAgentFallbacks:
    def test_all_sub_agents_have_fallback(self):
        for a in list_sub_agents():
            agent = get_agent(a["name"])
            assert agent.fallback, f"{a['name']} sin fallback"
            assert agent.welcome, f"{a['name']} sin welcome"
            assert agent.system_prompt, f"{a['name']} sin system_prompt"

    def test_router_does_not_have_fallback(self):
        # El router no responde al usuario; solo clasifica
        from app.services.ai_agents import ROUTER
        # Su fallback vacío es OK
        assert ROUTER.fallback == ""


# ── Orquestador con LLM caído ────────────────────────
@pytest.mark.asyncio
async def test_orchestrator_uses_fallback_when_llm_down(monkeypatch):
    """Si el LLM está caído (circuit abierto), el orquestador debe
    usar el fallback del sub-agente y persistir el log con status=fallback."""

    # Forzar circuit abierto
    get_circuit().force_open()

    # Crear una conversación fake en memoria
    from app.database import SessionLocal
    from app.models.user import User, UserRole
    from app.models.tenant import Tenant, TenantMembership, TenantPlan
    from app.models.ai import AIConversation, ConversationStatus, AgentKind

    db = SessionLocal()
    try:
        # Setup: usuario + tenant
        u = User(
            id=uuid4(),
            email=f"test-{uuid4().hex[:8]}@example.com",
            password_hash="x",
            full_name="Tester",
            is_active=True,
            default_role=UserRole.OWNER,
        )
        t = Tenant(
            id=uuid4(),
            slug=f"t-{uuid4().hex[:8]}",
            legal_name="Test Tenant SpA",
            display_name="Test Tenant",
            plan=TenantPlan.FREE,
            is_active=True,
        )
        m = TenantMembership(
            id=uuid4(), user_id=str(u.id), tenant_id=str(t.id),
            role="owner", is_owner=True, is_active=True,
        )
        db.add_all([u, t, m])
        db.commit()

        orch = AIOrchestrator(
            db,
            user_id=str(u.id),
            tenant_id=str(t.id),
            access_token="fake-token",
        )
        result = await orch.chat(message="hola, ¿cómo van las ventas?")

        # El orquestador debe haber devuelto algo
        assert result["conversation_id"]
        assert result["message_id"]
        assert result["content"]
        # Como el circuit está abierto, debe haber marcado fallback=True
        assert result["fallback"] is True
        # El agente debe ser uno válido (no router)
        assert result["agent"] in ("marketing", "growth", "automation", "marketplace")
    finally:
        db.close()
        get_circuit().force_close()


@pytest.mark.asyncio
async def test_orchestrator_fallback_per_agent(monkeypatch):
    """Cada sub-agente debe devolver su propio fallback (no genérico)."""
    from app.database import SessionLocal
    from app.models.user import User, UserRole
    from app.models.tenant import Tenant, TenantMembership, TenantPlan
    from app.models.ai import AgentKind

    get_circuit().force_open()

    db = SessionLocal()
    try:
        u = User(
            id=uuid4(), email=f"x-{uuid4().hex[:8]}@e.com",
            password_hash="x", full_name="X", is_active=True, default_role=UserRole.OWNER,
        )
        t = Tenant(
            id=uuid4(), slug=f"t-{uuid4().hex[:8]}",
            legal_name="T SpA", display_name="T",
            plan=TenantPlan.FREE, is_active=True,
        )
        m = TenantMembership(
            id=uuid4(), user_id=str(u.id), tenant_id=str(t.id),
            role="owner", is_owner=True, is_active=True,
        )
        db.add_all([u, t, m]); db.commit()

        orch = AIOrchestrator(db, user_id=str(u.id), tenant_id=str(t.id), access_token="x")

        for force in [AgentKind.MARKETING, AgentKind.GROWTH, AgentKind.AUTOMATION, AgentKind.MARKETPLACE]:
            r = await orch.chat(message="hola", force_agent=force)
            expected = get_agent(force.value).fallback
            assert r["content"] == expected, f"Fallback incorrecto para {force.value}"
            assert r["fallback"] is True
    finally:
        db.close()
        get_circuit().force_close()


# ── v1.9.1-r8: Anti-repetición (model degradation) ─────────────
# Bug visto en producción (2026-08-22): el LLM (MiniMax-M3) a veces
# devuelve respuestas con la misma frase repetida o con muchos puntos
# como padding. Estos tests cubren el helper `_is_repetitive_response`
# que detecta esos patrones.
class TestRepetitiveResponseDetector:
    def test_detects_repeated_substring(self):
        # Caso del bug real: misma frase dos veces separada por puntos.
        text = "si arma la priemra promociuon .... si arma la priemra promociuon"
        assert _is_repetitive_response(text) is True

    def test_detects_repeated_substring_with_padding(self):
        # Variante con "......" como separador.
        text = "lo mejor es empezar con un combo ...... lo mejor es empezar con un combo"
        assert _is_repetitive_response(text) is True

    def test_detects_repeated_sentence(self):
        # Oración completa repetida.
        text = "Te recomiendo crear una promo hoy. Te recomiendo crear una promo hoy."
        assert _is_repetitive_response(text) is True

    def test_detects_high_dot_ratio(self):
        # 50% de la respuesta son puntos.
        text = "...................................................."
        assert _is_repetitive_response(text) is True

    def test_detects_dot_padding_with_words(self):
        # Mezcla de palabras y muchos puntos.
        text = "hola ............................................ chau"
        assert _is_repetitive_response(text) is True

    def test_detects_word_repetition_loop(self):
        # La misma palabra repetida 4+ veces (modelo en loop).
        text = "promoción promoción promoción promoción promoción hoy"
        assert _is_repetitive_response(text) is True

    def test_does_not_flag_normal_response(self):
        # Respuesta normal: NO debe ser marcada como repetitiva.
        text = (
            "¡Hola! Te ayudo a crear tu primera promoción. "
            "Cuéntame: ¿qué producto quieres promocionar?"
        )
        assert _is_repetitive_response(text) is False

    def test_does_not_flag_long_helpful_response(self):
        # Walkthrough legítimo con varias frases y repetición natural
        # de palabras clave (ej. "promoción" 2 veces).
        text = (
            "Para crear tu primera promoción: 1) Elige un producto "
            "top. 2) Define un descuento. 3) Lanza la promoción. "
            "¿Quieres que te recomiende un producto?"
        )
        assert _is_repetitive_response(text) is False

    def test_does_not_flag_short_response(self):
        # Respuesta muy corta (la cubre el detector 7.8, no este).
        assert _is_repetitive_response("ok") is False
        assert _is_repetitive_response("sí") is False

    def test_does_not_flag_empty(self):
        # Vacío y None NO son repetitivos.
        assert _is_repetitive_response("") is False
        assert _is_repetitive_response(None) is False

    def test_does_not_flag_response_with_some_repetition(self):
        # "promoción" 2 veces es legítimo (palabra clave del dominio).
        # "la" 3 veces es muy común en español. NO debe flagear.
        text = (
            "La promoción de la semana es un 20% de descuento. "
            "Aprovecha la promo para tus clientes frecuentes."
        )
        assert _is_repetitive_response(text) is False
