"""Conftest — fixtures para tests."""
import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

# Forzar DB en memoria para tests
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["SECRET_KEY"] = "test-secret-key-min-32-chars-ok-test"
os.environ["JWT_SECRET"] = "test-jwt-secret-min-32-chars-ok-test"

# Importar DESPUÉS de setear env
from app.database import Base, SessionLocal, engine, get_db  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="function", autouse=True)
def reset_db():
    """Crea y luego tira las tablas en cada test (estado limpio)."""
    # Importar modelos para registrarlos en Base.metadata
    from app.models import (  # noqa: F401
        user, tenant, branch, category, product, customer,
        promotion, qr, landing, order,
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
