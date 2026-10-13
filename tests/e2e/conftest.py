"""Conftest para tests E2E (Playwright).

Los tests E2E NO usan la DB en memoria del conftest principal — apuntan
a un servidor WowHub real (``--base-url``). Por eso:

  1. Hacemos autouse=False y solo lo aplicamos a tests con @pytest.mark.e2e
  2. NO importamos ``app.main`` ni tocamos la DB local
  3. Usamos email/tenant únicos por test (uuid4) para no colisionar entre runs

Uso:
    pip install -e ".[e2e]"
    playwright install chromium
    pytest tests/e2e -m e2e --base-url=https://wowhub-app.up.railway.app
"""
from __future__ import annotations

import os
import uuid
from typing import Any

import pytest

# ── Skip limpio si pytest-playwright no está instalado ──────────
# El plugin ``pytest-playwright`` provee los fixtures ``page``, ``browser``,
# ``playwright`` y ``browser_context_args`` que los tests e2e necesitan.
# Si el plugin (o la lib ``playwright``) faltan, los tests e2e NO pueden
# correr; en lugar de explotar con "fixture 'page' not found" durante la
# collection, los marcamos como SKIP con un mensaje claro.
try:
    import playwright.sync_api  # noqa: F401
    import pytest_playwright  # noqa: F401  (registra los fixtures)
    _E2E_DEPS_AVAILABLE = True
    _E2E_SKIP_REASON = None
except ImportError as e:
    _E2E_DEPS_AVAILABLE = False
    _E2E_SKIP_REASON = (
        "E2E tests requieren playwright + pytest-playwright. "
        "Instalá con: `pip install -e .[e2e] && playwright install chromium`"
    )


def pytest_collection_modifyitems(config, items):
    """Si las deps e2e no están, marca todos los tests con marker ``e2e`` como skip."""
    if _E2E_DEPS_AVAILABLE:
        return
    skip_marker = pytest.mark.skip(reason=_E2E_SKIP_REASON)
    for item in items:
        if "e2e" in item.keywords:
            item.add_marker(skip_marker)


# ── Imports opcionales del plugin (solo si está disponible) ─────
if _E2E_DEPS_AVAILABLE:
    from playwright.sync_api import (  # noqa: E402
        Browser,
        BrowserContext,
        Page,
        Playwright,
        sync_playwright,
    )


# ── Helpers ─────────────────────────────────────────────────────
def _unique_id() -> str:
    """Genera un identificador único para que tests paralelos no chochen."""
    return uuid.uuid4().hex[:10]


# ── Fixtures ────────────────────────────────────────────────────
@pytest.fixture(scope="session")
def base_url(request) -> str:
    """URL base del WowHub bajo test. Default: http://localhost:8000.

    Se sobreescribe con ``--base-url=https://...`` (provisto por pytest-playwright).
    """
    return request.config.getoption("--base-url", default="http://localhost:8000")


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args: dict) -> dict:
    """Default browser context: viewport razonable + locale es-CL (formato CLP)."""
    return {
        **browser_context_args,
        "viewport": {"width": 1280, "height": 800},
        "locale": "es-CL",
        "timezone_id": "America/Santiago",
    }


@pytest.fixture
def tenant_slug() -> str:
    """Slug único por test."""
    return f"e2e-{_unique_id()}"


@pytest.fixture
def owner_email() -> str:
    """Email único por test."""
    return f"e2e-{_unique_id()}@wowhub-test.com"


@pytest.fixture
def owner_password() -> str:
    """Password determinístico (no random, para poder revisar logs en CI)."""
    return "E2EPass1234!"


@pytest.fixture
def api_request_context(playwright: Playwright, base_url: str):
    """Contexto HTTP para hablarle a la API directo (sin browser)."""
    ctx = playwright.request.new_context(base_url=base_url)
    yield ctx
    ctx.dispose()


@pytest.fixture
def registered_owner(api_request_context, owner_email: str, owner_password: str, tenant_slug: str) -> dict[str, Any]:
    """Crea un owner + tenant via API y devuelve {access, refresh, user, tenant}."""
    r = api_request_context.post(
        "/api/v1/auth/register",
        data={
            "email": owner_email,
            "password": owner_password,
            "full_name": f"E2E Owner {tenant_slug}",
            "create_tenant": True,
            "tenant_legal_name": f"E2E Test {tenant_slug}",
            "tenant_slug": tenant_slug,
        },
        headers={"Content-Type": "application/json"},
    )
    assert r.ok, f"register falló: {r.status} {r.text()}"
    data = r.json()
    return {
        "access": data["access_token"],
        "refresh": data["refresh_token"],
        "user": data["user"],
        "tenant_id": data["current_tenant"]["tenant_id"],
        "tenant_slug": tenant_slug,
    }


@pytest.fixture
def authed_page(page: Page, base_url: str, registered_owner: dict, api_request_context) -> Page:
    """Page con tokens del owner ya inyectados en localStorage.

    No navega al dashboard todavía — el test decide a dónde ir.
    """
    # Visitamos primero cualquier página del mismo origen para tener acceso
    # a localStorage.
    page.goto(f"{base_url}/login")
    # Inyectamos los tokens.
    payload = {
        "access_token": registered_owner["access"],
        "refresh_token": registered_owner["refresh"],
        "user": registered_owner["user"],
        "current_tenant": {
            "tenant_id": registered_owner["tenant_id"],
            "tenant_slug": registered_owner["tenant_slug"],
        },
    }
    import json
    page.evaluate(f"localStorage.setItem('wowhub.tokens', {json.dumps(json.dumps(payload))})")
    return page
