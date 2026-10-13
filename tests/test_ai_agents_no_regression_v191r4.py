"""Tests de no-regresión v1.9.1-r4 para `app/services/ai_agents.py`.

Este archivo protege contra la re-introducción de URLs/prompts rotos que
existían en v1.9.1-r3 y que fueron corregidos en el hotfix v1.9.1-r4.

Contexto del bug original (v1.9.1-r3):
- Los system_prompts de los 5 sub-agentes y `_GLOBAL_RULES` mencionaban el
  dominio `https://wowhub.app/dashboard/...` para invitar al usuario a
  visitar su panel. Ese dominio NO existe (NXDOMAIN) y rompía la
  experiencia de las fallbacks cuando el LLM no estaba disponible.
- Los prompts también sugerían el formato público viejo `/u/{slug}/...`
  (ej. `/u/cafeluna/reservar`) que NO está desplegado en producción.
- `_GLOBAL_RULES` referenciaba la tool `get_tenant_dashboard_urls` que está
  DEPRECATED en favor de `get_tenant_public_urls`.

El hotfix v1.9.1-r4 alineó todo a la realidad de producción:
- URLs públicas: formato `/api/v1/public/t/{slug}/...` (NO `/u/{slug}/...`)
- Dominio: el del backend de Railway (`wowhub-api-production.up.railway.app`)
- Tool única de URLs: `get_tenant_public_urls`
- Fallbacks: lenguaje neutro sin URLs hardcodeadas

Este test verifica que los 5 sub-agentes (marketing, growth, automation,
marketplace, help) cumplan TODAS las invariantes de v1.9.1-r4.
"""
from __future__ import annotations

import pytest

from app.services.ai_agents import (
    AUTOMATION,
    GROWTH,
    HELP,
    MARKETING,
    MARKETPLACE,
    ROUTER,
    _GLOBAL_RULES,
    get_agent,
)


# Catálogo de los 5 sub-agentes "habladores" (todos menos el ROUTER).
# Cada uno tiene system_prompt + welcome + fallback.
TALKING_AGENTS = [MARKETING, GROWTH, AUTOMATION, MARKETPLACE, HELP]


# ── 1. Anti-NXDOMAIN: cero URLs `wowhub.app/dashboard/*` ───────────
class TestNoNxdomainUrls:
    """v1.9.1-r4 PROHIBE `wowhub.app/dashboard/*` en prompts y fallbacks.

    Esos links no existen (NXDOMAIN). El usuario que los cliqueaba
    quedaba perdido. La solución es lenguaje neutro tipo "abre X desde
    tu panel" en vez de un link falso.
    """

    @pytest.mark.parametrize("agent", TALKING_AGENTS, ids=lambda a: a.name)
    def test_fallback_has_no_wowhub_app_dashboard_url(self, agent):
        forbidden = "wowhub.app/dashboard"
        assert forbidden not in agent.fallback, (
            f"v1.9.1-r4: el fallback de {agent.name} contiene "
            f"'{forbidden}' (NXDOMAIN). Usa lenguaje neutro."
        )
        assert "wowhub.app" not in agent.fallback, (
            f"v1.9.1-r4: el fallback de {agent.name} contiene "
            f"'wowhub.app' (NXDOMAIN)."
        )

    @pytest.mark.parametrize("agent", TALKING_AGENTS, ids=lambda a: a.name)
    def test_system_prompt_has_no_wowhub_app_dashboard_url(self, agent):
        """El prompt tampoco puede sugerir URLs rotas de wowhub.app."""
        # Excepción: la regla (d) de _GLOBAL_RULES que EXPLÍCITAMENTE dice
        # "NUNCA uses wowhub.app (da NXDOMAIN)". Esa mención es legítima
        # (es la regla anti-NXDOMAIN), no es un link sugerido.
        # Verificamos que NO haya un link activo de wowhub.app (con http/https).
        bad_url = "https://wowhub.app/"
        assert bad_url not in agent.system_prompt, (
            f"v1.9.1-r4: el prompt de {agent.name} contiene un link activo "
            f"a '{bad_url}' (NXDOMAIN)."
        )

    def test_global_rules_mentions_nxdomain_to_forbid_it(self):
        """La regla (d) de _GLOBAL_RULES DEBE mencionar wowhub.app como
        PROHIBIDO, para que el LLM no lo sugiera. Esta mención legítima
        no es regresión — es la regla anti-NXDOMAIN."""
        assert "wowhub.app" in _GLOBAL_RULES
        low = _GLOBAL_RULES.lower()
        assert "nxdomain" in low or "no existe" in low or "nunca uses" in low


# ── 2. Anti-formato-viejo: cero paths `/u/{slug}/...` ─────────────
class TestNoLegacyUSlugPaths:
    """v1.9.1-r4 PROHIBE el formato público viejo `/u/{slug}/...`.

    Esos paths NO están desplegados en producción (404). El formato
    vigente es `/api/v1/public/t/{slug}/...`.
    """

    @pytest.mark.parametrize("agent", TALKING_AGENTS, ids=lambda a: a.name)
    def test_fallback_has_no_u_slug_paths(self, agent):
        # Aceptamos menciones de la tool que YA DEVUELVE esos paths
        # (`/api/v1/public/...`), pero no paths desnudos del formato viejo.
        assert "/u/{slug}/" not in agent.fallback
        # Tampoco en formato URL completo
        assert "wowhub.app/u/" not in agent.fallback
        # Ni ejemplos de paths del formato viejo
        for legacy in (
            "/u/{slug}/reservar",
            "/u/{slug}/catalogo",
            "/u/{slug}/landing",
            "/u/{slug}/perfil",
        ):
            assert legacy not in agent.fallback, (
                f"v1.9.1-r4: el fallback de {agent.name} contiene "
                f"path del formato viejo '{legacy}' (NO desplegado)."
            )

    @pytest.mark.parametrize("agent", TALKING_AGENTS, ids=lambda a: a.name)
    def test_system_prompt_has_no_u_slug_paths(self, agent):
        """El prompt puede MENCIONAR el formato viejo (como anti-ejemplo
        en las reglas b/c/d de _GLOBAL_RULES), pero NO puede proponerlo
        como link sugerido al usuario."""
        for legacy in (
            "/u/{slug}/reservar",
            "/u/{slug}/catalogo",
        ):
            # Si aparece en el prompt, debe ser en contexto de prohibición.
            # Buscamos el contexto: si está, debe estar precedido por
            # "NUNCA" o "no existe" o "404".
            if legacy in agent.system_prompt:
                idx = agent.system_prompt.find(legacy)
                # 200 caracteres antes de la aparición
                context = agent.system_prompt[max(0, idx - 200):idx].lower()
                assert (
                    "nunca" in context
                    or "no existe" in context
                    or "404" in context
                    or "no esté" in context
                    or "prohibido" in context
                    or "prohibid" in context
                ), (
                    f"v1.9.1-r4: el prompt de {agent.name} menciona "
                    f"'{legacy}' SIN contexto de prohibición."
                )


# ── 3. Anti-tool-deprecada: cero refs a `get_tenant_dashboard_urls` ─
class TestNoDeprecatedTool:
    """v1.9.1-r4 PROHIBE referenciar `get_tenant_dashboard_urls` (DEPRECATED).

    La única tool vigente de URLs es `get_tenant_public_urls`.
    """

    @pytest.mark.parametrize("agent", TALKING_AGENTS, ids=lambda a: a.name)
    def test_no_deprecated_tool_in_prompt(self, agent):
        """Si la tool deprecada aparece en el prompt, debe ser en contexto
        de PROHIBICIÓN (típicamente en `app_knowledge.render_short_summary()`
        que advierte: 'esta tool está DEPRECATED, usa X en su lugar').

        Verificamos que NO haya un uso PRESCRIPTIVO del tool (ej. 'usa
        get_tenant_dashboard_urls para…') — eso sí sería regresión.
        """
        deprecated = "get_tenant_dashboard_urls"
        if deprecated in agent.system_prompt:
            # Si está, debe ser en contexto de prohibición. Buscamos
            # 200 chars antes para encontrar contexto como "DEPRECATED",
            # "DEPRECADA", "no uses", "en su lugar usa".
            idx = agent.system_prompt.find(deprecated)
            context = agent.system_prompt[max(0, idx - 200):idx + 200].lower()
            assert (
                "deprec" in context  # DEPRECATED / DEPRECADA
                or "en su lugar" in context
                or "no uses" in context
                or "no está disponible" in context
                or "ya no aparece" in context
            ), (
                f"v1.9.1-r4: el prompt de {agent.name} menciona la tool "
                f"DEPRECATED '{deprecated}' SIN contexto de prohibición."
            )

    @pytest.mark.parametrize("agent", TALKING_AGENTS, ids=lambda a: a.name)
    def test_no_deprecated_tool_in_fallback(self, agent):
        assert "get_tenant_dashboard_urls" not in agent.fallback

    def test_global_rules_has_no_deprecated_tool(self):
        """_GLOBAL_RULES NO debe mencionar la tool deprecada."""
        assert "get_tenant_dashboard_urls" not in _GLOBAL_RULES


# ── 4. Tool vigente: `get_tenant_public_urls` debe estar mencionada ─
class TestCurrentToolIsPresent:
    """v1.9.1-r4: `get_tenant_public_urls` debe ser mencionada en los
    lugares donde el LLM la necesita (todos los agentes pueden recibir
    preguntas de URLs públicas; HELP la debe nombrar explícitamente)."""

    @pytest.mark.parametrize("agent", TALKING_AGENTS, ids=lambda a: a.name)
    def test_global_rules_mentions_current_tool(self, agent):
        """`_GLOBAL_RULES` se concatena a todos. La regla 10a debe
        mencionar la tool vigente."""
        assert "get_tenant_public_urls" in _GLOBAL_RULES

    def test_help_agent_mentions_current_tool_explicitly(self):
        """HELP es el agente de plataforma; DEBE mencionar la tool por
        nombre en su prompt (no solo en _GLOBAL_RULES)."""
        assert "get_tenant_public_urls" in HELP.system_prompt

    def test_help_agent_has_regla_4_about_urls(self):
        """HELP debe tener una REGLA #4 explícita sobre URLs públicas."""
        assert "REGLA #4" in HELP.system_prompt
        # Y debe nombrar la tool
        assert "get_tenant_public_urls" in HELP.system_prompt
        # Y debe prohibir el placeholder `{slug}` literal
        assert "{slug}" in HELP.system_prompt


# ── 5. Dominio de producción correcto ──────────────────────────────
class TestProductionDomainIsCorrect:
    """v1.9.1-r4: el dominio del backend en producción es
    `wowhub-api-production.up.railway.app` (NO `wowhub.app`)."""

    def test_global_rules_cites_railway_domain(self):
        low = _GLOBAL_RULES.lower()
        assert "wowhub-api-production.up.railway.app" in low
        # Y debe decir que NUNCA uses wowhub.app
        assert "wowhub.app" in _GLOBAL_RULES
        low = _GLOBAL_RULES.lower()
        assert "nunca" in low  # énfasis

    def test_help_agent_cites_railway_domain(self):
        """HELP debe ilustrar la URL con el dominio REAL de Railway."""
        assert "wowhub-api-production.up.railway.app" in HELP.system_prompt
        # Y debe tener un ejemplo de URL REAL con slug sustituido
        assert "cafeluna" in HELP.system_prompt
        # La URL de ejemplo debe apuntar a la API (NO al SPA)
        assert "api/v1/public/t/" in HELP.system_prompt


# ── 6. Roadmap: el prompt debe advertir de features no desplegadas ─
class TestRoadmapWarning:
    """v1.9.1-r4: el LLM debe saber que reservas/loyalty/pedidos NO
    están en producción, para no sugerir URLs falsas para ellas."""

    def test_global_rules_mentions_roadmap_features(self):
        low = _GLOBAL_RULES.lower()
        assert "roadmap" in low
        # Debe mencionar al menos las features clave que están en roadmap
        assert "reservas" in low or "reserva" in low
        assert "loyalty" in low

    def test_help_agent_mentions_roadmap(self):
        """HELP debe tener una regla explícita sobre features en roadmap."""
        low = HELP.system_prompt.lower()
        assert "roadmap" in low
        assert "reservas" in low or "reserva" in low
        assert "loyalty" in low


# ── 7. Fallbacks estructuralmente válidos ─────────────────────────
class TestFallbacksAreUsable:
    """Las fallbacks son la red de seguridad cuando el LLM no responde.
    Deben ser útiles (no estar vacías, no contener URLs falsas, tener
    siguientes pasos concretos)."""

    @pytest.mark.parametrize("agent", TALKING_AGENTS, ids=lambda a: a.name)
    def test_fallback_is_non_empty(self, agent):
        assert agent.fallback and len(agent.fallback.strip()) > 20, (
            f"v1.9.1-r4: el fallback de {agent.name} está vacío o es "
            f"demasiado corto."
        )

    @pytest.mark.parametrize("agent", TALKING_AGENTS, ids=lambda a: a.name)
    def test_fallback_in_spanish(self, agent):
        """El fallback debe estar en español (no en inglés)."""
        # Heurística barata: presencia de acentos/ñ o palabras comunes
        # en español. Esto evita regresiones tipo "I'm sorry, I can't".
        common_es = ("para", "abre", "tu", "panel", "promoción", "cliente")
        low = agent.fallback.lower()
        assert any(w in low for w in common_es), (
            f"v1.9.1-r4: el fallback de {agent.name} no parece estar "
            f"en español."
        )

    @pytest.mark.parametrize("agent", TALKING_AGENTS, ids=lambda a: a.name)
    def test_fallback_has_concrete_next_step(self, agent):
        """El fallback debe terminar con un siguiente paso concreto."""
        # Busca indicadores de cierre útil: "vuelva", "cuando vuelva",
        # "en cuanto vuelva", "dime", "si me", "para que"
        low = agent.fallback.lower()
        has_next_step = any(
            phrase in low
            for phrase in (
                "vuelva",
                "cuando vuelva",
                "en cuanto vuelva",
                "si me",
                "para que",
                "quieres",
                "necesitas",
            )
        )
        assert has_next_step, (
            f"v1.9.1-r4: el fallback de {agent.name} no termina con "
            f"un siguiente paso concreto."
        )


# ── 8. Registro de agentes: los 5 deben existir ────────────────────
class TestAgentRegistry:
    """El módulo debe exportar los 5 sub-agentes esperados y un router."""

    def test_all_agents_exist(self):
        for name in ("marketing", "growth", "automation", "marketplace", "help"):
            agent = get_agent(name)
            assert agent is not None, f"Agente {name} no encontrado"
            assert agent.name == name

    def test_router_exists(self):
        assert ROUTER is not None
        assert ROUTER.name == "router"
