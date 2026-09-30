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
    """

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

    @property
    def plugin_slug(self) -> str:
        return self._plugin_slug