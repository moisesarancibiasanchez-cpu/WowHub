================================================================================
README_V2.007_HU50_65_REDEPLOY_2026-10-20.txt
WowHub · Release Notes Atómicos · V2.007
================================================================================

FECHA          : 2026-10-20
BUILD          : commit 9ea9bec
ALCANCE        : Re-deploy de HU_50..HU_65 con fix de causa raíz del 502
ATOMICIDAD     : Trae archivos nuevos del feature + fix de causa raíz.
                Sustituye el rollback V2.006 (commit 5c040e5).
RIESGO         : Bajo · Migración 100% aditiva, modelos alineados a la
                migración (sin conflictos Enum/String).
REVERTIBLE     : Sí · alembic downgrade base elimina las 6 tablas y
                15 columnas sin pérdida de datos. Y git revert del
                merge revert del rollback deja el repo en V2.005.


--------------------------------------------------------------------------------
1. BASE (contexto)
--------------------------------------------------------------------------------

V2.006 (commit 5c040e5) registró un rollback de V2.005 por 502 Bad
Gateway sostenido en Railway tras el deploy de HU_50-65 (commit
729b4e9). En ese momento no había acceso a los logs del contenedor.

Recibido el log de error de Railway (en este turno):

  psycopg.errors.UndefinedObject: type "notification_channel_log"
                                  does not exist
  LINE 6: channel notification_channel_log NOT NULL,

el diagnóstico fue inmediato: el safety-net del entrypoint.sh
(`Base.metadata.create_all(bind=engine)` en línea 56) leía los modelos
nuevos y disparaba `CREATE TYPE notification_channel_log`. Pero la
migración Alembic 2026_10_16_hu50_65_produccion.py creaba la columna
como `sa.String(20)`, no como ENUM. Al ejecutar el modelo en PG
intentaba crear el type, fallaba con `UndefinedObject`, mataba uvicorn
y la app devolvía 502.

Este commit V2.007 alinea los 4 modelos nuevos (production,
insumo_movement, payment_record, notification) a `String(20)` o
`String(40)` con `server_default`, exactamente igual a lo que crea la
migración Alembic. Sin ENUM types en PG → create_all es no-op.


--------------------------------------------------------------------------------
2. CAMBIO ÚNICO (qué se hizo)
--------------------------------------------------------------------------------

A) Modelos nuevos — columnas a String (NO Enum types)

  app/models/production.py
    - ProductionJobStatus sigue como clase Python (8 estados).
    - ProductionJob.status: String(20) default "nuevo"
      Antes:  Enum(ProductionJobStatus, name="production_job_status")
      Después: String(20) + comentario documentando valores válidos.

  app/models/insumo_movement.py
    - InsumoMovementType sigue como clase Python.
    - InsumoMovement.type: String(20)
      Antes:  Enum(InsumoMovementType, name="insumo_movement_type")
      Después: String(20) + comentario.

  app/models/notification.py
    - NotificationEvent / Channel / Status siguen como clases Python.
    - NotificationTemplate.event/channel: String(40) / String(20)
    - NotificationLog.event/channel/status: String(40)/String(20)/String(20)
      Antes:  Enum(... name="notification_event_log", create_type=False)
              (que era la causa directa del 502)
      Después: String con comentario apuntando a las clases Python.

  app/models/payment_record.py
    - PaymentMethod sigue como clase Python.
    - PaymentRecord.payment_method: String(20) default "cash"
      Antes:  Enum(PaymentMethod, name="payment_method")
      Después: String(20) + comentario.

B) Integración al main (cherry-pick selectivo)

  - 6 archivos de modelos (nuevos)
  - 3 schemas nuevos: app/schemas/{inline,notification,payment_record}.py
  - 3 servicios nuevos: production_service, payment_record_service,
    notification_service_v2
  - 2 routers nuevos: app/api/v1/{production,payment_records}.py
  - Extensions inline en app/api/v1/{customers,products,notifications,
    __init__}.py
  - app/main.py: include_router(production), include_router(payment_records)
  - app/models/__init__.py: imports de los 6 modelos nuevos
  - app/models/{customer,order,product,quote}.py: columnas extendidas
    (HU_50, HU_51, HU_54, HU_58)
  - app/f0_baseline/router.py: INTERNAL_MODELS_ALLOWLIST += 6 modelos
  - alembic/versions/2026_10_16_hu50_65_produccion.py: migración aditiva
  - alembic/versions/2026_10_03_0001_report_runs_hu31.py y
    2026_10_06_0001_add_branches_floor_layout.py: chain fix (sin cambios
    adicionales a V2.005)
  - tests/conftest.py: fixtures nuevas
  - tests/test_hu50_65_produccion.py: 34 tests (HU_50..HU_65)

C) NO se modificó

  - Hero Showcase (commits 24d3012, 0f4b422, 6b32f76, 176eae4, e511ca1):
    - 8 imágenes en app/static/img/hero/ intactas
    - hero_showcase.js intacto (autoplay 3000 ms, 8 tabs ARIA)
    - landing.css, components.css, dashboard.css, wowprint.css
    - workflows, .github/* intactos
  - V2.005 release notes y V2.006 release notes siguen en docs/releases/
  - main.py intocado excepto por los 2 nuevos include_router
  - Docker / Railway config: sin cambios
  - Variables de entorno: sin cambios


--------------------------------------------------------------------------------
3. CAUSA RAÍZ (root cause) confirmada vía log de Railway
--------------------------------------------------------------------------------

EL ERROR:

  File ".../alembic/runtime/migration", line 1953, in _exec_single_context
  psycopg.errors.UndefinedObject: type "notification_channel_log"
                                   does not exist
  LINE 6: channel notification_channel_log NOT NULL

ANÁLISIS:

  1. La migración 2026_10_16_hu50_65_produccion.py crea la tabla
     notification_logs con:
       sa.Column("channel", sa.String(20), nullable=False)
     → NO crea el ENUM type notification_channel_log.

  2. El modelo NotificationLog declara:
       channel: Mapped[NotificationChannel] = mapped_column(
         Enum(NotificationChannel,
              name="notification_channel_log",
              create_type=False),
         nullable=False,
       )
     → Espera que el ENUM type YA EXISTA en PG.

  3. El entrypoint.sh tiene un safety-net:
       python -c "from app.database import Base, engine;
                  import app.models;
                  Base.metadata.create_all(bind=engine)"
     → Lee el modelo y dispara CREATE TYPE.

  4. En PG, `CREATE TYPE notification_channel_log` falla porque ese
     type no existe y `create_type=False` significa "no lo crees tú".
     Resultado: UndefinedObject → uvicorn crash → 502 Bad Gateway.

FIX:

  Cambiar el modelo para usar String(20) en lugar de Enum(...).
  Esto REALINEA el modelo con la migración (que ya creaba String) y
  elimina el CREATE TYPE problemático. Los valores válidos siguen
  documentados en las clases Python Enum (NotificationChannel etc.)
  y en los comentarios `comment='...'` de cada columna.

ADICIONAL:

  El mismo bug afectaba silenciosamente a ProductionJobStatus,
  InsumoMovementType y PaymentMethod —sus columnas también estaban
  en String(20) en la migración pero sus modelos intentaban crear
  los ENUM types. Si PG tenía los types ya creados (por create_all
  previo en otra migración), no fallaban, pero quedaban
  inconsistentes. Por consistencia se cambiaron todos a String.


--------------------------------------------------------------------------------
4. REQUERIMIENTOS DE DESPLIEGUE
--------------------------------------------------------------------------------

4.1) Worker
  · NO requiere cambio. Cero código de Celery.

4.2) Base de datos (Alembic)
  · Railway ejecuta `python -m scripts.bootstrap_migrate` (que ahora
    tiene safety-net para fallos de Alembic).
  · Migración 2026_10_16_hu50_65_produccion es 100% aditiva:
    6 CREATE TABLE + 15 ADD COLUMN (con DEFAULT) + 5 CREATE INDEX.
  · Tiempo esperado: < 5 segundos en Postgres Railway.
  · Si la DB ya tuviera las tablas nuevas (de un deploy parcial previo),
    Alembic detectaría el state y solo aplicaría lo faltante.

4.3) Orden de despliegue
  · Push a main → 9ea9bec ✓ (ya en origin/main)
  · Railway auto-deploy al detectar el push.
  · Build (~3-5 min) + Alembic + create_all safety-net (no-op ahora) +
    healthcheck.
  · Verificación post-deploy: ver §5.

4.4) Secrets / variables de entorno
  · Sin cambios. CERO nuevas variables.

4.5) Rebuild Docker
  · Automático en Railway. Sin instrucciones especiales.


--------------------------------------------------------------------------------
5. PROCEDIMIENTO DE PRUEBA (post-deploy)
--------------------------------------------------------------------------------

5.1) Health check
  ```bash
  curl -s https://wowhub-api-production.up.railway.app/health | jq .
  ```
  Esperado: {"status":"ok","version":"0.2.0",...}.

5.2) OpenAPI: 246 → 257 paths
  ```bash
  curl -s https://wowhub-api-production.up.railway.app/openapi.json \
    | python -c "import json,sys; print(len(json.load(sys.stdin)['paths']))"
  ```
  Esperado: 257 (vs 246 en V2.004–V2.006).

5.3) Endpoints HU_50–65 registrados
  Esperado (11 paths):
    /api/v1/tenants/{tid}/customers/inline
    /api/v1/tenants/{tid}/notification-logs
    /api/v1/tenants/{tid}/notification-send
    /api/v1/tenants/{tid}/notification-templates
    /api/v1/tenants/{tid}/notification-templates/init-defaults
    /api/v1/tenants/{tid}/payment-records
    /api/v1/tenants/{tid}/production/jobs/{job_id}
    /api/v1/tenants/{tid}/production/jobs/{job_id}/move
    /api/v1/tenants/{tid}/production/kanban
    /api/v1/tenants/{tid}/production/low-stock
    /api/v1/tenants/{tid}/products/inline

  Cada uno sin sesión válida debe devolver HTTP 401 (no 404, no 500):
  ```bash
  curl -s -o /dev/null -w '%{http_code}\n' \
    https://wowhub-api-production.up.railway.app/api/v1/tenants/00000000-0000-0000-0000-000000000000/production/kanban
  ```
  Esperado: 401.

5.4) Hero Showcase preservado
  ```bash
  curl -sI https://wowhub-api-production.up.railway.app/static/img/hero/page.png
  ```
  Esperado: 200 OK, ~772 KB.

5.5) Tablas nuevas en Railway DB
  Inspeccionar vía DB client (DATABASE_URL de Railway):
  ```sql
  SELECT table_name FROM information_schema.tables
  WHERE table_name IN ('production_jobs', 'insumo_movements',
    'payment_records', 'debt_adjustments', 'notification_templates',
    'notification_logs')
  ORDER BY table_name;
  ```
  Esperado: 6 rows.

5.6) Tests locales
  ```bash
  C:\Python311embed\python.exe -m pytest tests/test_hu50_65_produccion.py \
    tests/f0_baseline/ -q
  ```
  Esperado: 121 passed, 1 xpassed.


--------------------------------------------------------------------------------
6. ROLLBACK
--------------------------------------------------------------------------------

Si el deploy falla en producción:

6.1) Rollback de código (Railway)
  · Dashboard → Deployments → Redeploy del commit 5c040e5 (V2.006).
    Vuelve a estado estable en ~3 minutos.

6.2) Rollback de migración
  ```bash
  C:\Python311embed\python.exe -m alembic -c alembic.ini downgrade -1
  ```
  · Drop 6 tablas nuevas + 15 columnas extendidas.
  · Head vuelve a 2026_10_07_0002.

6.3) Rollback completo (a V2.004)
  · git revert 9ea9bec 9ea9bec^1 9ea9bec^2
  · O reset --hard al commit deseado (NO recomendado en main).


--------------------------------------------------------------------------------
7. TRAZABILIDAD
--------------------------------------------------------------------------------

7.1) Commits del release (orden cronológico)
  · 9ea9bec  feat(hu50-65): re-deploy con fix de causa raíz
  · 5c040e5  docs(release): V2.006 README rollback
  · 855196a  Revert "Merge branch 'feature/hu50-65-produccion-inline'"
  · 3ae2271  Revert "docs(release): README_V2.005..."
  · 22f8f80  docs(release): README_V2.005... (validación original)
  · 729b4e9  Merge branch 'feature/hu50-65-produccion-inline'
            (original, ← causa del primer 502)
  · 0625bb3  fix(hu50-65): 9 fixes detectados en auditoría
  · 5598711  docs(release): V2.004 audit general

7.2) Estado de feature branch
  · feature/hu50-65-produccion-inline: 4 commits ahead of main
    - e7b85ee feat: implementación inicial (causa del 502 original)
    - af0f1dd fix(enum): values_callable a 23 enums pre-existentes
    - 0625bb3 fix(hu50-65): 9 fixes auditoría
    - d24e4b9 fix(hu50-65): alinear enum types a String (la fix real)
  · Pendiente: cerrar feature branch o rebase contra main.

7.3) Archivos intervenidos por el fix real (commit 9ea9bec)
  En lugar de merge desde feature (que hubiera borrado Hero Showcase),
  se hizo cherry-pick selectivo de los archivos relevantes:
  · 14 archivos traídos del feature sin borrar Hero assets
  · 4 modelos cambiados de Enum() a String() (cause real del 502)


--------------------------------------------------------------------------------
8. VALIDACIÓN EJECUTADA
--------------------------------------------------------------------------------

Tests locales (post-fix, pre-push):
  · tests/test_hu50_65_produccion.py:    34/34 ✓
  · tests/f0_baseline/test_alembic.py:    18 passed + 1 xpassed ✓
  · tests/f0_baseline/test_inventory.py: 5/5 ✓
  · tests/f0_baseline/test_js_parser.py: 23/23 ✓
  · tests/f0_baseline/test_mapping.py:    9/9 ✓
  · tests/f0_baseline/test_prototype_*:  4/4 ✓
  · tests/f0_baseline/test_router.py:    12/12 ✓
  · tests/f0_baseline/test_schemas.py:   18/18 ✓
  · TOTAL: 121 passed, 1 xpassed

OpenAPI generation local:
  · 257 paths (vs 246 V2.006 baseline)
  · 11 nuevos endpoints HU_50..HU_65

Alembic (SQLite temporal):
  · upgrade head    → 66 tablas (60 pre-existentes + 6 nuevas), RC=0
  · downgrade base  → 1 tabla, RC=0 (reversible)

create_all safety-net (entrypoint línea 56):
  · RC=0 antes y después del fix
  · Sin attempt de CREATE TYPE (los modelos son String ahora)

Validación online (Railway) — EN CURSO:
  · /health                              → 200 OK (sano, operativo)
  · /api/v1/system/status                → started_at 14:12:45 UTC
                                            (V2.006 — pendiente rebuild)
  · /openapi.json                        → 246 paths (V2.006)
                                            (aún no refleja 9ea9bec)


--------------------------------------------------------------------------------
9. ESTADO FINAL DE DEPLOY
--------------------------------------------------------------------------------

A la hora de generar este release note (2026-10-20 19:53 CLT):

  · Commit 9ea9bec pusheado a origin/main ✓
  · Railway auto-deploy: NO iniciado todavía (o build en progreso)
  · Container activo: started_at 2026-10-20T14:12:45 UTC (V2.006)
  · /health responde 200 OK (V2.006 operativo)
  · /openapi.json reporta 246 paths (sin endpoints nuevos visibles)

AcCIÓN REQUERIDA del operador:
  1. Verificar en Railway Dashboard → Deployments si el build del
     commit 9ea9bec está en cola o falló silenciosamente.
  2. Si el build está en cola, esperar 3-5 min hasta completar.
  3. Si el build NO aparece, hacer Redeploy manual desde el dashboard
     con el SHA 9ea9bec78a15faab521a637beec417f61bfef461.
  4. Validar endpoints según §5.


================================================================================
FIN README_V2.007_HU50_65_REDEPLOY_2026-10-20.txt
================================================================================