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


# ── Anti-regresión: URLs absolutas + anti-placeholder (v1.9.1-r2) ──
class TestAbsoluteURLsRegression:
    """Verifica que el sistema NUNCA devuelve placeholders literales,
    paths desnudos ni dominios hardcodeados. Solamente URLs ABSOLUTAS
    con el dominio de `settings.public_base_url` (default `https://wowhub.app`).

    Bug original: el AI respondía con `wowhub.app/u/tu-negocio/reservar` o
    con paths desnudos `/dashboard/products`, que NO son clickeables.
    """

    # Palabras/frases prohibidas como parte de una URL pública
    FORBIDDEN_PLACEHOLDERS = [
        "tu-negocio", "tu-tienda", "tu-empresa", "tu-sucursal", "tu-restaurante",
        "mi-negocio", "mi-tienda", "mi-empresa", "mi-sucursal",
        "my-business", "my-shop", "my-store",
    ]

    # Paths desnudos del panel (sin prefijo de dominio)
    NAKED_PATHS = [
        "/dashboard/products", "/dashboard/promotions", "/dashboard/bookings",
        "/dashboard/customers", "/dashboard/campaigns", "/dashboard/settings",
    ]

    # Dominios prohibidos hardcodeados en una URL de respuesta
    FORBIDDEN_DOMAINS = [
        "wowhub-api-production.up.railway.app",
        "localhost:3000", "localhost:8000", "127.0.0.1",
    ]

    def test_global_rules_has_links_rule_10(self):
        """La Regla 10 'LINKS Y URLS' debe existir en _GLOBAL_RULES (regla dura)."""
        from app.services.ai_agents import _GLOBAL_RULES
        assert "10. LINKS Y URLS" in _GLOBAL_RULES, (
            "Regla 10 LINKS Y URLS no encontrada en _GLOBAL_RULES. "
            "Esta es la regla dura anti-placeholder/anti-path-desnudo."
        )
        # Debe mencionar los placeholders prohibidos
        for placeholder in ("tu-negocio", "{slug}"):
            assert placeholder in _GLOBAL_RULES, (
                f"Regla 10 debe mencionar el placeholder prohibido {placeholder!r}"
            )
        # Debe mencionar el dominio backend prohibido
        assert "wowhub-api-production.up.railway.app" in _GLOBAL_RULES, (
            "Regla 10 debe mencionar explícitamente el dominio backend prohibido"
        )

    def test_no_existe_anti_placeholder(self):
        """NO_EXISTE debe tener entradas que prohíban placeholders literales."""
        no_existe = app_knowledge.list_no_existe()
        joined = " ".join(no_existe).lower()
        # Cada placeholder prohibido debe aparecer como PROHIBICIÓN explícita
        for placeholder in self.FORBIDDEN_PLACEHOLDERS:
            assert placeholder in joined, (
                f"NO_EXISTE debe prohibir el placeholder {placeholder!r}. "
                f"Encontrado: {[s for s in no_existe if placeholder in s.lower()]}"
            )
        # Y el patrón {slug} literal debe estar prohibido
        assert "{slug}" in joined, "NO_EXISTE debe mencionar '{slug}' como prohibido"

    def test_no_existe_anti_naked_path(self):
        """NO_EXISTE debe tener una entrada que prohíba paths desnudos."""
        no_existe = app_knowledge.list_no_existe()
        joined = " ".join(no_existe).lower()
        # Debe haber una entrada específica contra paths desnudos
        assert "paths desnudos" in joined or "path desnudo" in joined, (
            "NO_EXISTE debe tener una entrada específica contra paths desnudos"
        )

    def test_no_existe_anti_hardcoded_domain(self):
        """NO_EXISTE debe prohibir el dominio backend hardcodeado."""
        no_existe = app_knowledge.list_no_existe()
        joined = " ".join(no_existe).lower()
        for domain in self.FORBIDDEN_DOMAINS:
            assert domain in joined, (
                f"NO_EXISTE debe prohibir el dominio hardcodeado {domain!r}"
            )

    def test_render_short_summary_has_anti_placeholder_rule(self):
        """El render_short_summary debe incluir la regla anti-placeholder."""
        summary = app_knowledge.render_short_summary()
        low = summary.lower()
        # Anti-placeholder: debe mencionar 'tu-negocio' o 'mi-negocio' como prohibido
        assert ("anti-placeholder" in low) or ("tu-negocio" in low) or ("{slug}" in low), (
            "render_short_summary debe incluir la regla ANTI-PLACEHOLDER"
        )
        # Anti-dominio: debe mencionar 'anti-dominio' o el dominio backend
        assert ("anti-dominio" in low) or ("wowhub-api-production" in low), (
            "render_short_summary debe incluir la regla ANTI-DOMINIO"
        )

    def test_public_urls_tool_description_warns_about_placeholders(self):
        """El schema de get_tenant_public_urls debe mencionar placeholders prohibidos."""
        schemas = ai_tools.TOOL_SCHEMAS
        tool = next(
            (t for t in schemas if t.get("function", {}).get("name") == "get_tenant_public_urls"),
            None,
        )
        assert tool is not None, "get_tenant_public_urls no está en TOOL_SCHEMAS"
        desc = tool.get("function", {}).get("description", "").lower()
        # Debe mencionar al menos uno de los placeholders como prohibido
        assert (
            "tu-negocio" in desc
            or "tu-tienda" in desc
            or "my-business" in desc
            or "<slug>" in desc
        ), f"description debe mencionar placeholders prohibidos: {desc!r}"
        # Y debe mencionar el formato markdown
        assert "markdown" in desc or "[" in desc, (
            f"description debe indicar el formato markdown [Texto](url): {desc!r}"
        )

    def test_dashboard_urls_tool_description_warns_about_hardcoded_domain(self):
        """El schema de get_tenant_dashboard_urls debe mencionar el NO-hardcodeo de dominio."""
        schemas = ai_tools.TOOL_SCHEMAS
        tool = next(
            (t for t in schemas if t.get("function", {}).get("name") == "get_tenant_dashboard_urls"),
            None,
        )
        assert tool is not None
        desc = tool.get("function", {}).get("description", "").lower()
        # Debe mencionar que NUNCA se hardcodea el dominio
        assert "hardcode" in desc or "no uses" in desc or "nunca" in desc, (
            f"description debe advertir contra hardcodear el dominio: {desc!r}"
        )

    def test_settings_public_base_url_default_is_wowhub_app(self):
        """El default de settings.public_base_url debe ser https://wowhub.app.

        Esto es el fix raíz: si el .env o Railway no setean la variable,
        el sistema usa el dominio público correcto, NO el backend de Railway.
        """
        from app.config import Settings
        # Crear Settings sin leer el .env (para forzar el default puro)
        s = Settings(_env_file=None)
        assert s.public_base_url == "https://wowhub.app", (
            f"Default de public_base_url debe ser 'https://wowhub.app', "
            f"es {s.public_base_url!r}"
        )
        # Y NO debe ser el dominio backend
        assert "railway.app" not in s.public_base_url, (
            f"public_base_url no debe apuntar al backend de Railway: {s.public_base_url!r}"
        )

    def test_fallback_hint_no_naked_path_example(self):
        """El hint de la tool (con base_url OK) NO debe contener el ejemplo
        literal de un path desnudo que pueda confundir al LLM en few-shot.

        El hint reformulado (v1.9.1-r2) menciona 'paths desnudos' como
        prohibición, pero NO como ejemplo de path a evitar (eso era el bug
        que hacía que el LLM respondiera con el path desnudo).
        """
        from app.services.ai_tools import AIToolContext, tool_get_tenant_dashboard_urls

        class _C:
            user_id = "u"
            tenant_id = "t"
            access_token = "x"
            base_url = "https://wowhub.app"

        import asyncio
        out = asyncio.run(tool_get_tenant_dashboard_urls(_C()))
        hint = out.get("hint", "").lower()
        # Debe advertir contra paths desnudos
        assert "paths desnudos" in hint or "nunca respondas" in hint, (
            f"Hint debe advertir contra paths desnudos: {out['hint']!r}"
        )
        # Pero NO debe tener un ejemplo literal como `/dashboard/products` entre backticks
        # (porque el few-shot del LLM puede interpretar el ejemplo como OK)
        assert "/dashboard/products" not in hint, (
            f"Hint NO debe contener el ejemplo literal /dashboard/products "
            f"(puede confundir al LLM en few-shot): {out['hint']!r}"
        )
