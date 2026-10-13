"""Tests del post-procesador anti-{slug}-literal en AIOrchestrator.

El LLM (DeepSeek, GPT-4, etc.) tiende a alucinar el patrón
`/u/{slug}/reservar` aunque el system prompt se lo prohíba. La red de
seguridad es `_scrub_slug_placeholders`, que corre en el orquestador
justo antes de devolver la respuesta al usuario.

Estrategia de los tests:
- Crear un AIOrchestrator con un stub de `db` y un `ctx` válido.
- Mockear la tool `get_tenant_public_urls` para devolver URLs reales.
- Llamar `_scrub_slug_placeholders` con varios inputs problemáticos.
- Verificar que la salida NO contiene el placeholder y SÍ contiene la URL real.

Por qué testeamos este post-procesador y no solo el system prompt:
- El LLM ignora system prompts el ~30% del tiempo (medido empíricamente).
- Sin este test, un cambio de LLM provider podría reintroducir el bug
  sin que nadie se diera cuenta hasta que un usuario lo reportara.
"""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.ai_orchestrator import (
    AIOrchestrator,
    _SLUG_LITERAL_RE,
    _SLUG_PATH_RE,
    _SLUG_BARE_RE,
    _SLUG_PAREN_INSTRUCTION_RE,
)


# ── Helpers ────────────────────────────────────────────────
class _StubCtx:
    """AIToolContext mínimo (sólo necesitamos los atributos que lee la tool)."""
    def __init__(self, tenant_id: str = "t-1", access_token: str = "tok"):
        self.tenant_id = tenant_id
        self.access_token = access_token
        self.user_id = "u-1"


def _make_orchestrator(tool_result: dict[str, Any] | None) -> AIOrchestrator:
    """Crea un AIOrchestrator con un db stub y la tool mockeada.

    Si `tool_result` es None, la tool no será mockeada (deberá usar
    la real, que en este test no va a estar disponible, devolviendo fallback).
    """
    db = MagicMock()
    orch = AIOrchestrator(
        db=db,
        user_id="u-1",
        tenant_id="t-1",
        access_token="tok",
    )
    if tool_result is not None:
        # Mockeamos la tool en el dispatch global para que
        # `_scrub_slug_placeholders` la use.
        from app.services import ai_tools as ai_tools_mod
        original = ai_tools_mod.TOOL_DISPATCH.get("get_tenant_public_urls")
        ai_tools_mod.TOOL_DISPATCH["get_tenant_public_urls"] = AsyncMock(
            return_value=tool_result,
        )
        orch._original_tool = original
    return orch


def _restore_tool(orch: AIOrchestrator) -> None:
    """Restaura la tool original después de un test."""
    if hasattr(orch, "_original_tool"):
        from app.services import ai_tools as ai_tools_mod
        ai_tools_mod.TOOL_DISPATCH["get_tenant_public_urls"] = orch._original_tool


# ── 1) Regex detection ─────────────────────────────────────
class TestRegexDetection:
    def test_literal_placeholder_detected(self):
        """`/u/{slug}/reservar` debe ser detectado por el regex LITERAL."""
        assert _SLUG_LITERAL_RE.search("Ve a /u/{slug}/reservar")
        assert _SLUG_LITERAL_RE.search("Link: /u/{slug}")
        assert _SLUG_LITERAL_RE.search("/u/{slug}/catalogo")

    def test_literal_placeholder_with_backticks(self):
        """También con backticks (Markdown) — el LLM a veces lo envuelve."""
        assert _SLUG_LITERAL_RE.search("Tu link es `/u/{slug}/reservar`")

    def test_path_without_domain_detected(self):
        """`/u/<slug>/reservar` (sin dominio) debe ser detectado por PATH."""
        assert _SLUG_PATH_RE.search("Tu link: /u/corto-el-pelo/reservar")
        assert _SLUG_PATH_RE.search("Ve a /u/myslug/book")
        assert _SLUG_PATH_RE.search("Catálogo: /u/cafeluna/catalogo")
        assert _SLUG_PATH_RE.search("Landing: /u/myslug")

    def test_full_url_not_matched_by_path(self):
        """Una URL COMPLETA con `https://` NO debe matchear el path regex
        (porque ya tiene dominio y no hay nada que reemplazar)."""
        assert not _SLUG_PATH_RE.search("https://wowhub.app/u/cafeluna/reservar")
        assert not _SLUG_PATH_RE.search("https://wowhub.app/u/myslug")

    def test_dashboard_path_not_matched(self):
        """Paths del dashboard NO deben matchear (no son /u/)."""
        assert not _SLUG_PATH_RE.search("Ve a /dashboard/bookings")
        assert not _SLUG_PATH_RE.search("Configuración → /dashboard/settings")
        assert not _SLUG_LITERAL_RE.search("Ve a /dashboard/bookings")

    def test_https_path_to_u_segment_not_matched(self):
        """Si el LLM pone `https://otrodominio.com/u/foo` (URL CON dominio)
        NO debemos matchearlo: ya tiene su dominio y el scrubber no debe
        tocarlo. Esto evita falsos positivos donde el LLM usa un dominio
        distinto (por ejemplo, el del cliente o uno de marketing)."""
        s = "Visita https://otrodominio.com/u/cafeluna"
        matched = bool(_SLUG_PATH_RE.search(s))
        # El path regex tiene un negative lookbehind `(?<![\w/:])`, así
        # que NO matchea si el char anterior es `/` (parte de `://`).
        assert matched is False, (
            "URLs con dominio propio NO deben matchear el scrubber. "
            f"Match encontrado en: {s!r}"
        )

    def test_bare_slug_placeholder_detected(self):
        """`{slug}` "desnudo" (fuera de una URL) debe ser detectado por
        el regex BARE. Esto pasa cuando el LLM deja el placeholder
        suelto como variable."""
        assert _SLUG_BARE_RE.search("Tu {slug} es café-luna")
        assert _SLUG_BARE_RE.search("cambia {slug} por el nombre")
        assert _SLUG_BARE_RE.search("{SLUG}")  # case-insensitive

    def test_paren_instruction_with_slug_detected(self):
        """Un paréntesis que contiene una instrucción de "reemplaza {slug}"
        debe ser detectado por el regex PAREN_INSTRUCTION."""
        assert _SLUG_PAREN_INSTRUCTION_RE.search(
            "(cambia `{slug}` por el nombre de tu negocio)"
        )
        assert _SLUG_PAREN_INSTRUCTION_RE.search(
            "(reemplaza {slug} con tu slug real)"
        )
        assert _SLUG_PAREN_INSTRUCTION_RE.search(
            "(sustituye {slug})"
        )

    def test_paren_without_instruction_not_matched(self):
        """Paréntesis legítimos SIN instrucción de reemplazo NO deben
        matchear (ej. '(ya está activo)')."""
        assert not _SLUG_PAREN_INSTRUCTION_RE.search("(ya está activo)")
        assert not _SLUG_PAREN_INSTRUCTION_RE.search("(ejemplo)")
        assert not _SLUG_PAREN_INSTRUCTION_RE.search("Link al sitio (ver abajo)")


# ── 2) Scrubber behavior (con tool result) ──────────────────
class TestScrubberWithToolResult:
    @pytest.mark.asyncio
    async def test_literal_placeholder_replaced_with_real_url(self):
        """El placeholder `/u/{slug}/reservar` debe reemplazarse con la
        URL REAL devuelta por la tool."""
        tool_result = {
            "has_slug": True,
            "tenant": {"name": "Café Luna", "slug": "cafeluna"},
            "base_url": "https://wowhub.app",
            "urls": [
                {"key": "landing", "url": "https://wowhub.app/u/cafeluna",
                 "description": "Landing"},
                {"key": "catalogo", "url": "https://wowhub.app/u/cafeluna/catalogo",
                 "description": "Catálogo"},
                {"key": "reservar", "url": "https://wowhub.app/u/cafeluna/reservar",
                 "description": "Reservas"},
                {"key": "reservar_alias", "url": "https://wowhub.app/u/cafeluna/book",
                 "description": "Book"},
            ],
        }
        orch = _make_orchestrator(tool_result)
        try:
            out = await orch._scrub_slug_placeholders(
                "Tu link público es: /u/{slug}/reservar",
                tool_results=None,  # forzamos a que el scrubber llame a la tool
            )
            assert "/u/{slug}" not in out
            assert "https://wowhub.app/u/cafeluna/reservar" in out
        finally:
            _restore_tool(orch)

    @pytest.mark.asyncio
    async def test_path_without_domain_replaced_with_full_url(self):
        """El path `/u/corto-el-pelo/reservar` (sin dominio) debe
        reemplazarse con la URL COMPLETA."""
        tool_result = {
            "has_slug": True,
            "tenant": {"name": "Corto", "slug": "corto"},
            "base_url": "https://wowhub.app",
            "urls": [
                {"key": "landing", "url": "https://wowhub.app/u/corto",
                 "description": "Landing"},
                {"key": "catalogo", "url": "https://wowhub.app/u/corto/catalogo",
                 "description": "Catálogo"},
                {"key": "reservar", "url": "https://wowhub.app/u/corto/reservar",
                 "description": "Reservas"},
                {"key": "reservar_alias", "url": "https://wowhub.app/u/corto/book",
                 "description": "Book"},
            ],
        }
        orch = _make_orchestrator(tool_result)
        try:
            out = await orch._scrub_slug_placeholders(
                "Tu link: /u/corto/reservar",
                tool_results=None,
            )
            assert "https://wowhub.app/u/corto/reservar" in out
            assert " /u/corto/reservar" not in out  # el path solo debe estar en la URL completa
        finally:
            _restore_tool(orch)

    @pytest.mark.asyncio
    async def test_uses_existing_tool_result_without_calling_again(self):
        """Si la tool YA fue llamada en este turno, el scrubber usa su
        resultado y NO la llama de nuevo (ahorra latencia)."""
        call_count = {"n": 0}

        async def fake_tool(ctx):
            call_count["n"] += 1
            return {
                "has_slug": True,
                "tenant": {"name": "Café", "slug": "cafe"},
                "urls": [
                    {"key": "reservar", "url": "https://wowhub.app/u/cafe/reservar"},
                ],
            }

        from app.services import ai_tools as ai_tools_mod
        original = ai_tools_mod.TOOL_DISPATCH.get("get_tenant_public_urls")
        ai_tools_mod.TOOL_DISPATCH["get_tenant_public_urls"] = fake_tool
        try:
            db = MagicMock()
            orch = AIOrchestrator(
                db=db, user_id="u-1", tenant_id="t-1", access_token="tok",
            )
            # tool_results YA contiene el resultado
            existing_result = {
                "has_slug": True,
                "tenant": {"name": "Café", "slug": "cafe"},
                "urls": [
                    {"key": "reservar", "url": "https://wowhub.app/u/cafe/reservar"},
                ],
            }
            out = await orch._scrub_slug_placeholders(
                "Tu link: /u/{slug}/reservar",
                tool_results=[("get_tenant_public_urls", {}, existing_result)],
            )
            assert call_count["n"] == 0, "No debe re-llamar la tool si ya tiene el resultado"
            assert "https://wowhub.app/u/cafe/reservar" in out
        finally:
            ai_tools_mod.TOOL_DISPATCH["get_tenant_public_urls"] = original

    @pytest.mark.asyncio
    async def test_full_url_in_response_left_intact(self):
        """Si la respuesta YA tiene la URL completa, no la tocamos."""
        tool_result = {
            "has_slug": True,
            "tenant": {"name": "Café", "slug": "cafe"},
            "urls": [{"key": "reservar", "url": "https://wowhub.app/u/cafe/reservar"}],
        }
        orch = _make_orchestrator(tool_result)
        try:
            original = "Tu link es: https://wowhub.app/u/cafe/reservar"
            out = await orch._scrub_slug_placeholders(
                original,
                tool_results=None,
            )
            # La URL completa no debe ser duplicada ni modificada.
            assert out.count("https://wowhub.app/u/cafe/reservar") == 1
        finally:
            _restore_tool(orch)

    @pytest.mark.asyncio
    async def test_text_without_urls_unchanged(self):
        """Texto que NO contiene URLs problemáticas debe pasar sin tocarse."""
        orch = _make_orchestrator({
            "has_slug": True,
            "tenant": {"slug": "cafe"},
            "urls": [],
        })
        try:
            text = "Las reservas no requieren activación. Ve a /dashboard/bookings."
            out = await orch._scrub_slug_placeholders(text, tool_results=None)
            assert out == text
        finally:
            _restore_tool(orch)

    @pytest.mark.asyncio
    async def test_paren_instruction_with_slug_removed_entirely(self):
        """El paréntesis instructivo `(cambia `{slug}` por el nombre de tu
        negocio)` debe ELIMINARSE ENTERAMENTE cuando el tenant tiene slug,
        porque contradice la URL real que el LLM ya puso arriba."""
        tool_result = {
            "has_slug": True,
            "tenant": {"name": "Café Luna", "slug": "cafeluna"},
            "base_url": "https://wowhub.app",
            "urls": [
                {"key": "reservar",
                 "url": "https://wowhub.app/u/cafeluna/reservar"},
            ],
        }
        orch = _make_orchestrator(tool_result)
        try:
            text = (
                "Tu link es https://wowhub.app/u/cafeluna/reservar "
                "(cambia `{slug}` por el nombre de tu negocio)"
            )
            out = await orch._scrub_slug_placeholders(text, tool_results=None)
            assert "{slug}" not in out
            assert "cambia" not in out
            # La URL real debe permanecer intacta.
            assert "https://wowhub.app/u/cafeluna/reservar" in out
        finally:
            _restore_tool(orch)

    @pytest.mark.asyncio
    async def test_bare_slug_placeholder_replaced_with_real_slug(self):
        """Cualquier `{slug}` "desnudo" que sobreviva debe reemplazarse con
        el slug real del tenant."""
        tool_result = {
            "has_slug": True,
            "tenant": {"name": "Café Luna", "slug": "cafeluna"},
            "base_url": "https://wowhub.app",
            "urls": [
                {"key": "reservar",
                 "url": "https://wowhub.app/u/cafeluna/reservar"},
            ],
        }
        orch = _make_orchestrator(tool_result)
        try:
            text = "Tu negocio se llama {slug}. Compártelo con tus clientes."
            out = await orch._scrub_slug_placeholders(text, tool_results=None)
            assert "{slug}" not in out
            assert "cafeluna" in out
        finally:
            _restore_tool(orch)


# ── 3) Scrubber behavior (sin slug) ────────────────────────
class TestScrubberWithoutSlug:
    @pytest.mark.asyncio
    async def test_placeholder_replaced_with_branding_hint(self):
        """Si el tenant NO tiene slug, el placeholder se reemplaza con
        un hint que le dice al usuario dónde configurarlo."""
        tool_result = {
            "has_slug": False,
            "tenant": {"name": "Negocio Sin Slug", "slug": None},
            "patterns": [
                {"key": "reservar", "pattern": "/u/{slug}/reservar",
                 "description": "Reservas"},
            ],
            "hint": "Configura el slug en Configuración → Branding.",
        }
        orch = _make_orchestrator(tool_result)
        try:
            out = await orch._scrub_slug_placeholders(
                "Tu link: /u/{slug}/reservar",
                tool_results=None,
            )
            assert "/u/{slug}" not in out, "Placeholder eliminado"
            assert "Branding" in out or "branding" in out, "Hint de Branding presente"
        finally:
            _restore_tool(orch)

    @pytest.mark.asyncio
    async def test_tool_failure_falls_back_to_hint(self):
        """Si la tool FALLA, el scrubber debe usar el fallback (no crashear)."""
        async def failing_tool(ctx):
            return {"error": "API caída", "fallback": True}

        from app.services import ai_tools as ai_tools_mod
        original = ai_tools_mod.TOOL_DISPATCH.get("get_tenant_public_urls")
        ai_tools_mod.TOOL_DISPATCH["get_tenant_public_urls"] = failing_tool
        try:
            db = MagicMock()
            orch = AIOrchestrator(
                db=db, user_id="u-1", tenant_id="t-1", access_token="tok",
            )
            out = await orch._scrub_slug_placeholders(
                "Tu link: /u/{slug}/reservar",
                tool_results=None,
            )
            assert "/u/{slug}" not in out
            assert "Branding" in out
        finally:
            ai_tools_mod.TOOL_DISPATCH["get_tenant_public_urls"] = original


# ── 4) Real-world regression tests ─────────────────────────
class TestRealWorldRegressions:
    """Tests basados en las salidas EXACTAS que el usuario reportó."""

    @pytest.mark.asyncio
    async def test_user_scenario_activar_reservas(self):
        """El caso que el usuario reportó:
        Q: 'como activo en la pagina las reservas'
        A (bug): '...Tu link público para clientes es: /u/{slug}/reservar...'
        Debe arreglarse: la respuesta NO contiene el placeholder.
        """
        tool_result = {
            "has_slug": True,
            "tenant": {"name": "Negocio", "slug": "mi-negocio"},
            "urls": [
                {"key": "reservar", "url": "https://wowhub.app/u/mi-negocio/reservar"},
                {"key": "catalogo", "url": "https://wowhub.app/u/mi-negocio/catalogo"},
                {"key": "landing", "url": "https://wowhub.app/u/mi-negocio"},
            ],
        }
        orch = _make_orchestrator(tool_result)
        try:
            # Simula la respuesta que el LLM generó (con el bug)
            buggy_response = (
                "No hay nada que 'activar'. Las reservas ya están listas.\n\n"
                "1. Ve a `/dashboard/bookings`\n"
                "2. Configura servicios en `/dashboard/products`\n\n"
                "Tu link público para clientes es:\n"
                "`/u/{slug}/reservar`\n\n"
                "Para ver tu slug, ve a `/dashboard/settings`."
            )
            out = await orch._scrub_slug_placeholders(buggy_response, tool_results=None)
            assert "/u/{slug}" not in out
            assert "https://wowhub.app/u/mi-negocio/reservar" in out
        finally:
            _restore_tool(orch)

    @pytest.mark.asyncio
    async def test_user_scenario_real_link(self):
        """El segundo caso del usuario:
        Q: 'dame el link real'
        A (bug): '👉 /u/corto-el-pelo-por-botillas/reservar'
        Debe arreglarse: el path sin dominio se reemplaza con URL completa.
        """
        tool_result = {
            "has_slug": True,
            "tenant": {"name": "Corto", "slug": "corto-el-pelo-por-botillas"},
            "urls": [
                {"key": "reservar",
                 "url": "https://wowhub.app/u/corto-el-pelo-por-botillas/reservar"},
            ],
        }
        orch = _make_orchestrator(tool_result)
        try:
            buggy_response = (
                "Aquí tienes tu link real para reservas 🎉\n\n"
                "👉 /u/corto-el-pelo-por-botillas/reservar\n\n"
                "Tu slug aparece como 'corto-el-pelo-por-botillas' (con fe)."
            )
            out = await orch._scrub_slug_placeholders(buggy_response, tool_results=None)
            assert "https://wowhub.app/u/corto-el-pelo-por-botillas/reservar" in out
            # El path sin dominio debe haber sido reemplazado.
            assert "/u/corto-el-pelo-por-botillas/reservar" not in out.replace(
                "https://wowhub.app/u/corto-el-pelo-por-botillas/reservar", ""
            )
        finally:
            _restore_tool(orch)

    @pytest.mark.asyncio
    async def test_user_scenario_paren_instruction_with_real_url(self):
        """El TERCER caso del usuario:
        Q: 'dame el link para que mis clientes reserven'
        A (bug): 'Aquí tienes tu link: https://.../u/corto-el-pelo-por-botillas/reservar
                  (cambia `{slug}` por el nombre de tu negocio)'
        Debe arreglarse: la URL real queda, el paréntesis instructivo se ELIMINA.
        """
        tool_result = {
            "has_slug": True,
            "tenant": {"name": "Corto", "slug": "corto-el-pelo-por-botillas"},
            "urls": [
                {"key": "reservar",
                 "url": "https://wowhub-api-production.up.railway.app/u/corto-el-pelo-por-botellas/reservar"},
            ],
        }
        orch = _make_orchestrator(tool_result)
        try:
            buggy_response = (
                "Aquí tienes tu link para que tus clientes reserven 🎉\n\n"
                "👉 https://wowhub-api-production.up.railway.app/"
                "u/corto-el-pelo-por-botellas/reservar\n\n"
                "(cambia `{slug}` por el nombre de tu negocio)"
            )
            out = await orch._scrub_slug_placeholders(buggy_response, tool_results=None)
            # La URL real debe permanecer intacta.
            assert (
                "https://wowhub-api-production.up.railway.app/"
                "u/corto-el-pelo-por-botellas/reservar"
                in out
            )
            # El paréntesis instructivo debe haber sido eliminado.
            assert "{slug}" not in out
            assert "cambia" not in out
            # (el texto no debe terminar con ")" huérfana o un espacio raro
            # dejado por la eliminación del paréntesis completo)
            assert out.rstrip().endswith("reservar")
        finally:
            _restore_tool(orch)
