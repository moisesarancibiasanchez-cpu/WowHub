#!/bin/sh
# ─── WowHub · entrypoint (Render / Railway) ───────────────
# Espera a que la DB esté lista, corre migrations y arranca uvicorn.

set -e

# ── FIX V2.015 · Volumen persistente en /app/storage ─────────────────────
# Railway monta los volúmenes con el usuario `root`. La imagen corre como
# `wowhub` (no-root), así que sin este bloque el servicio no puede escribir
# en el volumen: las subidas fallan con
#   EACCES: permission denied, mkdir '/app/storage/<tenant_id>'
# (documentado por Railway: "Docker images that run as a non-root UID by
# default will have permissions issues when performing operations within an
# attached volume").
#
# Solución: el contenedor arranca como root (RAILWAY_RUN_UID=0 en las
# variables del servicio), el entrypoint da el volumen al usuario de la app
# y BAJA PRIVILEGIOS antes de arrancar uvicorn. La app sigue corriendo como
# `wowhub`; sólo el arranque es root.
if [ "$(id -u)" = "0" ]; then
    echo "▶ Ajustando permisos del almacenamiento (arranque como root)..."
    mkdir -p /app/storage /app/data
    # -R: el volumen puede traer archivos de un arranque anterior como root.
    chown -R wowhub:wowhub /app/storage /app/data 2>/dev/null || \
        echo "⚠ No se pudo hacer chown de /app/storage (revisar permisos del volumen)"
    chmod 755 /app/storage 2>/dev/null || true
    if command -v gosu >/dev/null 2>&1; then
        echo "▶ Bajando privilegios a 'wowhub' (gosu)..."
        exec gosu wowhub /app/entrypoint.sh
    fi
    if command -v setpriv >/dev/null 2>&1; then
        echo "▶ Bajando privilegios a 'wowhub' (setpriv)..."
        exec setpriv --reuid=wowhub --regid=wowhub --init-groups /app/entrypoint.sh
    fi
    if command -v su >/dev/null 2>&1; then
        echo "▶ Bajando privilegios a 'wowhub' (su)..."
        exec su -s /bin/sh wowhub -c 'exec /app/entrypoint.sh'
    fi
    echo "⚠ No se encontró gosu/setpriv/su: se sigue como root."
fi

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

# ── FIX 2026-10-21: reconciliación de esquema (columnas faltantes) ────────
# create_all() sólo crea tablas QUE NO EXISTEN: nunca hace ALTER TABLE sobre
# tablas ya presentes. Por eso no puede reparar el drift de columnas (el
# bug de producción: `products.product_type does not exist` → /products 500).
#
# reconcile_schema compara Base.metadata contra el esquema real y:
#   1) crea las tablas que falten,
#   2) agrega las columnas que falten (con tipo y default del modelo),
#   3) crea los índices que falten.
# Es idempotente y agnóstico del estado de Alembic (legacy/stamped/alembic).
echo "▶ Reconciliando esquema (columnas/índices faltantes)..."
python -m scripts.reconcile_schema || echo "⚠ reconcile_schema falló (continúa igualmente)"

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
