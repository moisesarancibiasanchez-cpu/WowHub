#!/bin/sh
# ─── WowHub · entrypoint para Render ─────────────────────
# Espera a que la DB esté lista, corre migrations y arranca uvicorn.

set -e

echo "▶ WowHub entrypoint — esperando DB..."
python -c "
import os, time, sys
import psycopg
url = os.environ.get('DATABASE_URL', '').replace('postgresql+psycopg://', 'postgresql://')
for i in range(30):
    try:
        with psycopg.connect(url, connect_timeout=2) as conn:
            conn.execute('SELECT 1')
        print('DB ready')
        sys.exit(0)
    except Exception as e:
        print(f'waiting db ({i+1}/30): {e}')
        time.sleep(1)
print('DB no responde')
sys.exit(1)
"

echo "▶ Corriendo migrations Alembic..."
alembic upgrade head 2>/dev/null || echo "⚠ alembic no inicializado aún — usando Base.metadata.create_all"
python -c "
import os
os.environ.setdefault('APP_ENV','production')
from app.database import Base, engine
import app.models  # noqa: F401
Base.metadata.create_all(bind=engine)
print('✔ schema OK')
"

echo "▶ Aplicando migraciones idempotentes (enum ai_agent_kind 'help')..."
python -m scripts.migrate_ai_help_enum || echo "⚠ migrate_ai_help_enum falló (continúa igualmente)"

echo "▶ Sembrando datos demo (si DB vacía)..."
python -m app.seed || echo "⚠ seed falló (continúa igualmente)"

echo "▶ Arrancando uvicorn..."
exec uvicorn app.main:app \
    --host 0.0.0.0 \
    --port "${PORT:-8000}" \
    --workers 2 \
    --proxy-headers \
    --forwarded-allow-ips='*'
