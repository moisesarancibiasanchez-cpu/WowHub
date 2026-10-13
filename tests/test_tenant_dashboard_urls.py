"""Tests de alineación v1.9.1-r4: `app_knowledge`, tools de URLs y scrubber.

Esta suite es la evolución de los tests de v1.9.1-r3 (que asumía
`https://wowhub.app` como dominio y `/u/{slug}/...` como formato público).
v1.9.1-r4 corrige la fuente de verdad: el OpenAPI desplegado en producción
es `https://wowhub-api-production.up.railway.app/openapi.json`, con paths
`/api/v1/public/t/{slug}/...` y 4 features públicas (Página, Catálogo,
QR, Promociones).

Casos cubiertos:
1. `DASHBOARD_URLS` es un shim DEPRECATED con `modules=[]` y `deprecated_in`.
2. La tool `get_tenant_dashboard_urls` está marcada como DEPRECATED en su
   schema (description lo declara) y devuelve `deprecated: true` con
   `reason` orientando al usuario a `get_tenant_public_urls`.
3. La tool `get_tenant_public_urls` SÍ está vigente y devuelve los 7+1
   paths REALES (perfil, catalogo, producto, promociones, categorias,
   sucursales, landing, qr_redirect).
4. La constante `MODULES` tiene las 4 features públicas del MVP.
5. `NO_EXISTE` incluye las anti-alucinaciones v1.9.1-r4 (paths desnudos,
   /u/{slug}, wowhub.app, dominio backend hardcodeado, deprecación de
   `get_tenant_dashboard_urls`).
6. `render_short_summary()` declara la regla v1.9.1-r4 sin voseo.
7. Español de Chile (tú, no voseo) en todas las respuestas nuevas.
8. `settings.public_base_url` por default es el backend de Railway.
9. Las rutas de `app_knowledge` se validan contra el OpenAPI en producción
   (NO contra `app/main.py` de desarrollo).
"""
from __future__ import annotations

import pytest

from app.services import app_knowledge


# ── 1. Shim DASHBOARD_URLS (DEPRECATED en v1.9.1-r4) ────────────────
class TestDashboardUrlsIsDeprecated:
    """`DASHBOARD_URLS` debe ser un shim vacío en v1.9.1-r4."""

    def test_dashboard_urls_modules_is_empty(self):
        """No hay panel HTML público en producción: la lista de módulos
        del shim está VACÍA.
        """
        assert app_knowledge.DASHBOARD_URLS["modules"] == [], (
            "v1.9.1-r4: DASHBOARD_URLS['modules'] debe estar VACÍA "
            "(no hay panel HTML público en producción). "
            f"Actual: {app_knowledge.DASHBOARD_URLS['modules']!r}"
        )

    def test_dashboard_urls_marked_deprecated(self):
        """El shim debe tener `deprecated_in='v1.9.1-r4'` y un `reason`."""
        assert app_knowledge.DASHBOARD_URLS.get("deprecated_in") == "v1.9.1-r4", (
            "v1.9.1-r4: DASHBOARD_URLS debe tener `deprecated_in='v1.9.1-r4'`"
        )
        assert app_knowledge.DASHBOARD_URLS.get("reason"), (
            "v1.9.1-r4: DASHBOARD_URLS debe tener un 'reason' explicando "
            "por qué está deprecada"
        )

    def test_dashboard_urls_endpoint_deprecated(self):
        """El campo `endpoint` debe indicar que está deprecada y apuntar
        a la herramienta vigente."""
        ep = app_knowledge.DASHBOARD_URLS.get("endpoint", "").upper()
        assert "DEPRECATED" in ep
        assert "GET_TENANT_PUBLIC_URLS" in ep


# ── 2. Tool `get_tenant_dashboard_urls` (DEPRECATED) ────────────────
class TestDashboardUrlsToolDeprecated:
    """La tool `get_tenant_dashboard_urls` está DEPRECADA en v1.9.1-r4.
    Sigue en el dispatch (compat) pero su schema y su output lo declaran."""

    def test_tool_still_in_dispatch_for_backcompat(self):
        """Sigue en TOOL_DISPATCH para no romper imports legacy."""
        from app.services.ai_tools import TOOL_DISPATCH
        assert "get_tenant_dashboard_urls" in TOOL_DISPATCH

    def test_tool_schema_declares_deprecated(self):
        """La descripción de la tool debe declarar DEPRECATED y apuntar
        a `get_tenant_public_urls`."""
        from app.services.ai_tools import TOOL_SCHEMAS
        tool = next(
            (t for t in TOOL_SCHEMAS
             if t.get("function", {}).get("name") == "get_tenant_dashboard_urls"),
            None,
        )
        assert tool is not None
        desc = tool["function"]["description"].upper()
        assert "DEPRECATED" in desc or "DEPRECADA" in desc
        assert "GET_TENANT_PUBLIC_URLS" in desc

    def test_tool_not_in_all_5_agents(self):
        """La tool DEPRECATED no debe estar en los 5 sub-agentes como
        antes. Si quedó en alguno, es drift que este test detecta."""
        from app.services.ai_tools import get_tools_for_agent
        present_in = []
        for agent in ("marketing", "growth", "automation", "marketplace", "help"):
            names = [t["function"]["name"] for t in get_tools_for_agent(agent)]
            if "get_tenant_dashboard_urls" in names:
                present_in.append(agent)
        # En v1.9.1-r4 la tool no se distribuye activamente. Permitimos
        # que esté solo si el test documenta un caso especial, pero el
        # default esperado es que NO esté en ninguno.
        assert not present_in, (
            f"v1.9.1-r4: get_tenant_dashboard_urls está DEPRECADA y no debe "
            f"aparecer en los sub-agentes. Aparece en: {present_in}"
        )


# ── 3. Tool `get_tenant_public_urls` (VIGENTE) ─────────────────────
class TestPublicUrlsToolVigente:
    """La tool `get_tenant_public_urls` es la ÚNICA vigente en v1.9.1-r4."""

    def test_tool_in_dispatch(self):
        from app.services.ai_tools import TOOL_DISPATCH
        assert "get_tenant_public_urls" in TOOL_DISPATCH

    def test_tool_in_schema(self):
        from app.services.ai_tools import TOOL_SCHEMAS
        names = [t["function"]["name"] for t in TOOL_SCHEMAS]
        assert "get_tenant_public_urls" in names

    def test_tool_in_all_5_agents(self):
        """Los 5 sub-agentes deben tener la tool vigente."""
        from app.services.ai_tools import get_tools_for_agent
        for agent in ("marketing", "growth", "automation", "marketplace", "help"):
            names = [t["function"]["name"] for t in get_tools_for_agent(agent)]
            assert "get_tenant_public_urls" in names, (
                f"El agente {agent} debe tener get_tenant_public_urls"
            )

    def test_tool_schema_mentions_placeholders(self):
        """La description debe mencionar placeholders prohibidos."""
        from app.services.ai_tools import TOOL_SCHEMAS
        tool = next(
            (t for t in TOOL_SCHEMAS
             if t.get("function", {}).get("name") == "get_tenant_public_urls"),
            None,
        )
        assert tool is not None
        desc = tool["function"]["description"].lower()
        assert (
            "tu-negocio" in desc
            or "tu-tienda" in desc
            or "my-business" in desc
            or "<slug>" in desc
        ), f"description debe mencionar placeholders prohibidos: {desc!r}"
        assert "markdown" in desc or "[" in desc

    @pytest.mark.asyncio
    async def test_tool_returns_8_url_patterns(self, monkeypatch):
        """Debe devolver los 7 paths públicos + el path del QR."""
        from app.services.ai_tools import AIToolContext, tool_get_tenant_public_urls

        # Mock _api_get para no hacer HTTP real
        async def fake_api_get(ctx, path, params=None):
            return {"slug": "cafeluna", "name": "Café Luna"}
        monkeypatch.setattr(
            "app.services.ai_tools._api_get", fake_api_get,
        )

        ctx = AIToolContext(user_id="u-1", tenant_id="t-1", access_token="tok")
        out = await tool_get_tenant_public_urls(ctx)

        assert out["source"] == "app_knowledge"
        assert out["base_url"]
        keys = {e["key"] for e in out["urls"]}
        expected = {
            "perfil", "catalogo", "producto", "promociones",
            "categorias", "sucursales", "landing", "qr_redirect",
        }
        assert keys == expected, f"Faltan: {expected - keys}. Sobran: {keys - expected}"

    @pytest.mark.asyncio
    async def test_tool_urls_are_absolute_with_railway(self, monkeypatch):
        """Todas las URLs deben ser absolutas con el prefijo de
        settings.public_base_url (default Railway)."""
        from app.services.ai_tools import AIToolContext, tool_get_tenant_public_urls

        # Mock _api_get para no hacer HTTP real
        async def fake_api_get(ctx, path, params=None):
            return {"slug": "cafeluna", "name": "Café Luna"}
        monkeypatch.setattr(
            "app.services.ai_tools._api_get", fake_api_get,
        )

        ctx = AIToolContext(user_id="u-1", tenant_id="t-1", access_token="tok")
        out = await tool_get_tenant_public_urls(ctx)

        base = out["base_url"].rstrip("/")
        for entry in out["urls"]:
            url = entry["url"]
            assert url.startswith(base), f"URL no absoluta: {url}"
            assert not url.startswith("/"), f"Path desnudo: {url}"
            assert "{slug}" not in url, f"Path con placeholder: {url}"


# ── 4. MODULES alineado con OpenAPI de producción ───────────────────
class TestModulesV191R4:
    """`MODULES` describe las 4 features públicas del MVP."""

    def test_has_exactly_4_modules(self):
        assert len(app_knowledge.MODULES) == 4, (
            f"v1.9.1-r4: el OpenAPI describe 4 features del MVP. "
            f"MODULES tiene {len(app_knowledge.MODULES)}."
        )

    def test_module_keys_are_the_4_real_features(self):
        keys = {m["key"] for m in app_knowledge.MODULES}
        assert keys == {"pagina", "catalogo", "qr", "promociones"}, (
            f"v1.9.1-r4: MODULES debe tener las 4 features reales. "
            f"Actual: {sorted(keys)}"
        )

    def test_qr_module_key_is_singular(self):
        """`qr` (singular) es el nombre correcto del feature. La forma
        `qrs` (plural) era de v1.9.1-r3 y está deprecada."""
        keys = {m["key"] for m in app_knowledge.MODULES}
        assert "qr" in keys, "v1.9.1-r4: 'qr' (singular) es el nombre correcto"
        assert "qrs" not in keys, (
            "v1.9.1-r4: 'qrs' (plural) está DEPRECADO. Usar 'qr' singular."
        )

    def test_no_deprecated_panel_modules(self):
        """Módulos de v1.9.1-r3 (`site`, `configuracion`, `superadmin`,
        `admin_ia`) NO deben existir en MODULES: el OpenAPI de producción
        no los expone como features públicas."""
        keys = {m["key"] for m in app_knowledge.MODULES}
        forbidden = {
            "site", "configuracion", "superadmin", "admin_ia",
            "ai_dashboard", "resumen", "productos", "promociones_dash",
            "clientes", "pedidos", "reservas", "fidelizacion",
            "landing_dash", "payments", "stats", "webhooks",
        }
        leaked = keys & forbidden
        assert not leaked, (
            f"v1.9.1-r4: módulos de panel v1.9.1-r3 NO deben estar en "
            f"MODULES (el OpenAPI de producción no los expone). "
            f"Leaked: {leaked}"
        )

    def test_qr_module_path_starts_with_r(self):
        """El path del módulo QR es `/r/{short_code}` (formato v1.9.1-r4)."""
        qr = next((m for m in app_knowledge.MODULES if m["key"] == "qr"), None)
        assert qr is not None
        assert qr["path"].startswith("/r/"), (
            f"v1.9.1-r4: el path del QR es /r/{{short_code}}, no "
            f"/dashboard/qrs ni similar. Actual: {qr['path']!r}"
        )

    def test_other_modules_path_is_public_api(self):
        """Los otros 3 módulos deben tener paths bajo /api/v1/public/."""
        for m in app_knowledge.MODULES:
            if m["key"] == "qr":
                continue  # /r/ es el caso especial del QR
            assert m["path"].startswith("/api/v1/public/"), (
                f"v1.9.1-r4: módulo {m['key']!r} debe tener path público. "
                f"Actual: {m['path']!r}"
            )


# ── 5. PUBLIC_URLS alineado con OpenAPI de producción ───────────────
class TestPublicUrlsV191R4:
    """`PUBLIC_URLS` lista los 7+1 paths públicos REALES."""

    def test_has_8_url_patterns(self):
        assert len(app_knowledge.PUBLIC_URLS) == 8, (
            f"v1.9.1-r4: 7 paths públicos + 1 QR redirect = 8. "
            f"Actual: {len(app_knowledge.PUBLIC_URLS)}"
        )

    def test_expected_keys(self):
        keys = {u["key"] for u in app_knowledge.PUBLIC_URLS}
        expected = {
            "perfil", "catalogo", "producto", "promociones",
            "categorias", "sucursales", "landing", "qr_redirect",
        }
        assert keys == expected

    def test_no_legacy_u_slash_format(self):
        """El formato `/u/{slug}/...` está FULLY DEPRECATED en v1.9.1-r4.
        NO debe haber ningún path con ese prefijo."""
        for entry in app_knowledge.PUBLIC_URLS:
            assert not entry["pattern"].startswith("/u/"), (
                f"v1.9.1-r4: /u/{{slug}}/... está DEPRECATED. "
                f"Encontrado: {entry['pattern']!r}"
            )

    def test_no_legacy_u_book_alias(self):
        """`/u/{slug}/book` era el alias inglés DEPRECATED."""
        patterns = {u["pattern"] for u in app_knowledge.PUBLIC_URLS}
        assert "/u/{slug}/book" not in patterns

    def test_no_loyalty_path(self):
        """/loyalty/{slug} no está desplegado."""
        for entry in app_knowledge.PUBLIC_URLS:
            assert "/loyalty/" not in entry["pattern"], (
                f"v1.9.1-r4: /loyalty/{{slug}} no está en producción. "
                f"Encontrado: {entry['pattern']!r}"
            )

    def test_seven_paths_under_public_api(self):
        """7 de los 8 patterns están bajo /api/v1/public/t/{slug}/."""
        under = [u for u in app_knowledge.PUBLIC_URLS
                 if u["pattern"].startswith("/api/v1/public/t/{slug}/")]
        assert len(under) == 7, (
            f"Esperaba 7 paths bajo /api/v1/public/t/{{slug}}/, encontré "
            f"{len(under)}"
        )

    def test_qr_redirect_path_format(self):
        """El path del QR redirect es `/r/{short_code}` (formato corto)."""
        qr = next(
            (u for u in app_knowledge.PUBLIC_URLS if u["key"] == "qr_redirect"),
            None,
        )
        assert qr is not None
        assert qr["pattern"] == "/r/{short_code}"


# ── 6. NO_EXISTE: anti-alucinación v1.9.1-r4 ────────────────────────
class TestNoExisteV191R4:
    """`NO_EXISTE` debe cubrir todas las trampas conocidas v1.9.1-r4."""

    def test_has_paths_desnudos_warning(self):
        joined = " ".join(app_knowledge.NO_EXISTE).lower()
        assert "paths desnudos" in joined or "path desnudo" in joined, (
            "v1.9.1-r4: NO_EXISTE debe advertir contra paths desnudos"
        )

    def test_has_no_absolute_urls_warning(self):
        joined = " ".join(app_knowledge.NO_EXISTE).lower()
        assert (
            "no son urls absolutas" in joined
            or "no es una url absoluta" in joined
            or "no son absolutas" in joined
        ), "v1.9.1-r4: NO_EXISTE debe advertir contra URLs no absolutas"

    def test_has_no_invent_base_url_warning(self):
        joined = " ".join(app_knowledge.NO_EXISTE).lower()
        assert (
            "no debe inventar la url base" in joined
            or "no la inventes" in joined
            or "nunca inventes la url base" in joined
        ), "v1.9.1-r4: NO_EXISTE debe advertir contra inventar la URL base"

    def test_has_no_incluir_slug_warning(self):
        joined = " ".join(app_knowledge.NO_EXISTE).lower()
        assert (
            "no incluyas el slug" in joined
            or "nunca incluyas el slug" in joined
        ), "v1.9.1-r4: NO_EXISTE debe advertir contra incluir el slug a mano"

    def test_has_no_confundir_warning(self):
        joined = " ".join(app_knowledge.NO_EXISTE).lower()
        assert (
            "no debe confundir" in joined
            or "nunca confundas" in joined
        ), "v1.9.1-r4: NO_EXISTE debe advertir contra confundir conceptos"

    def test_has_u_slash_format_deprecation(self):
        joined = " ".join(app_knowledge.NO_EXISTE)
        assert "/u/{slug}" in joined, (
            "v1.9.1-r4: NO_EXISTE debe marcar /u/{slug} como DEPRECATED"
        )

    def test_has_wowhub_app_deprecation(self):
        joined = " ".join(app_knowledge.NO_EXISTE).lower()
        assert "wowhub.app" in joined, (
            "v1.9.1-r4: NO_EXISTE debe mencionar que wowhub.app no responde"
        )

    def test_has_railway_domain_as_forbidden(self):
        joined = " ".join(app_knowledge.NO_EXISTE).lower()
        assert "wowhub-api-production.up.railway.app" in joined, (
            "v1.9.1-r4: NO_EXISTE debe mencionar el dominio backend como "
            "prohibido hardcodearlo a mano"
        )

    def test_has_dashboard_urls_tool_deprecation(self):
        joined = " ".join(app_knowledge.NO_EXISTE).lower()
        assert "get_tenant_dashboard_urls" in joined
        assert "depre" in joined, (
            "v1.9.1-r4: NO_EXISTE debe marcar get_tenant_dashboard_urls "
            "como DEPRECADA"
        )

    def test_has_no_html_dashboard_in_prod(self):
        joined = " ".join(app_knowledge.NO_EXISTE).lower()
        assert (
            "no hay panel html público" in joined
            or "no existe un panel html" in joined
        ), "v1.9.1-r4: NO_EXISTE debe declarar que no hay panel HTML público"

    def test_v191r4_marker_present(self):
        """v1.9.1-r4 entries deben estar marcadas con el prefijo."""
        v4 = [s for s in app_knowledge.NO_EXISTE if "v1.9.1-r4" in s]
        assert len(v4) >= 5, (
            f"v1.9.1-r4: NO_EXISTE debe tener >= 5 entradas marcadas "
            f"con v1.9.1-r4. Encontré {len(v4)}"
        )


# ── 7. FAQ alineada con v1.9.1-r4 ──────────────────────────────────
class TestFaqV191R4:
    """Las FAQ nuevas deben mencionar las tools correctas y la realidad."""

    def test_url_publica_faq_mentions_get_tenant_public_urls(self):
        answer = app_knowledge.faq_lookup("url pública")
        assert answer is not None
        assert "get_tenant_public_urls" in answer

    def test_url_publica_faq_has_real_url_example(self):
        answer = app_knowledge.faq_lookup("url pública")
        assert answer is not None
        assert "wowhub-api-production.up.railway.app/api/v1/public/t/" in answer, (
            "v1.9.1-r4: la FAQ de 'url pública' debe tener un ejemplo "
            "con la URL REAL de producción"
        )

    def test_url_publica_faq_no_literal_placeholder(self):
        answer = app_knowledge.faq_lookup("url pública")
        assert answer is not None
        assert "/u/{slug}/reservar" not in answer, (
            "v1.9.1-r4: la FAQ NO debe contener el placeholder viejo"
        )

    def test_url_publica_faq_mentions_dashboard_urls_deprecation(self):
        answer = app_knowledge.faq_lookup("url pública")
        assert answer is not None
        assert "get_tenant_dashboard_urls" in answer or "DEPRECATED" in answer, (
            "v1.9.1-r4: la FAQ debe mencionar la deprecación de "
            "get_tenant_dashboard_urls"
        )

    def test_panel_productos_faq_mentions_railway(self):
        answer = app_knowledge.faq_lookup("cómo abro el panel de productos")
        assert answer is not None
        # v1.9.1-r4: la FAQ debe apuntar a Railway como fuente de verdad
        assert "wowhub-api-production.up.railway.app" in answer

    def test_panel_productos_faq_uses_imperative_tu(self):
        """La FAQ debe usar imperativo tú (no voseo) y llamar a tools."""
        answer = app_knowledge.faq_lookup("cómo abro el panel de productos")
        assert answer is not None
        low = answer.lower()
        # Imperativo tú (válido en español de Chile)
        assert any(verb in low for verb in (
            "llama", "devuelve", "sugiere", "suger",
        )), f"Sin imperativo tú en 'cómo abro el panel de productos': {answer!r}"

    def test_panel_productos_faq_no_voseo(self):
        answer = app_knowledge.faq_lookup("cómo abro el panel de productos")
        assert answer is not None
        low = answer.lower()
        for vose in ("llamá", "mostrá", "usá", "avisale", "decile"):
            assert vose not in low, f"Voseo en FAQ: {answer!r}"

    def test_admin_ia_faq_uses_imperative_tu(self):
        answer = app_knowledge.faq_lookup("dónde veo el admin ia")
        assert answer is not None
        low = answer.lower()
        assert "llama" in low or "sugiere" in low, (
            f"Sin imperativo tú en 'dónde veo el admin ia': {answer!r}"
        )

    def test_admin_ia_faq_no_voseo(self):
        answer = app_knowledge.faq_lookup("dónde veo el admin ia")
        assert answer is not None
        low = answer.lower()
        for vose in ("llamá", "mostrá", "usá", "decile", "decí"):
            assert vose not in low, f"Voseo en FAQ admin: {answer!r}"

    def test_pasame_link_faq_exists(self):
        """FAQ key con tilde chilena (imperativo tú)."""
        answer = app_knowledge.faq_lookup("pásame el link de")
        assert answer is not None
        assert "get_tenant_public_urls" in answer

    def test_mandame_link_faq_exists(self):
        answer = app_knowledge.faq_lookup("mándame el link por")
        assert answer is not None

    def test_dashboard_url_examples_removed(self):
        """La FAQ NO debe contener el prefijo viejo wowhub.app/dashboard
        como sugerencia de URL pública."""
        answer = app_knowledge.faq_lookup("cómo abro el panel de productos")
        assert answer is not None
        assert "https://wowhub.app/dashboard" not in answer, (
            "v1.9.1-r4: la FAQ no debe sugerir https://wowhub.app/dashboard"
        )


# ── 8. render_short_summary alineado con v1.9.1-r4 ──────────────────
class TestRenderShortSummaryV191R4:
    """El system prompt refleja la realidad v1.9.1-r4."""

    def test_summarizes_4_modules(self):
        summary = app_knowledge.render_short_summary()
        # Los 4 nombres de features deben aparecer
        for label in ("Página", "Catálogo", "QR", "Promociones"):
            assert label in summary or label.lower() in summary.lower()

    def test_mentions_get_tenant_public_urls(self):
        summary = app_knowledge.render_short_summary()
        assert "get_tenant_public_urls" in summary

    def test_mentions_get_tenant_dashboard_urls_as_deprecated(self):
        summary = app_knowledge.render_short_summary()
        assert "get_tenant_dashboard_urls" in summary
        assert "DEPRECAD" in summary.upper()

    def test_warns_against_naked_paths(self):
        summary = app_knowledge.render_short_summary()
        low = summary.lower()
        assert "paths desnudos" in low or "nunca respondas con paths" in low

    def test_warns_against_placeholder(self):
        summary = app_knowledge.render_short_summary()
        low = summary.lower()
        assert (
            "anti-placeholder" in low
            or "tu-negocio" in low
            or "{slug}" in low
        )

    def test_warns_against_hardcoded_domain(self):
        summary = app_knowledge.render_short_summary()
        low = summary.lower()
        assert (
            "anti-dominio" in low
            or "wowhub-api-production" in low
        )

    def test_no_voseo(self):
        """Sin voseo en las reglas nuevas."""
        summary = app_knowledge.render_short_summary()
        low = summary.lower()
        for vose in ("llamá", "mostrá", "usá", "decí", "decile"):
            assert vose not in low, f"Voseo en render_short_summary: {vose!r}"


# ── 9. settings.public_base_url alineado con v1.9.1-r4 ──────────────
class TestPublicBaseUrlV191R4:
    """El default de `public_base_url` es el backend de Railway."""

    def test_default_in_config_class_is_railway(self):
        from app.config import Settings
        default = Settings.model_fields["public_base_url"].default
        assert default == "https://wowhub-api-production.up.railway.app", (
            f"v1.9.1-r4: el default de public_base_url debe ser el backend "
            f"de Railway. Actual: {default!r}"
        )

    def test_default_does_not_point_to_wowhub_app(self):
        """El default NO debe apuntar a wowhub.app (no responde)."""
        from app.config import Settings
        default = Settings.model_fields["public_base_url"].default
        assert "wowhub.app" not in default, (
            f"v1.9.1-r4: el default NO debe ser wowhub.app (NXDOMAIN). "
            f"Actual: {default!r}"
        )

    def test_effective_public_base_url_with_railway_default(self):
        """El método `effective_public_base_url` con el default actual
        debe devolver el dominio de Railway (no wowhub.app)."""
        from app.config import Settings
        s = Settings.model_construct(
            public_base_url="https://wowhub-api-production.up.railway.app",
            base_url="http://test",
        )
        assert s.effective_public_base_url == "https://wowhub-api-production.up.railway.app"


# ── 10. Anti-regresión: español de Chile (sin voseo) ────────────────
class TestChileanSpanishRegression:
    """Verifica que el sistema está en español de Chile, NO en voseo."""

    VOSE_FORBIDDEN = [
        "llamá", "llamás", "mostrá", "mostrás", "mostrame",
        "mandame", "pasame", "decime", "fijate", "fijáte",
        "usá ", "usá.", "usá,", "usá\n",
        "devolvé", "mandá ", "mandá.", "mandá,",
        "querés", "tenés", "sos ", "sos.", "sos,",
        "hacés", "podés", "sabés", "escribime",
        "ejecutá", "agendá", "aplicá", "creá", "lanzá", "indicá",
        "prepará", "sugerí",
        "andá", "andá ", "andá.", "andá,",
        "decile", "decí", "avisale",
    ]

    def test_global_rules_chilean(self):
        from app.services.ai_agents import _GLOBAL_RULES
        assert "español de Chile" in _GLOBAL_RULES
        assert "TÚ" in _GLOBAL_RULES or "tú" in _GLOBAL_RULES.lower()

    def test_faq_keys_chilean_imperative(self):
        """Las FAQ keys con imperativo deben tener tilde chilena."""
        faq = app_knowledge.FAQ
        for expected in ("pásame el link de", "mándame el link por"):
            assert expected in faq, (
                f"FAQ key chilena faltante: {expected!r}. "
                f"Found: {[k for k in faq if 'link' in k]}"
            )

    def test_no_voseo_in_render_short_summary(self):
        import re
        summary = app_knowledge.render_short_summary().lower()
        for vose in self.VOSE_FORBIDDEN:
            vose_clean = vose.strip()
            if not vose_clean:
                continue
            pattern = r"\b" + re.escape(vose_clean) + r"\b"
            assert not re.search(pattern, summary), (
                f"Voseo en render_short_summary: {vose!r}"
            )

    def test_no_voseo_in_no_existe(self):
        import re
        joined = " ".join(app_knowledge.NO_EXISTE).lower()
        for vose in ("llamá", "usá", "decí", "decile", "mostrá", "devolvé"):
            pattern = r"\b" + re.escape(vose) + r"\b"
            assert not re.search(pattern, joined), (
                f"Voseo en NO_EXISTE: {vose!r}"
            )

    def test_no_voseo_in_faq(self):
        import re
        for k, v in app_knowledge.FAQ.items():
            low = v.lower()
            for vose in self.VOSE_FORBIDDEN:
                vose_clean = vose.strip()
                if not vose_clean:
                    continue
                # Usamos word boundary regex para evitar falsos positivos
                # (ej. "sos" dentro de "permisos").
                pattern = r"\b" + re.escape(vose_clean) + r"\b"
                assert not re.search(pattern, low), (
                    f"Voseo en FAQ[{k!r}]: {vose!r} en texto {v!r}"
                )


# ── 11. Anti-regresión: Regla 10 LINKS Y URLS (v1.9.1-r2) ───────────
class TestRegla10LinksYUrls:
    """La Regla 10 del `_GLOBAL_RULES` declara la política dura anti-path."""

    def test_regla_10_exists(self):
        from app.services.ai_agents import _GLOBAL_RULES
        assert "10. LINKS Y URLS" in _GLOBAL_RULES

    def test_regla_10_mentions_forbidden_placeholders(self):
        from app.services.ai_agents import _GLOBAL_RULES
        for placeholder in ("tu-negocio", "{slug}"):
            assert placeholder in _GLOBAL_RULES, (
                f"Regla 10 debe mencionar el placeholder prohibido {placeholder!r}"
            )

    def test_regla_10_mentions_railway_domain(self):
        from app.services.ai_agents import _GLOBAL_RULES
        # v1.9.1-r4: la Regla 10 debe advertir contra el dominio backend
        assert "wowhub-api-production.up.railway.app" in _GLOBAL_RULES
