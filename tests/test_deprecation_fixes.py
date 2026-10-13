"""Tests de regresión para los fixes de deprecations aplicadas.

Estos tests verifican que el código del proyecto NO use APIs deprecadas
que serían removidas en próximas versiones de:

  - Pydantic v3 (class-based ``Config`` → ``model_config = ConfigDict(...)``)
  - Starlette >=0.40 (``HTTP_422_UNPROCESSABLE_ENTITY`` → ``HTTP_422_UNPROCESSABLE_CONTENT``)
  - Python 3.12+ (``datetime.utcnow()`` → ``datetime.now(timezone.utc)``)
  - pytest >=8 (class-scoped fixtures como instance methods → @classmethod)

Si alguno de estos tests falla, significa que alguien re-introdujo
una API deprecada.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
APP_DIR = ROOT / "app"


# ── Pydantic v2: no class-based Config ──────────────────────────
class TestNoPydanticV1Config:
    """El class-based ``Config`` está deprecado en Pydantic v2."""

    # Archivos que pueden contener schemas de Pydantic
    CANDIDATE_FILES = [
        APP_DIR / "schemas" / "webhook.py",
        APP_DIR / "schemas" / "upload.py",
    ]

    def _read(self, path: Path) -> str:
        return path.read_text(encoding="utf-8")

    def _strip_comments(self, source: str) -> str:
        """Remueve comentarios para no matchear falsos positivos."""
        return re.sub(r"#[^\n]*", "", source)

    @pytest.mark.parametrize("path", CANDIDATE_FILES, ids=lambda p: p.name)
    def test_no_class_based_config(self, path: Path):
        source = self._strip_comments(self._read(path))
        # Busca bloques ``class Config:`` indentados dentro de un BaseModel
        # (no dentro de comentarios o strings). Excluimos ``class ConfigDict`` (Pydantic v2).
        # Patrón: whitespace + "class Config:" + indent (no ``Dict``)
        bad = re.search(r"^\s*class\s+Config\s*:\s*$", source, re.M)
        assert not bad, (
            f"{path.relative_to(ROOT)} usa class-based Config (deprecado en Pydantic v2). "
            "Migrar a: model_config = ConfigDict(...)"
        )

    def test_upload_uses_configdict(self):
        source = self._read(APP_DIR / "schemas" / "upload.py")
        assert "ConfigDict" in source, "upload.py debe importar ConfigDict"
        assert "model_config = ConfigDict" in source, (
            "upload.py debe declarar model_config = ConfigDict(...)"
        )

    def test_webhook_uses_configdict(self):
        source = self._read(APP_DIR / "schemas" / "webhook.py")
        assert "ConfigDict" in source, "webhook.py debe importar ConfigDict"
        # Hay 2 clases (WebhookOut y WebhookDeliveryOut) → 2 model_config
        count = source.count("model_config = ConfigDict")
        assert count >= 2, (
            f"webhook.py debe tener 2 model_config = ConfigDict(...) (uno por cada Out); "
            f"encontré {count}"
        )


# ── Starlette >=0.40: no HTTP_422_UNPROCESSABLE_ENTITY ───────────
class TestNoStarletteUnprocessableEntityDeprecation:
    """Starlette >=0.40 renombró la constante. Acceder a la vieja emite warning."""

    ERRORS_FILE = APP_DIR / "core" / "errors.py"

    def test_errors_py_uses_unprocessable_content(self):
        source = self.ERRORS_FILE.read_text(encoding="utf-8")
        # Debe usar el nombre nuevo (con fallback a 422)
        assert "HTTP_422_UNPROCESSABLE_CONTENT" in source, (
            "errors.py debe usar HTTP_422_UNPROCESSABLE_CONTENT (Starlette >=0.40)"
        )

    def test_errors_py_does_not_reference_old_constant(self):
        source = self.ERRORS_FILE.read_text(encoding="utf-8")
        # Removemos comentarios para no matchear menciones en docstrings/explicaciones
        # (el comentario del fix puede mencionar el nombre viejo; lo que importa
        # es que el CÓDIGO no acceda al atributo deprecado).
        no_comments = re.sub(r"#[^\n]*", "", source)
        assert "HTTP_422_UNPROCESSABLE_ENTITY" not in no_comments, (
            "errors.py NO debe mencionar HTTP_422_UNPROCESSABLE_ENTITY en código "
            "(Starlette emite DeprecationWarning al acceder al atributo viejo). "
            "Los comentarios están OK, pero el código activo no debe usarlo."
        )

    def test_validation_error_uses_int_fallback(self):
        """Si Starlette no tiene la constante, caemos al literal 422."""
        source = self.ERRORS_FILE.read_text(encoding="utf-8")
        assert re.search(
            r'getattr\(\s*status\s*,\s*"HTTP_422_UNPROCESSABLE_CONTENT"\s*,\s*422\s*\)',
            source,
        ), "errors.py debe hacer getattr(... , 422) como fallback numérico"


# ── Python 3.12+: no datetime.utcnow() ───────────────────────────
class TestNoDatetimeUtcnow:
    """datetime.utcnow() es deprecated en Python 3.12+. Usar datetime.now(tz=timezone.utc)."""

    CANDIDATE_FILES = [
        APP_DIR / "schemas" / "ai.py",
    ]

    def _read(self, path: Path) -> str:
        return path.read_text(encoding="utf-8")

    def _strip_strings_and_comments(self, source: str) -> str:
        # Remueve strings simples y comentarios
        s = re.sub(r"#[^\n]*", "", source)
        s = re.sub(r'"(?:[^"\\]|\\.)*"', '""', s)
        s = re.sub(r"'(?:[^'\\]|\\.)*'", "''", s)
        return s

    @pytest.mark.parametrize("path", CANDIDATE_FILES, ids=lambda p: p.name)
    def test_no_datetime_utcnow(self, path: Path):
        source = self._strip_strings_and_comments(self._read(path))
        # Busca tanto ``datetime.utcnow()`` como ``__import__("datetime").datetime.utcnow()``
        bad = re.search(r"datetime\.utcnow\s*\(", source)
        assert not bad, (
            f"{path.relative_to(ROOT)} usa datetime.utcnow() (deprecado en Python 3.12+). "
            "Usar datetime.now(timezone.utc)."
        )

    def test_ai_uses_timezone_aware_now(self):
        source = self._read(APP_DIR / "schemas" / "ai.py")
        # Debe importar timezone
        assert "from datetime import" in source and "timezone" in source, (
            "ai.py debe importar timezone de datetime"
        )
        # Debe usar datetime.now(timezone.utc) en al menos un lugar
        assert re.search(r"datetime\.now\s*\(\s*timezone\.utc\s*\)", source), (
            "ai.py debe usar datetime.now(timezone.utc) en lugar de utcnow()"
        )


# ── pytest >=8: class-scoped fixture con @classmethod ───────────
class TestPytestClassScopedFixture:
    """pytest >=8 deprecates class-scoped fixtures como instance methods."""

    TEST_FILE = ROOT / "tests" / "test_dashboard_modal_refactor.py"

    def test_node_env_fixture_uses_classmethod(self):
        source = self.TEST_FILE.read_text(encoding="utf-8")
        # Debe tener @classmethod antes del @pytest.fixture(scope="class")
        # Patrón: @classmethod ... @pytest.fixture(scope="class") ... def node_env(cls, ...)
        pattern = (
            r"@classmethod\s+"
            r"@pytest\.fixture\(scope\s*=\s*[\"']class[\"']\)\s+"
            r"def\s+node_env\s*\(\s*cls\s*,"
        )
        assert re.search(pattern, source), (
            "test_dashboard_modal_refactor.py:node_env debe usar @classmethod "
            "encima de @pytest.fixture(scope='class') para evitar el DeprecationWarning "
            "de pytest >=8."
        )


# ── e2e conftest: skip limpio cuando no hay playwright ──────────
class TestE2EConftestSkipsCleanly:
    """Si las deps e2e no están, los tests deben saltarse, no explotar."""

    CONFTEST = ROOT / "tests" / "e2e" / "conftest.py"

    def test_conftest_has_collection_modifyitems(self):
        source = self.CONFTEST.read_text(encoding="utf-8")
        assert "pytest_collection_modifyitems" in source, (
            "tests/e2e/conftest.py debe tener un hook pytest_collection_modifyitems "
            "que marque los tests e2e como skip cuando las deps no estén."
        )

    def test_conftest_imports_playwright_in_try_block(self):
        source = self.CONFTEST.read_text(encoding="utf-8")
        # Debe tener un try/except ImportError alrededor de los imports de playwright
        assert re.search(
            r"try\s*:\s*\n[^\n]*import\s+playwright",
            source,
        ), "conftest.py debe proteger los imports de playwright con try/except ImportError"

    def test_conftest_uses_skip_marker(self):
        source = self.CONFTEST.read_text(encoding="utf-8")
        assert "pytest.mark.skip" in source, (
            "conftest.py debe usar pytest.mark.skip cuando no haya deps e2e"
        )
