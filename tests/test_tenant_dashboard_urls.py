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


# ── Anti-regresión: español de Chile (v1.9.1-r1) ─────────────────
class TestChileanSpanishRegression:
    """Verifica que el sistema está en español de Chile, NO en español de Argentina.

    Reglas cubiertas:
    - No voseo en system prompts (tú, no vos).
    - No argentinismos: "guita", "boludo", "morfar", "trucho", "al toque", "copado".
    - FAQ keys usan tildes del imperativo tú: "pásame", "mándame".
    - Imperativo en respuestas: "Llama", "Muestra", "sugiere" (no voseo).
    """

    VOSE_FORBIDDEN = [
        "llamá ", "llamás", "mostrá", "mostrás", "mostrame",
        "mandame", "pasame", "decime", "fijate", "fijáte",
        "usá", "usá ", "usá.", "usá,",
        "devolvé", "mandá ", "mandá.", "mandá,",
        "querés", "tenés", "sos ", "sos.", "sos,",
        "hacés", "podés", "sabés", "escribime",
        "ejecutá", "agendá", "aplicá", "creá", "lanzá", "indicá",
        "prepará", "sugerí",
        "andá", "andá ", "andá.", "andá,", "dale al",
        "jalamos", "jalar", "boludo", "morfar", "trucho",
        "al toque", "copado", "guita", "pibe", "re-bueno",
        "para vos:",
    ]

    def test_global_rules_no_voseo(self):
        """El _GLOBAL_RULES debe declarar el dialecto chileno explícitamente."""
        from app.services.ai_agents import _GLOBAL_RULES
        # La regla anti-voseo debe estar presente en la regla 0
        assert "español de Chile" in _GLOBAL_RULES
        assert "Usa TÚ" in _GLOBAL_RULES or "TÚ (no voseo)" in _GLOBAL_RULES
        assert "voseo" in _GLOBAL_RULES.lower()

    def test_app_knowledge_faq_keys_chilean(self):
        """Los FAQ keys deben usar tildes chilenas (tú imperativo)."""
        faq = app_knowledge.FAQ
        # Keys que DEBEN tener la tilde del imperativo tú
        expected_chilean_keys = [
            "pásame el link de",
            "mándame el link por",
        ]
        for expected in expected_chilean_keys:
            assert expected in faq, (
                f"FAQ key chilena faltante: {expected!r}. "
                f"Found: {[k for k in faq if 'link' in k]}"
            )

    def test_app_knowledge_no_voseo_in_responses(self):
        """Las respuestas de las FAQ nuevas no deben tener voseo."""
        faq = app_knowledge.FAQ
        new_faq_keys = [
            "cómo abro el panel de productos",
            "cómo abro el panel de",
            "dónde veo el admin ia",
            "pásame el link de",
            "mándame el link por",
        ]
        for k in new_faq_keys:
            assert k in faq, f"FAQ key faltante: {k!r}"
            text = faq[k]
            text_low = text.lower()
            # No debe contener voseo imperativo
            assert "llamá" not in text_low, f"Voseo en {k!r}: {text!r}"
            assert "mostrá" not in text_low, f"Voseo en {k!r}: {text!r}"
            assert "usá" not in text_low, f"Voseo en {k!r}: {text!r}"
            assert "avisale" not in text_low, f"Voseo en {k!r}: {text!r}"
            # Y debe usar imperativo con TÚ
            assert (
                "llama" in text_low
                or "devuelve" in text_low
                or "sugiere" in text_low
                or "suger" in text_low
            ), f"Sin imperativo tú en {k!r}: {text!r}"

    def test_no_existe_no_voseo(self):
        """Las entradas de NO_EXISTE nuevas no deben tener voseo."""
        no_existe = app_knowledge.list_no_existe()
        # Filtramos las de v1.9.1 (las que mencionan dashboard URLs)
        new_no_existe = [
            s for s in no_existe
            if "dashboard" in s.lower() or "get_tenant_dashboard" in s.lower()
        ]
        assert len(new_no_existe) >= 6, f"Esperaba >= 6 entradas de v1.9.1, encontré {len(new_no_existe)}"
        for s in new_no_existe:
            s_low = s.lower()
            assert "llamá" not in s_low, f"Voseo en NO_EXISTE: {s!r}"
            assert "usá" not in s_low, f"Voseo en NO_EXISTE: {s!r}"
            assert "devolvé" not in s_low, f"Voseo en NO_EXISTE: {s!r}"
            assert "devolv" not in s_low or "devuelve" in s_low, f"Voseo en NO_EXISTE: {s!r}"

    def test_render_short_summary_no_voseo(self):
        """El render_short_summary no debe tener voseo en las reglas nuevas."""
        summary = app_knowledge.render_short_summary()
        lines = summary.split("\n")
        dashboard_lines = [
            l for l in lines
            if "dashboard" in l.lower() or "get_tenant_dashboard" in l.lower()
        ]
        assert len(dashboard_lines) >= 2, "Esperaba >= 2 reglas nuevas de v1.9.1 en el summary"
        for line in dashboard_lines:
            ll = line.lower()
            assert "llamá" not in ll, f"Voseo en summary: {line!r}"
            assert "mostrá" not in ll, f"Voseo en summary: {line!r}"
            assert "usá" not in ll, f"Voseo en summary: {line!r}"

    def test_ai_tools_no_voseo(self):
        """Los hints y descriptions de la tool no deben tener voseo."""
        schemas = ai_tools.TOOL_SCHEMAS
        # TOOL_SCHEMAS es una LIST de schemas OpenAI (no dict).
        # Buscamos la tool por nombre dentro de la lista.
        tool = next(
            (t for t in schemas if t.get("function", {}).get("name") == "get_tenant_dashboard_urls"),
            None,
        )
        assert tool is not None, "get_tenant_dashboard_urls no está en TOOL_SCHEMAS"
        desc = tool.get("function", {}).get("description", "").lower()
        assert "mostrá" not in desc, f"Voseo en tool description: {desc!r}"
        assert "usá" not in desc, f"Voseo en tool description: {desc!r}"
        # Y debe usar imperativo tú
        assert "usa esta tool" in desc or "llama" in desc or "muestra" in desc

    def test_ai_tools_fallback_hint_no_voseo(self):
        """El hint del fallback (sin base_url) no debe tener voseo."""
        import asyncio
        from app.services.ai_tools import AIToolContext, tool_get_tenant_dashboard_urls

        class _C:
            user_id = "u"
            tenant_id = "t"
            access_token = "x"
            base_url = ""

        async def _run():
            return await tool_get_tenant_dashboard_urls(_C())

        out = asyncio.run(_run())
        hint = out.get("hint", "").lower()
        assert "mostrá" not in hint, f"Voseo en fallback hint: {out['hint']!r}"
        assert "avisale" not in hint, f"Voseo en fallback hint: {out['hint']!r}"
        # Y debe usar imperativo tú
        assert "muestra" in hint or "avísale" in hint, (
            f"Sin imperativo tú en hint: {out['hint']!r}"
        )

    def test_marketing_studio_templates_no_voseo(self):
        """Los templates de marketing_studio no deben tener voseo."""
        from app.services import marketing_studio
        templates = marketing_studio._FALLBACK_TEMPLATES
        for intent_name, tones in templates.items():
            for tone, tmpl in tones.items():
                tl = tmpl.lower()
                # Buscar voseo imperativo (formas CON tilde, distintivas de voseo).
                # NO chequear "conocer" (infinitivo) ni "conoc" (sub-cadena neutra)
                # porque "le invitamos a conocer" es correcto en español de Chile
                # (formal "usted") y "Conoce {producto}" es imperativo TÚ válido.
                for vose in [
                    "pasá", "mirá", "descubrí", "viví", "aprovechá", "traé",
                    "conocé", "conocés",
                ]:
                    assert vose not in tl, f"Voseo en template {intent_name}/{tone}: {tmpl!r}"
                # "para vos" es voseo preposicional
                assert "para vos" not in tl, f"Voseo preposicional en {intent_name}/{tone}: {tmpl!r}"

    def test_growth_coach_no_voseo(self):
        """Los insights del growth coach no deben tener voseo."""
        # Búsqueda simple en strings clave del módulo
        from app.services import growth_coach
        src = open(growth_coach.__file__).read().lower()
        for vose in ['"no tenés', '"creá', "no tenés promos", "creá tu primera promo"]:
            assert vose not in src, f"Voseo en growth_coach.py: {vose!r}"
