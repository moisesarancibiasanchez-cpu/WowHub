"""PluginContext — API explícita y mínima que un plugin en sandbox puede usar.

HU_45 — Plugin Sandbox.

Esta clase define el "contrato" entre el sandbox y el código del plugin.
El plugin NUNCA recibe acceso directo a:
  - `os`, `sys`, `subprocess`, `socket`, `urllib`, `requests`
  - variables de entorno (secretos)
  - la sesión de DB del proceso principal

Sólo puede llamar a los métodos definidos aquí:
  - `log.info(msg)` / `log.warn(msg)` / `log.error(msg)` — logging etiquetado
  - `storage.get(key, default=None)` / `storage.set(key, value)` — KV en memoria
    (aislado por ejecución; NO persistente)
  - `tenant.get_info()` — datos públicos del tenant (nombre, slug)
    (NO incluye email, RUT, ni credenciales)

Este aislamiento es deliberado: cualquier ampliación del contrato debe pasar
por un audit log explícito (HU_40).
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional


class _PluginLog:
    """Wrapper de logging limitado. Sólo permite .info/.warn/.error."""

    def __init__(self, plugin_slug: str, tenant_id: Optional[str]):
        self._logger = logging.getLogger(f"wowhub.plugins.{plugin_slug}")
        self._tenant_id = tenant_id

    def info(self, msg: str, **kv: Any) -> None:
        self._logger.info(msg, extra={"plugin_kv": kv, "tenant_id": self._tenant_id})

    def warn(self, msg: str, **kv: Any) -> None:
        self._logger.warning(msg, extra={"plugin_kv": kv, "tenant_id": self._tenant_id})

    def error(self, msg: str, **kv: Any) -> None:
        self._logger.error(msg, extra={"plugin_kv": kv, "tenant_id": self._tenant_id})


class _PluginStorage:
    """KV en memoria aislado por ejecución. NO persistente."""

    def __init__(self):
        self._data: Dict[str, Any] = {}

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value


class _PluginTenant:
    """Vista pública y mínima del tenant."""

    def __init__(self, tenant_id: Optional[str], name: Optional[str] = None):
        self._tenant_id = tenant_id
        self._name = name

    def get_info(self) -> Dict[str, Any]:
        """Datos NO sensibles del tenant."""
        return {
            "id": self._tenant_id,
            "name": self._name,
        }


class PluginContext:
    """API explícita que el plugin puede invocar desde su sandbox.

    Instanciar con: `PluginContext(tenant_id=str(uuid), tenant_name="...")`.

    HU_45 — Hooks: el plugin puede registrar hooks via
    ``ctx.register_hook(event_name, callable)``. El callable debe estar
    definido en el propio install_script. El runtime (no el sandbox)
    extrae la fuente del callable via ``linecache`` y la persiste en la
    tabla ``plugin_subscriptions.hooks`` (columna JSON).
    """

    # Set de eventos que el dispatcher acepta. Cualquier hook registrado
    # fuera de esta lista se ignora silenciosamente al persistir para
    # evitar typos.
    ALLOWED_HOOKS = frozenset({
        "on_order_created",
        "on_order_paid",
        "on_customer_created",
        "on_payment_received",
    })

    def __init__(
        self,
        *,
        tenant_id: Optional[str] = None,
        tenant_name: Optional[str] = None,
        plugin_slug: str = "anon",
    ):
        self.log = _PluginLog(plugin_slug=plugin_slug, tenant_id=tenant_id)
        self.storage = _PluginStorage()
        self.tenant = _PluginTenant(tenant_id=tenant_id, name=tenant_name)
        self._plugin_slug = plugin_slug
        # Registro de hooks: nombre_evento → callable (definido en el
        # install_script). NO se serializa como callable; el runtime
        # extrae la fuente vía inspect.getsource (que funciona porque el
        # sandbox pobló el linecache con el código fuente).
        self.hooks: Dict[str, Any] = {}

    @property
    def plugin_slug(self) -> str:
        return self._plugin_slug

    def register_hook(self, event: str, fn: Any) -> None:
        """Registra un hook para un evento del ciclo de vida.

        Args:
            event: nombre del evento (uno de ``ALLOWED_HOOKS``).
            fn: callable definido en el install_script.

        Raises:
            TypeError: si ``fn`` no es callable.
            ValueError: si ``event`` no está en ``ALLOWED_HOOKS``.
        """
        if event not in self.ALLOWED_HOOKS:
            raise ValueError(
                f"Hook event '{event}' no soportado. "
                f"Eventos válidos: {sorted(self.ALLOWED_HOOKS)}"
            )
        if not callable(fn):
            raise TypeError("El hook debe ser callable")
        self.hooks[event] = fn