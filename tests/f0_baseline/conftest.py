"""Conftest local para F0.

Los tests de F0 son **offline** (no tocan la base de datos real, no hacen
HTTP saliente, no requieren rate-limit ni auditoría). El conftest global
``tests/conftest.py`` registra fixtures *autouse* pesadas
(`reset_db` con `drop_all`/`create_all` sobre 40 tablas y un walker del
ASGI stack para limpiar buckets de rate-limit) que pueden hacer colgar
el runner cuando se importan routers pesados. Aquí las neutralizamos
para esta sub-suite sin tocar el comportamiento del resto del proyecto.
"""
from __future__ import annotations

import os

# Forzar entorno en memoria / deshabilitar rate-limit ANTES de importar
# la app (mismo patrón que el conftest global).
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "test-secret-key-min-32-chars-ok-test")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-min-32-chars-ok-test")
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")
os.environ.setdefault("AUDIT_ENABLED", "false")


import pytest  # noqa: E402


# ─────────────────────────────────────────────────────────────────────
# Override de fixtures autouse del conftest padre.
# pytest resuelve fixtures del conftest más cercano primero, por lo que
# basta con declarar aquí los mismos nombres como no-ops.
# ─────────────────────────────────────────────────────────────────────
@pytest.fixture(scope="function", autouse=True)
def reset_db():
    """NO-OP: F0 no toca la base de datos real."""
    yield


@pytest.fixture(autouse=True)
def _clear_rate_limit_buckets():
    """NO-OP: F0 no necesita limpiar buckets de rate-limit."""
    yield
