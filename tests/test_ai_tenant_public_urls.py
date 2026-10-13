"""Tests de la tool `get_tenant_public_urls` y su registro.

Esta tool resuelve las URLs públicas del tenant YA CON EL SLUG REAL
sustituido (en vez de devolver el patrón con `{slug}` literal), para
que el asistente HELP pueda entregarle al usuario links reales para
compartir (Instagram bio, WhatsApp, Google Maps, etc.).

Casos cubiertos:
1. Dispatch: la tool está en TOOL_DISPATCH.
2. Schema: tiene JSON schema declarativo para el LLM.
3. Agent: el sub-agente "help" la tiene disponible.
4. Behavior con slug → URLs reales sustituidas.
5. Behavior sin slug → patrones + hint.
6. Behavior con error de API → mensaje claro.
7. Anti-regresión: la FAQ "url pública" menciona la tool.
"""
from __future__ import annotations

import pytest

from app.services import ai_tools, app_knowledge
from app.services.ai_tools import (
    AIToolContext,
    TOOL_DISPATCH,
    TOOL_SCHEMAS,
    tool_get_tenant_public_urls,
    get_tools_for_agent,
)


# ── Registro ──────────────────────────────────────────────
class TestToolRegistration:
    def test_dispatch_has_tool(self):
        """La tool debe estar en el TOOL_DISPATCH."""
        assert "get_tenant_public_urls" in TOOL_DISPATCH
        assert TOOL_DISPATCH["get_tenant_public_urls"] is tool_get_tenant_public_urls

    def test_schema_has_tool(self):
        """La tool debe tener un JSON schema declarativo para el LLM."""
        names = [t["function"]["name"] for t in TOOL_SCHEMAS]
        assert "get_tenant_public_urls" in names

        schema = next(
            t for t in TOOL_SCHEMAS if t["function"]["name"] == "get_tenant_public_urls"
        )
        assert schema["type"] == "function"
        # No requiere parámetros
        assert schema["function"]["parameters"]["properties"] == {}
        # La descripción debe mencionar el slug y el uso
        desc = schema["function"]["description"].lower()
        assert "slug" in desc
        assert "url" in desc or "link" in desc

    def test_help_agent_includes_tool(self):
        """El sub-agente HELP debe poder llamar a la tool."""
        tool_names = [t["function"]["name"] for t in get_tools_for_agent("help")]
        assert "get_tenant_public_urls" in tool_names
        # Y no debe incluir tools de escritura
        for forbidden in ("create_promotion", "create_booking", "send_campaign"):
            assert forbidden not in tool_names, (
                f"HELP no debe tener {forbidden} (es del agente automation)"
            )

    def test_other_agents_do_not_have_it(self):
        """v1.9.1-r4: TODOS los agentes tienen la tool. Cualquier agente
        puede recibir una pregunta del tipo 'dame mi link público' (ej.
        marketing recomendando dónde publicar el catálogo), y la única
        forma de no alucinar la URL es tener la tool disponible.
        """
        for agent in ("help", "marketing", "growth", "automation", "marketplace"):
            names = [t["function"]["name"] for t in get_tools_for_agent(agent)]
            assert "get_tenant_public_urls" in names, (
                f"v1.9.1-r4: el agente {agent} DEBE tener "
                f"get_tenant_public_urls (cualquier agente puede recibir "
                f"preguntas de URLs públicas)"
            )


# ── Knowledge base sincronizada ──────────────────────────
class TestAppKnowledgeSynced:
    def test_faq_url_publica_exists(self):
        """La FAQ 'url pública' debe existir (es la consulta más común)."""
        answer = app_knowledge.faq_lookup("url pública")
        assert answer is not None
        # v1.9.1-r4: la URL de ejemplo REAL es del backend de Railway
        # (NO wowhub.app, NO /u/{slug}/...).
        assert "wowhub-api-production.up.railway.app" in answer
        assert "/api/v1/public/t/cafeluna/catalog" in answer
        # Y referencia explícita a la tool obligatoria
        assert "get_tenant_public_urls" in answer
        # Y debe marcar la tool vieja como DEPRECATED
        assert "DEPRECAD" in answer

    def test_short_summary_unchanged(self):
        """v1.9.1-r4: el render_short_summary describe el formato de
        producción (`/api/v1/public/...`), NO el formato viejo
        `/u/{slug}/...` (que NO existe en producción).
        """
        summary = app_knowledge.render_short_summary()
        # Formato NUEVO (v1.9.1-r4)
        assert "/api/v1/public/t/{slug}" in summary
        # Formato VIEJO eliminado
        assert "/u/{slug}/reservar" not in summary
        assert "/u/{slug}/catalogo" not in summary
        # Y mantiene la regla crítica
        assert "NUNCA inventes" in summary


# ── Behavior de la tool ───────────────────────────────────
class TestToolBehavior:
    @pytest.mark.asyncio
    async def test_returns_real_urls_with_slug(self, monkeypatch):
        """Si el tenant tiene slug, devuelve URLs con el slug REAL sustituido."""
        from app.config import settings
        expected_base = settings.public_base_url.rstrip("/")

        async def fake_api_get(ctx, path, params=None):
            assert path == f"/api/v1/tenants/{ctx.tenant_id}"
            return {
                "id": ctx.tenant_id,
                "slug": "cafeluna",
                "name": "Café Luna",
            }

        monkeypatch.setattr(ai_tools, "_api_get", fake_api_get)

        ctx = AIToolContext(
            user_id="u-1", tenant_id="t-1", access_token="tok",
        )
        out = await tool_get_tenant_public_urls(ctx)

        assert out["source"] == "app_knowledge"
        assert out["has_slug"] is True
        assert out["tenant"]["slug"] == "cafeluna"
        assert out["tenant"]["name"] == "Café Luna"
        assert out["base_url"] == expected_base

        # v1.9.1-r4: las URLs públicas son del formato de producción
        # (`/api/v1/public/t/{slug}/...`), NO del formato viejo
        # `/u/{slug}/...` (que NO existe en producción).
        urls_by_key = {u["key"]: u["url"] for u in out["urls"]}
        # Todas las URLs deben tener el slug REAL (no el placeholder)
        assert "{slug}" not in str(urls_by_key)
        # Y deben tener el formato de producción
        assert "cafeluna" in urls_by_key["perfil"]
        assert "cafeluna" in urls_by_key["catalogo"]
        assert urls_by_key["perfil"] == f"{expected_base}/api/v1/public/t/cafeluna/profile"
        assert urls_by_key["catalogo"] == f"{expected_base}/api/v1/public/t/cafeluna/catalog"
        # El QR redirect usa /r/{short_code} (no contiene el slug del tenant)
        assert "qr_redirect" in urls_by_key or "qr" in urls_by_key
        # NO debe haber keys del formato viejo
        assert "reservar" not in urls_by_key, (
            "v1.9.1-r4: /u/{slug}/reservar NO existe en producción. "
            "Las reservas están en roadmap."
        )
        assert "loyalty" not in urls_by_key, (
            "v1.9.1-r4: /loyalty/{slug} NO está desplegado. Está en roadmap."
        )

    @pytest.mark.asyncio
    async def test_returns_patterns_when_no_slug(self, monkeypatch):
        """Si el tenant NO tiene slug, devuelve los patrones + hint."""
        async def fake_api_get(ctx, path, params=None):
            return {
                "id": ctx.tenant_id,
                "slug": None,
                "name": "Café Sin Slug",
            }

        monkeypatch.setattr(ai_tools, "_api_get", fake_api_get)

        ctx = AIToolContext(
            user_id="u-1", tenant_id="t-1", access_token="tok",
        )
        out = await tool_get_tenant_public_urls(ctx)

        assert out["has_slug"] is False
        assert out["tenant"]["slug"] is None
        assert out["tenant"]["name"] == "Café Sin Slug"

        # Devuelve los patrones (no las URLs) para que la IA sepa qué completar
        assert "patterns" in out
        patterns_by_key = {p["key"]: p["pattern"] for p in out["patterns"]}
        # v1.9.1-r4: los patrones son del formato de producción
        assert patterns_by_key["perfil"] == "/api/v1/public/t/{slug}/profile"
        assert patterns_by_key["catalogo"] == "/api/v1/public/t/{slug}/catalog"
        assert patterns_by_key["landing"] == "/api/v1/public/t/{slug}/landing"
        assert patterns_by_key["qr_redirect"] == "/r/{short_code}"
        # NO debe haber patterns del formato viejo
        assert "reservar" not in patterns_by_key, (
            "v1.9.1-r4: el patrón /u/{slug}/reservar NO debe existir. "
            "Las reservas están en roadmap."
        )
        assert "loyalty" not in patterns_by_key, (
            "v1.9.1-r4: el patrón /loyalty/{slug} NO debe existir. "
            "Está en roadmap."
        )

        # Y un hint útil para que el LLM sepa qué decirle al usuario
        assert "hint" in out
        assert "slug" in out["hint"].lower()
        assert "Configuración" in out["hint"] or "configuracion" in out["hint"].lower()

        # NO debe incluir URLs ya armadas
        assert "urls" not in out

    @pytest.mark.asyncio
    async def test_returns_patterns_when_slug_empty_string(self, monkeypatch):
        """Si el slug es string vacío, también se considera 'sin slug'."""
        async def fake_api_get(ctx, path, params=None):
            return {"id": ctx.tenant_id, "slug": "", "name": "X"}

        monkeypatch.setattr(ai_tools, "_api_get", fake_api_get)

        ctx = AIToolContext(
            user_id="u-1", tenant_id="t-1", access_token="tok",
        )
        out = await tool_get_tenant_public_urls(ctx)

        assert out["has_slug"] is False
        assert "patterns" in out

    @pytest.mark.asyncio
    async def test_returns_error_on_api_failure(self, monkeypatch):
        """Si la API falla, devuelve un error claro (no revienta)."""
        async def fake_api_get(ctx, path, params=None):
            return {"error": "GET /api/v1/tenants/t-1 → HTTP 401", "detail": "Unauthorized"}

        monkeypatch.setattr(ai_tools, "_api_get", fake_api_get)

        ctx = AIToolContext(
            user_id="u-1", tenant_id="t-1", access_token="tok",
        )
        out = await tool_get_tenant_public_urls(ctx)

        assert "error" in out
        assert "hint" in out
        assert "tenant" not in out  # no se construyó tenant

    @pytest.mark.asyncio
    async def test_uses_settings_public_base_url_when_not_provided(
        self, monkeypatch
    ):
        """Si no se pasa base_url al context, usa settings.public_base_url.

        v1.9.1-r4: monkeypatch sobre settings para forzar el default de
        Railway (porque el .env puede tener un valor distinto en dev/test).
        Lo importante es que la tool USA `settings.public_base_url` como
        source of truth (no la hardcodea).
        """
        from app.config import settings

        # Forzamos el setting al default de v1.9.1-r4 (Railway), sin
        # importar qué diga el .env del entorno de test.
        monkeypatch.setattr(
            settings, "public_base_url",
            "https://wowhub-api-production.up.railway.app",
        )

        async def fake_api_get(ctx, path, params=None):
            return {"id": ctx.tenant_id, "slug": "mislug", "name": "Mi Negocio"}

        monkeypatch.setattr(ai_tools, "_api_get", fake_api_get)

        ctx = AIToolContext(
            user_id="u-1", tenant_id="t-1", access_token="tok",
            base_url=None,  # forzar fallback
        )
        out = await tool_get_tenant_public_urls(ctx)

        # La base debe coincidir con settings.public_base_url sin la barra final
        expected_base = "https://wowhub-api-production.up.railway.app"
        assert out["base_url"] == expected_base
        # v1.9.1-r4: el default es el backend de Railway, NO wowhub.app
        assert "wowhub-api-production.up.railway.app" in out["base_url"]
        assert "wowhub.app" not in out["base_url"], (
            "v1.9.1-r4: el default de public_base_url debe ser Railway, "
            "no wowhub.app (que da NXDOMAIN)."
        )
        # Y todas las URLs deben empezar con esa base
        for u in out["urls"]:
            assert u["url"].startswith(expected_base)
            # El QR redirect no tiene slug del tenant (es /r/{short_code})
            if u["key"] != "qr_redirect":
                assert "mislug" in u["url"], (
                    f"URL {u['key']!r} no tiene el slug sustituido: {u['url']!r}"
                )
            assert "{slug}" not in u["url"]

    @pytest.mark.asyncio
    async def test_descriptions_are_preserved(self, monkeypatch):
        """Las descripciones de cada URL deben venir de app_knowledge."""
        async def fake_api_get(ctx, path, params=None):
            return {"id": ctx.tenant_id, "slug": "demo", "name": "Demo"}

        monkeypatch.setattr(ai_tools, "_api_get", fake_api_get)

        ctx = AIToolContext(
            user_id="u-1", tenant_id="t-1", access_token="tok",
        )
        out = await tool_get_tenant_public_urls(ctx)

        # Las descripciones deben coincidir con las de app_knowledge
        kb_descriptions = {u["key"]: u["description"] for u in app_knowledge.list_public_urls()}
        for u in out["urls"]:
            assert u["description"] == kb_descriptions[u["key"]]


# ── E2E-like: el orchestrator HELP debería poder usar la tool ──
class TestHelpAgentE2E:
    def test_help_system_prompt_mentions_new_tool(self):
        """El system prompt del agente HELP debe mencionar la nueva tool
        para que el LLM la use (no devuelva patrones con {slug})."""
        from app.services.ai_agents import HELP, get_agent

        agent = get_agent("help")
        assert agent is HELP
        prompt = agent.system_prompt
        assert "get_tenant_public_urls" in prompt, (
            "El system prompt de HELP debe mencionar la tool por nombre"
        )
        # Y debe explicar CUÁNDO usarla
        assert "slug" in prompt.lower()
        # Debe decir que la respuesta ya viene CON el slug
        assert "real" in prompt.lower() or "ya con" in prompt.lower() or "ya" in prompt.lower()

    def test_help_welcome_mentions_url_sharing(self):
        """El welcome del agente HELP debe seguir mencionando URLs públicas
        (no se rompe la UX existente)."""
        from app.services.ai_agents import get_agent

        welcome = get_agent("help").welcome.lower()
        assert "url" in welcome or "compartir" in welcome or "link" in welcome

    def test_help_system_prompt_has_regla_4(self):
        """REGLA #4 del system prompt de HELP debe insistir en llamar a
        `get_tenant_public_urls` para CUALQUIER URL del tenant. Sin esta
        regla, el LLM cae en el patrón con `{slug}` literal."""
        from app.services.ai_agents import get_agent

        prompt = get_agent("help").system_prompt
        # REGLA #4 explícita
        assert "REGLA #4" in prompt, "HELP debe tener una REGLA #4 sobre URLs"
        # Y debe nombrar la tool como la acción OBLIGATORIA
        assert "get_tenant_public_urls" in prompt
        # Y debe prohibir explícitamente responder con el patrón literal
        assert "{slug}" in prompt, "REGLA #4 debe mencionar `{slug}` como prohibido"
        # Y debe decir "NUNCA" (énfasis)
        low = prompt.lower()
        assert "nunca" in low

    def test_faq_url_publica_puts_tool_instruction_first(self):
        """La FAQ 'url pública' debe arrancar con la instrucción de LLAMAR
        A LA TOOL, no con el patrón literal. Si arranca con el patrón, el
        LLM lo copia como respuesta (el bug que el usuario reportó).
        v1.9.1-r4: el ejemplo de URL es del backend de Railway, NO
        wowhub.app/u/... (esos paths NO existen en producción).
        """
        answer = app_knowledge.faq_lookup("url pública")
        assert answer is not None
        # La PRIMERA mención de la tool debe estar ANTES de la primera
        # mención de cualquier URL de ejemplo, para que el LLM lea
        # primero la regla.
        low = answer.lower()
        pos_tool = low.find("get_tenant_public_urls")
        # v1.9.1-r4: el ejemplo de URL es de Railway, NO wowhub.app/u/
        pos_example = low.find("wowhub-api-production.up.railway.app/api/v1/public/t/")
        assert pos_tool != -1, "FAQ debe mencionar la tool"
        assert pos_example != -1, "FAQ debe contener al menos un ejemplo de URL"
        assert pos_tool < pos_example, (
            f"FAQ debe poner la tool ANTES del ejemplo de URL. "
            f"tool@{pos_tool} example@{pos_example}"
        )
        # Y NO debe contener ya el patrón literal `/u/{slug}/reservar`
        # (porque eso es exactamente lo que queremos evitar como respuesta).
        assert "/u/{slug}/reservar" not in answer, (
            "FAQ no debe contener el patrón literal; usa ejemplos de URL real"
        )
        # Y NO debe mencionar el dominio viejo wowhub.app
        assert "wowhub.app" not in answer, (
            "v1.9.1-r4: la FAQ no debe mencionar wowhub.app (da NXDOMAIN)"
        )
        # Y debe arrancar con un NO imperativo (anti-copia del patrón)
        first_50 = answer[:50].lower()
        assert "no respondas" in first_50 or "no devuelvas" in first_50 or "siempre llama" in first_50, (
            f"FAQ debe arrancar con instrucción imperativa; arrancó con: {first_50!r}"
        )
