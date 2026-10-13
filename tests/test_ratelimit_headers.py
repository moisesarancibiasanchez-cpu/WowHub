"""Tests para HU_41 — Rate limit middleware con headers RFC 6585.

Valida que el middleware responda con los headers X-RateLimit-* en respuestas
exitosas y que aplique 429 con Retry-After al exceder el límite.
"""
import pytest
from fastapi.testclient import TestClient

from app.core.security import RateLimitMiddleware


def _enable_rate_limit(stack):
    """Recorre el ASGI stack y reactiva RateLimitMiddleware (lo opuesto a conftest).

    FIX 2026-10: usa ``type(stack) is RateLimitMiddleware`` en vez de
    ``stack.cls is RateLimitMiddleware`` (las instancias de BaseHTTPMiddleware
    no exponen ``.cls``). Antes la detección era un no-op y el re-enable nunca
    tomaba efecto — los tests fallaban porque el bucket no se vaciaba entre tests.
    """
    if type(stack) is RateLimitMiddleware:
        try:
            stack.enabled = True
            stack.buckets.clear()
        except Exception:
            pass
    inner = getattr(stack, "app", None)
    if inner is not None and inner is not stack:
        _enable_rate_limit(inner)


@pytest.fixture
def ratelimited_client(client):
    """Re-activar RateLimitMiddleware dentro del TestClient."""
    # Re-correr el conftest disabled no afecta al stack ya materializado.
    stack = getattr(client.app, "middleware_stack", None)
    if stack is not None:
        _enable_rate_limit(stack)
    # Limpiar cualquier bucket residual entre tests
    stack = getattr(client.app, "middleware_stack", None)
    if stack is not None:
        def _walk_clear(app_obj):
            if type(app_obj) is RateLimitMiddleware:
                try:
                    app_obj.buckets.clear()
                except Exception:
                    pass
            inner = getattr(app_obj, "app", None)
            if inner is not None and inner is not app_obj:
                _walk_clear(inner)
        _walk_clear(stack)
    return client


def test_login_returns_ratelimit_headers(ratelimited_client):
    """Test 1: Primera respuesta debe tener X-RateLimit-* headers."""
    # El login con credenciales malas retorna 401, pero los headers deben ir.
    r = ratelimited_client.post(
        "/api/v1/auth/login",
        json={"email": "rl-test@x.com", "password": "wrongpass"},
    )
    assert r.headers.get("X-RateLimit-Limit") == "10"
    assert r.headers.get("X-RateLimit-Remaining") == "9"
    assert r.headers.get("X-RateLimit-Reset") == "60"


def test_ratelimit_remaining_decrements(ratelimited_client):
    """Test 2: El remaining decrementa con cada request al bucket."""
    for i in range(5):
        r = ratelimited_client.post(
            "/api/v1/auth/login",
            json={"email": "u@e.com", "password": "x"},
        )
        expected_remaining = str(9 - i)
        assert r.headers.get("X-RateLimit-Remaining") == expected_remaining, (
            f"Iter {i}: expected {expected_remaining}, got {r.headers.get('X-RateLimit-Remaining')}"
        )


def test_register_429_after_limit(ratelimited_client):
    """Test 3: register tiene bucket independiente de 5/60s."""
    # Saturamos el bucket de register (5 req).
    for i in range(5):
        r = ratelimited_client.post(
            "/api/v1/auth/register",
            json={"email": f"r{i}@x.com", "password": "Test1234!", "full_name": "X"},
        )
        # No nos importa el status del negocio, sólo los headers
        assert r.headers.get("X-RateLimit-Limit") == "5"

    # 6ta debe ser 429.
    r = ratelimited_client.post(
        "/api/v1/auth/register",
        json={"email": "r6@x.com", "password": "Test1234!", "full_name": "X"},
    )
    assert r.status_code == 429, r.text
    assert r.headers.get("Retry-After") == "60"
    assert r.headers.get("X-RateLimit-Remaining") == "0"


def test_no_ratelimit_headers_on_non_matched_paths(ratelimited_client):
    """Test 4: Paths no rate-limiteados no llevan headers X-RateLimit-*."""
    r = ratelimited_client.get("/api/v1/tenants/me")
    # 401 porque no hay JWT, pero NO debe tener headers de rate limit.
    assert r.headers.get("X-RateLimit-Limit") is None
