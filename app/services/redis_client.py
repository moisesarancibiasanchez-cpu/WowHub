"""HU_41 — Cliente Redis síncrono con fallback seguro a in-memory.

Este módulo expone un singleton lazy del cliente Redis (sync, NO asyncio).
Está pensado para ser usado por ``RateLimitMiddleware`` en
``app/core/security.py`` para distribuir el rate limit entre los pods
de Railway (el bug activo de producción: con N pods, el límite efectivo
se multiplica por N porque cada pod cuenta sus propias requests en su
``defaultdict`` local).

Diseño
------
1. **Lazy**: el cliente NO se inicializa en el lifespan de FastAPI. Se
   crea la primera vez que ``get_redis()`` se llama y se cachea en el
   módulo. Si falla, NO se reintenta por cada request — se reintenta
   cada ``_RECONNECT_COOLDOWN_SECONDS`` para no saturar la CPU si
   Redis está caído.

2. **Defensivo**: CUALQUIER excepción al construir el cliente o al
   hacer ping se loguea como WARNING y ``is_available()`` devuelve
   ``False``. ``get_redis()`` devuelve ``None`` en ese caso. Esto
   permite que ``RateLimitMiddleware`` caiga transparentemente al
   fallback in-memory sin que la API rompa.

3. **Síncrono**: usa ``redis.Redis`` (no ``redis.asyncio``). El
   middleware de FastAPI llama ``await call_next(...)``, así que las
   llamadas a Redis se ejecutan en el event loop. Como Redis-py sync
   no es async-friendly, el middleware las hace en un thread executor
   (ver ``app.core.security.RateLimitMiddleware``). Esta es una
   decisión deliberada para minimizar la superficie de cambio: no se
   introduce ``redis.asyncio`` ni se reescribe el dispatch.

4. **Sliding window log atómico (Lua)**: el script Lua
   ``SLIDING_WINDOW_LUA`` ejecuta ZREMRANGEBYSCORE → ZCARD → ZADD →
   PEXPIRE en una sola operación atómica. Si Redis no soporta Lua
   (versiones muy viejas), el caller debe usar un pipeline normal;
   este módulo NO obliga al caller a soportar Lua — expone un
   fallback al rate limit in-memory.

Variables de entorno
--------------------
- ``REDIS_URL`` — URL estilo ``redis://host:port/db`` o
  ``rediss://...`` para TLS. Si está vacío o no se puede parsear,
  ``is_available()`` devuelve ``False``.
- ``REDIS_ENABLED`` (default ``"true"``) — kill-switch global. Si
  se setea ``"false"``, ``get_redis()`` devuelve ``None``
  independientemente de ``REDIS_URL``. Útil para tests y para
  apagar el rate limit distribuido sin redeploy.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Optional

# Importamos ``redis`` (síncrono). Si no está instalado, todo el
# módulo es no-op: ``get_redis()`` devuelve None y el middleware
# usa in-memory. Esto es importante porque ``redis`` está en
# requirements.txt desde HU_36 (Celery broker) y siempre debe estar
# disponible, pero queremos que HU_41 sea defensivo al 100%.
try:
    import redis as redis_sync  # type: ignore
    from redis.exceptions import RedisError  # type: ignore
except ImportError:  # pragma: no cover — sólo si redis no está instalado
    redis_sync = None  # type: ignore
    RedisError = Exception  # type: ignore

from app.config import get_settings

logger = logging.getLogger("wowhub.redis_client")

# Lua script: sliding window log atómico.
# KEYS[1] = bucket key (e.g. "rl:1.2.3.4:/api/v1/auth/login")
# ARGV[1] = current timestamp (ms)
# ARGV[2] = window (ms)
# ARGV[3] = limit (max requests)
# ARGV[4] = unique request id (UUID hex)
#
# Devuelve: {allowed (1|0), count_after, retry_after_ms}
SLIDING_WINDOW_LUA = """
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local req_id = ARGV[4]
local cutoff = now - window
redis.call('ZREMRANGEBYSCORE', KEYS[1], 0, cutoff)
local count = redis.call('ZCARD', KEYS[1])
if count >= limit then
    local oldest = redis.call('ZRANGE', KEYS[1], 0, 0, 'WITHSCORES')
    local ra = window
    if oldest[2] then
        ra = (tonumber(oldest[2]) + window) - now
        if ra < 0 then ra = 0 end
    end
    return {0, count, ra}
end
redis.call('ZADD', KEYS[1], now, req_id)
redis.call('PEXPIRE', KEYS[1], window)
return {1, count + 1, 0}
"""

# Reintento de conexión cuando falla: 30s es suficiente para que el
# middleware no queme CPU en un loop de reconexión agresivo.
_RECONNECT_COOLDOWN_SECONDS = 30.0


class _RedisSingleton:
    """Holder thread-safe del cliente Redis.

    El cliente se construye UNA vez y se reutiliza. Si falla, se
    marca ``_last_failure_ts`` y NO se reintenta hasta que pase el
    cooldown. Esto es importante porque las excepciones de conexión
    son rápidas y, sin cooldown, una Redis caída nos costaría miles
    de timeouts por segundo.
    """

    def __init__(self) -> None:
        self._client: Optional[object] = None
        self._last_attempt_ts: float = 0.0
        self._last_failure_ts: float = 0.0
        self._script_sha: Optional[str] = None
        self._lock = threading.Lock()

    @property
    def client(self) -> Optional[object]:
        return self._client

    @property
    def available(self) -> bool:
        return self._client is not None

    def get_or_init(self, url: str, *, force: bool = False) -> Optional[object]:
        """Devuelve el cliente Redis, inicializándolo si hace falta.

        Retorna ``None`` si Redis no está disponible o si
        ``REDIS_ENABLED`` está en ``False``. ``force=True`` ignora
        el cooldown (útil para tests).
        """
        if redis_sync is None:
            return None
        if not url:
            return None

        with self._lock:
            if self._client is not None:
                return self._client

            now = time.time()
            # Si falló recientemente y no estamos forzando, no reintentar.
            if not force and self._last_failure_ts > 0 and (
                now - self._last_failure_ts < _RECONNECT_COOLDOWN_SECONDS
            ):
                return None

            self._last_attempt_ts = now
            try:
                client = redis_sync.from_url(
                    url,
                    decode_responses=True,
                    socket_connect_timeout=2.0,
                    socket_timeout=2.0,
                    # Si Redis está detrás de un proxy y el pool de conexiones
                    # muere, queremos reconectar transparente.
                    health_check_interval=30,
                )
                # ping() fuerza la conexión real. Si falla aquí, NO dejamos
                # el cliente "medio-inicializado" en el singleton.
                client.ping()
                self._client = client
                self._script_sha = None  # se carga lazy en check_redis
                logger.info("Redis client inicializado OK (url=%s)", _redact(url))
                return client
            except Exception as exc:  # noqa: BLE001 — defensivo
                self._last_failure_ts = now
                # No logueamos el stack completo para no spamear.
                logger.warning(
                    "Redis no disponible (url=%s, error=%s: %s). "
                    "Rate limit caerá a in-memory.",
                    _redact(url),
                    type(exc).__name__,
                    exc,
                )
                self._client = None
                return None

    def invalidate(self) -> None:
        """Fuerza reintento en la próxima llamada."""
        with self._lock:
            self._client = None
            self._script_sha = None
            self._last_failure_ts = 0.0


_singleton = _RedisSingleton()


def _redact(url: str) -> str:
    """Saca credenciales de la URL para logging seguro."""
    if "@" not in url:
        return url
    try:
        scheme, rest = url.split("://", 1)
        _, host_part = rest.split("@", 1)
        return f"{scheme}://***@{host_part}"
    except Exception:
        return "<redacted>"


def get_redis() -> Optional[object]:
    """Devuelve el cliente Redis o ``None`` si no está disponible.

    Lee ``get_settings().redis_enabled`` y ``get_settings().redis_url``.
    Usamos ``get_settings()`` (no el ``settings`` cached a nivel de
    módulo) para que los cambios de env vars en runtime (p.ej. en
    tests) se reflejen sin reiniciar el proceso. Si
    ``redis_enabled`` es ``False``, devuelve ``None`` sin intentar
    conectar (kill-switch explícito).

    No usar directamente desde hot paths sincrónicos con latencia
    alta: preferir ``is_available()`` si sólo se necesita saber si
    Redis está vivo.
    """
    s = get_settings()
    if not getattr(s, "redis_enabled", True):
        return None
    url = (getattr(s, "redis_url", "") or "").strip()
    if not url:
        return None
    return _singleton.get_or_init(url)


def is_available() -> bool:
    """True si hay un cliente Redis listo para usar.

    No inicializa si no lo estaba — sólo verifica el estado cacheado.
    Llamar ``get_redis()`` es lo que efectivamente abre la conexión.
    """
    return _singleton.available


def check_redis(
    key: str,
    *,
    limit: int,
    window_seconds: int,
    request_id: str,
    now_ms: Optional[int] = None,
) -> Optional[tuple[bool, int, int]]:
    """Ejecuta el script Lua de sliding window sobre Redis.

    Devuelve ``(allowed, count, retry_after_ms)`` si Redis está OK.
    Devuelve ``None`` si Redis NO está disponible — el caller debe
    entonces usar el fallback in-memory.

    Esta función NO se cachea por bucket: cada llamada es una
    EVALSHA contra Redis. Si el script se invalidó (Redis reinició),
    el ``except NoScriptError`` lo recarga y reintenta UNA vez.

    Parámetros
    ----------
    key : str
        Identificador del bucket, e.g. ``rl:1.2.3.4:/api/v1/auth/login``.
    limit : int
        Máximo de requests permitidas en la ventana.
    window_seconds : int
        Ancho de la ventana en segundos.
    request_id : str
        Identificador único de la request (UUID hex) para evitar
        colisiones en el ZSET si dos requests llegan en el mismo ms.
    now_ms : int | None
        Timestamp actual en ms. Si es None, se calcula acá.
    """
    client = get_redis()
    if client is None:
        return None

    if now_ms is None:
        now_ms = int(time.time() * 1000)
    window_ms = int(window_seconds * 1000)

    try:
        if _singleton._script_sha is None:
            _singleton._script_sha = client.script_load(SLIDING_WINDOW_LUA)
        sha = _singleton._script_sha
        try:
            res = client.evalsha(sha, 1, key, now_ms, window_ms, limit, request_id)
        except Exception as exc:  # noqa: BLE001
            # Si el script no está en el cache del servidor (Redis se
            # reinició o se hizo FLUSHALL), recargamos y reintentamos.
            err_name = type(exc).__name__
            if "NoScript" in err_name or "NOSCRIPT" in str(exc):
                _singleton._script_sha = client.script_load(SLIDING_WINDOW_LUA)
                sha = _singleton._script_sha
                res = client.evalsha(
                    sha, 1, key, now_ms, window_ms, limit, request_id
                )
            else:
                raise
        # res = [allowed (0|1), count, retry_after_ms]
        return (bool(int(res[0])), int(res[1]), int(res[2]))
    except Exception as exc:  # noqa: BLE001 — defensivo
        # CUALQUIER error de Redis ⇒ invalidar cliente y devolver
        # None para que el caller caiga a in-memory.
        logger.warning(
            "check_redis falló (key=%s, error=%s: %s). Fallback a in-memory.",
            key,
            type(exc).__name__,
            exc,
        )
        _singleton.invalidate()
        return None


def reset_for_tests() -> None:
    """Resetea el singleton. SOLO para tests."""
    _singleton.invalidate()
