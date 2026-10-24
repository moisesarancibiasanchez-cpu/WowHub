================================================================================
README V2.015 — ALMACENAMIENTO PERSISTENTE EN RAILWAY
Preparación del código y del runbook para que las imágenes subidas no se
pierdan en cada despliegue
================================================================================

VERSIÓN         : V2.015
FECHA           : 2026-10-24
VENTANA         : 2026-10-24 (Chile)
BUILD           : rama main (base 9b3772f, cierre de V2.014)
ALCANCE         : requisito de despliegue que quedaba abierto en V2.014 §4:
                  montar un volumen persistente en /app/storage y poder
                  diagnosticar qué imágenes se perdieron.
ATOMICIDAD      : 5 commits independientes, cada uno revertible por separado.
REVERSIÓN       : 5 commits, 5 archivos
RIESGO          : BAJO para la app. El único cambio de ejecución es el
                  entrypoint (permisos del volumen + bajada de privilegios);
                  el volumen en sí lo crea el usuario en el panel.

--------------------------------------------------------------------------------
1. BASE
--------------------------------------------------------------------------------

Rama          : main
Base          : 9b3772f (cierre de V2.014)
Commits       : 5, en orden de aplicación:

  <c1>  fix(scripts): el diagnostico de uploads distingue el disco local del
        de produccion
  <c2>  fix(deploy): el entrypoint prepara el volumen y baja privilegios
  <c3>  docs(runbook): procedimiento de almacenamiento persistente en Railway
  <c4>  test(v2.015): regresion del volumen persistente de Railway
  <c5>  docs(release): README V2.015

Archivos modificados:

  scripts/check_missing_uploads.py       +50 / -3
  scripts/entrypoint.sh                  +35
  docs/DEPLOY_RAILWAY.md                 +162 / -1
  tests/test_v2_015_volumen_railway.py   +179  (nuevo)
  docs/releases/README_V2.015_ALMACENAMIENTO_PERSISTENTE_2026-10-24.txt
                                         (nuevo)

--------------------------------------------------------------------------------
2. CAMBIO ÚNICO
--------------------------------------------------------------------------------

Una sola idea: **que las imágenes subidas sobrevivan a los despliegues, y
que se pueda saber con certeza cuáles se perdieron**.

V2.014 arregló el error de la previsualización y dejó anotado que el
almacenamiento de producción es efímero. Este release deja el lado de
código y el procedimiento listos para que eso se solucione.

═══ 2.1) EL DIAGNÓSTICO NO PODÍA DARSE DESDE FUERA ═══

ARCHIVO: scripts/check_missing_uploads.py

FUNCIÓN INTERVENIDA: `main()`

    El script comparaba la tabla `uploads` contra el directorio de storage
    de DONDE SE ESTABA EJECUTANDO. Como el volumen de producción vive
    dentro del contenedor de Railway, correrlo desde la máquina del
    usuario daba un resultado engañoso: TODOS los uploads aparecían como
    "sin archivo en disco" (porque el disco local está vacío), cuando en
    realidad ese no era el disco que había que mirar.

    Cambios:
      · Nuevo modo `--db-only`: lista lo que la plataforma tiene
        registrado en la base de datos. Es lo que sirve para saber qué
        imágenes hay que volver a subir, y sí se puede hacer desde tu
        máquina.
      · Cuando el directorio de storage no existe, el script AVISA que ese
        resultado no describe el disco de producción y cómo correrlo bien
        (dentro del servicio, con `railway ssh` / `railway run`).
      · La salida indica siempre qué `storage_dir` se está revisando.
      · Se fuerza UTF-8 en stdout: el aviso usa caracteres no-ASCII y con
        la consola de Windows (cp1252) reventaba con UnicodeEncodeError.

    El script sigue siendo de SÓLO LECTURA.

═══ 2.2) EL VOLUMEN DE RAILWAY ES DEL USUARIO ROOT ═══

Railway monta los volúmenes con el usuario `root`. La imagen de WowHub
corre como `wowhub` (`USER wowhub` en el Dockerfile). Con un volumen
montado en `/app/storage`, las subidas fallaban con:

    EACCES: permission denied, mkdir '/app/storage/<tenant_id>'

Es la advertencia de la propia documentación de Railway: *"Docker images
that run as a non-root UID by default will have permissions issues when
performing operations within an attached volume"*.

ARCHIVO: scripts/entrypoint.sh

FUNCIÓN INTERVENIDA: bloque de arranque (antes de esperar la DB)

    Si el contenedor arranca como root (RAILWAY_RUN_UID=0 en las variables
    del servicio), el entrypoint:

      1. crea /app/storage y /app/data,
      2. se los da al usuario `wowhub` (chown -R),
      3. BAJA PRIVILEGIOS antes de arrancar uvicorn.

    La app sigue corriendo como `wowhub`; sólo el arranque es root. La
    bajada de privilegios intenta `gosu`, `setpriv` y `su`, en ese orden, y
    si no hubiera ninguno sigue como root avisando.

    El bloque es idempotente: al re-ejecutarse como `wowhub`, `id -u` ya no
    es 0 y no vuelve a ejecutarse (sin bucle).

    Sin `RAILWAY_RUN_UID=0` el contenedor arranca como `wowhub`, no puede
    hacer el chown y las subidas siguen fallando: esa variable es
    obligatoria en el servicio.

═══ 2.3) EL PROCEDIMIENTO, POR ESCRITO ═══

ARCHIVO: docs/DEPLOY_RAILWAY.md

FUNCIÓN INTERVENIDA: nueva sección 7 (la 7 vieja pasa a ser la 8)

    7.0 Por qué (el filesystem de Railway es efímero; evidencia)
    7.1 Crear el volumen en el panel (Mount Path /app/storage)
    7.2 Permisos (RAILWAY_RUN_UID=0) — el paso que casi todos se saltan
    7.3 Desplegar
    7.4 Verificar (log esperado, prueba funcional y la prueba clave:
        forzar un redeploy y ver si la imagen sigue viéndose)
    7.5 Resubir las imágenes perdidas (dónde se sube cada una)
    7.6 Rollback
    7.7 Checklist de 6 puntos

    Dato incluido: el esquema oficial de railway.json NO admite
    `volumeMounts` (<https://railway.app/railway.schema.json>); el volumen
    se crea desde el panel, no desde el repo.

--------------------------------------------------------------------------------
3. QUÉ NO SE MODIFICÓ
--------------------------------------------------------------------------------

· La API: 0 cambios. Ningún endpoint, ninguna firma, ningún status.
· Los modelos, las migraciones y el esquema: 0 cambios. No hay revisión
  nueva de Alembic; la head sigue siendo 2026_10_24_fix_rbac_id_type.
· La matriz de permisos y el seed de Casbin: 0 cambios.
· El Dockerfile: 0 cambios. Sigue siendo `USER wowhub`; el bloque del
  entrypoint sólo actúa si el contenedor arrancó como root.
  No se añadió ningún paquete a la imagen (gosu/setpriv/su se buscan en
  el PATH; si no están, se sigue como root avisando).
· railway.json: 0 cambios. El esquema oficial no admite `volumeMounts`.
· El servicio de archivos (app/services/upload_service.py) y los endpoints
  de uploads: 0 cambios. No se cambia ni la ruta ni el formato de la URL
  canónica.
· El flujo de subida y el preview: 0 cambios (los de V2.014).
· El script check_missing_uploads sigue siendo de sólo lectura: no borra
  ni modifica nada.
· Variables de entorno existentes: 0 cambios. Se AGREGA una
  (RAILWAY_RUN_UID=0) y se documenta que es obligatoria cuando haya
  volumen.
· Tareas Celery / Worker: 0 cambios.
· Hero Showcase, estilos, i18n: 0 cambios.
· Documentos V2.001-V2.014: intactos.
· No se ejecutó ningún DROP ni borrado de filas en ninguna DB.
· No se usó git reset --hard ni git push --force.

--------------------------------------------------------------------------------
4. REQUERIMIENTOS DE DESPLIEGUE
--------------------------------------------------------------------------------

Este release NO despliega nada por sí solo: deja el código y el
procedimiento listos. Lo que hay que hacer, en orden:

  1. Railway → servicio de la API → **Volumes** → **Add Volume** →
     Mount Path `/app/storage`. (Desde el panel: el esquema oficial de
     railway.json no admite volumeMounts.)
  2. Railway → servicio de la API → **Variables** → `RAILWAY_RUN_UID=0`.
     Sin esta variable el contenedor arranca como `wowhub`, no puede dar
     el volumen al usuario de la app y las subidas fallan con EACCES.
  3. Push a main (este release) → Railway redespliega.
  4. Verificar según docs/DEPLOY_RAILWAY.md §7.4: las dos líneas en el log,
     una subida de prueba y —la que importa— un redeploy forzado: si la
     imagen sigue viéndose, el volumen funciona.
  5. Resubir las imágenes perdidas (§7.5).

· REQUIERE CAMBIAR EL WORKER: NO.
· BASE DE DATOS: ninguna migración, ninguna intervención manual.
· ROLLBACK:
  - Quitar el volumen desde el panel (detach): la app vuelve a
    /app/storage efímero. Funciona; se pierden imágenes en cada deploy.
    Es el estado anterior a V2.014, sin revertir código.
  - `git revert <commit-del-fix-v2.015>` + push: el entrypoint vuelve a
    arrancar sin el ajuste de permisos. El resto de la app no cambia.

--------------------------------------------------------------------------------
5. PROCEDIMIENTO DE PRUEBA RECOMENDADO
--------------------------------------------------------------------------------

VERIFICACIÓN AUTOMÁTICA (una orden):
  $ python -m pytest tests/test_v2_015_volumen_railway.py -q
  Esperado: 12 passed.

COMPROBACIÓN MANUAL DEL PROCEDIMIENTO (la que de verdad importa):
  1. Crear el volumen con Mount Path /app/storage.
  2. Poner RAILWAY_RUN_UID=0.
  3. Desplegar y revisar el log: deben salir
     "▶ Ajustando permisos del almacenamiento (arranque como root)..." y
     "▶ Bajando privilegios a 'wowhub' (gosu|setpriv|su)...".
  4. Subir una imagen desde el dashboard → debe previsualizarse.
  5. Forzar un redeploy → volver a abrir la imagen → debe SEGUIR viéndose.
  6. `railway run --service <servicio> python -m scripts.check_missing_uploads`
     → debe listar los archivos presentes en el volumen.

--------------------------------------------------------------------------------
6. TRAZABILIDAD
--------------------------------------------------------------------------------

Defecto / requisito                          Commit  Prueba de regresión
------------------------------------------------------------------------------
El diagnóstico no servía desde fuera        <c1>    test_el_script_avisa_cuando_el_
(daba falsos positivos)                               disco_no_es_el_de_produccion
                                                        test_el_script_tiene_modo_db_only
El script reventaba en la consola de        <c1>    test_el_script_acepta_console_utf8
Windows (UnicodeEncodeError)
El volumen del panel es de root y la        <c2>    test_el_entrypoint_ajusta_los_
imagen corre como wowhub (EACCES)                   permisos_del_volumen
                                                        test_el_entrypoint_baja_privilegios_
                                                        antes_de_arrancar_uvicorn
                                                        test_el_bloque_de_privilegios_no_se_
                                                        reentra_en_bucle
El Mount Path debe coincidir con            <c2>    test_el_workdir_de_la_imagen_coincide_
STORAGE_PATH                                        con_el_mount_path
                                                        test_la_imagen_sigue_corriendo_como_
                                                        usuario_no_root
No había procedimiento escrito              <c3>    test_el_runbook_documenta_el_
                                                        procedimiento_completo
                                                        test_el_runbook_explica_el_paso_de_
                                                        verificacion
El volumen no se declara en railway.json     <c4>    test_railway_json_no_declara_volumemounts

--------------------------------------------------------------------------------
7. LÍMITES DE LA VERIFICACIÓN
--------------------------------------------------------------------------------

7.1) EL VOLUMEN LO CREA EL USUARIO EN EL PANEL
  No hay acceso al dashboard de Railway desde este entorno (el login pide
  credenciales de la cuenta del usuario). Lo que sí se verificó: el
  esquema oficial de railway.json, el comportamiento documentado por
  Railway sobre permisos de volúmenes con imágenes no-root, y el
  comportamiento del entrypoint. El volumen hay que crearlo en el panel.

7.2) EL ENTRYPOINT NO SE EJECUTÓ COMO ROOT EN ESTE ENTORNO
  No hay un contenedor Linux con root disponible aquí. La lógica se revisó
  línea por línea y se cubre con tests estáticos, pero el arranque real
  con volumen se verifica en el primer deploy (el log dice si el bloque
  corrió).

7.3) PENDIENTES HEREDADOS
  · La cadena de Alembic de producción sigue sin avanzar (V2.012 §7.1):
    falta leer el log de Railway para identificar la migración que falla.
  · Los 22 scripts de auditoría untracked en la raíz del repo, más
    `storage/` y `wowhub.db` que generé en las pruebas locales: hay que
    borrarlos a mano (la política local bloquea el borrado).
  · La inspección visual del uploader con la cuenta real del usuario:
    sigue pendiente (V2.014 §7.3).

--------------------------------------------------------------------------------
8. RESULTADOS DE LA VALIDACIÓN
--------------------------------------------------------------------------------

LOCAL:
  · tests/test_v2_015_volumen_railway.py  → 12 passed (nuevo)
  · py_compile sobre scripts/check_missing_uploads.py → OK
  · El script se probó en los tres modos contra una base SQLite con
    esquema real y una fila de prueba:
      - --db-only → lista los uploads de la base ✓
      - disco con el archivo presente → "OK: todos los archivos están
        presentes." ✓
      - disco inexistente → avisa que no es el disco de producción ✓
  · Suite crítica completa (375 tests) → 370 passed, 5 skipped, 0 fallos
    (310 s). Archivos cubiertos: test_v2_012_ui_and_permissions,
    test_v2_013_admin_menu_roles, test_v2_014_uploads_preview,
    test_v2_015_volumen_railway, test_dashboard_routes_and_scripts,
    test_dashboard_layout, test_dashboard_modal_refactor,
    test_tenant_dashboard_urls, test_rbac, test_auth, test_tenants,
    test_tenants_me, test_schema_drift_reconciliation,
    test_enum_labels_consistency, test_hu50_65_produccion,
    test_deprecation_fixes.

ONLINE: no aplica a este release (cambios de despliegue e infra, no de
comportamiento de la API). El endpoint de contenido y el preview ya
verificados en V2.014 §8 siguen en pie.
