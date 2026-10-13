"""Plugin hook dispatcher (HU_45).

El sistema de hooks permite que un plugin reaccione a eventos del ciclo
de vida de WowHub. El plugin registra hooks en su ``install_script``
vía ``ctx.register_hook(event, fn)``. El runtime extrae la fuente de
``fn`` y la persiste en ``plugin_subscriptions.hooks`` (JSON).

Cuando se dispara un evento (``trigger_hooks``), el dispatcher:

1. Carga todas las suscripciones activas del tenant.
2. Decodifica el campo ``hooks`` (JSON: ``{event_name: source_code}``).
3. Compila + ejecuta cada source en sandbox (sin ``db`` — los hooks
   reciben ``payload`` y ``ctx`` solamente).
4. Llama al callable resultante con ``(payload)``.
5. Los errores se loggean pero NO bloquean el flujo principal.

Aislamiento por tenant: ``trigger_hooks`` filtra por ``tenant_id`` antes
de ejecutar — un tenant jamás puede disparar hooks de otro.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

from RestrictedPython import compile_restricted
from sqlalchemy import and_
from sqlalchemy.orm import Session

import linecache

from app.models.marketplace import MarketplacePlugin, PluginSubscription
from app.services.plugin_context import PluginContext
from app.services.plugin_sandbox import (
    _SAFE_BUILTINS,
    _safe_getattr,
    _safe_getitem,
    _safe_getiter,
    _inplacevar,
    _safe_print_factory,
    _PluginTimeout,
    _install_timeout,
    _SafeTime,
)

logger = logging.getLogger("wowhub.plugin_hooks")

# Tiempo máximo de ejecución de UN hook. Más corto que install_script
# porque los hooks se llaman en línea con requests de usuario.
_HOOK_TIMEOUT_SEC = 3


def _exec_hook_source(source: str, slug: str) -> Optional[Any]:
    """Compila + ejecuta el source de un hook y devuelve el namespace.

    El plugin debe definir una función top-level con el mismo nombre
    que el evento (p.ej. ``def on_order_created(payload): ...``).
    """
    filename = f"<hook:{slug}>"
    linecache.cache[filename] = (
        len(source),
        None,
        [line + "\n" for line in source.splitlines()],
        filename,
    )
    try:
        code = compile_restricted(source, filename=filename, mode="exec")
    except SyntaxError as e:
        logger.error("hook source syntax error slug=%s: %s", slug, e)
        return None

    plugin_ctx = PluginContext(plugin_slug=slug)
    safe_time = _SafeTime(timeout_check=lambda: False)
    sandbox_globals: Dict[str, Any] = {
        "__name__": "__hook__",
        "__loader__": None,
        "__spec__": None,
        "_print_": _safe_print_factory,
        "_getattr_": _safe_getattr,
        "_getitem_": _safe_getitem,
        "_getiter_": _safe_getiter,
        "_inplacevar_": _inplacevar,
        "__builtins__": dict(_SAFE_BUILTINS),
        "ctx": plugin_ctx,
        "time": safe_time,
    }
    # Sin `db` en globals: tienen payload + ctx solamente.

    timer_container: Dict[str, Any] = {}
    _install_timeout(_HOOK_TIMEOUT_SEC, timer_container)

    try:
        exec(code, sandbox_globals)
    except _PluginTimeout:
        logger.warning("hook slug=%s excedió timeout (%ss)", slug, _HOOK_TIMEOUT_SEC)
        return None
    except BaseException as e:  # noqa: BLE001
        logger.warning("hook slug=%s falló al cargar: %s: %s", slug, type(e).__name__, e)
        return None
    finally:
        cancel = timer_container.get("_cancel_timeout")
        if cancel is not None:
            try:
                cancel()
            except Exception:  # pragma: no cover
                pass
    return sandbox_globals


def trigger_hooks(
    db: Session,
    tenant_id: Any,
    event: str,
    payload: Dict[str, Any],
) -> int:
    """Dispara todos los hooks registrados para `event` en el tenant.

    Args:
        db: sesión SQLAlchemy.
        tenant_id: UUID del tenant.
        event: nombre del evento (p.ej. ``on_order_created``).
        payload: dict con datos del evento que el hook recibirá.

    Returns:
        Número de hooks ejecutados con éxito (0 si ninguno).
        Los errores individuales se loggean y NO se propagan.
    """
    if not event:
        return 0

    # Cargar suscripciones activas con hooks
    rows = (
        db.query(PluginSubscription)
        .join(MarketplacePlugin, PluginSubscription.plugin_id == MarketplacePlugin.id)
        .filter(
            and_(
                PluginSubscription.tenant_id == str(tenant_id),
                PluginSubscription.status == "active",
                PluginSubscription.hooks.isnot(None),
                PluginSubscription.hooks != "",
            )
        )
        .all()
    )

    executed = 0
    for sub in rows:
        plugin = db.get(MarketplacePlugin, sub.plugin_id)
        if plugin is None:
            continue
        try:
            hooks_map = json.loads(sub.hooks) if isinstance(sub.hooks, str) else (sub.hooks or {})
        except (json.JSONDecodeError, TypeError):
            logger.warning(
                "hook registry corrupto: tenant=%s plugin=%s",
                tenant_id, plugin.slug,
            )
            continue
        if not isinstance(hooks_map, dict):
            continue
        source = hooks_map.get(event)
        if not source:
            continue

        ns = _exec_hook_source(source, plugin.slug)
        if ns is None:
            continue
        fn = ns.get(event)
        if not callable(fn):
            logger.warning(
                "hook '%s' en plugin '%s' no expuso un callable con ese nombre",
                event, plugin.slug,
            )
            continue

        # Aislamiento: el payload se sanitiza a un dict plano (defensa
        # en profundidad — el plugin no debería recibir objetos SQLAlchemy
        # vivos). Si el payload ya es dict, lo clonamos superficialmente.
        safe_payload = dict(payload) if isinstance(payload, dict) else {"value": payload}

        try:
            fn(safe_payload)
            executed += 1
        except _PluginTimeout:
            logger.warning("hook '%s' (plugin '%s') excedió timeout", event, plugin.slug)
        except BaseException as e:  # noqa: BLE001
            logger.warning(
                "hook '%s' (plugin '%s') lanzó: %s: %s",
                event, plugin.slug, type(e).__name__, e,
            )

    return executed


__all__ = ["trigger_hooks"]