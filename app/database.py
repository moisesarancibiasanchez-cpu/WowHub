"""SQLAlchemy engine, session factory y base declarativa."""
from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker, Session
from sqlalchemy.pool import StaticPool

from app.config import settings


class Base(DeclarativeBase):
    """Base declarativa para todos los modelos."""
    pass


# Engine: configuración distinta para SQLite (dev) vs Postgres (prod)
if settings.is_sqlite:
    # StaticPool cuando es :memory: para que todas las conexiones
    # compartan el mismo store (necesario para tests).
    is_memory = settings.database_url.endswith(":memory:")
    engine = create_engine(
        settings.database_url,
        echo=settings.debug,
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool if is_memory else None,
    )
else:
    engine = create_engine(
        settings.database_url,
        echo=settings.debug,
        future=True,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
    )

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
    future=True,
)


def get_db() -> Generator[Session, None, None]:
    """Dependencia FastAPI que provee una sesión de DB y la cierra al final."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Crea las tablas. En producción usar Alembic."""
    # Importar modelos para que SQLAlchemy los registre
    from app.models import (  # noqa: F401
        user, tenant, branch, category, product, customer,
        promotion, qr, landing, order,
        site_config,  # noqa
        loyalty_pass,  # noqa
    )
    Base.metadata.create_all(bind=engine)
    # ── Migración puntual: cashier_pin VARCHAR(8) → VARCHAR(64) ──
    # El campo cambió de tamaño porque el hash SHA-256 (64 hex chars)
    # no entraba en 8. create_all no altera columnas existentes.
    try:
        from sqlalchemy import text
        with engine.begin() as conn:
            conn.execute(text(
                "ALTER TABLE loyalty_campaigns "
                "ALTER COLUMN cashier_pin TYPE VARCHAR(64)"
            ))
    except Exception:
        # Idempotente: si la tabla no existe o el tipo ya es correcto, sigue.
        pass
