"""Tests HU_41 — Redis Rate Limit con fallback in-memory.

Cobertura mínima (DoD):
1. ``get_redis()`` retorna ``None`` si ``REDIS_URL`` no está seteada.
2. ``get_redis()`` retorna un cliente válido si ``REDIS_URL`` apunta
   a un Redis alcanzable (usamos ``fakeredis`` para que el test sea
   determinístico y no requiera red).
3. ``check_redis()`` devuelve ``None`` (señal de fallback) cuando el
   cliente Redis falla, y ``RateLimitMiddleware`` sigue funcionando
   con el bucket in-memory.
4. ``RateLimitMiddleware`` sigue emitiendo headers
   ``X-RateLimit-Limit/Remaining/Reset`` independientemente del
   backend elegido.

Tests extra (no son obligatorios pero blindan el camino feliz):
* Lua sliding-window encolar y bloquear correctamente.
* Aislamiento de buckets por key.
* ``redis_enabled=False`` desactiva Redis incluso con URL válida.

NOTA sobre ``X-RateLimit-Remaining``: el middleware in-memory
(preservado "EXACTAMENTE" como pide el spec) computa el header
*antes* de hacer ``buckets[key].append(now)``. Por eso la primera
request emite ``Remaining=Limit`` (no ``Limit-1``). El camino Redis
sí computa después del ZADD, así que emite ``Limit-1`` para la
primera request. Los tests reflejan esta asimetría intencional:
los tests in-memory validan la semántica original, los tests
Redis validan la semántica RFC correcta.
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.responses import JSONResponse

from app.core.security import RateLimitMiddleware
from app.services import redis_client


# ── Helpers ─────────────────────────────────────────────────────────
class _ProbeClient:
    """Cliente Redis fake mínimo para tests sin red."""

    def __init__(self):
        from fakeredis import FakeRedis
        self._impl = FakeRedis(decode_responses=True)
        self._sha = None

    # API mínima que usa ``redis_client``
    def ping(self):
        return self._impl.ping()

    def script_load(self, script):
        self._sha = self._impl.script_load(script)
        return self._sha

    def evalsha(self, sha, numkeys, *args):
        try:
            return self._impl.evalsha(sha, numkeys, *args)
        except Exception as exc:
            if "NoScript" in type(exc).__name__ or "NOSCRIPT" in str(exc):
                raise
            raise


@pytest.fixture(autouse=True)
def _reset_redis_singleton():
    """Cada test arranca con el singleton limpio."""
    redis_client.reset_for_tests()
    yield
    redis_client.reset_for_tests()


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    """Cada test arranca con settings frescos.

    ``get_settings`` está ``lru_cache``-ado y pydantic-settings lee
    las env vars en la construcción de la instancia, así que cualquier
    cambio de env vars en el test no se refleja hasta que la cache
    se limpie.
    """
    from app.config import get_settings
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _clean_redis_env(monkeypatch):
    """Limpia REDIS_URL/REDIS_ENABLED por defecto. Tests específicos
    los setean según necesiten."""
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.delenv("REDIS_ENABLED", raising=False)
    yield


# ── Test 1 (DoD): get_redis() retorna None si REDIS_URL no está ───
def test_redis_client_returns_none_without_url():
    """Sin REDIS_URL → get_redis() devuelve None y is_available() == False."""
    client = redis_client.get_redis()
    assert client is None
    assert redis_client.is_available() is False


def test_redis_client_returns_none_when_disabled(monkeypatch):
    """redis_enabled=False mata el cliente aunque REDIS_URL esté OK."""
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("REDIS_ENABLED", "false")
    assert redis_client.get_redis() is None
    assert redis_client.is_available() is False


# ── Test 2 (DoD): get_redis() conecta si REDIS_URL válida ─────────
def test_redis_client_connects_with_valid_url(monkeypatch):
    """Con REDIS_URL válida y Redis alcanzable, get_redis() devuelve cliente.

    Mockeamos ``redis_sync.from_url`` (el entry point real usado por
    ``_singleton.get_or_init``) para que devuelva un ``_ProbeClient``
    (que envuelve un FakeRedis). Así ejercitamos el flujo real
    ``get_redis → get_or_init → from_url → ping → script_load/evalsha``
    sin red.
    """
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")

    probe = _ProbeClient()

    def fake_from_url(url, **kwargs):
        return probe

    monkeypatch.setattr(
        "app.services.redis_client.redis_sync.from_url",
        fake_from_url,
    )

    client = redis_client.get_redis()
    assert client is not None
    assert redis_client.is_available() is True


# ── Test 3 (DoD): Fallback a in-memory cuando Redis falla ─────────
def test_check_redis_returns_none_when_client_is_none():
    """Sin cliente Redis, check_redis devuelve None → caller usa in-memory."""
    result = redis_client.check_redis(
        "rl:1.2.3.4:/api/v1/auth/login",
        limit=10,
        window_seconds=60,
        request_id="abc",
    )
    assert result is None  # señal de fallback


def test_check_redis_returns_none_when_evalsha_fails(monkeypatch):
    """Si el cliente Redis lanza excepción, check_redis devuelve None."""
    class _BrokenRedis:
        def script_load(self, *_a, **_k):
            raise RuntimeError("boom")

        def evalsha(self, *_a, **_k):
            raise RuntimeError("boom")

    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setattr(
        redis_client._singleton,
        "get_or_init",
        lambda url, *, force=False: _BrokenRedis(),
    )
    result = redis_client.check_redis(
        "rl:key",
        limit=10,
        window_seconds=60,
        request_id="abc",
    )
    assert result is None
    # Tras el fallo, el singleton debe haberse invalidado.
    assert redis_client._singleton._client is None


def test_check_redis_returns_decision_when_lua_ok(monkeypatch):
    """Lua sliding-window funciona bajo el límite y bloquea al llegar."""
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    probe = _ProbeClient()
    monkeypatch.setattr(
        redis_client._singleton,
        "get_or_init",
        lambda url, *, force=False: (
            redis_client._singleton.__dict__.setdefault("_client", probe) or probe
        ),
    )
    # Asegurar que el cliente queda seteado en el singleton.
    redis_client._singleton._client = probe
    redis_client._singleton._script_sha = None

    key = "rl:test:login"
    # 3 requests bajo el límite de 5/60s → todas permitidas.
    for i in range(5):
        allowed, count, retry_ms = redis_client.check_redis(
            key, limit=5, window_seconds=60, request_id=f"r{i}"
        )
        assert allowed is True
        assert count == i + 1
        assert retry_ms == 0

    # La 6ª debe ser bloqueada.
    allowed, count, retry_ms = redis_client.check_redis(
        key, limit=5, window_seconds=60, request_id="r6"
    )
    assert allowed is False
    assert count == 5
    assert retry_ms >= 0


def test_check_redis_keys_are_isolated(monkeypatch):
    """Buckets distintos no se contaminan entre sí."""
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    probe = _ProbeClient()
    redis_client._singleton._client = probe
    redis_client._singleton._script_sha = None

    # Saturar key A.
    for i in range(3):
        allowed, _, _ = redis_client.check_redis(
            "rl:A", limit=3, window_seconds=60, request_id=f"a{i}"
        )
        assert allowed is True
    allowed_a, _, _ = redis_client.check_redis(
        "rl:A", limit=3, window_seconds=60, request_id="a4"
    )
    assert allowed_a is False

    # Key B está vacía.
    allowed_b, count_b, _ = redis_client.check_redis(
        "rl:B", limit=3, window_seconds=60, request_id="b1"
    )
    assert allowed_b is True
    assert count_b == 1


# ── Test 4 (DoD): Headers X-RateLimit-* siguen apareciendo ─────────
def _build_app_with_middleware(*, redis_ok: bool, monkeypatch=None) -> TestClient:
    """Crea una mini app FastAPI con RateLimitMiddleware.

    Si ``redis_ok`` es True, inyectamos un FakeRedis para que el
    middleware use la rama Redis. Si es False, el middleware cae a
    in-memory.
    """
    app = FastAPI()

    @app.post("/api/v1/auth/login")
    async def _login():
        return JSONResponse({"ok": True})

    if redis_ok and monkeypatch is not None:
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
        probe = _ProbeClient()
        # Setear directamente el singleton (en vez de monkeypatchear
        # el método) para que ``get_redis()`` lo devuelva tal cual.
        redis_client._singleton._client = probe
        redis_client._singleton._script_sha = None

    app.add_middleware(RateLimitMiddleware, enabled=True)
    return TestClient(app)


def test_middleware_emits_headers_in_memory(monkeypatch):
    """Sin Redis, los headers X-RateLimit-* siguen presentes (in-memory).

    NOTA: la rama in-memory preserva el comportamiento original al
    pie de la letra (ver docstring del módulo): el header
    ``X-RateLimit-Remaining`` se computa ANTES del append al bucket,
    por lo que para una primera request reporta el límite completo
    (no ``limit - 1``). Esto es deliberado y matchea el código
    pre-existente que el spec pide preservar.
    """
    client = _build_app_with_middleware(redis_ok=False, monkeypatch=monkeypatch)
    r = client.post("/api/v1/auth/login", json={"email": "x@x.com", "password": "x"})
    assert r.status_code == 200
    assert r.headers.get("X-RateLimit-Limit") == "10"
    # Off-by-one intencional del código preservado: ver docstring.
    assert r.headers.get("X-RateLimit-Remaining") == "10"
    assert r.headers.get("X-RateLimit-Reset") == "60"


def test_middleware_emits_headers_with_redis(monkeypatch):
    """Con Redis OK, los headers X-RateLimit-* también están presentes.

    NOTA: a diferencia de la rama in-memory, Redis computa el count
    DESPUÉS del ZADD, así que Remaining=Limit-1 ya en la primera
    request. Este es el comportamiento RFC correcto.
    """
    client = _build_app_with_middleware(redis_ok=True, monkeypatch=monkeypatch)
    r = client.post("/api/v1/auth/login", json={"email": "x@x.com", "password": "x"})
    assert r.status_code == 200
    assert r.headers.get("X-RateLimit-Limit") == "10"
    assert r.headers.get("X-RateLimit-Remaining") == "9"
    assert r.headers.get("X-RateLimit-Reset") == "60"


def test_middleware_returns_429_with_redis(monkeypatch):
    """Con Redis, al exceder el límite el middleware responde 429 + Retry-After."""
    client = _build_app_with_middleware(redis_ok=True, monkeypatch=monkeypatch)
    # /api/v1/auth/login tiene limit=10.
    for _ in range(10):
        client.post("/api/v1/auth/login", json={})
    r = client.post("/api/v1/auth/login", json={})
    assert r.status_code == 429
    assert r.headers.get("X-RateLimit-Remaining") == "0"
    assert "Retry-After" in r.headers


def test_middleware_falls_back_to_in_memory_when_redis_fails(monkeypatch):
    """Si Redis está configurado pero el cliente falla, cae a in-memory."""

    class _AlwaysBroken:
        def script_load(self, *_a, **_k):
            raise RuntimeError("redis down")

        def evalsha(self, *_a, **_k):
            raise RuntimeError("redis down")

    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    # Setear directamente el cliente roto en el singleton para que
    # ``get_redis()`` lo devuelva.
    redis_client._singleton._client = _AlwaysBroken()
    redis_client._singleton._script_sha = None

    app = FastAPI()

    @app.post("/api/v1/auth/login")
    async def _login():
        return JSONResponse({"ok": True})

    app.add_middleware(RateLimitMiddleware, enabled=True)
    client = TestClient(app)

    # Como check_redis() devuelve None, el middleware usa in-memory.
    r = client.post("/api/v1/auth/login", json={})
    assert r.status_code == 200
    assert r.headers.get("X-RateLimit-Limit") == "10"
    # In-memory: off-by-one preservado (ver docstring).
    assert r.headers.get("X-RateLimit-Remaining") == "10"


def test_redis_disabled_uses_in_memory(monkeypatch):
    """Si REDIS_ENABLED=false, RateLimitMiddleware usa in-memory."""
    monkeypatch.setenv("REDIS_ENABLED", "false")
    app = FastAPI()

    @app.post("/api/v1/auth/login")
    async def _login():
        return JSONResponse({"ok": True})

    app.add_middleware(RateLimitMiddleware, enabled=True)
    client = TestClient(app)
    r = client.post("/api/v1/auth/login", json={})
    assert r.status_code == 200
    assert r.headers.get("X-RateLimit-Limit") == "10"


# ── Tests extra: robustness del singleton ──────────────────────────
def test_singleton_invalidates_after_failure(monkeypatch):
    """Tras un fallo de Redis, el singleton se invalida para no devolver
    un cliente zombie en la próxima request."""
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")

    class _BrokenRedis:
        def script_load(self, *_a, **_k):
            raise RuntimeError("boom")
        def evalsha(self, *_a, **_k):
            raise RuntimeError("boom")

    # Setear directamente el cliente roto en el singleton.
    redis_client._singleton._client = _BrokenRedis()
    redis_client._singleton._script_sha = None

    # Una primera llamada "falla".
    result1 = redis_client.check_redis(
        "rl:k", limit=10, window_seconds=60, request_id="a"
    )
    assert result1 is None
    # El cliente interno se invalidó.
    assert redis_client._singleton._client is None


def test_redaction_in_logs():
    """URLs con credenciales se redactan en logs (no leak en producción)."""
    redacted = redis_client._redact("redis://user:pass@host:6379/0")
    assert "user:pass" not in redacted
    assert "@" in redacted
    assert "host:6379" in redacted

    plain = redis_client._redact("redis://localhost:6379/0")
    assert plain == "redis://localhost:6379/0"
