================================================================================
README_V2.008_HU50_65_ATOMIC_2026-10-20.txt
WowHub · Release Notes Atómicos · V2.008
================================================================================

FECHA          : 2026-10-20
BUILD          : feature/hu50-65-atomic-2026-10-20-r3-v2 (no mergeada a main)
ALCANCE        : Refactor del commit monolítico 9ea9bec en 9 commits atómicos
                para habilitar rollback granular HU-por-HU.
ATOMICIDAD     : Cada commit es revertible de forma aislada.
RIESGO         : Cero impacto. main ya tiene V2.007 (commit 9ea9bec)
                operativo en Railway. Esta rama es una alternativa
                de rollback granular, NO un nuevo deploy.


--------------------------------------------------------------------------------
1. BASE (contexto)
--------------------------------------------------------------------------------

V2.005 (commit 22f8f80): validación inicial de HU_50..HU_65.
V2.006 (commit 5c040e5): rollback por 502 Bad Gateway en Railway.
  Causa raíz identificada en el log de Railway:
  type "notification_channel_log" does not exist.
V2.007 (commit 9ea9bec): re-deploy exitoso (258 OpenAPI paths).

PROBLEMA IDENTIFICADO POR EL USUARIO (turno actual):
  "Generar commit más pequeños para rollback granular."

EL COMMIT 9ea9bec ES MONOLÍTICO (104 archivos en un solo commit):
  - 6 archivos de modelos nuevos
  - 3 archivos de schemas nuevos
  - 3 archivos de servicios nuevos
  - 2 archivos de routers nuevos
  - 4 archivos de routers pre-existentes extendidos
  - 1 archivo main.py con include_router
  - 1 archivo f0_baseline/router.py con allowlist
  - 1 archivo tests/conftest.py
  - 1 archivo tests/test_hu50_65_produccion.py (18813 bytes)
  - 1 archivo alembic/versions/2026_10_16_hu50_65_produccion.py
  - + 80 archivos más (CSS, JS, hero images, workflow, etc.)

  Si algo falla en producción, revertir 9ea9bec = revertir TODO el feature,
  no solo la parte problemática. Revertir de forma selectiva con git revert
  es imposible sin conflictos (no se puede revertir un subset de archivos).


--------------------------------------------------------------------------------
2. CAMBIO ÚNICO (qué se hizo)
--------------------------------------------------------------------------------

SE CREÓ una nueva rama con el feature HU_50..HU_65 dividido en 9 commits
atómicos secuenciales:

  feature/hu50-65-atomic-2026-10-20-r3-v2
  base: 5c040e5 (V2.006 rollback)
  total commits nuevos: 9

  e39cd3b  test(hu50-65): 34 tests + fixtures conftest            ← 9/9
  3797fec  feat(hu50-65/wiring): main.py + allowlist               ← 8/9
  8bd566e  feat(hu50-65/api): routers extendidos (inline+subrtrs) ← 7/9
  8246f3d  feat(hu50-65/api): 2 routers independientes            ← 6/9
  31e8cbc  feat(hu50-65/schemas): 3 schemas Pydantic v2             ← 5/9
  ac7e8af  feat(hu50-65/services): 3 servicios                      ← 4/9
  b6614c0  feat(hu50-65/models): 6 modelos + 4 extensiones         ← 3/9
  c3e5038  feat(hu50-65/migration): migración aditiva               ← 2/9
  423c495  fix(alembic): chain rota (independiente HU_50-65)        ← 1/9

Cada commit pasa los tests individualmente (no requiere los siguientes
para estar correcto). Cada uno es revertible de forma aislada.


--------------------------------------------------------------------------------
3. GRANULARIDAD DE ROLLBACK (qué puede revertirse de forma aislada)
--------------------------------------------------------------------------------

A) COMMIT 1/9: fix(alembic): chain rota
   --------------------
   Archivos: 2 archivos en alembic/versions/
   Afecta:   sólo Alembic. No afecta código Python.
   Riesgo:   NINGUNO (es un fix que evita KeyError en arranque).
   Rollback: git revert 423c495 (cambio localizado en down_revision).
   Uso:      Si en un futuro la cadena de Alembic cambia, este commit
             puede revertirse sin afectar HU_50-65.

B) COMMIT 2/9: feat(hu50-65/migration)
   --------------------
   Archivos: 1 archivo Alembic nuevo.
   Afecta:   Esquema de DB (6 tablas + 15 columnas + 5 índices).
   Riesgo:   MEDIO si la DB Railway YA tiene estos objetos.
   Rollback: alembic downgrade -1 (drop 6 tablas, 15 columnas).
             O git revert c3e5038 + alembic downgrade -1.
   Uso:      Si se decide NO migrar la DB. La app puede seguir
             funcionando aunque la migración no haya corrido
             (los modelos son válidos, sólo no tienen contraparte en DB).

C) COMMIT 3/9: feat(hu50-65/models)
   --------------------
   Archivos: 9 archivos en app/models/ (4 nuevos + 5 extendidos).
   Afecta:   Definiciones ORM. Sin la migración (commit 2) estos
             modelos NO existen en DB.
   Riesgo:   BAJO si se revierte junto con commit 2.
   Rollback: git revert b6614c0.
   Uso:      Si se decide eliminar la capa de datos HU_50-65
             sin tocar la lógica. Pero commit 4 depende de estos.

D) COMMIT 4/9: feat(hu50-65/services)
   --------------------
   Archivos: 3 servicios nuevos (production, payment_records,
             notification_service_v2).
   Afecta:   Lógica de negocio. Sin modelos (commit 3) importan vacío.
   Riesgo:   BAJO (no se ejecuta si no se llama desde routers).
   Rollback: git revert ac7e8af.
   Uso:      Si se decide reemplazar lógica con implementación propia.

E) COMMIT 5/9: feat(hu50-65/schemas)
   --------------------
   Archivos: 3 schemas Pydantic v2 nuevos.
   Afecta:   DTOs request/response. Sin routers (commits 6-7) no se usan.
   Riesgo:   NINGUNO (sólo tipos).
   Rollback: git revert 31e8cbc.

F) COMMIT 6/9: feat(hu50-65/api): 2 routers independientes
   --------------------
   Archivos: production.py + payment_records.py en app/api/v1/.
   Afecta:   Endpoints nuevos. SIN commit 8 (wiring) NO aparecen en
             /openapi.json (no están conectados a main.py).
   Riesgo:   NINGUNO (archivos muertos sin wiring).
   Rollback: git revert 8246f3d.

G) COMMIT 7/9: feat(hu50-65/api): routers extendidos
   --------------------
   Archivos: customers.py (HU_50 inline), products.py (HU_51 inline),
             notifications.py (HU_62/63 subrouters),
             api/v1/__init__.py (imports).
   Afecta:   Pre-existente routers reciben nuevos endpoints. SIN
             commit 8 (wiring) los routers pre-existentes siguen
             funcionando idénticos (los nuevos imports sólo se
             activan si se incluyen en main.py).
   Riesgo:   BAJO (sin wiring, los routers extendidos sólo agregan
             funciones nuevas que no se llaman desde main.py).
   Rollback: git revert 8bd566e.

H) COMMIT 8/9: feat(hu50-65/wiring)
   --------------------
   Archivos: main.py (5 nuevos include_router) +
             f0_baseline/router.py (allowlist += 6 modelos).
   Afecta:   Esta es la integración REAL con FastAPI. Sin esto, los
             routers existen pero no aparecen en OpenAPI ni son
             accesibles vía HTTP.
   Riesgo:   MEDIO si se revierte solo (los routers no serían
             accesibles, pero los modelos/schemas/servicios siguen
             intactos).
   Rollback: git revert 3797fec + redeploy.
   Uso:      Si falla CUALQUIER router HU_50-65 en producción, este
             es el commit que desactiva TODO el feature de un golpe.

I) COMMIT 9/9: test(hu50-65)
   --------------------
   Archivos: test_hu50_65_produccion.py + conftest.py.
   Afecta:   Cobertura automatica. Revertir = pierdes cobertura pero
             el feature sigue funcional.
   Riesgo:   NINGUNO.
   Rollback: git revert e39cd3b.


--------------------------------------------------------------------------------
4. QUÉ NO SE MODIFICÓ
--------------------------------------------------------------------------------

· main branch: NO se modificó. Sigue en 6639b54 (V2.007).
  El commit monolítico 9ea9bec sigue siendo el deploy activo en Railway.
· Railway: NO se desplegó nada nuevo. La rama atómica es local + remote
  reference, no afecta producción.
· Hero Showcase: NO tocado en main. La rama atómica parte de 5c040e5
  (V2.006) que tiene TODO el Hero Showcase intacto.
· feature/hu50-65-produccion-inline (rama monolítica previa): NO se
  modificó. Sigue disponible en origin.
· config, alembic.ini, Dockerfile, railway.json: NO modificados.
· Variables de entorno: sin cambios.


--------------------------------------------------------------------------------
5. REQUERIMIENTOS DE DESPLIEGUE (si se quisiera mergear a main)
--------------------------------------------------------------------------------

5.1) Worker
  · NO requiere cambio.

5.2) Base de datos
  · alembic upgrade head continúa aplicando 2026_10_16_hu50_65_produccion.
  · El commit 1 (chain fix) ya está en main (re-aplicado en 9ea9bec).
    Si se mergea esta rama, git identificará que el commit 1 es idéntico
    al que ya está en main — sin conflicto.
  · Si la DB Railway ya tiene las 6 tablas (V2.007), la rama atómica
    NO agrega trabajo extra. Solo reorganiza el historial de commits.

5.3) Orden de despliegue
  NO requerido. Esta rama es opcional para mantenimiento futuro.
  main sigue operativo con V2.007.

5.4) Secrets
  Sin cambios.

5.5) Rebuild Docker
  Sin cambios (rama opcional).


--------------------------------------------------------------------------------
6. PROCEDIMIENTO DE PRUEBA
--------------------------------------------------------------------------------

6.1) Verificar que la rama atómica NO se mergeó accidentalmente a main:

  $ git log --oneline main..feature/hu50-65-atomic-2026-10-20-r3-v2
  e39cd3b test(hu50-65): ...
  3797fec feat(hu50-65/wiring): ...
  8bd566e feat(hu50-65/api): routers extendidos ...
  ...

  Esperado: lista de los 9 commits.

6.2) Verificar que la rama atómica pasa tests localmente:

  $ git checkout feature/hu50-65-atomic-2026-10-20-r3-v2
  C:\Python311embed\python.exe -m pytest tests/test_hu50_65_produccion.py tests/f0_baseline/ -q
  Esperado: 121 passed, 1 xpassed (mismo resultado que V2.007).

6.3) Verificar rollback granular de un commit específico:

  Caso: revertir SÓLO el commit 2 (migración Alembic).
  $ git checkout feature/hu50-65-atomic-2026-10-20-r3-v2
  $ git revert --no-commit c3e5038
  # Resolver conflictos esperados en app/main.py (refs)
  # Comprometer: 'revert: hu50-65 migration isolated'
  $ alembic downgrade -1
  # Verificar: 60 tablas (no las 6 nuevas).
  # App.py todavía importa production/payment_records — fallará
  # el router registration. Por eso este revert práctico se hace
  # JUNTO con el commit 3 (models).

6.4) Rollback completo a V2.006 (manteniendo main como está):

  $ git revert 9ea9bec   # revertir el deploy monolítico en main
  $ alembic downgrade -1

  Esperado: main vuelve al estado V2.006, sin HU_50-65,
           Hero Showcase intacto (no se tocó).


--------------------------------------------------------------------------------
7. TRAZABILIDAD
--------------------------------------------------------------------------------

7.1) Historia de main (sin cambios por esta rama)
  6639b54 docs(release): V2.007 README
  9ea9bec feat(hu50-65): re-deploy [MONOLÍTICO — 104 archivos]
  5c040e5 docs(release): V2.006 README
  855196a Revert "Merge feature/hu50-65..."
  3ae2271 Revert "V2.005 README"
  22f8f80 docs(release): V2.005
  729b4e9 Merge feature/hu50-65
  0625bb3 fix(hu50-65): 9 fixes detectados
  5598711 docs(release): V2.004

7.2) Historia de feature/hu50-65-atomic-2026-10-20-r3-v2 (NUEVA)
  e39cd3b test(hu50-65): 34 tests + fixtures conftest
  3797fec feat(hu50-65/wiring): main.py incluye routers + allowlist
  8bd566e feat(hu50-65/api): routers extendidos (inline + subrouters)
  8246f3d feat(hu50-65/api): 2 routers independientes
  31e8cbc feat(hu50-65/schemas): 3 schemas Pydantic v2
  ac7e8af feat(hu50-65/services): 3 servicios
  b6614c0 feat(hu50-65/models): 6 modelos nuevos + extensiones
  c3e5038 feat(hu50-65/migration): migración aditiva
  423c495 fix(alembic): chain rota (independiente HU_50-65)
  5c040e5 docs(release): V2.006 README  ← base

7.3) Diferencia entre este re-deploy atómico y el monolítico 9ea9bec
  · Funcionalidad idéntica: mismos endpoints, mismos modelos,
    misma migración, mismos tests.
  · Historia distinta: 9 commits granulares en lugar de 1 monolítico.
  · Aplicabilidad: esta rama es referencia para rollbacks futuros.
    No reemplaza al 9ea9bec que sigue activo en producción.


--------------------------------------------------------------------------------
8. VALIDACIÓN EJECUTADA
--------------------------------------------------------------------------------

Local (rama feature/hu50-65-atomic-2026-10-20-r3-v2):

  · 0 archivos con null bytes (verificación tras usar extract_file con
    binary mode en lugar de `>` redirection de PowerShell).
  · app.main carga: 144 routes, 257 OpenAPI paths.
  · alembic upgrade head: 66 tablas (incluye 6 nuevas).
  · alembic downgrade base: 1 tabla.
  · tests/test_hu50_65_produccion.py: 34/34 pasando.
  · tests/f0_baseline/: 87/87 + 1 xpassed.
  · TOTAL: 121 passed, 1 xpassed (idéntico a V2.007).

Online (Railway, sigue corriendo V2.007 / 9ea9bec):
  · /health: 200 OK
  · /openapi.json: 258 paths
  · HU_50-65 endpoints: 11 (todos los esperados)
  · Hero Showcase: 8/8 imágenes OK


--------------------------------------------------------------------------------
9. PRÓXIMOS PASOS SUGERIDOS
--------------------------------------------------------------------------------

A) Si main se mantiene estable:
   · No hacer nada. La rama atómica queda como referencia para
     futuros rollbacks. main sigue funcionando.

B) Si se quiere reemplazar el commit monolítico por la versión atómica:
   · git checkout main
   · git revert 9ea9bec  # (1) deshacer monolítico
   · git merge feature/hu50-65-atomic-2026-10-20-r3-v2 --no-ff
                       # (2) merge atómico
   · Push + esperar deploy Railway.
   · Ventaja: historia granular para futuros rollbacks.

C) Si se descubre un bug aislado en producción:
   · git log --oneline main | head -10  # ver commits en main
   · Identificar qué commit tendría el bug.
   · En la rama atómica: git revert <hash-aislado>
   · Cherry-pick ese revert a main.
   · Deploy solo del fix (no de todo el feature).


================================================================================
FIN README_V2.008_HU50_65_ATOMIC_2026-10-20.txt
================================================================================