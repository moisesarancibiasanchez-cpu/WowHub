"""Conftest — fixtures para tests."""
import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

# Forzar DB en memoria para tests
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["SECRET_KEY"] = "test-secret-key-min-32-chars-ok-test"
os.environ["JWT_SECRET"] = "test-jwt-secret-min-32-chars-ok-test"
# Desactivar rate limit y auditoría en tests (estado limpio, sin 429 spurios)
os.environ["RATE_LIMIT_ENABLED"] = "false"
os.environ["AUDIT_ENABLED"] = "false"

# Importar DESPUÉS de setear env
from app.database import Base, SessionLocal, engine, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.core.security import RateLimitMiddleware  # noqa: E402


def _disable_rate_limit_middleware():
    """Marca como deshabilitado cualquier RateLimitMiddleware registrado.

    El middleware usa ``self.enabled = enabled`` por defecto ``True``. Como en
    ``app.add_middleware(RateLimitMiddleware)`` no se pasa ``enabled``, modificamos
    directamente las instancias que el ASGI app termina envolviendo.
    """
    # Buscar en app.user_middleware (Starlette guarda specs aquí)
    for spec in list(getattr(app, "user_middleware", [])):
        cls = getattr(spec, "cls", None)
        if cls is RateLimitMiddleware:
            # Marcar el flag de la spec para que cuando se construya la instancia
            # se cree con ``enabled=False``. Starlette/FastAPI instancian con
            # ``cls(app=app, **spec.options)``.
            spec.options = {**getattr(spec, "options", {}), "enabled": False}

    # Además, si el ASGI stack ya fue construido (p.ej. tests anteriores),
    # recorremos el stack para encontrar la instancia viva y flagearla.
    try:
        stack = app.middleware_stack
    except Exception:
        stack = None
    if stack is not None:
        _walk_and_disable(stack)


def _walk_and_disable(app_obj):
    """Recorre recursivamente el ASGI stack y deshabilita RateLimitMiddleware."""
    cls = getattr(app_obj, "cls", None)
    if cls is RateLimitMiddleware:
        try:
            app_obj.enabled = False
            app_obj.buckets.clear()
        except Exception:
            pass
    inner = getattr(app_obj, "app", None)
    if inner is not None and inner is not app_obj:
        _walk_and_disable(inner)


_disable_rate_limit_middleware()


@pytest.fixture(autouse=True)
def _clear_rate_limit_buckets():
    """Limpia los buckets de rate limit antes Y después de cada test."""
    stack = getattr(app, "middleware_stack", None)
    if stack is not None:
        _walk_and_disable(stack)
    yield
    stack = getattr(app, "middleware_stack", None)
    if stack is not None:
        _walk_and_disable(stack)


@pytest.fixture(scope="function", autouse=True)
def reset_db():
    """Crea y luego tira las tablas en cada test (estado limpio)."""
    # Importar modelos para registrarlos en Base.metadata
    from app.models import (  # noqa: F401
        user, tenant, branch, category, product, customer,
        promotion, qr, landing, order,
        # v0.2.0 — modelos nuevos
        payment, webhook, audit, branch_product, token,
        cart, invoice, booking, legal, onboarding, upload,
        # Loyalty Pass
        loyalty_pass,  # noqa
    )
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def db_session():
    """Sesión de DB para cada test."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(scope="function")
def client():
    """Cliente de testing con DB en memoria (usa el engine global)."""
    def _override_get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
