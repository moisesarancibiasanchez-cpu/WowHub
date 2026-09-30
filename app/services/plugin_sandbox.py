"""Plugin Sandbox — ejecución aislada de código de plugin (HU_45).

MVP basado en `RestrictedPython`. Compila el código fuente en modo restringido,
filtra builtins peligrosos, captura stdout vía `PrintCollector` y aplica un
timeout de wall-clock:

  - Unix: `signal.SIGALRM` (C-level, interrumpe CPU-bound code).
  - Windows: `threading.Timer` (sólo interrumpe código que libera el GIL,
    p.ej. `time.sleep`). Esta limitación está documentada; los infinite loops
    puros (`while True: pass`) NO se pueden matar en Windows. Se recomienda
    que los plugins usen `time.sleep` en loops de espera.

Política de seguridad aplicada:
  - `_getattr_`: bloquea atributos que empiezan con `__` (excepto los
    explícitamente seguros). Evita `obj.__class__.__mro__...` style escapes.
  - `_getitem_`/`_getiter_`: no-op restrictivos (sólo delegan a `obj[key]`
    e `iter(obj)`).
  - `_print_`: factory que devuelve un `PrintCollector` para que las llamadas
    `print(...)` se capturen en memoria.
  - Builtins reducidos a una whitelist explícita:
      print, len, str, int, float, dict, list, tuple, set, bool, range,
      enumerate, zip, map, filter, sum, min, max, abs, round, sorted, reversed,
      isinstance, issubclass, type, repr, hash, id, any, all, None, True, False.
  - NO se expone `__import__`, `eval`, `exec`, `open`, `compile`, `globals`,
    `locals`, `vars`, `input`, `getattr`, `setattr`, `delattr` directos.
  - RestrictedPython ya bloquea `import os`, `import subprocess`, etc. a nivel
    de AST. Ver tests para confirmación.

API pública:
  - `run_plugin(plugin_code: str, context: dict, timeout_sec=10) -> dict`

Retorna `{"output": str, "error": str | None, "timed_out": bool,
           "duration_ms": int}`.
"""
from __future__ import annotations

import io
import logging
import signal
import sys
import threading
import time as _time  # se inyecta al sandbox para time.sleep
from typing import Any, Dict

from RestrictedPython import compile_restricted
from RestrictedPython.PrintCollector import PrintCollector

from app.services.plugin_context import PluginContext

logger = logging.getLogger("wowhub.plugin_sandbox")


# ── Whitelist de builtins seguros ────────────────────────────
# Sólo lo que un plugin legítimo puede necesitar. Cualquier builtin fuera de
# esta lista NO estará disponible, y por tanto un `eval(...)` o
# `__import__(...)` fallará con NameError en tiempo de ejecución.
_SAFE_BUILTINS: Dict[str, Any] = {
    # tipos base
    "bool": bool,
    "dict": dict,
    "float": float,
    "int": int,
    "list": list,
    "set": set,
    "str": str,
    "tuple": tuple,
    # constantes
    "None": None,
    "True": True,
    "False": False,
    # helpers de inspección seguros
    "isinstance": isinstance,
    "issubclass": issubclass,
    "type": type,
    "repr": repr,
    "hash": hash,
    "id": id,
    # funciones puras
    "abs": abs,
    "all": all,
    "any": any,
    "enumerate": enumerate,
    "filter": filter,
    "len": len,
    "map": map,
    "max": max,
    "min": min,
    "range": range,
    "reversed": reversed,
    "round": round,
    "sorted": sorted,
    "sum": sum,
    "zip": zip,
    # print inyectado vía _print_; aquí lo dejamos como identidad para
    # que el código que haga `print = ...` no rompa (el bytecode real usa
    # el _print_ generado por RestrictedPython, NO este `print`).
    "print": lambda *a, **kw: None,
}


# ── Guards exigidos por RestrictedPython ──────────────────────
def _safe_getattr(obj: Any, name: str, default: Any = None) -> Any:
    """Bloquea atributos `dunder` excepto `_print` que usa internamente."""
    if not isinstance(name, str):
        return default
    if name.startswith("__") and name.endswith("__"):
        return default
    # bloquear atributos privados peligrosos en tipos built-in
    if name.startswith("_"):
        return default
    return getattr(obj, name, default)


def _safe_getitem(obj: Any, key: Any) -> Any:
    return obj[key]


def _safe_getiter(obj: Any) -> Any:
    return iter(obj)


def _inplacevar(op: str, x: Any, y: Any) -> Any:
    """Guard requerido por RestrictedPython para operadores `+=`, `-=`, etc.

    `op` es el nombre textual del operador (p.ej. '+='). Devuelve el resultado
    de aplicar el operador y RE-ASIGNAR `x` (mutación in-place si el tipo lo
    soporta). Para tipos inmutables (int, str) devuelve el valor nuevo.
    """
    operators = {
    "": lambda a, b: a,
    "+=": lambda a, b: a + b,
    "-=": lambda a, b: a - b,
    "*=": lambda a, b: a * b,
    "/=": lambda a, b: a / b,
    "//=": lambda a, b: a // b,
    "%=": lambda a, b: a % b,
    "**=": lambda a, b: a ** b,
    "&=": lambda a, b: a & b,
    "|=": lambda a, b: a | b,
    "^=": lambda a, b: a ^ b,
    "<<=": lambda a, b: a << b,
    ">>=": lambda a, b: a >> b,
    }
    if op not in operators:
        raise ValueError(f"Operator {op!r} is not allowed in sandbox")
    return operators[op](x, y)


# ── Manejo de timeout (SIGALRM en Unix, threading.Timer en Windows) ─────
class _PluginTimeout(Exception):
    """Excepción interna que el handler de timeout lanza."""


_IS_WINDOWS = sys.platform.startswith("win")


def _install_timeout(timeout_sec: float, container: Dict[str, Any]) -> None:
    """Registra un timer que, al disparar, marca timeout en `container`.

    Devuelve un callable `cancel()` que desactiva el timer.
    """
    container["timed_out"] = False

    def _fire() -> None:
        container["timed_out"] = True
        # En Unix esto NO se ejecuta porque SIGALRM lo interrumpe antes.
        # En Windows es lo único que podemos hacer: marcar el flag y esperar
        # que el código esté en un punto que libere el GIL (p.ej. time.sleep).

    if _IS_WINDOWS:
        timer = threading.Timer(timeout_sec, _fire)
        timer.daemon = True
        timer.start()

        def _cancel() -> None:
            timer.cancel()

    else:
        def _handler(signum: int, frame: Any) -> None:
            container["timed_out"] = True
            raise _PluginTimeout("plugin execution exceeded timeout")

        old_handler = signal.signal(signal.SIGALRM, _handler)
        # setitimer acepta floats; signal.alarm sólo enteros.
        signal.setitimer(signal.ITIMER_REAL, float(timeout_sec))

        def _cancel() -> None:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, old_handler)

    container["_cancel_timeout"] = _cancel


def _safe_print_factory(_getattr_: Any) -> PrintCollector:
    """Factory invocada por el bytecode como `_print = _print_(_getattr_)`.

    Devuelve un PrintCollector fresco por ejecución. El parámetro `_getattr_`
    se IGNORA porque RestrictedPython sólo lo usa para extraer `_call_print`
    del objeto retornado (vía LOAD_ATTR).
    """
    return PrintCollector()


# ── Wrapper seguro del módulo `time` ─────────────────────────
class _SafeTime:
    """Sustituto del módulo `time` para el sandbox.

    Provee sólo las funciones seguras (`time`, `sleep`, `monotonic`).
    `sleep` está parcheada para verificar el flag de timeout cada 50 ms,
    lo que permite al watchdog interrumpir infinite loops en Windows
    (donde SIGALRM no existe y `threading.Timer` no puede matar el main
    thread por el GIL).
    """

    def __init__(self, timeout_check):
        # timeout_check: callable () -> bool que retorna True si expiró
        self._timeout_check = timeout_check
        self._real_time = _time.time
        self._real_monotonic = _time.monotonic

    def time(self) -> float:
        return self._real_time()

    def monotonic(self) -> float:
        return self._real_monotonic()

    def sleep(self, seconds: float) -> None:
        # Dormir en chunks de 50 ms para revisar el flag.
        end_at = self._real_monotonic() + max(0.0, float(seconds))
        chunk = 0.05
        while True:
            if self._timeout_check():
                raise _PluginTimeout("plugin execution exceeded timeout")
            remaining = end_at - self._real_monotonic()
            if remaining <= 0:
                return
            _time.sleep(min(chunk, remaining))
def run_plugin(
    plugin_code: str,
    context: Dict[str, Any] | None = None,
    timeout_sec: int = 10,
) -> Dict[str, Any]:
    """Compila y ejecuta `plugin_code` en el sandbox.

    Args:
        plugin_code: código fuente Python del plugin.
        context: dict con datos de entrada. Por convención, `tenant_id`,
            `tenant_name`, `plugin_slug`, `payload` se inyectan en el
            globals del sandbox. `payload` es accesible como variable
            `payload`.
        timeout_sec: límite de wall-clock en segundos. Default 10.

    Returns:
        dict con keys: `output` (str), `error` (str | None),
        `timed_out` (bool), `duration_ms` (int).
    """
    context = context or {}
    tenant_id = context.get("tenant_id")
    tenant_name = context.get("tenant_name")
    plugin_slug = context.get("plugin_slug", "anon")
    payload = context.get("payload", {})

    # Compilar en modo restringido
    try:
        code = compile_restricted(
            plugin_code,
            filename=f"<plugin:{plugin_slug}>",
            mode="exec",
        )
    except SyntaxError as e:
        return {
            "output": "",
            "error": f"SyntaxError: {e}",
            "timed_out": False,
            "duration_ms": 0,
        }

    # Crear contexto
    plugin_ctx = PluginContext(
        tenant_id=str(tenant_id) if tenant_id else None,
        tenant_name=tenant_name,
        plugin_slug=plugin_slug,
    )

    # Capturar stderr también, por si algo escribe al fd 2 antes de la
    # excepción (mensajes de runtime que no son excepciones).
    stderr_buf = io.StringIO()
    saved_stderr_fd: Any = None
    try:
        try:
            saved_stderr_fd = sys.stderr
            sys.stderr = stderr_buf
        except Exception:  # pragma: no cover - muy raro fallar asignación
            saved_stderr_fd = None

        # Instalar timeout
        timer_container: Dict[str, Any] = {}
        _install_timeout(timeout_sec, timer_container)

        # `time` con `sleep` parcheado que verifica el flag de timeout.
        # Esto es crítico en Windows: SIGALRM no existe, el watchdog sólo
        # puede marcar el flag, y necesitamos que el plugin lo vea al
        # volver de un sleep.
        safe_time = _SafeTime(
            timeout_check=lambda: timer_container.get("timed_out", False)
        )

        # Construir globals del sandbox. NO pasamos `__builtins__` real:
        # RestrictedPython exige que proveamos uno reducido.
        sandbox_globals: Dict[str, Any] = {
            "__name__": "__plugin__",
            "__loader__": None,
            "__spec__": None,
            # Guards exigidos por RestrictedPython
            "_print_": _safe_print_factory,
            "_getattr_": _safe_getattr,
            "_getitem_": _safe_getitem,
            "_getiter_": _safe_getiter,
            "_inplacevar_": _inplacevar,
            # Builtins reducidos
            "__builtins__": dict(_SAFE_BUILTINS),
            # API explícita del plugin
            "ctx": plugin_ctx,
            "payload": payload,
            # Módulos curados — `time` se permite porque `time.sleep` libera
            # el GIL y permite al timeout interrumpir en Windows.
            "time": safe_time,
        }

        # Métrica de duración
        started = _time.perf_counter()
        error: Any = None
        output = ""
        timed_out = False

        try:
            exec(code, sandbox_globals)
        except _PluginTimeout as e:
            timed_out = True
            error = f"TimeoutError: {e}"
        except SystemExit as e:
            # SystemExit es legítimo (sys.exit). Lo reportamos como error
            # de sandbox porque el plugin no debería poder salir del proceso.
            error = f"SystemExit: {e.code!r}"
            logger.warning(
                "Plugin '%s' intentó SystemExit (code=%r)", plugin_slug, e.code
            )
        except BaseException as e:  # noqa: BLE001 - capturar todo lo del plugin
            error = f"{type(e).__name__}: {e}"

        duration_ms = int((_time.perf_counter() - started) * 1000)
        timed_out = timed_out or timer_container.get("timed_out", False)

        # Capturar lo impreso por el plugin
        try:
            # El PrintCollector es accesible vía el closure de _safe_print_factory
            # ya que exec() lo llamó. Pero como _safe_print_factory es llamada
            # DENTRO del sandbox, no tenemos referencia directa al collector.
            # Solución: lo recuperamos del globals del sandbox.
            _print_local = sandbox_globals.get("_print")
            if _print_local is not None and hasattr(_print_local, "__call__"):
                # `_print` es un PrintCollector; su __call__ retorna el texto.
                output = _print_local()
        except Exception:
            pass

        # Concatenar stderr si capturamos algo
        stderr_text = stderr_buf.getvalue()
        if stderr_text and not error:
            error = stderr_text.strip()[:1000]

    finally:
        # Restaurar timeout
        try:
            cancel = timer_container.get("_cancel_timeout")
            if cancel is not None:
                cancel()
        except Exception:  # pragma: no cover - best effort
            pass

        # Restaurar stderr
        if saved_stderr_fd is not None:
            try:
                sys.stderr = saved_stderr_fd
            except Exception:  # pragma: no cover
                pass

    # Log de auditoría (HU_40 integrará este log con el hash chain; por
    # ahora dejamos un log estructurado estándar).
    log_method = logger.warning if timed_out or error else logger.info
    log_method(
        "plugin_sandbox: slug=%s tenant=%s timed_out=%s duration_ms=%d err=%s",
        plugin_slug,
        tenant_id,
        timed_out,
        duration_ms,
        (error or "")[:200],
    )

    return {
        "output": output,
        "error": error,
        "timed_out": timed_out,
        "duration_ms": duration_ms,
    }


__all__ = ["run_plugin"]