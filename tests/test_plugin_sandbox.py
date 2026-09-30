"""Tests para HU_45 — Plugin Sandbox (RestrictedPython).

Valida:
  1. Plugin simple retorna output esperado.
  2. Plugin con `import os` es rechazado.
  3. Plugin accede a `ctx.log.info` correctamente.
  4. Plugin con loop infinito es matado por timeout.

Notas:
  - Los tests 1-3 NO requieren DB; usan `run_plugin` directamente.
  - El test 4 usa `time.sleep(0.05)` dentro del loop para que en Windows
    el watchdog (`threading.Timer`) pueda interrumpir el main thread.
    En Unix el loop infinito `while True: pass` también funciona porque
    `signal.SIGALRM` lo interrumpe a nivel C.
"""
import sys

import pytest

from app.services.plugin_sandbox import run_plugin


IS_WINDOWS = sys.platform.startswith("win")


def test_simple_plugin_returns_expected_output():
    """Test 1: Plugin simple retorna output esperado."""
    result = run_plugin("print('hello world')", {})
    assert result["output"].strip() == "hello world"
    assert result["error"] is None
    assert result["timed_out"] is False
    assert isinstance(result["duration_ms"], int)
    assert result["duration_ms"] >= 0


def test_plugin_with_import_os_is_blocked():
    """Test 2: Plugin con `import os` es rechazado."""
    result = run_plugin("import os\nprint(os.name)", {})
    assert result["output"] == ""
    # RestrictedPython no permite import en absoluto sin __import__ en builtins.
    # El error concreto puede ser ImportError, SyntaxError o NameError según
    # la versión; lo importante es que el plugin NO se ejecute.
    assert result["error"] is not None
    assert result["timed_out"] is False
    # El output nunca debe contener el resultado de os.name
    assert "posix" not in result["output"]
    assert "nt" not in result["output"]


def test_plugin_can_access_ctx_log_info():
    """Test 3: Plugin accede a `ctx.log.info` correctamente."""
    code = (
        "ctx.log.info('mensaje informativo')\n"
        "ctx.log.warn('warning')\n"
        "ctx.log.error('error')\n"
        "print('plugin finished')\n"
    )
    result = run_plugin(
        code,
        {"plugin_slug": "test-plugin", "tenant_id": "abc-123"},
    )
    # No debe haber error — el log debe aceptar los 3 niveles sin fallar
    assert result["error"] is None, result["error"]
    assert result["timed_out"] is False
    assert "plugin finished" in result["output"]


def test_plugin_with_infinite_loop_is_killed_by_timeout():
    """Test 4: Plugin con loop infinito es matado por timeout."""
    if IS_WINDOWS:
        # En Windows el GIL impide interrumpir CPU-bound code; usamos
        # `time.sleep(0.05)` para liberar el GIL periódicamente y que el
        # watchdog (`threading.Timer`) marque el flag.
        code = (
            "i = 0\n"
            "while True:\n"
            "    i += 1\n"
            "    time.sleep(0.05)\n"
        )
    else:
        # En Unix SIGALRM interrumpe CPU-bound code directamente.
        code = "while True:\n    pass\n"

    result = run_plugin(code, {}, timeout_sec=1)
    assert result["timed_out"] is True, (
        f"expected timed_out=True, got {result!r}"
    )
    # El error debe indicar timeout
    assert result["error"] is not None
    assert "timeout" in result["error"].lower() or "TimeoutError" in result["error"]
    # La duración debe estar cerca del timeout (1s) — toleramos margen
    assert result["duration_ms"] < 3000, (
        f"plugin should have been killed within 3s, took {result['duration_ms']}ms"
    )