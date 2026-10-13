"""Tests del helper `strip_think` y `_format_tool_result`.

El LLM que usa WowHub (DeepSeek-compatible) emite bloques
`<think>...</think>` con su razonamiento interno. El orquestador
los quita antes de devolver la respuesta al usuario.

Estos tests cubren:
- Eliminación del bloque think
- Bloques multilinea
- Variantes case-insensitive
- Tags "leaky" como <reasoning>
- Caso real: respuesta del screenshot del usuario
- _format_tool_result pasa los datos REALES (no solo el nombre)
"""
from app.services.ai_orchestrator import strip_think, _format_tool_result


# ── strip_think ────────────────────────────────────────
class TestStripThink:
    def test_removes_think_block(self):
        text = (
            "<think>The user wants a promotion. Let me plan.</think>\n"
            "¡Hola! Aquí tienes tu promo."
        )
        out = strip_think(text)
        assert "<think>" not in out
        assert "Aquí tienes tu promo." in out

    def test_removes_multiline_think_block(self):
        text = (
            "<think>\n"
            "multi\n"
            "line\n"
            "reasoning\n"
            "</think>\n\n"
            "Respuesta final."
        )
        assert strip_think(text) == "Respuesta final."

    def test_leaves_plain_text_untouched(self):
        text = "Plain response without think block."
        assert strip_think(text) == text

    def test_empty_string(self):
        assert strip_think("") == ""

    def test_case_insensitive_tag(self):
        assert strip_think("<THINK>hidden</THINK>visible") == "visible"
        assert strip_think("<Think>hidden</Think>visible") == "visible"

    def test_removes_reasoning_tag(self):
        assert strip_think("<reasoning>internal</reasoning>User visible.") == "User visible."

    def test_removes_reflection_tag(self):
        assert strip_think("<reflection>foo</reflection>bar") == "bar"

    def test_real_world_user_screenshot(self):
        """Replica exacta de la respuesta del LLM en la captura del usuario."""
        text = (
            "<think>The user wants me to create a 15% promotion for their "
            "featured products, valid for 7 days. Based on the developer policy:\n"
            "...\n"
            "Let me draft a response in Spanish...\n"
            "Should NOT call create_promotion yet because I need to confirm "
            "details first.</think>\n"
            "\n"
            "¡Perfecto, vamos a crear esa promo! 🎯\n"
            "\n"
            "Datos que tengo claros:\n"
            "• \n"
            "• \n"
            "• \n"
        )
        out = strip_think(text)
        assert "<think>" not in out
        assert "Should NOT call" not in out
        assert "Let me draft" not in out
        assert "¡Perfecto, vamos a crear esa promo!" in out
        assert "Datos que tengo claros" in out

    def test_multiple_think_blocks(self):
        text = "<think>uno</think>hola<think>dos</think>mundo"
        assert strip_think(text) == "holamundo"

    def test_returns_string_type(self):
        out = strip_think("<think>x</think>y")
        assert isinstance(out, str)


# ── _format_tool_result ────────────────────────────────
class TestFormatToolResult:
    def test_includes_real_data(self):
        out = _format_tool_result("get_sales", {"days": 30}, {"total": 1500, "items": 42})
        assert "get_sales" in out
        assert "1500" in out
        assert '"days": 30' in out or "'days': 30" in out
        # Antes este helper no existía; el LLM recibía "- get_sales: get_sales → OK"
        # sin ningún dato. Ahora el LLM ve los números reales.
        assert "OK" not in out  # no se repite el placeholder genérico

    def test_truncates_huge_payload(self):
        big = {"data": "x" * 5000}
        out = _format_tool_result("big_tool", {}, big)
        assert "truncado" in out
        # Garantiza que no metemos 5KB en el contexto del LLM
        assert len(out) < 2000

    def test_empty_args_uses_brace_dict(self):
        out = _format_tool_result("ping", {}, {"ok": True})
        assert "ping({})" in out
        assert "true" in out

    def test_non_serializable_objects_handled(self):
        out = _format_tool_result("weird", {}, {"obj": object()})
        assert "weird" in out  # no se cae

    def test_includes_args_for_context(self):
        """El LLM necesita saber con qué args se llamó la tool."""
        out = _format_tool_result(
            "create_promotion", {"discount": 15, "days": 7}, {"id": "promo-123"}
        )
        assert "discount" in out
        assert "15" in out
        assert "promo-123" in out
