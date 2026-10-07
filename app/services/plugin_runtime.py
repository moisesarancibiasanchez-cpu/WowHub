"""Plugin runtime — glue entre install_script y el sandbox (HU_45).

Responsabilidades:
  - Ejecutar ``install_script`` de un plugin con `db`, `tenant_id`,
    `config` en el sandbox de RestrictedPython.
  - Extraer las fuentes de los hooks registrados por el plugin para
    serializarlas a JSON (persistidas en ``plugin_subscriptions.hooks``).
  - Devolver un log estructurado (``output``, ``error``, ``timed_out``,
    ``duration_ms``, ``hooks``) listo para guardarse en
    ``plugin_subscriptions.install_log``.

Convenciones de seguridad:
  - El install_script NO puede hacer commit/rollback por sí mismo:
    opera sobre la sesión del caller. El caller decide commit/rollback.
  - El install_script tiene timeout duro de 10s (vía run_plugin).
  - Los hooks se extraen vía ``inspect.getsource``; eso funciona porque
    ``plugin_sandbox.run_plugin`` pobló el linecache con el código
    fuente antes de exec.
"""
from __future__ import annotations

import inspect
import json
import logging
from typing import Any, Dict

from app.models.marketplace import MarketplacePlugin
from app.services.plugin_sandbox import run_plugin as run_sandbox

# Límite duro de codigo permitido en un install_script (10 KB). El sandbox
# valida tamaño por separado (100 KB en plugins.py), pero el install
# debe ser mucho más compacto porque se ejecuta con DB real.
MAX_INSTALL_SCRIPT_BYTES = 10_000


logger = logging.getLogger("wowhub.plugin_runtime")


def _safe_getsource(fn: Any) -> str | None:
    """Extrae el source de un callable, o None si no se puede."""
    try:
        return inspect.getsource(fn)
    except (OSError, TypeError, IndentationError):
        return None


def run_install_script(
    db: Any,
    plugin: MarketplacePlugin,
    tenant_id: Any,
    config: Dict[str, Any] | None,
    timeout_sec: int = 10,
) -> Dict[str, Any]:
    """Ejecuta ``plugin.install_script`` en sandbox con DB real.

    Args:
        db: sesión SQLAlchemy (la transacción es caller-controlled).
        plugin: MarketplacePlugin (con ``install_script`` no-None).
        tenant_id: UUID del tenant que está instalando.
        config: dict de config (output del schema). Se inyecta como
            variable ``config`` en el sandbox.
        timeout_sec: límite de wall-clock. Default 10.

    Returns:
        dict con keys:
          - ``output`` (str): stdout del plugin.
          - ``error`` (str|None): mensaje de error si falló.
          - ``timed_out`` (bool): True si excedió el timeout.
          - ``duration_ms`` (int): tiempo de ejecución.
          - ``hooks`` (Dict[str, str]): mapa event_name -> source del hook.
          - ``ok`` (bool): True si ejecutó sin error.
    """
    code = plugin.install_script
    if not code or not code.strip():
        return {
            "ok": True,
            "output": "",
            "error": None,
            "timed_out": False,
            "duration_ms": 0,
            "hooks": {},
        }
    if len(code) > MAX_INSTALL_SCRIPT_BYTES:
        return {
            "ok": False,
            "output": "",
            "error": (
                f"install_script excede el límite de "
                f"{MAX_INSTALL_SCRIPT_BYTES} bytes (recibí {len(code)})."
            ),
            "timed_out": False,
            "duration_ms": 0,
            "hooks": {},
        }

    context: Dict[str, Any] = {
        "tenant_id": str(tenant_id),
        "tenant_name": None,
        "plugin_slug": plugin.slug,
        "payload": {},
        "config": config or {},
    }

    result = run_sandbox(
        plugin_code=code,
        context=context,
        timeout_sec=timeout_sec,
        db=db,
    )

    # Serializar hooks: cada callable registrado → fuente (vía linecache
    # que el sandbox pobló).
    hooks_map: Dict[str, str] = {}
    raw_hooks = result.get("hooks") or {}
    for event, fn in raw_hooks.items():
        if not callable(fn):
            continue
        src = _safe_getsource(fn)
        if src:
            hooks_map[event] = src
        else:
            logger.warning(
                "plugin_runtime: no se pudo extraer source del hook '%s' "
                "(plugin=%s tenant=%s)",
                event, plugin.slug, tenant_id,
            )

    return {
        "ok": result.get("error") is None and not result.get("timed_out", False),
        "output": result.get("output") or "",
        "error": result.get("error"),
        "timed_out": result.get("timed_out", False),
        "duration_ms": result.get("duration_ms", 0),
        "hooks": hooks_map,
    }


def serialize_install_log(result: Dict[str, Any]) -> str:
    """Convierte el resultado de run_install_script a JSON para DB."""
    return json.dumps(
        {
            "ok": result.get("ok", False),
            "output": result.get("output") or "",
            "error": result.get("error"),
            "timed_out": result.get("timed_out", False),
            "duration_ms": result.get("duration_ms", 0),
            "hooks_count": len(result.get("hooks") or {}),
        },
        ensure_ascii=False,
    )


def serialize_hooks(hooks: Dict[str, str]) -> str:
    """Convierte el mapa de hooks a JSON para DB."""
    return json.dumps(hooks, ensure_ascii=False)


__all__ = [
    "run_install_script",
    "serialize_install_log",
    "serialize_hooks",
    "MAX_INSTALL_SCRIPT_BYTES",
]