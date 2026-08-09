"""Audit middleware — registra todas las llamadas a la API."""
import logging
import time
from typing import Optional

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.tenant_context import get_tenant
from app.database import SessionLocal
from app.services.audit_service import AuditService

logger = logging.getLogger("wowhub.audit")


class AuditMiddleware(BaseHTTPMiddleware):
    """Registra cada request a la API con método, path, status, duración.

    Solo audita paths bajo /api/ y excluye health/docs.
    """

    EXCLUDED_PATHS = {"/health", "/docs", "/redoc", "/openapi.json"}

    def __init__(self, app, enabled: bool = True):
        super().__init__(app)
        self.enabled = enabled

    async def dispatch(self, request: Request, call_next):
        if not self.enabled or not request.url.path.startswith("/api/"):
            return await call_next(request)
        if request.url.path in self.EXCLUDED_PATHS:
            return await call_next(request)

        start = time.time()
        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception as exc:
            status_code = 500
            logger.exception("Error en request: %s", exc)
            raise
        finally:
            duration = time.time() - start
            # Log asíncrono (no bloquea el response)
            try:
                self._log_async(
                    request=request,
                    status_code=status_code,
                    duration=duration,
                )
            except Exception as e:
                logger.warning("No se pudo escribir audit log: %s", e)
        return response

    def _log_async(self, request: Request, status_code: int, duration: float):
        """Escribe el log en una sesión separada (no afecta el request)."""
        from app.deps import get_current_user_optional

        tenant_id = request.headers.get("X-Tenant-Id")
        if not tenant_id:
            return  # No loguear requests sin tenant (login, health, etc.)

        # Resolver user (opcional) sin cortar el flujo si falla.
        actor = None
        try:
            with SessionLocal() as _db:
                actor = get_current_user_optional(
                    authorization=request.headers.get("authorization"),
                    db=_db,
                )
        except Exception:
            actor = None

        with SessionLocal() as db:
            audit = AuditService(db)
            audit.log(
                tenant_id=tenant_id,
                actor=actor,
                action=f"{request.method.lower()}.{request.url.path.replace('/', '.')}",
                method=request.method,
                path=str(request.url.path),
                ip=self._client_ip(request),
                user_agent=request.headers.get("user-agent", "")[:500],
                status_code=status_code,
                extra={"duration_ms": int(duration * 1000)},
            )

    @staticmethod
    def _client_ip(request: Request) -> str:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"
