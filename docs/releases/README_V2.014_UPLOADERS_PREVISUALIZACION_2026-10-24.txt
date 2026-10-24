================================================================================
README V2.014 — UPLOADERS Y PREVISUALIZACIÓN DE IMÁGENES
Restauración de la previsualización de archivos en todas las páginas del
dashboard
================================================================================

VERSIÓN         : V2.014
FECHA           : 2026-10-24
VENTANA         : 2026-10-24 (Chile)
BUILD           : rama main (base 4bbda0e, cierre de V2.013)
ALCANCE         : 1 defecto reportado por el usuario (todos los uploaders de
                  archivos del dashboard lanzan "⚠ No se pudo cargar la
                  imagen"), más 3 defectos hermanos que el mismo caso raíz
                  dejaba rotos en otras páginas.
ATOMICIDAD      : 7 commits independientes, cada uno revertible por separado
                  sin arrastrar a los demás.
REVERSIÓN       : 7 commits, 8 archivos
RIESGO          : BAJO. Sin migraciones, sin DROP, sin cambios de contrato de
                  la API. No se abre acceso a ningún recurso nuevo.

--------------------------------------------------------------------------------
1. BASE
--------------------------------------------------------------------------------

Rama          : main
Base          : 4bbda0e (cierre de V2.013)
Commits       : 7, en orden de aplicación:

  <c1>  fix(deps): acepta la cookie de sesion en los endpoints que sirven
        archivos
  <c2>  fix(api/uploads): el endpoint de contenido daba 500 en todas las
        peticiones
  <c3>  fix(ui/app): el preview muestra el motivo real y no culpa siempre a
        la URL
  <c4>  fix(api/loyalty): el logo de la campana de fidelizacion se sirve por
        la ruta publica
  <c5>  feat(scripts): check_missing_uploads lista los archivos que no estan
        en disco
  <c6>  test(v2.014): regresion de los uploaders y la previsualizacion de
        imagenes
  <c7>  docs(release): README V2.014

Archivos modificados:

  app/deps.py                            +105 / -46
  app/api/v1/uploads.py                  +45 / -18
  app/api/v1/public.py                   +7
  app/api/v1/loyalty.py                  +16
  app/static/js/app.js                   +56 / -14
  scripts/check_missing_uploads.py       +79   (nuevo)
  tests/test_v2_014_uploads_preview.py   +430  (nuevo)
  docs/releases/README_V2.014_UPLOADERS_PREVISUALIZACION_2026-10-24.txt
                                         (nuevo)

--------------------------------------------------------------------------------
2. CAMBIO ÚNICO
--------------------------------------------------------------------------------

Una sola idea: **la previsualización de una imagen subida vuelve a funcionar,
en todas las páginas, y cuando falla dice la verdad.**

El reporte fue: "Revisa cada uno de los UPLOADER de archivos en todas las
páginas, dado que cuando se cargan arroja un error: ⚠ No se pudo cargar la
imagen. La URL puede haber cambiado o el archivo ya no existe.
/api/v1/tenants/29642114-.../uploads/85d09ee2-.../content"

La URL que aparece en el mensaje es correcta y el archivo NO tenía nada de
raro. El problema estaba en el servidor y en cómo el frontend reportaba el
fallo. Y el mensaje, además, mentía: echaba la culpa a la URL cuando la
culpa era del backend.

═══ 2.1) LA CAUSA RAÍZ: UN IMPORT ROTO QUE VOLVÍA 500 TODO ═══

ARCHIVO: app/api/v1/uploads.py

FUNCIÓN INTERVENIDA: `get_upload_content()` (GET /tenants/{tid}/uploads/{uid}/content)

    El import estaba DENTRO de la función:

        from fastapi.responses import FileResponse, HTTPException

    `HTTPException` NO existe en `fastapi.responses` (está en `fastapi`), así
    que la línea levantaba ImportError en CADA petición y el endpoint
    respondía 500:

        GET /api/v1/tenants/{tid}/uploads/{uid}/content
        → 500 {"detail":"Internal error: ImportError: cannot import name
                'HTTPException' from 'fastapi.responses'"}

    Verificado contra producción antes de corregir: los 12 uploads del
    tenant de prueba respondían 500, y un archivo subido en ese mismo
    momento tampoco se podía leer.

    Era el ÚNICO import de `HTTPException` desde `fastapi.responses` en todo
    el repositorio; los otros 25 lo importan correctamente desde `fastapi`.

    El fallo se encadenaba así:

      1. El preview (ImagePicker) descarga la imagen con fetch + Bearer.
      2. El endpoint responde 500.
      3. El preview caía EN SILENCIO a la URL cruda.
      4. Esa URL la pedía un <img>, que no puede mandar el header
         Authorization → 401.
      5. El <img> disparaba su onerror → "⚠ No se pudo cargar la imagen".

    O sea: el 500 real se disfrazaba de "URL inválida".

    Corrección: los imports suben a nivel de módulo y son correctos
    (`from fastapi import HTTPException`, `from fastapi.responses import
    FileResponse`).

═══ 2.2) LOS <img> NATIVOS NO PODÍAN AUTENTICARSE ═══

Un `<img src>` no puede mandar el header `Authorization`. Las imágenes del
tenant se sirven por un endpoint autenticado, así que en el dashboard
cualquier imagen puesta en un `<img>` nativo daba 401 aunque el archivo
existiera. Casos afectados: la miniatura de cada producto en la tabla del
catálogo (dashboard/products.html) y los logos de campaña y de landing.

El login ya setea una cookie httpOnly (`wowhub_access_token`, SameSite=Lax,
path=/) con el access token: el navegador la envía sola en las peticiones
same-origin, incluidas las subrecurso como <img>.

ARCHIVO: app/deps.py

FUNCIÓN INTERVENIDA: `get_current_user_allow_cookie()` (nueva)

    Como `get_current_user`, pero con fallback a la cookie de sesión cuando
    no hay header Authorization.

FUNCIÓN INTERVENIDA: `get_current_membership_allow_cookie()` (nueva)

    Lo mismo para la membresía del tenant.

FUNCIÓN INTERVENIDA: `_user_from_token()` (nueva)

    Núcleo de resolución de usuario, extraído para que las dos variantes
    compartan EXACTAMENTE la misma lógica (incluida la impersonación).

FUNCIÓN INTERVENIDA: `_resolve_membership()` (nueva)

    Núcleo de resolución de membresía (path → header X-Tenant-Id → claim
    `tid`), antes embebido en `get_current_membership`.

FUNCIÓN INTERVENIDA: `_peek_jwt_payload()`

    Ahora lee también la cookie, para que el claim `tid` se resuelva igual
    en peticiones autenticadas por cookie.

ARCHIVO: app/api/v1/uploads.py

FUNCIÓN INTERVENIDA: `get_upload_content()`

    Usa `get_current_membership_allow_cookie` en lugar de
    `get_current_membership`.

    ALCANCE DE SEGURIDAD: las variantes `*_allow_cookie` NO se usan en
    ningún endpoint que modifique estado. No se abre superficie de CSRF:
    la cookie es SameSite=Lax (no viaja en POST/PUT/DELETE cross-site) y el
    token sigue siendo de tipo "access". `get_current_user`, que usa toda la
    API, sigue exigiendo el header Authorization: sin él, 401.

═══ 2.3) EL MENSAJE DE ERROR DECÍA MENTIRAS ═══

ARCHIVO: app/static/js/app.js

FUNCIÓN INTERVENIDA: `previewSrc()`

    ANTES devolvía la URL cruda cuando la descarga fallaba, sin dejar
    rastro del motivo. Ahora devuelve `{ src, error }`: si la descarga
    falla, se conoce el status HTTP y el detalle de la respuesta.

FUNCIÓN INTERVENIDA: `previewErrorMessage()` (nueva)

    Traduce el status a un mensaje accionable:
      · 401 / 403 → "Tu sesión expiró o no tienes permiso para ver esta
                     imagen. Recarga la página."
      · 404      → "El archivo ya no está en el servidor (se perdió en un
                     despliegue). Vuelve a subirlo."
      · 5xx      → "Error del servidor (500). Revisa el log del backend."
      · 0        → "No se pudo conectar con el servidor."

FUNCIÓN INTERVENIDA: `setPreview()`

    Usa ese motivo en el bloque de error y en el toast. Se elimina el
    `onerror` inline en HTML (anidaba comillas y era frágil) y se maneja
    con un listener. La URL directa se conserva como plan B: ahora
    funciona, porque el endpoint acepta la cookie.

    Se elimina el texto "La URL puede haber cambiado o el archivo ya no
    existe": para el usuario era una pista falsa.

═══ 2.4) EL LOGO DE LA TARJETA DEL CLIENTE (PÁGINA PÚBLICA) ═══

El logo de la campaña de fidelización se sube desde el dashboard y se
guarda con la URL autenticada. La tarjeta del cliente
(GET /api/v1/loyalty/c/{slug}/campaign) es pública, sin sesión: esa URL
daba 401 y el logo no cargaba nunca.

ARCHIVO: app/api/v1/public.py

FUNCIÓN INTERVENIDA: `_PUBLIC_MEDIA_PURPOSES`

    Se agrega "loyalty_campaign_logo" al conjunto de usos de upload que
    pueden servirse sin sesión.

ARCHIVO: app/api/v1/loyalty.py

FUNCIÓN INTERVENIDA: `get_public_campaign()`

    Reescribe `logo_url` e `icon_url` con `_public_media_url()`, igual que
    ya se hacía en el landing y el catálogo públicos.

═══ 2.5) DIAGNÓSTICO DE LOS ARCHIVOS PERDIDOS ═══

ARCHIVO: scripts/check_missing_uploads.py (nuevo)

    Script de SÓLO LECTURA que lista los uploads cuyo archivo no está en
    disco, para saber exactamente qué imágenes hay que volver a subir.

    Existe porque el almacenamiento de producción es EFÍMERO (ver §4): los
    12 uploads del tenant de prueba están en la base de datos pero ninguno
    está en el disco, así que sus imágenes están perdidas y hay que
    resubirlas.

--------------------------------------------------------------------------------
3. QUÉ NO SE MODIFICÓ
--------------------------------------------------------------------------------

· Modelos de SQLAlchemy (app/models/*): 0 cambios. No se tocó User,
  TenantMembership, Upload, LoyaltyCampaign ni ningún ENUM.
· Migraciones de Alembic: 0. No hay revisión nueva, ni siquiera aditiva.
  La head de la cadena sigue siendo 2026_10_24_fix_rbac_id_type.
· El esquema de la tabla `uploads`: 0 cambios. En particular NO se tocó
  `stored_filename` (que existe y está poblado; la hipótesis de que estaba
  en NULL era una lectura errónea de mi propio script, que leía un campo
  que `UploadOut` no expone — se verificó contra la DB real).
· La matriz de permisos (app/core/rbac_policies_matrix.py) y el seed de
  Casbin: 0 cambios. No se abrió ni se cerró ningún permiso.
· Endpoints de la API: 0 cambios de contrato. Ninguna ruta nueva, ninguna
  firma nueva, ningún status nuevo, ningún campo nuevo en ninguna respuesta.
  `GET /tenants/{tid}/uploads/{uid}/content` sigue siendo la misma ruta
  con las mismas respuestas (200 con el archivo, 401 sin sesión, 404 si no
  existe o no es de ese tenant).
· El cuerpo de la respuesta 404 del endpoint de contenido: cambió el texto
  del `detail` para que sea accionable. El status sigue siendo 404.
· Los status de la API de uploads: 0 cambios (201 al subir, 200 al leer,
  204 al borrar, 404/401 los de siempre).
· `get_current_user`: 0 cambios de comportamiento. Sigue exigiendo el
  header Authorization. La cookie sólo la aceptan las variantes
  `*_allow_cookie`.
· `get_current_membership`: 0 cambios de comportamiento. Su lógica se
  movió a `_resolve_membership()` y se comparte, pero el resultado es
  idéntico.
· `require_superuser` y `require_role`: 0 cambios. Siguen usando
  `get_current_user`, así que una petición con sólo cookie nunca llega a
  la comprobación de superusuario (401 antes).
· Los mounts de estáticos: 0 cambios. `/storage` sigue sin montarse en
  producción (STORAGE_PUBLIC=false) y `/static` sigue igual.
· El endpoint público `GET /api/v1/public/t/{slug}/media/{upload_id}`: 0
  cambios de comportamiento; sólo se amplió el conjunto de purposes
  públicos (un item más).
· Los uploaders y sus templates: 0 cambios.
  · dashboard/products.html (Imagen del producto)
  · dashboard/landing.html (Imagen del hero, Logo de tu marca)
  · dashboard/admin_loyalty.html (Logo de la tarjeta)
  · dashboard/_ai_panel.html (adjuntos del asistente IA)
  · public/loyalty.html
  Todos siguen usando el mismo ImagePicker; lo que se corrigió es lo que
  hay detrás.
· El resto de app.js: 0 cambios fuera de `previewSrc`, `setPreview` y la
  nueva `previewErrorMessage`.
· El Hero Showcase (app/static/img/hero/, hero_showcase.js, autoplay 3000
  ms, 8 tabs ARIA): 0 cambios. No se tocó la home ni sus assets.
· Tareas Celery / Worker: 0 cambios.
· Variables de entorno / secrets: 0 cambios.
· Documentos V2.001-V2.013: intactos.
· No se ejecutó ningún DROP de tabla ni de columna en ninguna DB.
· No se usó git reset --hard ni git push --force.
· No se borró ningún archivo del repositorio.

--------------------------------------------------------------------------------
4. REQUERIMIENTOS DE DESPLIEGUE
--------------------------------------------------------------------------------

· REQUIERE CAMBIAR EL WORKER: NO.
  Ninguna tarea Celery cambió. El Worker puede seguir corriendo sin
  reiniciar y sin recrear.

· BASE DE DATOS
  · Ninguna migración. La cadena de Alembic no se toca y sigue bloqueada en
    la misma revisión que documenta V2.012 §7.1 (pendiente heredado).
  · NO se requiere ninguna intervención manual en la DB.
  · NO se requiere restore ni backup: no hay DROP, ni borrado de filas.

· ⚠ REQUIERE UN VOLUMEN PERSISTENTE (PENDIENTE, FUERA DEL CÓDIGO)
  En producción el almacenamiento es local y EFÍMERO: `railway.json` no
  declara ningún `volumeMount` y el Dockerfile crea `/app/storage` dentro
  del contenedor. El filesystem de un servicio de Railway es efímero: cada
  despliegue reconstruye el contenedor y borra los archivos subidos.

  Consecuencia, verificada en producción: los uploads siguen en la base de
  datos (la API los lista) pero sus archivos ya no existen, así que las
  imágenes de la landing, del catálogo y de las campañas no cargan y hay
  que volver a subirlas.

  Para que no se vuelva a perder:
    1) En Railway, crear un Volume y montarlo en /app/storage.
    2) Confirmar que STORAGE_PATH=/app/storage en las variables de entorno.

  Este release NO puede resolverlo (es configuración de infraestructura, no
  código) y su ausencia hace que las imágenes antiguas sigas perdidas. El
  script scripts/check_missing_uploads.py lista exactamente cuáles.

· ARCHIVOS ESTÁTICOS
  · app.js cambia. El HTML lo referencia con versionado por query string,
    así que el navegador toma la versión nueva en la primera carga tras el
    deploy.

· ROLLBACK
  · git revert <commit> + push normal a main, en orden inverso:
    <c7> → <c6> → <c5> → <c4> → <c3> → <c2> → <c1>
  · Notas:
    - Revertir <c7> (documentación) no tiene efecto funcional.
    - Revertir <c6> (tests) no tiene efecto funcional.
    - Revertir <c5> (script) no tiene efecto funcional.
    - Revertir <c4> (loyalty) devuelve el logo de campaña a su URL
      autenticada (que en la tarjeta pública daba 401): estado previo.
    - Revertir <c3> (preview) vuelve al mensaje viejo, que culpa a la URL.
    - Revertir <c2> (uploads) reintroduce el 500 y el preview deja de
      funcionar: estado previo.
    - Revertir <c1> (deps) deja las variantes *_allow_cookie sin usar.

--------------------------------------------------------------------------------
5. PROCEDIMIENTO DE PRUEBA RECOMENDADO
--------------------------------------------------------------------------------

VERIFICACIÓN AUTOMÁTICA (una orden):
  $ python -m pytest tests/test_v2_014_uploads_preview.py -q
  Esperado: 17 passed.

  $ python -m pytest tests/test_v2_012_ui_and_permissions.py \
      tests/test_v2_013_admin_menu_roles.py \
      tests/test_v2_014_uploads_preview.py \
      tests/test_dashboard_routes_and_scripts.py \
      tests/test_dashboard_layout.py \
      tests/test_dashboard_modal_refactor.py \
      tests/test_tenant_dashboard_urls.py \
      tests/test_rbac.py tests/test_auth.py \
      tests/test_tenants.py tests/test_tenants_me.py \
      tests/test_schema_drift_reconciliation.py \
      tests/test_enum_labels_consistency.py \
      tests/test_hu50_65_produccion.py \
      tests/test_deprecation_fixes.py -q
  Esperado: 363 tests, 0 fallos.

Comprobaciones manuales equivalentes:

5.1) PREVISUALIZACIÓN AL SUBIR (Products)
  1. Ir a Catálogo / Productos y abrir "Nuevo producto" (o editar uno).
  2. En "Imagen del producto", subir un JPG o PNG.
  3. La previsualización debe MOSTRAR la imagen (no el aviso de error).
  4. Si la imagen no se puede mostrar, el mensaje debe indicar el motivo
     real (sesión expirada / archivo perdido / error del servidor), nunca
     "La URL puede haber cambiado".
  5. Guardar y recargar: la miniatura de la fila del catálogo debe verse.

5.2) LOS OTROS UPLOADERS
  1. Landing → "Imagen del hero" y "Logo de tu marca": deben previsualizar.
  2. Fidelización → "Logo de la tarjeta": debe previsualizar.
  3. Asistente IA → adjuntar imagen: debe subirse sin error.

5.3) TARJETA PÚBLICA DEL CLIENTE
  1. Con una campaña de fidelización con logo, abrir la tarjeta pública
     del comercio (/loyalty/{slug}).
  2. El logo debe verse (antes daba 401).

5.4) IMÁGENES ANTIGUAS PERDIDAS
  1. Correr:  python -m scripts.check_missing_uploads
  2. La lista que salga son imágenes que hay que volver a subir (se
     perdieron en un despliegue).

5.5) AISLAMIENTO DE SESIÓN
  1. Con la sesión expirada, abrir un producto con imagen: el preview debe
     avisar que la sesión expiró, no culpar a la URL.

--------------------------------------------------------------------------------
6. TRAZABILIDAD
--------------------------------------------------------------------------------

Defecto reportado                                Commit  Prueba de regresión
------------------------------------------------------------------------------
"⚠ No se pudo cargar la imagen" al subir       <c2>    test_el_contenido_se_sirve_
(a todas las páginas)                                     con_bearer
                                                              test_el_endpoint_de_
                                                              contenido_no_importa_dentro_
                                                              de_la_funcion
                                                              test_ningun_modulo_importa_
                                                              http_exception_desde_fastapi_
                                                              responses
                                                              test_el_flujo_completo_de_
                                                              subida_sirve_la_imagen
El mensaje acusaba siempre a la URL            <c3>    test_el_preview_muestra_el_
                                                              motivo_y_no_la_url_como_
                                                              culpa
                                                              test_el_preview_devuelve_el_
                                                              motivo_real_del_fallo
El preview caía en silencio a una URL          <c3>    test_el_preview_devuelve_el_
imposible                                                  motivo_real_del_fallo
Los <img> nativos daban 401                    <c1>    test_el_contenido_se_sirve_
                                                        con_la_cookie_de_sesion
                                                        test_el_contenido_sin_sesion_
                                                        responde_401
                                                        test_get_current_user_sigue_
                                                        exigiendo_el_header_
                                                        authorization
Logo de la tarjeta del cliente (público) 404   <c4>    test_el_logo_de_la_campana_se_
                                                        reescribe_en_la_ruta_publica
Diagnóstico de archivos perdidos               <c5>    test_el_script_de_diagnostico_
                                                        de_archivos_faltantes_existe
Fuga de detalle del upload (URL absoluta)       —      test_la_url_de_la_imagen_es_
                                                        relativa_y_estable

--------------------------------------------------------------------------------
7. LÍMITES DE LA VERIFICACIÓN
--------------------------------------------------------------------------------

7.1) LAS IMÁGENES ANTIGUAS NO SE PUEDEN RECUPERAR
  Los archivos que ya no están en disco no se recuperan con código: hay que
  volver a subirlos. Lo único que hace este release es decírselo al usuario
  de forma explícita (404 accionable) y dar el script que lista cuáles
  faltan.

7.2) EL VOLUMEN PERSISTENTE HAY QUE CONFIGURARLO EN RAILWAY
  Este release deja el código listo, pero el volumen no se puede crear desde
  el repositorio: hay que hacerlo en el panel de Railway (Volume → Mount
  Path /app/storage). Hasta que exista, cada despliegue volverá a borrar
  las imágenes.

7.3) LA INSPECCIÓN VISUAL CON LA CUENTA DEL USUARIO QUEDA PENDIENTE
  El preview se verificó en un navegador real, pero con una imagen de
  prueba subida por el propio banco y no con la cuenta del usuario: en este
  entorno no hay sesión de WowHub abierta en el navegador. Con la cuenta
  real hay que repetir el paso manual 5.1 (subir una imagen en Productos y
  confirmar que la previsualización aparece).

7.4) LA CADENA DE ALEMBIC DE PRODUCCIÓN SIGUE SIN AVANZAR
  Pendiente heredado de V2.012 §7.1, sin cambios en este release.

7.5) LOS 22 SCRIPTS DE AUDITORÍA UNTRACKED EN LA RAÍZ DEL REPO
  Pendiente heredado de V2.012 §7.5, sin cambios: hay que borrarlos a mano
  (el lanzador `mavis-trash` no está disponible en este entorno).

--------------------------------------------------------------------------------
8. RESULTADOS DE LA VALIDACIÓN
--------------------------------------------------------------------------------

LOCAL (antes del push):
  · tests/test_v2_014_uploads_preview.py  → 17 passed (nuevo)
  · Suite crítica completa (363 tests)     → 358 passed, 5 skipped,
                                             0 fallos (5m55s)
  · py_compile sobre app/deps.py, app/api/v1/uploads.py,
    app/api/v1/public.py y app/api/v1/loyalty.py → OK
  · Parseo Jinja de los 10 templates del dashboard → OK (sin cambios en §2)
  · Balance de llaves/paréntesis de app.js y de los 4 bloques <script>
    inline del sidebar → OK (comparado contra los originales de HEAD con el
    mismo verificador: idéntico)
  · alembic heads → una sola head: 2026_10_24_fix_rbac_id_type (sin cambios)

ONLINE (post-deploy, Railway):
  Script de verificación propio contra el sitio desplegado: 17 OK / 0 FAIL.
  (La cuenta usada es la demo del repo: demo@wowhub.app.)

  · POST /api/v1/tenants/{tid}/uploads → 201, y la URL canónica devuelta es
    /api/v1/tenants/{tid}/uploads/{uid}/content
  · GET de esa URL con Bearer → 200 (ya NO 500), content-type image/png y
    los bytes exactos de la imagen
  · GET de esa URL con la COOKIE de sesión y SIN header Authorization → 200
    con los bytes exactos (es el camino del <img> nativo)
  · GET de esa URL sin ninguna credencial → 401
  · GET /api/v1/public/t/{slug}/media/{uid} → 200
  · El app.js desplegado trae previewErrorMessage, devuelve {src, error} y
    ya no contiene el mensaje que culpaba a la URL
  · GET /api/v1/loyalty/c/{slug}/campaign → 200 y el logo no apunta a una
    URL autenticada
  · DELETE del upload de prueba → 204 (el tenant quedó con sus 12 uploads
    originales, sin residuos de prueba)
  · /health → 200, /openapi.json → 200

VERIFICACIÓN EN NAVEGADOR REAL (banco local con el app.js y el backend
desplegados):
  Se subió una imagen real (PNG 200x120) al tenant de prueba y se montó un
  banco local que carga el ImagePicker del app.js DESPLEGADO y reenvía
  /api/v1/* a producción con el Bearer (para que el fetch del preview sea
  same-origin, sin CORS). Resultado leído del DOM:

    "OK: la previsualización cargó la imagen (200x120)."

  La imagen se ve renderizada dentro del picker, sin el aviso de error.
  Es exactamente el síntoma reportado por el usuario.
