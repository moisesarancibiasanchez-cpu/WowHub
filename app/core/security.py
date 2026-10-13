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

        reset_seconds = int(window)

        if len(self.buckets[key]) >= limit:
            # 429 — el bucket está saturado ANTES de este request.
            logger.warning("Rate limit exceeded for %s on %s", client_ip, path)
            rl_headers = {
                "X-RateLimit-Limit": str(limit),
                # FIXED 2026-10: remaining=0 en 429 (no mostrar el count pre-append
                # porque no se consumió cupo). Antes mostraba `limit` en la
                # primera request porque se computaba antes del append.
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(reset_seconds),
            }
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

        # Consumir el cupo y reportar el estado POST-append para cumplir
        # RFC 6585 / draft-ietf-httpapi-ratelimit-headers (X-RateLimit-Remaining
        # refleja lo que QUEDA tras este request).
        self.buckets[key].append(now)

        # HU_41 — Headers RFC 6585 / draft-ietf-httpapi-ratelimit-headers.
        # Permite al cliente conocer su estado sin esperar el 429.
        remaining = max(0, limit - len(self.buckets[key]))
        rl_headers = {
            "X-RateLimit-Limit": str(limit),
            "X-RateLimit-Remaining": str(remaining),
            "X-RateLimit-Reset": str(reset_seconds),
        }

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


# ──────────────────────────────────────────────────────────────────────
# HU_38 — RBAC Granular con Casbin
# ──────────────────────────────────────────────────────────────────────
# IMPORTANTE: este bloque es APPEND-ONLY. No tocar ``RateLimitMiddleware``
# arriba — fue re-escrito por HU_41 y debe seguir funcionando intacto.
#
# Lo que hace este bloque:
#   * Singleton del Casbin Enforcer (``_get_rbac_enforcer``), con
#     inicialización perezosa para no romper tests sin seed.
#   * Decorator ``@requires_permission(obj, act)`` que aplica RBAC a un
#     endpoint FastAPI. Funciona sobre cualquier endpoint que tenga
#     ``membership`` (TenantMembership) o ``user`` (User) como kwarg.
#   * Helper ``_legacy_check()`` con la matriz hard-coded de roles, usada
#     como fallback cuando Casbin no está disponible.
#   * Invalidación del singleton vía ``_invalidate_rbac_enforcer()`` para
#     que POST/DELETE /rbac/policies tengan efecto inmediato.
#
# Coexistencia:
#   * Casbin (>=1.35,<2) es la única dependencia nueva.
#   * El adapter (``app/core/rbac_adapter.py``) es genérico y no requiere
#     modelos específicos.
# ──────────────────────────────────────────────────────────────────────
import logging
import threading
from typing import TYPE_CHECKING

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

if TYPE_CHECKING:
    from app.models.tenant import TenantMembership
    from app.models.user import User

logger = logging.getLogger("wowhub.rbac.security")

# Lazy-loaded global enforcer (singleton + lock para thread-safety).
_RBAC_ENFORCER = None
_RBAC_LOCK = threading.Lock()

# Modelo legacy hard-coded. Réplica exacta de la matriz del repo antes
# de HU_38 — es la fuente de verdad para el fallback ``_legacy_check()``.
#
# Estructura: { "ROLE": { "obj": { "act": bool } } }. Si ``obj`` o ``act``
# no están presentes, el deny es implícito (default = False).
_LEGACY_ROLE_MATRIX: dict[str, dict[str, dict[str, bool]]] = {
    "SUPERADMIN": {"*": {"*": True}},
    "OWNER":      {"*": {"*": True}},
    "ADMIN": {
        "product":   {"read": True, "write": True, "delete": True},
        "category":  {"read": True, "write": True, "delete": True},
        "order":     {"read": True, "write": True, "delete": True},
        "customer":  {"read": True, "write": True, "delete": True},
        "promotion": {"read": True, "write": True, "delete": True},
        "branch":    {"read": True, "write": True, "delete": True},
        "stats":     {"read": True},
        "loyalty":   {"read": True, "write": True},
        "audit":     {"read": True},
        "settings":  {"read": True, "write": True},
    },
    "STAFF": {
        "product":   {"read": True, "write": True, "delete": False},
        "category":  {"read": True, "write": True, "delete": False},
        "order":     {"read": True, "write": True, "delete": False},
        "customer":  {"read": True, "write": True, "delete": False},
        "promotion": {"read": True, "write": True, "delete": False},
        "branch":    {"read": True},
        "stats":     {"read": True},
        "loyalty":   {"read": True, "write": True},
    },
    "CASHIER": {
        "product":  {"read": True},
        "order":    {"read": True, "write": True, "delete": False},
        "customer": {"read": True, "write": True, "delete": False},
        "loyalty":  {"read": True, "write": True, "delete": False},
    },
    "VIEWER": {
        "product":   {"read": True},
        "category":  {"read": True},
        "order":     {"read": True},
        "customer":  {"read": True},
        "promotion": {"read": True},
        "branch":    {"read": True},
        "stats":     {"read": True},
        "loyalty":   {"read": True},
        "settings":  {"read": True},
    },
}


# ── Helpers de inicialización ─────────────────────────────────────────
def _get_rbac_enforcer():
    """Devuelve el Casbin Enforcer singleton (lazy init).

    Inicialización:
      1) Carga el modelo desde ``app/core/rbac_model.conf``.
      2) Crea el adapter SQLAlchemy apuntando a ``SessionLocal``.
      3) Llama ``enforcer.load_policy()`` para levantar policies y
         groupings de la DB.

    Si Casbin no está disponible (ImportError) o la carga falla
    (DB no inicializada en tests), retorna ``None`` — el decorator
    hace fallback a ``_legacy_check``.
    """
    global _RBAC_ENFORCER
    if _RBAC_ENFORCER is not None:
        return _RBAC_ENFORCER

    with _RBAC_LOCK:
        if _RBAC_ENFORCER is not None:
            return _RBAC_ENFORCER  # type: ignore[unreachable]

        try:
            from casbin.enforcer import Enforcer
            from app.core.rbac_adapter import SQLAlchemyAdapter
            from app.database import SessionLocal
            from pathlib import Path

            model_path = Path(__file__).parent / "rbac_model.conf"
            adapter = SQLAlchemyAdapter(SessionLocal)
            enforcer = Enforcer(str(model_path), adapter)
            _RBAC_ENFORCER = enforcer
            logger.info(
                "rbac.enforcer: inicializado con %d policies",
                len(enforcer.get_policy()),
            )
            return enforcer
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "rbac.enforcer: no se pudo inicializar (%s: %s) — "
                "fallback a legacy",
                type(exc).__name__,
                exc,
            )
            return None


def _invalidate_rbac_enforcer() -> None:
    """Invalida el singleton — útil cuando cambia la DB de policies.

    La próxima llamada a ``_get_rbac_enforcer()`` re-inicializa y
    re-carga ``load_policy()``.
    """
    global _RBAC_ENFORCER
    with _RBAC_LOCK:
        _RBAC_ENFORCER = None


# ── Legacy check (fallback) ───────────────────────────────────────────
def _legacy_check(role: str, obj: str, act: str) -> bool:
    """Evalúa la matriz legacy hard-coded.

    Retorna True si el rol tiene permiso (obj, act).
    """
    role = (role or "").upper()
    rules = _LEGACY_ROLE_MATRIX.get(role, {})

    # 1) Match exacto obj/act.
    obj_rules = rules.get(obj, {})
    if obj_rules.get(act) is True:
        return True

    # 2) Match ``obj='*'`` (role permite todo sobre cualquier obj).
    if rules.get("*", {}).get(act) is True:
        return True

    # 3) Match ``act='*'`` (role permite cualquier act sobre el obj).
    if obj_rules.get("*") is True:
        return True

    # 4) Match ``obj='*' act='*'`` (ej. OWNER/SUPERADMIN).
    if rules.get("*", {}).get("*") is True:
        return True

    return False


# ── Decorador ─────────────────────────────────────────────────────────
def _resolve_subject_and_domain(args: tuple, kwargs: dict) -> tuple[str, str]:
    """Extrae ``(subject, dom)`` de los kwargs del endpoint.

    Busca ``membership`` (TenantMembership) o ``user`` (User) en ese
    orden. Si no encuentra ninguno, retorna ``("", "")`` y el caller
    retorna 401 limpio.

    Retorna:
      * subject: ``"role:<UPPER>"`` (formato Casbin)
      * dom: ``tenant_id`` del membership o ``"*"`` si no hay.
    """
    membership = kwargs.get("membership")
    user = kwargs.get("user")

    role_value = ""
    dom = "*"

    if membership is not None:
        # ``role`` puede ser enum o string.
        role = getattr(membership, "role", None)
        if role is not None:
            role_value = getattr(role, "value", str(role)).upper()
        tid = getattr(membership, "tenant_id", None)
        if tid:
            dom = str(tid)
    elif user is not None:
        # Si no hay membership, el ``user`` manda — usamos default_role.
        # Esto pasa en endpoints cross-tenant (e.g. /superadmin/...).
        role = getattr(user, "default_role", None) or getattr(user, "role", None)
        if role is not None:
            role_value = getattr(role, "value", str(role)).upper()

    subject = f"role:{role_value}" if role_value else ""
    return subject, dom


def requires_permission(obj: str, act: str):
    """Decorator FastAPI: aplica RBAC al endpoint.

    Uso::

        @router.post("/tenants/{tenant_id}/products")
        @requires_permission("product", "write")
        async def create_product(
            tenant_id: UUID,
            payload: ProductIn,
            membership: TenantMembership = Depends(get_current_membership),
        ):
            ...

    Reglas:
      * ``membership`` o ``user`` deben aparecer en los kwargs (FastAPI
        los inyecta via ``Depends(...)``). Si no están, 401.
      * Si ``user.is_superuser`` → bypass total (return sin check).
      * Si Casbin está inicializado → ``enforce(subject, dom, obj, act)``.
      * Si Casbin falla o no está disponible → ``_legacy_check(role, obj, act)``.

    Para acciones "delete" usar ``act='delete'``. Wildcards ``"*"``
    en ``obj`` o ``act`` también son válidos.
    """
    import functools
    from app.core.errors import ForbiddenError, UnauthorizedError

    def _decorator(fn):
        @functools.wraps(fn)
        async def _async_wrapper(*args, **kwargs):
            return await _check_and_call(fn, args, kwargs, obj, act)

        @functools.wraps(fn)
        def _sync_wrapper(*args, **kwargs):
            return _check_and_call_sync(fn, args, kwargs, obj, act)

        import inspect
        if inspect.iscoroutinefunction(fn):
            return _async_wrapper
        return _sync_wrapper

    return _decorator


async def _check_and_call(fn, args, kwargs, obj, act):
    from app.core.errors import ForbiddenError, UnauthorizedError

    # 1) Bypass para superusers.
    user = kwargs.get("user")
    if user is not None and getattr(user, "is_superuser", False):
        return await fn(*args, **kwargs)

    # 2) Resolver subject + dom.
    subject, dom = _resolve_subject_and_domain(args, kwargs)
    if not subject:
        raise UnauthorizedError(
            "Endpoint protegido por RBAC requiere 'membership' o 'user'"
        )

    # 3) Evaluar Casbin (con fallback a legacy).
    allowed = _enforce_with_fallback(subject, dom, obj, act)
    if not allowed:
        logger.info(
            "rbac.requires_permission: deny sub=%s dom=%s obj=%s act=%s",
            subject, dom, obj, act,
        )
        raise ForbiddenError(
            f"Permiso denegado: {subject} no puede '{act}' sobre '{obj}'"
        )

    return await fn(*args, **kwargs)


def _check_and_call_sync(fn, args, kwargs, obj, act):
    from app.core.errors import ForbiddenError, UnauthorizedError

    user = kwargs.get("user")
    if user is not None and getattr(user, "is_superuser", False):
        return fn(*args, **kwargs)

    subject, dom = _resolve_subject_and_domain(args, kwargs)
    if not subject:
        raise UnauthorizedError(
            "Endpoint protegido por RBAC requiere 'membership' o 'user'"
        )

    allowed = _enforce_with_fallback(subject, dom, obj, act)
    if not allowed:
        raise ForbiddenError(
            f"Permiso denegado: {subject} no puede '{act}' sobre '{obj}'"
        )

    return fn(*args, **kwargs)


def _enforce_with_fallback(subject: str, dom: str, obj: str, act: str) -> bool:
    """Llama a Casbin; si falla, cae a ``_legacy_check``.

    Retorna True si el permiso está permitido.
    """
    enforcer = _get_rbac_enforcer()
    if enforcer is not None:
        try:
            return bool(enforcer.enforce(subject, dom, obj, act))
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "rbac.enforce: falló sub=%s dom=%s obj=%s act=%s (%s) — "
                "fallback a legacy",
                subject, dom, obj, act, exc,
            )

    # Fallback: extraer role del subject y usar matriz legacy.
    role = subject.replace("role:", "", 1) if subject.startswith("role:") else subject
    return _legacy_check(role, obj, act)
