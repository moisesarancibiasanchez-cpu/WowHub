"""Rate limiting middleware — protección contra abuso en endpoints sensibles.

HU_41: si Redis está disponible, usa sliding-window log atómico vía
Lua para que el límite sea compartido entre los pods de Railway (sin
esto, con N pods el límite efectivo se multiplica por N). Si Redis no
está disponible (sin ``REDIS_URL`` configurado, conexión caída, etc.),
cae transparente al bucket in-memory — el código original intacto, así
no rompemos dev ni degradamos producción si Redis se cae a mitad del
día.
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections import defaultdict
from typing import Optional

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("wowhub.ratelimit")

# Configuración por defecto
DEFAULT_LIMITS = {
    "/api/v1/auth/login": (10, 60),         # 10 req / 60s
    "/api/v1/auth/register": (5, 60),       # 5 req / 60s
    "/api/v1/auth/forgot-password": (3, 300),  # 3 req / 5 min
    "/api/v1/auth/reset-password": (10, 60),
    "/api/v1/public/t/.*/orders": (20, 60), # 20 orders / min
    # Loyalty — anti-abuso en endpoints sensibles
    "/api/v1/loyalty/scan": (60, 60),                  # 60 scans / min / IP
    "/api/v1/loyalty/c/.*/register": (5, 60),          # 5 altas / min / IP
    "/api/v1/tenants/.*/loyalty/campaigns/.*/qr-token": (20, 60),  # 20 tokens / min
}


def _run_redis_check(key: str, limit: int, window_s: int, request_id: str):
    """Helper sincrónico que llama a ``check_redis``.

    Vive fuera de la clase para que sea fácil mockearlo en tests.
    Importamos acá (no arriba) para no introducir import-time
    failures si Redis no está instalado: el módulo
    ``app.services.redis_client`` es defensivo y maneja ImportError.
    """
    from app.services.redis_client import check_redis
    return check_redis(
        key,
        limit=limit,
        window_seconds=window_s,
        request_id=request_id,
    )


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limiter con Redis (sliding window) + fallback in-memory.

    Comportamiento por defecto (compatible con la versión anterior):

    * Si ``self.enabled`` es False → passthrough total.
    * Si Redis está disponible → usa Lua sliding-window log atómico
      (un solo round-trip por request).
    * Si Redis no está disponible → usa el bucket in-memory
      ``self.buckets`` (dict de timestamps por ``(ip, pattern)``).
    * En ambos casos emite headers ``X-RateLimit-Limit/Remaining/Reset``
      y ``Retry-After`` cuando corresponde.

    La rama Redis se ejecuta en un ``ThreadPoolExecutor`` (vía
    ``asyncio.to_thread``) para no bloquear el event loop. El
    fallback in-memory se mantiene EXACTAMENTE igual al código
    anterior — sólo extrajimos la lógica a ``_check_in_memory``
    para mantener ``dispatch`` legible.
    """

    def __init__(self, app, enabled: bool = True):
        super().__init__(app)
        self.enabled = enabled
        # key = (ip, path_pattern) -> [timestamps] (fallback)
        self.buckets: dict[tuple, list[float]] = defaultdict(list)
        # Limpiar buckets viejos cada 100 req
        self._last_cleanup = time.time()

    async def dispatch(self, request: Request, call_next):
        if not self.enabled:
            return await call_next(request)

        path = request.url.path
        method = request.method

        # Solo aplicar a paths que matchean
        matched_limit = None
        matched_pattern = None
        for pattern, (limit, window) in DEFAULT_LIMITS.items():
            if self._match(path, pattern):
                matched_limit = (limit, window)
                matched_pattern = pattern
                break

        if matched_limit is None:
            return await call_next(request)

        limit, window = matched_limit
        client_ip = self._client_ip(request)
        redis_key = f"rl:{client_ip}:{matched_pattern}"
        now = time.time()

        # ── 1) Intentar Redis (sliding window log atómico) ─────────
        # Devuelve ``None`` si Redis no está disponible ⇒ fallback.
        redis_result: Optional[tuple[bool, int, int]] = None
        try:
            redis_result = await asyncio.to_thread(
                _run_redis_check,
                redis_key,
                limit,
                window,
                uuid.uuid4().hex,
            )
        except Exception as exc:  # noqa: BLE001 — defensivo
            # to_thread podría fallar si el loop está cerrado durante
            # shutdown. Tratamos como "Redis no disponible".
            logger.warning(
                "RateLimit: error ejecutando Redis en thread (error=%s: %s). "
                "Fallback a in-memory.",
                type(exc).__name__,
                exc,
            )
            redis_result = None

        if redis_result is not None:
            allowed, count, retry_after_ms = redis_result
            # Headers consistentes con la rama in-memory.
            remaining = max(0, limit - count)
            reset_seconds = int(window)
            rl_headers = {
                "X-RateLimit-Limit": str(limit),
                "X-RateLimit-Remaining": str(remaining),
                "X-RateLimit-Reset": str(reset_seconds),
            }
            if not allowed:
                # retry_after_ms → segundos (redondeo hacia arriba).
                retry_after_s = max(1, (retry_after_ms + 999) // 1000)
                logger.warning(
                    "Rate limit exceeded for %s on %s (Redis)", client_ip, path
                )
                return JSONResponse(
                    status_code=429,
                    content={
                        "detail": "Demasiadas solicitudes. Intenta de nuevo en un momento.",
                        "retry_after": retry_after_s,
                    },
                    headers={
                        **rl_headers,
                        "Retry-After": str(retry_after_s),
                    },
                )
            response = await call_next(request)
            try:
                for hk, hv in rl_headers.items():
                    response.headers[hk] = hv
            except Exception:
                # Algunos tipos de respuesta (p.ej. StreamingResponse)
                # son inmutables.
                pass
            return response

        # ── 2) Fallback in-memory (código original, sin cambios) ──
        return await self._dispatch_in_memory(
            request, call_next, limit, window, client_ip, matched_pattern, path, now
        )

    async def _dispatch_in_memory(
        self,
        request: Request,
        call_next,
        limit: int,
        window: int,
        client_ip: str,
        matched_pattern: str,
        path: str,
        now: float,
    ):
        """Rama in-memory: idéntica al comportamiento anterior.

        Extraída a un método aparte para mantener ``dispatch``
        legible y para que ``_check_in_memory`` sea fácilmente
        testeable sin levantar el middleware completo.
        """
        key = (client_ip, matched_pattern)

        # Limpiar entradas antiguas
        self.buckets[key] = [t for t in self.buckets[key] if t > now - window]

        # HU_41 — Headers RFC 6585 / draft-ietf-httpapi-ratelimit-headers.
        # Permite al cliente conocer su estado sin esperar el 429.
        remaining = max(0, limit - len(self.buckets[key]))
        reset_seconds = int(window)
        rl_headers = {
            "X-RateLimit-Limit": str(limit),
            "X-RateLimit-Remaining": str(remaining),
            "X-RateLimit-Reset": str(reset_seconds),
        }

        if len(self.buckets[key]) >= limit:
            logger.warning("Rate limit exceeded for %s on %s", client_ip, path)
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Demasiadas solicitudes. Intenta de nuevo en un momento.",
                    "retry_after": window,
                },
                headers={
                    **rl_headers,
                    "Retry-After": str(window),
                },
            )

        self.buckets[key].append(now)

        # Cleanup periódico
        if now - self._last_cleanup > 300:
            self._cleanup()
            self._last_cleanup = now

        response = await call_next(request)
        # Propagar los headers al cliente en respuestas 2xx/4xx que no sean 429.
        try:
            for hk, hv in rl_headers.items():
                response.headers[hk] = hv
        except Exception:
            # Algunos tipos de respuesta (p.ej. StreamingResponse) son inmutables.
            pass
        return response

    @staticmethod
    def _match(path: str, pattern: str) -> bool:
        import re
        return bool(re.match(f"^{pattern}$", path))

    @staticmethod
    def _client_ip(request: Request) -> str:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    def _cleanup(self):
        now = time.time()
        keys_to_remove = []
        for key, timestamps in self.buckets.items():
            self.buckets[key] = [t for t in timestamps if t > now - 600]
            if not self.buckets[key]:
                keys_to_remove.append(key)
        for key in keys_to_remove:
            del self.buckets[key]
