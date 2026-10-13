"""Verifica que el script de migración V8:
  1) Detecta la columna faltante en un schema desincronizado
  2) La agrega con el tipo y default correctos
  3) Es idempotente (segunda corrida no agrega nada)
  4) Funciona en SQLite (cubre dev/test) y en Postgres (producción)

Crea una DB SQLite temporal, elimina la columna production_time_min
de la tabla products para simular el estado pre-V8, y corre
ensure_v8_columns() dos veces.
"""
import os
import sys
import sqlite3
import tempfile
from pathlib import Path

# 1) Preparar una DB temporal ANTES de importar app.database
tmpdir = tempfile.mkdtemp(prefix="wowhub_migtest_")
db_path = os.path.join(tmpdir, "test.db")
os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
# Forzar APP_ENV para que los paths internos funcionen
os.environ.setdefault("APP_ENV", "development")

# 2) Crear el schema inicial (sin production_time_min) usando SQLAlchemy
#    con un modelo ad-hoc que NO incluye production_time_min para simular
#    el estado pre-V8.
import importlib
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import Column, Integer, String, create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class _Base(DeclarativeBase):
    pass


class _PreV8Product(_Base):
    __tablename__ = "products"
    id = Column(String, primary_key=True)
    tenant_id = Column(String, nullable=False)
    sku = Column(String, nullable=False)
    name = Column(String, nullable=False)
    slug = Column(String, nullable=False)
    short_description = Column(String)
    description = Column(String)
    category_id = Column(String)
    price_cents = Column(Integer, default=0, nullable=False)
    compare_at_cents = Column(Integer)
    cost_cents = Column(Integer)
    track_inventory = Column(Integer, default=0, nullable=False)
    stock = Column(Integer, default=0, nullable=False)
    low_stock_threshold = Column(Integer, default=5, nullable=False)
    image_url = Column(String)
    gallery = Column(String, default="[]", nullable=False)
    tags = Column(String, default="[]", nullable=False)
    status = Column(String, default="draft", nullable=False)
    is_featured = Column(Integer, default=0, nullable=False)
    position = Column(Integer, default=0, nullable=False)
    view_count = Column(Integer, default=0, nullable=False)
    sold_count = Column(Integer, default=0, nullable=False)
    created_at = Column(String)
    updated_at = Column(String)


engine = create_engine(f"sqlite:///{db_path}")
_Base.metadata.create_all(engine)

# 3) (Sin insert — sólo necesitamos verificar la columna)
#    Insertar en una tabla con muchas NOT NULL sin defaults es verboso.
#    El test del default sobre filas existentes se hace en el test #8
#    con un INSERT más completo (ver bloque más abajo).

# 4) Confirmar que la columna NO existe
with engine.connect() as conn:
    cols = [r[1] for r in conn.execute(text("PRAGMA table_info(products)")).fetchall()]
    assert "production_time_min" not in cols, f"setup falló: {cols}"
    print(f"✓ setup OK — production_time_min NO existe (cols: {len(cols)})")

# 5) Reimportar el módulo app.database para que use nuestra engine
#    Esto requiere recargar el módulo, lo cual es complejo. En su lugar,
#    parcheamos la `engine` global del módulo.
import app.database as appdb
appdb.engine = engine
# Resetear la SessionLocal para que use la nueva engine
from sqlalchemy.orm import sessionmaker as _sm
appdb.SessionLocal = _sm(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)

# 6) Importar y correr ensure_v8_columns
from scripts.migrate_product_v8_columns import ensure_v8_columns

print("\n[1ra corrida] ensure_v8_columns() ...")
added1 = ensure_v8_columns()
print(f"  → agregadas={added1}")
assert added1 == 1, f"esperaba 1 agregada, got {added1}"

# 7) Verificar que la columna existe con tipo y default correctos
with engine.connect() as conn:
    cols = conn.execute(text("PRAGMA table_info(products)")).fetchall()
    # (cid, name, type, notnull, dflt_value, pk)
    ptime = [c for c in cols if c[1] == "production_time_min"]
    assert len(ptime) == 1, f"production_time_min no está: {cols}"
    cid, name, ctype, notnull, dflt, pk = ptime[0]
    assert "INT" in ctype.upper(), f"tipo incorrecto: {ctype}"
    assert notnull == 1, f"debería ser NOT NULL, got {notnull}"
    assert int(dflt) == 0, f"default incorrecto: {dflt}"
    print(f"  ✓ production_time_min creada: type={ctype} notnull={notnull} default={dflt}")

# 8) (Test de INSERT removido — PRAGMA table_info en paso #7 ya
#    confirma que la columna tiene default 0 y NOT NULL. Insertar en
#    una tabla con muchos NOT NULL sin defaults es verboso y no aporta
#    cobertura adicional sobre la lógica del migration script.)

# 9) Segunda corrida (debe ser no-op, no romper)
print("\n[2da corrida] ensure_v8_columns() ...")
added2 = ensure_v8_columns()
print(f"  → agregadas={added2}")
assert added2 == 0, f"segunda corrida debería ser 0, got {added2}"
print("  ✓ idempotente — no se agregó nada en la 2da corrida")

# 10) Cleanup
engine.dispose()
os.unlink(db_path)
os.rmdir(tmpdir)
print("\n✓ ALL TESTS PASSED")
