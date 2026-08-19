"""Tests de la tool `get_tenant_dashboard_urls` y su registro.

Esta tool devuelve los links del PANEL autenticado (no las URLs públicas)
YA CON URL ABSOLUTA clickeable (ej. `https://wowhub.app/dashboard/products`),
usando `settings.public_base_url` como prefijo. Es la respuesta a la pregunta
del usuario: "el link debiera cargar la ruta completa, para que pueda entrar
fácilmente".

Casos cubiertos:
1. Registro: la tool está en TOOL_DISPATCH + TOOL_SCHEMAS.
2. Agents: los 5 sub-agentes (marketing, growth, automation, marketplace, help)
   la tienen disponible.
3. Knowledge base sincronizada: DASHBOARD_URLS constant, FAQ entries,
   NO_EXISTE entries, render_short_summary incluye la regla.
4. Behavior: devuelve URLs absolutas con el prefijo correcto, paths desnudos
   NO aparecen en el output, requires_role está anotado por módulo.
5. Anti-regresión: el FAQ menciona la tool, el summary menciona la regla
   de "links absolutos", NO_EXISTE menciona "no respondas con paths desnudos".
"""
from __future__ import annotations

import pytest

from app.services import ai_tools, app_knowledge
from app.services.ai_tools import (
    AIToolContext,
    TOOL_DISPATCH,
    TOOL_SCHEMAS,
    get_tools_for_agent,
)


# ── Registro ──────────────────────────────────────────────
class TestToolRegistration:
    def test_dispatch_has_tool(self):
        """La tool debe estar en el TOOL_DISPATCH."""
        from app.services.ai_tools import tool_get_tenant_dashboard_urls
        assert "get_tenant_dashboard_urls" in TOOL_DISPATCH
        assert TOOL_DISPATCH["get_tenant_dashboard_urls"] is tool_get_tenant_dashboard_urls

    def test_schema_has_tool(self):
        """La tool debe tener un JSON schema declarativo para el LLM."""
        names = [t["function"]["name"] for t in TOOL_SCHEMAS]
        assert "get_tenant_dashboard_urls" in names

        schema = next(
            t for t in TOOL_SCHEMAS if t["function"]["name"] == "get_tenant_dashboard_urls"
        )
        assert schema["type"] == "function"
        # No requiere parámetros
        assert schema["function"]["parameters"]["properties"] == {}
        # La descripción debe mencionar el prefijo base_url y el clickeable
        desc = schema["function"]["description"].lower()
        assert "absolut" in desc or "url" in desc
        assert "click" in desc or "panel" in desc

    def test_all_5_agents_include_tool(self):
        """Los 5 sub-agentes deben tener la tool (no es de un solo agente)."""
        for agent in ("marketing", "growth", "automation", "marketplace", "help"):
            names = [t["function"]["name"] for t in get_tools_for_agent(agent)]
            assert "get_tenant_dashboard_urls" in names, (
                f"El agente {agent} debe tener get_tenant_dashboard_urls"
            )


# ── Knowledge base sincronizada ──────────────────────────
class TestAppKnowledgeSynced:
    def test_dashboard_urls_constant_exists(self):
        """La constante DASHBOARD_URLS debe existir con los 13 módulos."""
        from app.services.app_knowledge import DASHBOARD_URLS
        assert DASHBOARD_URLS["base_url_source"] == "settings.public_base_url"
        assert len(DASHBOARD_URLS["modules"]) == 13
        # Reglas críticas
        rules_text = " ".join(DASHBOARD_URLS["rules"]).lower()
        assert "get_tenant_dashboard_urls" in rules_text
        assert "nunca" in rules_text
        assert "markdown" in rules_text

    def test_faq_como_abro_panel_productos(self):
        """FAQ 'cómo abro el panel de productos' debe mencionar la tool."""
        answer = app_knowledge.faq_lookup("cómo abro el panel de productos")
        assert answer is not None
        assert "get_tenant_dashboard_urls" in answer
        # Y un ejemplo de URL REAL (absoluta, no path)
        assert "https://wowhub.app/dashboard" in answer
        # Y NUNCA debe contener el path desnudo como sugerencia de respuesta
        # (solo puede aparecer como "NO respondas con...")
        # (Verificamos que la regla "NO respondas" esté presente)
        assert "nunca" in answer.lower()

    def test_faq_donde_admin_ia(self):
        """FAQ 'dónde veo el admin ia' debe mencionar la tool + rol."""
        answer = app_knowledge.faq_lookup("dónde veo el admin ia")
        assert answer is not None
        assert "get_tenant_dashboard_urls" in answer
        # Debe mencionar que requiere admin
        assert "admin" in answer.lower() or "OWNER" in answer

    def test_no_existe_has_dashboard_urls_anti_hallucination(self):
        """La lista NO_EXISTE debe tener entradas sobre el bug 'paths desnudos'."""
        no_existe = app_knowledge.list_no_existe()
        joined = " ".join(no_existe).lower()
        # Reglas críticas que SIEMPRE deben estar
        assert "no son urls absolutas" in joined or "no es una url absoluta" in joined
        assert "no debe inventar la url base" in joined
        assert "no debe responder con paths desnudos" in joined
        assert "no incluyas el slug" in joined
        assert "no debe confundir" in joined

    def test_render_short_summary_has_dashboard_rule(self):
        """El system prompt (render_short_summary) debe mencionar la regla nueva."""
        summary = app_knowledge.render_short_summary()
        low = summary.lower()
        # Las 2 reglas críticas nuevas
        assert "get_tenant_dashboard_urls" in low
        assert "links absolutos clickeables" in low or "links absolutos" in low
        # Regla anti-alucinación sobre no incluir slug en panel
        assert "mismas para todos los tenants" in low


# ── Behavior de la tool ───────────────────────────────────
class TestToolBehavior:
    @pytest.mark.asyncio
    async def test_returns_absolute_urls(self):
        """Debe devolver URLs ABSOLUTAS con settings.public_base_url como prefijo."""
        from app.config import settings
        from app.services.ai_tools import tool_get_tenant_dashboard_urls

        expected_base = settings.public_base_url.rstrip("/")
        ctx = AIToolContext(
            user_id="u-1", tenant_id="t-1", access_token="tok",
        )
        out = await tool_get_tenant_dashboard_urls(ctx)

        assert out["source"] == "app_knowledge"
        assert out["has_base_url"] is True
        assert out["base_url"] == expected_base

        # Todos los URLs deben ser absolutos y arrancar con la base
        for entry in out["dashboard_urls"]:
            url = entry["url"]
            assert url.startswith(expected_base), f"URL no absoluta: {url}"
            # NO debe contener el path desnudo sin prefijo
            assert not url.startswith("/dashboard"), f"Path desnudo: {url}"
            # NO debe contener {slug} (no aplica al panel)
            assert "{slug}" not in url, f"Path con placeholder: {url}"
            # NO debe incluir el prefijo público
            assert "/u/" not in url, f"URL pública usada: {url}"

    @pytest.mark.asyncio
    async def test_includes_all_13_modules(self):
        """Debe incluir los 13 módulos del panel."""
        from app.services.ai_tools import tool_get_tenant_dashboard_urls
        ctx = AIToolContext(
            user_id="u-1", tenant_id="t-1", access_token="tok",
        )
        out = await tool_get_tenant_dashboard_urls(ctx)

        keys = {e["key"] for e in out["dashboard_urls"]}
        expected_keys = {
            "resumen", "productos", "promociones", "clientes", "pedidos",
            "reservas", "campanas", "sucursales", "fidelizacion", "qr",
            "configuracion", "admin_ia", "superadmin",
        }
        assert keys == expected_keys, f"Faltan módulos: {expected_keys - keys}"

    @pytest.mark.asyncio
    async def test_requires_role_per_module(self):
        """Cada módulo debe anotar el rol mínimo requerido."""
        from app.services.ai_tools import tool_get_tenant_dashboard_urls
        ctx = AIToolContext(
            user_id="u-1", tenant_id="t-1", access_token="tok",
        )
        out = await tool_get_tenant_dashboard_urls(ctx)

        by_key = {e["key"]: e for e in out["dashboard_urls"]}
        assert by_key["superadmin"]["requires_role"] == "superuser"
        assert by_key["admin_ia"]["requires_role"] == "admin"
        # El resto es viewer+ (cualquiera con acceso al tenant)
        for key in ("resumen", "productos", "promociones", "clientes", "pedidos",
                    "reservas", "campanas", "sucursales", "fidelizacion", "qr",
                    "configuracion"):
            assert by_key[key]["requires_role"] == "viewer", f"{key} mal anotado"

    @pytest.mark.asyncio
    async def test_fallback_when_no_base_url(self, monkeypatch):
        """Si settings.public_base_url está vacío, devuelve paths relativos + warning."""
        from app.services.ai_tools import tool_get_tenant_dashboard_urls
        from app.config import settings

        # Forzar base_url vacío
        monkeypatch.setattr(settings, "public_base_url", "")

        ctx = AIToolContext(
            user_id="u-1", tenant_id="t-1", access_token="tok",
        )
        out = await tool_get_tenant_dashboard_urls(ctx)

        assert out["has_base_url"] is False
        assert "warning" in out
        assert "paths" in out
        # Los paths deben ser relativos (sin prefijo) y ser paths internos del panel
        # (algunos están bajo /dashboard/*, otros bajo /admin/* como admin_ia o superadmin)
        for entry in out["paths"]:
            p = entry["path"]
            assert p.startswith("/"), f"Path sin / inicial: {p}"
            assert not p.startswith("http"), f"Path con esquema http: {p}"
            assert "://" not in p, f"Path con esquema: {p}"
        # Y debe tener un hint útil (que oriente al usuario sobre qué hacer)
        assert "hint" in out
        hint_low = out["hint"].lower()
        assert (
            "logueado" in hint_low
            or "login" in hint_low
            or "configuraci" in hint_low
            or "branding" in hint_low
            or "public_base_url" in hint_low
        ), f"Hint no orienta al usuario: {out['hint']!r}"

    @pytest.mark.asyncio
    async def test_descriptions_match_app_knowledge(self):
        """Las descripciones de cada módulo deben venir de app_knowledge."""
        from app.services.ai_tools import tool_get_tenant_dashboard_urls
        ctx = AIToolContext(
            user_id="u-1", tenant_id="t-1", access_token="tok",
        )
        out = await tool_get_tenant_dashboard_urls(ctx)

        kb_descriptions = {m["key"]: m["description"] for m in app_knowledge.list_modules()}
        for entry in out["dashboard_urls"]:
            assert entry["description"] == kb_descriptions[entry["key"]]

    @pytest.mark.asyncio
    async def test_returns_hint_about_markdown(self):
        """El hint debe recordarle al LLM que muestre los links como markdown."""
        from app.services.ai_tools import tool_get_tenant_dashboard_urls
        ctx = AIToolContext(
            user_id="u-1", tenant_id="t-1", access_token="tok",
        )
        out = await tool_get_tenant_dashboard_urls(ctx)

        hint = out["hint"].lower()
        assert "markdown" in hint or "clickeable" in hint
        # Y debe advertir contra paths desnudos
        assert "no respondas" in hint or "nunca" in hint or "path" in hint


# ── Anti-regresión: el system prompt global debe estar sincronizado ──
class TestSystemPromptRegression:
    def test_render_short_summary_warns_against_naked_paths(self):
        """El system prompt debe advertir que NO se responda con paths desnudos."""
        summary = app_knowledge.render_short_summary()
        low = summary.lower()
        # La regla nueva debe estar
        assert "nunca respondas con paths desnudos" in low or (
            "paths desnudos" in low and "nunca" in low
        )

    def test_render_short_summary_distinguishes_panel_vs_public(self):
        """El summary debe distinguir entre URLs del panel y URLs públicas."""
        summary = app_knowledge.render_short_summary()
        low = summary.lower()
        # Las dos reglas deben estar (la del panel + la de NO slug en panel)
        assert "get_tenant_dashboard_urls" in low
        assert "get_tenant_public_urls" in low

    def test_no_existe_mentions_dashboard_urls_tool(self):
        """Al menos una entrada de NO_EXISTE debe mencionar la tool por nombre."""
        no_existe = app_knowledge.list_no_existe()
        joined = " ".join(no_existe).lower()
        assert "get_tenant_dashboard_urls" in joined
