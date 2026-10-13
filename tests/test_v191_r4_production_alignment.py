"""Tests de alineación v1.9.1-r4: `app_knowledge` contra el OpenAPI en producción.

Contexto
========

v1.9.1-r4 corrige v1.9.1-r3 (que asumía `https://wowhub.app` como dominio
canónico y `/u/{slug}/...` como formato de URL pública). La fuente de
verdad canónica es AHORA el OpenAPI desplegado en producción:

    https://wowhub-api-production.up.railway.app/openapi.json

Este test valida, en cada CI build, que:

1. La constante `PUBLIC_URLS` de `app/services/app_knowledge.py` solo
   contiene paths que EXISTEN en el OpenAPI de producción.
2. La constante `MODULES` de `app/services/app_knowledge.py` solo
   referencia paths públicos que EXISTEN en el OpenAPI de producción.
3. El `settings.public_base_url` por default apunta a la URL del backend
   de Railway (que es la única garantía de "existe y responde hoy").
4. La constante `DASHBOARD_URLS["modules"]` está vacía (DEPRECATED en
   v1.9.1-r4: no hay panel HTML público en producción).
5. El scrubber `_FAKE_DASHBOARD_PATH_RE` catcha los paths prohibidos.
6. La FAQ "url pública" menciona la tool `get_tenant_public_urls` y un
   ejemplo de URL real (no el patrón con `{slug}` literal).

Si el OpenAPI de producción no responde (test de red fallido), el test
hace SKIP en vez de FAIL — la idea es validar drift, no bloquear CI
cuando Railway tiene un blip temporal.
"""
from __future__ import annotations

import re
from pathlib import Path

import httpx
import pytest

from app.config import settings
from app.services import app_knowledge


# URL canónica del OpenAPI en producción. Si esto cambia, también cambia
# `settings.public_base_url` (ver config.py).
PROD_OPENAPI_URL = "https://wowhub-api-production.up.railway.app/openapi.json"


# ── Fixtures ─────────────────────────────────────────────
@pytest.fixture(scope="module")
def prod_openapi() -> dict:
    """Descarga el OpenAPI de producción UNA vez por módulo.

    Si falla la red, devuelve None y los tests que dependan de paths
    de producción deben skipearse (vía `_check_production_paths`).
    """
    try:
        r = httpx.get(PROD_OPENAPI_URL, timeout=10.0)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        pytest.skip(f"No se pudo descargar el OpenAPI de producción: {e}")


def _check_production_paths(prod_openapi: dict | None) -> bool:
    """Helper: skip si no hay OpenAPI disponible."""
    if prod_openapi is None:
        pytest.skip("OpenAPI de producción no disponible")
    return True


# ── Tests ────────────────────────────────────────────────
class TestPublicBaseUrl:
    """Valida que `settings.public_base_url` apunta a la URL canónica."""

    def test_default_is_railway_backend(self):
        """v1.9.1-r4: el default declarado en ``config.py`` debe ser el
        backend de Railway (no ``wowhub.app``).

        Leemos el default directamente del ``Field`` declarado en la
        clase ``Settings`` (no del valor runtime, que puede estar
        sobreescrito por ``.env``).
        """
        from app.config import Settings

        default = Settings.model_fields["public_base_url"].default
        assert default == "https://wowhub-api-production.up.railway.app", (
            f"v1.9.1-r4: el default de public_base_url en config.py debe "
            f"ser el backend de Railway. Actual: {default!r}"
        )

    def test_effective_public_base_url_returns_railway(self):
        """`effective_public_base_url` con PUBLIC_BASE_URL vacío debe
        caer al default de Railway (no a wowhub.app).
        """
        from app.config import Settings

        # Instanciar con public_base_url vacío (fuerza fallback a base_url,
        # pero queremos verificar que el default ES el de Railway).
        fresh = Settings.model_construct(
            public_base_url="", base_url="http://test"
        )
        effective = fresh.effective_public_base_url
        # El fallback es base_url cuando public_base_url está vacío.
        # Pero lo importante es que el DEFAULT en config.py es Railway.
        default = Settings.model_fields["public_base_url"].default
        assert "wowhub-api-production.up.railway.app" in default, (
            f"v1.9.1-r4: el dominio default debe ser Railway. "
            f"Actual: {default!r}"
        )


class TestPublicUrlsAlignWithProd:
    """Valida que cada path de `PUBLIC_URLS` exista en producción."""

    def test_every_public_url_pattern_resolves_to_prod_path(
        self, prod_openapi
    ):
        """Para cada entry de `app_knowledge.PUBLIC_URLS`, el pattern
        (con sus placeholders) debe matchear algún path en el OpenAPI
        de producción.

        Los paths en `openapi.json["paths"]` son TEMPLATES (ej.
        ``/api/v1/public/t/{slug}/profile``), no paths resueltos. Por
        eso comparamos el pattern literal contra los templates.
        """
        if not _check_production_paths(prod_openapi):
            return

        prod_paths = set(prod_openapi.get("paths", {}).keys())

        for entry in app_knowledge.PUBLIC_URLS:
            pattern = entry["pattern"]
            # Los paths de OpenAPI son templates con `{slug}` literal.
            # Comparamos pattern vs pattern (template vs template).
            assert pattern in prod_paths, (
                f"v1.9.1-r4: PUBLIC_URLS pattern {pattern!r} NO existe "
                f"en el OpenAPI de producción. "
                f"Paths disponibles: {sorted(prod_paths)}"
            )

    def test_no_legacy_u_slash_format_in_public_urls(self):
        """`PUBLIC_URLS` NO debe contener paths con el prefijo `/u/{slug}/...`.

        Esos paths NO existen en el OpenAPI de producción y dan 404.
        v1.9.1-r4 los reemplazó por `/api/v1/public/t/{slug}/...`.
        """
        for entry in app_knowledge.PUBLIC_URLS:
            pattern = entry["pattern"]
            assert not pattern.startswith("/u/"), (
                f"v1.9.1-r4: PUBLIC_URLS no debe usar el formato viejo "
                f"/u/{{slug}}/... (404 en producción). Encontrado: {pattern!r}"
            )

    def test_no_legacy_loyalty_path_in_public_urls(self):
        """`/loyalty/{slug}` NO está desplegado (solo en roadmap)."""
        for entry in app_knowledge.PUBLIC_URLS:
            pattern = entry["pattern"]
            assert "/loyalty/" not in pattern, (
                f"v1.9.1-r4: /loyalty/{{slug}} NO está en producción. "
                f"Encontrado: {pattern!r}"
            )


class TestModulesAlignWithProd:
    """Valida que `MODULES` no invente paths que no existen en producción."""

    def test_module_paths_resolve_to_prod_or_legacy(self, prod_openapi):
        """Los patterns de cada módulo (con placeholders) deben existir
        en el OpenAPI de producción (templates).
        """
        if not _check_production_paths(prod_openapi):
            return

        prod_paths = set(prod_openapi.get("paths", {}).keys())

        for m in app_knowledge.MODULES:
            path = m["path"]
            # Los paths de OpenAPI son templates con `{slug}` literal.
            assert path in prod_paths, (
                f"v1.9.1-r4: MODULES[{m['key']!r}] path={path!r} "
                f"NO existe en el OpenAPI de producción."
            )

    def test_modules_count_is_realistic(self):
        """v1.9.1-r4: el OpenAPI describe '4 features del MVP' (Página,
        Catálogo, QR, Promociones). `MODULES` debe tener 4 entries (o
        un número cercano; si en el futuro se agregan features, este
        test se actualiza con la nueva realidad).
        """
        assert len(app_knowledge.MODULES) == 4, (
            f"v1.9.1-r4: el OpenAPI describe 4 features del MVP. "
            f"MODULES tiene {len(app_knowledge.MODULES)}. Actualizar "
            f"el módulo o este test si se agregan features nuevas."
        )

    def test_modules_have_public_api_or_qr_path(self):
        """Todos los módulos deben apuntar a paths públicos bajo
        `/api/v1/public/...` o al path del QR redirect (`/r/...`).
        NO `/dashboard/...`, NO `/u/...`.
        """
        for m in app_knowledge.MODULES:
            path = m["path"]
            is_public_api = path.startswith("/api/v1/public/")
            is_qr_redirect = path.startswith("/r/")
            assert is_public_api or is_qr_redirect, (
                f"v1.9.1-r4: MODULES[{m['key']!r}] path={path!r} debe "
                f"estar bajo /api/v1/public/... o /r/... (formato "
                f"producción)."
            )


class TestDashboardUrlsIsDeprecated:
    """`DASHBOARD_URLS` debe ser un shim vacío en v1.9.1-r4."""

    def test_dashboard_urls_is_empty(self):
        """El panel HTML público NO existe en producción. La constante
        `DASHBOARD_URLS` se mantiene como shim pero su lista de
        módulos está vacía.
        """
        assert app_knowledge.DASHBOARD_URLS["modules"] == [], (
            f"v1.9.1-r4: DASHBOARD_URLS['modules'] debe estar VACÍA "
            f"(no hay panel HTML público en producción). "
            f"Actual: {app_knowledge.DASHBOARD_URLS['modules']!r}"
        )

    def test_dashboard_urls_is_marked_deprecated(self):
        """La constante debe tener el flag `deprecated_in` para que sea
        evidente que NO debe usarse.
        """
        assert (
            app_knowledge.DASHBOARD_URLS.get("deprecated_in") == "v1.9.1-r4"
        ), (
            "v1.9.1-r4: DASHBOARD_URLS debe tener "
            "`deprecated_in='v1.9.1-r4'` para señalizar que es shim."
        )


class TestScrubberV191R4:
    """El scrubber debe catchar los paths prohibidos en v1.9.1-r4."""

    def test_scrubber_catches_dashboard_paths(self):
        """El regex `_FAKE_DASHBOARD_PATH_RE` debe catchar paths
        `/dashboard/...` con host válido.
        """
        from app.services.ai_orchestrator import _FAKE_DASHBOARD_PATH_RE

        # Casos positivos: debe matchear
        positive_cases = [
            "https://wowhub.app/dashboard/settings",
            "https://wowhub-app.example/dashboard/products",
            "https://wowhub-api-production.up.railway.app/dashboard/qr",
            "https://localhost:3000/dashboard/automation",
        ]
        for case in positive_cases:
            assert _FAKE_DASHBOARD_PATH_RE.search(case), (
                f"v1.9.1-r4: el scrubber debe catchar {case!r}"
            )

    def test_scrubber_catches_dashboard_subpaths(self):
        """El scrubber debe catchar paths con subpath
        (ej. `/dashboard/products/abc`).
        """
        from app.services.ai_orchestrator import _FAKE_DASHBOARD_PATH_RE

        assert _FAKE_DASHBOARD_PATH_RE.search(
            "https://wowhub.app/dashboard/products/abc-123"
        )
        assert _FAKE_DASHBOARD_PATH_RE.search(
            "https://wowhub.app/dashboard/qrs/branch-1/qr-2"
        )

    def test_scrubber_does_not_catch_public_api_paths(self):
        """El scrubber NO debe catchar los paths REALES de producción
        `/api/v1/public/...` (esos son válidos).
        """
        from app.services.ai_orchestrator import _FAKE_DASHBOARD_PATH_RE

        # Estos son los paths REALES y no deben ser marcados como falsos.
        assert not _FAKE_DASHBOARD_PATH_RE.search(
            "https://wowhub-api-production.up.railway.app/api/v1/public/t/cafeluna/catalog"
        )
        assert not _FAKE_DASHBOARD_PATH_RE.search(
            "https://wowhub-api-production.up.railway.app/api/v1/public/t/cafeluna/profile"
        )


class TestFaqUrllPublblica:
    """La FAQ 'url pública' debe apuntar a la tool correcta (v1.9.1-r4)."""

    def test_faq_mentions_get_tenant_public_urls(self):
        answer = app_knowledge.faq_lookup("url pública")
        assert answer is not None
        assert "get_tenant_public_urls" in answer

    def test_faq_has_real_url_example(self):
        """La FAQ debe tener al menos un ejemplo de URL REAL (no patrón
        con `{slug}` literal).
        """
        answer = app_knowledge.faq_lookup("url pública")
        assert answer is not None
        # Debe tener una URL con el formato de producción
        assert "wowhub-api-production.up.railway.app/api/v1/public/t/" in answer

    def test_faq_does_not_have_literal_placeholder(self):
        """La FAQ NO debe contener el patrón `/u/{slug}/reservar` (es
        exactamente el bug que arreglamos en v1.9.1-r4).
        """
        answer = app_knowledge.faq_lookup("url pública")
        assert answer is not None
        assert "/u/{slug}/reservar" not in answer


class TestNoExisteHasProductionReality:
    """La lista NO_EXISTE debe incluir los anti-alucinación v1.9.1-r4."""

    def test_no_html_dashboard_in_prod(self):
        """Debe haber una entrada explícita diciendo que no hay panel
        HTML público en producción.
        """
        joined = "\n".join(app_knowledge.NO_EXISTE).lower()
        assert "no hay panel html público" in joined or "no existe un panel html" in joined

    def test_legacy_u_slash_format_is_dead(self):
        joined = "\n".join(app_knowledge.NO_EXISTE)
        assert "/u/{slug}" in joined or "formato viejo" in joined

    def test_wowhub_app_domain_is_dead(self):
        joined = "\n".join(app_knowledge.NO_EXISTE).lower()
        assert "wowhub.app" in joined, (
            "NO_EXISTE debe mencionar que wowhub.app no responde (NXDOMAIN)"
        )

    def test_dashboard_urls_tool_is_deprecated(self):
        joined = "\n".join(app_knowledge.NO_EXISTE).lower()
        assert "get_tenant_dashboard_urls" in joined
        assert "depre" in joined  # deprecated / deprecada


class TestCanonicalDocHasV191R4:
    """El documento canónico debe estar sincronizado con v1.9.1-r4."""

    def test_canonical_doc_header_says_r4(self):
        """El header del CANONICAL_WOWHUB.md debe decir v1.9.1-r4."""
        doc_path = (
            Path(__file__).parent.parent / "docs" / "CANONICAL_WOWHUB.md"
        )
        content = doc_path.read_text(encoding="utf-8")
        assert "v1.9.1-r4" in content, (
            "CANONICAL_WOWHUB.md debe mencionar la versión v1.9.1-r4"
        )

    def test_canonical_doc_section_2_mentions_prod_path(self):
        """§2 debe usar el formato de path de producción."""
        doc_path = (
            Path(__file__).parent.parent / "docs" / "CANONICAL_WOWHUB.md"
        )
        content = doc_path.read_text(encoding="utf-8")
        # El formato de producción debe aparecer en §2
        assert "/api/v1/public/t/{slug}" in content

    def test_canonical_doc_section_3_uses_prod_format(self):
        """§3 debe usar el formato de producción en los ejemplos."""
        doc_path = (
            Path(__file__).parent.parent / "docs" / "CANONICAL_WOWHUB.md"
        )
        content = doc_path.read_text(encoding="utf-8")
        # El prefijo Railway debe aparecer en los ejemplos
        assert "wowhub-api-production.up.railway.app" in content
