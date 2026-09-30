"""Rate limiting middleware — protección contra abuso en endpoints sensibles."""
import logging
import time
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


class RateLimitMiddleware(BaseHTTPMiddleware):
    """In-memory rate limiter. Para producción multi-instancia usar Redis."""

    def __init__(self, app, enabled: bool = True):
        super().__init__(app)
        self.enabled = enabled
        # key = (ip, path_pattern) -> [timestamps]
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
        key = (client_ip, matched_pattern)
        now = time.time()

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
