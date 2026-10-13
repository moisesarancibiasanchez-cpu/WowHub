#!/bin/sh
# ─── WowHub · entrypoint (Render / Railway) ───────────────
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

# ── FIX 2026-09-29: bootstrap idempotente de migraciones ──────────
# Antes:  `alembic upgrade head 2>/dev/null || echo "…create_all"` — se
#         tragaba el error y caía a create_all(), lo que impedía aplicar
#         migraciones futuras.
# Después: `python -m scripts.bootstrap_migrate` decide entre:
#           - DB vacía        → alembic upgrade head
#           - DB pre-existente sin alembic_version (legacy create_all) →
#             alembic stamp head (alinea) + upgrade head (no-op)
#           - DB gestionada   → alembic upgrade head (idempotente)
# En cualquier caso abortamos con exit 1 si falla — el deploy no se considera
# exitoso sin esquema aplicado.
echo "▶ Bootstrap de migraciones (idempotente)..."
python -m scripts.bootstrap_migrate
rc=$?
if [ $rc -ne 0 ]; then
    echo "✖ FALLO CRÍTICO: bootstrap_migrate salió con código $rc."
    echo "  Si el error es 'DuplicateTable', la DB tiene un esquema previo que"
    echo "  bootstrap_migrate debería haber detectado. Revisa que el script"
    echo "  se ejecute contra la misma DATABASE_URL que la app."
    exit $rc
fi
echo "✔ Migraciones aplicadas"

# create_all sólo como red de seguridad para tablas que la migración no cubre
# (no altera ni borra nada; es idempotente).
python -c "
import os
os.environ.setdefault('APP_ENV','production')
from app.database import Base, engine
import app.models  # noqa: F401
Base.metadata.create_all(bind=engine)
print('✔ create_all red de seguridad OK')
"

echo "▶ Aplicando migraciones idempotentes (enum ai_agent_kind 'help')..."
python -m scripts.migrate_ai_help_enum || echo "⚠ migrate_ai_help_enum falló (continúa igualmente)"

echo "▶ Aplicando migraciones idempotentes (V8 columns: production_time_min)..."
python -m scripts.migrate_product_v8_columns || echo "⚠ migrate_product_v8_columns falló (continúa igualmente)"

# ── FIX 2026-09-27: el seed creaba un admin con credencial conocida ──
# Antes: `python -m app.seed` corría siempre en producción y creaba
# maria@cafenorte.cl / demo1234 con rol OWNER, imprimiendo la credencial
# en el log de arranque. Ahora el seed es opt-in por variable de entorno.
if [ "${SEED_DEMO_DATA:-false}" = "true" ]; then
    echo "▶ SEED_DEMO_DATA=true — sembrando datos demo..."
    python -m app.seed || echo "⚠ seed falló (continúa igualmente)"
else
    echo "↷ Seed de demo omitido (SEED_DEMO_DATA != true)"
fi

echo "▶ Arrancando uvicorn..."
# Usar app.main_compat en vez de app.main para cargar el compat router
# (incluye /api/v1/me/memberships, /api/v1/auth/logout-strict, etc.).
# main_compat importa main y le agrega el router compat sin tocar el resto.
exec uvicorn app.main_compat:app \
    --host 0.0.0.0 \
    --port "${PORT:-8000}" \
    --workers "${WEB_CONCURRENCY:-2}" \
    --proxy-headers \
    --forwarded-allow-ips='*'
