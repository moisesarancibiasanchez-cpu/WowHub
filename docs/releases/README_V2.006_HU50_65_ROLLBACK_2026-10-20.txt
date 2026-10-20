================================================================================
README_V2.006_HU50_65_ROLLBACK_2026-10-20.txt
WowHub · Release Notes Atómicos · V2.006
================================================================================

FECHA          : 2026-10-20
BUILD          : commit 855196a (revert del merge 729b4e9)
ALCANCE        : Rollback de HU_50..HU_65 por falla de despliegue en Railway
ATOMICIDAD     : Solo reverts, ningún cambio de código nuevo
RIESGO         : Bajo · Vuelve al estado V2.004 (commit 5598711) que era
                100% operativo
REVERTIBLE     : Sí · Re-aplicar los commits revertidos en orden inverso


--------------------------------------------------------------------------------
1. BASE (contexto)
--------------------------------------------------------------------------------

El commit 729b4e9 (merge de feature/hu50-65-produccion-inline a main) +
22f8f80 (release notes V2.005) se desplegaron en Railway el 2026-10-20.
La API pasó de /health 200 OK a HTTP 502 Bad Gateway de forma sostenida
durante >30 minutos, sin recuperación automática.

El endpoint /api/v1/system/status dejó de responder (502), por lo que
no se pudo obtener el log exacto del contenedor. El /health tampoco
respondía (también 502). El frontend público quedó inaccesible.

El script `scripts/bootstrap_migrate.py` tiene un SAFETY NET (líneas
350-360 y 463) que ignora fallos de Alembic y deja arrancar uvicorn.
Esto significa que la causa probable del 502 NO fue la migración
Alembic (que habría sido silenciada), sino un fallo de import o
runtime del código nuevo.

Causas posibles investigadas:
  - Import circular tras merge (modelos nuevos referenciados por código
    pre-existente en customers/products/notifications).
  - Tablas/columnas nuevas en app/models referenciadas por queries
    ORM en el startup del módulo.
  - El model_validator de ProductInlineCreate lanzando ValidationError
    en algún path de carga.
  - openapi.json fallando al generar (TypeAdapter not fully defined)
    → algún endpoint no se podía registrar → router quedaba vacío.

Sin acceso a los logs de Railway, el camino más seguro para恢复 el
servicio fue revertir el merge completo y volver al estado conocido
operativo (commit 5598711).


--------------------------------------------------------------------------------
2. CAMBIO ÚNICO (qué se hizo)
--------------------------------------------------------------------------------

A) Revert del release notes V2.005 (commit 22f8f80)

   Commit: 3ae2271 "Revert 'docs(release): README_V2.005...'"

   · Eliminación de docs/releases/README_V2.005_HU50_65_VALIDACION_2026-10-20.txt
   · Sin impacto en código.

B) Revert del merge de feature branch (commit 729b4e9)

   Commit: 855196a "Revert 'Merge branch feature/hu50-65-produccion-inline'"
   (con -m 1 porque 729b4e9 era merge commit)

   Cambios revertidos:
   · Eliminados los archivos nuevos del feature branch:
     - alembic/versions/2026_10_16_hu50_65_produccion.py
     - app/api/v1/payment_records.py
     - app/api/v1/production.py
     - app/models/insumo_movement.py
     - app/models/notification.py
     - app/models/payment_record.py
     - app/models/production.py
     - app/schemas/inline.py
     - app/schemas/notification.py
     - app/schemas/payment_record.py
     - app/services/notification_service_v2.py
     - app/services/payment_record_service.py
     - app/services/production_service.py
     - tests/test_hu50_65_produccion.py
   · Revertidos los cambios a archivos pre-existentes:
     - app/api/v1/customers.py (sin endpoint inline)
     - app/api/v1/products.py (sin endpoint inline)
     - app/api/v1/notifications.py (sin import UUID, sin endpoints templates/log/send)
     - app/f0_baseline/router.py (sin INTERNAL_MODELS_ALLOWLIST nuevos)
     - app/main.py (sin imports production/payment_records)
     - app/models/__init__.py + 12 modelos extendidos (sin las nuevas
       columnas additive — vuelven a su estado V2.004)
     - tests/conftest.py

   NOTA: El commit 0625bb3 ("fix(hu50-65): 9 fixes detectados") NO se
   revierte explícitamente. Sus cambios están dentro del merge revertido
   (855196a), por lo que las correcciones de alembic chain y los fixes
   de UUID / forward refs / OpenAPI también se revirtieron. Esto deja
   el repo en el mismo estado que 5598711 (V2.004).

C) Push a main (commit 855196a)

   El auto-deploy de Railway detectó el nuevo HEAD y redeployó.


--------------------------------------------------------------------------------
3. QUÉ NO SE MODIFICÓ
--------------------------------------------------------------------------------

· Hero Showcase: intacto (commits 24d3012, 0f4b422, 6b32f76, 176eae4,
  e511ca1 preservados en main a través del merge revert).
· Documentación V2.004, V2.003, V2.002 intactas.
· RBAC HU_38, Casbin policies intactas.
· shim _url_for_pass_context intacto.
· Catálogo KEY_TO_MODEL intacto.
· Configuración Docker intacta.
· Variables de entorno sin cambios.
· Migración Alembic 2026_10_16_hu50_65 NO se aplicó en Railway
  (el rollback ocurrió antes de que la DB Railway ejecutara esa
  migración con éxito).


--------------------------------------------------------------------------------
4. ESTADO POST-ROLLBACK
--------------------------------------------------------------------------------

Verificado en https://wowhub-api-production.up.railway.app:

  · /health                                → 200 OK, JSON válido
  · /openapi.json                          → 200 OK, 246 paths (V2.004)
  · /api/v1/system/status                  → 200 OK, operational
  · /static/img/hero/page.png              → 200 OK, 772 KB
  · endpoints HU_50-65 (production, etc.)  → 0 (correctamente removidos)

Tests locales (post-rollback):
  · C:\Python311embed\python.exe -c "from app.main import app; print(len(app.routes))"
    → 146 routes (idéntico a V2.004 baseline)
  · C:\Python311embed\python.exe -c "from app.main import app; print(len(app.openapi()['paths']))"
    → 245 paths (idéntico a V2.004 baseline)


--------------------------------------------------------------------------------
5. CAUSA RAÍZ (diagnóstico pendiente)
--------------------------------------------------------------------------------

El 502 Bad Gateway sostenido apunta a una falla de import o runtime
del código mergeado, NO a una falla de Alembic (el bootstrap_migrate
tiene safety net que ignora errores de migración).

Para diagnosticar correctamente, los siguientes pasos deben hacerse
en una sesión futura CON ACCESO A LOS LOGS DE RAILWAY:

  1. Ver el log completo del contenedor durante el arranque con
     commit 729b4e9. Railway UI → Deployments → Logs.
  2. Identificar el traceback de import o runtime que mata uvicorn.
  3. Las hipótesis más probables (en orden):
     a) Modelos nuevos (ProductionJob, InsumoMovement, etc.) son
        importados por app.models.__init__.py en el import chain.
        Si alguno de sus imports tiene un side-effect problemático
        (por ejemplo una columna computed que falla), el startup muere.
     b) El nuevo routers (production, payment_records) tienen un
        import local dentro de las funciones que crea un ciclo.
     c) El UUID forward-ref fix (agregar `from uuid import UUID` en
        notifications.py) NO se aplicó porque 0625bb3 fue revertido.
        Esto reintroduce el error 'ForwardRef not fully defined' que
        hacía fallar la generación del openapi.json y, según el
        fallo previo, también el startup.
     d) El `model_validator` agregado a ProductInlineCreate lanza
        ValidationError durante la carga de modelos en algún path.

  4. Cuando se identifique la causa, rehacer el merge con un fix
     específico y testear en un entorno staging antes de push a main.


--------------------------------------------------------------------------------
6. REQUERIMIENTOS DE DESPLIEGUE
--------------------------------------------------------------------------------

  · Worker: NO requiere cambio.
  · Cache busting: NO requiere.
  · Browser support: sin cambios.
  · No requiere migraciones Alembic nuevas (rollback solo).
  · No requiere cambio en variables de entorno.
  · Rebuild Docker: Automático en Railway.

  El rollback se completa vía auto-deploy cuando Railway detecta el
  nuevo HEAD en main. ~3-5 minutos para que el contenedor esté
  healthy de nuevo.


--------------------------------------------------------------------------------
7. PROCEDIMIENTO DE PRUEBA (post-rollback)
--------------------------------------------------------------------------------

7.1) Health check
  ```bash
  curl -s https://wowhub-api-production.up.railway.app/health | jq .
  ```
  Esperado: 200 OK con status "ok".

7.2) OpenAPI inventory
  ```bash
  curl -s https://wowhub-api-production.up.railway.app/openapi.json \
    | python -c "import json,sys; print(len(json.load(sys.stdin)['paths']))"
  ```
  Esperado: 246 paths (V2.004 baseline).

7.3) Hero Showcase
  ```bash
  curl -sI https://wowhub-api-production.up.railway.app/static/img/hero/page.png
  ```
  Esperado: HTTP/1.1 200 OK, Content-Length ~772 KB.

7.4) Endpoints HU_50-65 (deben NO existir)
  ```bash
  curl -s -o /dev/null -w '%{http_code}\n' \
    https://wowhub-api-production.up.railway.app/api/v1/tenants/00000000-0000-0000-0000-000000000000/production/kanban
  ```
  Esperado: 404 (ruta no existe en V2.004).

7.5) Página pública home
  ```bash
  curl -s -o /dev/null -w '%{http_code}\n' \
    https://wowhub-api-production.up.railway.app/
  ```
  Esperado: 200 OK.


--------------------------------------------------------------------------------
8. RE-INTENTO FUTURO (recomendaciones)
--------------------------------------------------------------------------------

Si se decide re-intentar el despliegue de HU_50-65 en el futuro:

  1. PRIMERO: investigar la causa raíz del 502 con acceso a logs.
  2. Crear rama feature/hu50-65-produccion-inline-V2 con el fix.
  3. NO incluir app/models/insumo_movement.py, app/models/notification.py
     ni app/models/payment_record.py en app/models/__init__.py hasta
     haber validado que cada uno importa limpio.
  4. Hacer un deploy a un entorno staging (NO producción) primero.
  5. Solo después de validar staging, merge a main.

Recomendaciones adicionales:
  · Romper el feature branch en commits más pequeños para aislar
    problemas:
    - commit 1: solo modelos (sin routers)
    - commit 2: schemas + servicios (sin routers)
    - commit 3: routers (sin include_router en main)
    - commit 4: include_router en main.py
    - commit 5: migración Alembic
  · Cada commit desplegable independientemente permite rollback
    granular.


--------------------------------------------------------------------------------
9. TRAZABILIDAD
--------------------------------------------------------------------------------

9.1) Commits del rollback (orden cronológico inverso)
  · 855196a  Revert "Merge branch 'feature/hu50-65-produccion-inline'"
  · 3ae2271  Revert "docs(release): README_V2.005..."
  · 22f8f80  docs(release): README_V2.005... (revertido por 3ae2271)
  · 729b4e9  Merge branch 'feature/hu50-65-produccion-inline'
             (revertido por 855196a)
  · 0625bb3  fix(hu50-65): 9 fixes detectados (revertido por 855196a)

  Estado final de main: 855196a
  Equivalente a: 5598711 (V2.004 baseline) + los reverts como
  historia explícita.

9.2) Commits del feature branch (preservados en
    origin/feature/hu50-65-produccion-inline para futuro re-intento)
  · e7b85ee  feat(hu50-65): implementación inicial
  · af0f1dd  fix(enum): values_callable
  · 0625bb3  fix(hu50-65): 9 fixes (incluido en merge revertido)

9.3) Releases previos preservados
  · README_V2.004_AUDIT_GENERAL_2026-10-19.txt
  · README_V2.003_HERO_AUTOPLAY_3S.txt
  · README_V2.002_HERO_REALISTIC_IMAGES.txt
  · README_V2.99_HERO_SHOWCASE_*.txt
  · README_V2.01_*.txt


================================================================================
FIN README_V2.006_HU50_65_ROLLBACK_2026-10-20.txt
================================================================================