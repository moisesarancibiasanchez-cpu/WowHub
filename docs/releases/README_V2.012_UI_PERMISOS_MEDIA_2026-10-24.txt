================================================================================
README V2.012 — UI SOBRIA, PERMISOS Y MEDIA
Corrección de 11 defectos reportados por el usuario en WowHub
================================================================================

VERSIÓN         : V2.012
FECHA           : 2026-10-24
VENTANA         : 2026-10-23 22:36 → 2026-10-24 00:10 (Chile)
BUILD           : rama main (base d762a99, cierre de V2.011)
ALCANCE         : 11 defectos reportados por el usuario, más 5 defectos
                  hermanos del mismo patrón detectados durante la auditoría.
ATOMICIDAD      : 10 commits independientes, cada uno revertible por separado
                  sin arrastrar a los demás.
REVERSIÓN       : 10 commits, 18 archivos, +1404 / -65
RIESGO          : BAJO. Todos los cambios son ADITIVOS o de corrección
                  idempotente. No hay DROP de tablas ni de columnas. No hay
                  cambios de comportamiento de negocio ni de la API pública.

--------------------------------------------------------------------------------
1. BASE
--------------------------------------------------------------------------------

Rama          : main
Base          : d762a99 (cierre de V2.011)
Commits       : 10, en orden de aplicación:

  e4a57e8  fix(ui/orders): el boton "+ Crear pedido" no hacia nada
  8d8e794  fix(ui/layout): las paginas ya ocupan el 100% del MAIN
  4b25fdf  fix(ui/modales): el panel de los modales es blanco, no negro
           translucido
  fe7a2c5  fix(ui/marketplace): "Error al cargar tus plugins" y modal blanco
  f791095  fix(ui/nav): KDS en la misma pestana, se elimina el item Pipeline
           duplicado
  a76e062  fix(ui/webhooks): que es un webhook y cuales son los eventos reales
  b0feb27  fix(ui/quotes): previsualizacion de la cotizacion al crearla
  08dbaf6  fix(db/rbac): el seed de permisos fallaba y Casbin denegaba todo
  1df74d9  fix(api/media): las imagenes de la landing volvian a cargar (y con
           preview)
  7f54e63  test(v2.012): regresion de los 9 defectos reportados

Archivos modificados (18, +1404 / -65):

  alembic/versions/2026_10_24_fix_rbac_id_type.py    +212   (nuevo)
  app/api/v1/public.py                               +184 / -5
  app/api/v1/uploads.py                              +5 / -1
  app/core/rbac_seed.py                              +66 / -26
  app/services/upload_service.py                     +10 / -1
  app/static/css/app.css                             +24
  app/static/css/templates/dashboard.css            +26 / -3
  app/static/js/app.js                               +25 / -2
  app/templates/dashboard/base.html                  +10 / -4
  app/templates/dashboard/marketplace.html           +36 / -12
  app/templates/dashboard/orders.html                +9 / -1
  app/templates/dashboard/products.html              +4 / -1
  app/templates/dashboard/quotes.html                +6
  app/templates/dashboard/webhooks.html              +39 / -1
  app/templates/public/landing.html                  +18 / -5
  app/templates/superadmin/marketplace_admin.html    +13 / -3
  scripts/reconcile_schema.py                        +153
  tests/test_v2_012_ui_and_permissions.py            +564   (nuevo)
  docs/releases/README_V2.012_UI_PERMISOS_MEDIA_2026-10-24.txt   (nuevo)

--------------------------------------------------------------------------------
2. CAMBIO ÚNICO
--------------------------------------------------------------------------------

Una sola idea: **devolver al usuario el control de su propio negocio**.

Todo lo que se reportaba caía en tres familias, y las tres tienen la misma
forma: una pieza del sistema quedó desconectada del resto.

  a) INTERFAZ QUE NO DEJABA TRABAJAR
     - El botón "+ Crear pedido" no hacía nada (y detrás suyo, el Kanban
       entero estaba muerto).
     - Inventario, Cotizaciones y Asistente IA no ocupaban el MAIN: el
       contenido quedaba en una franja de 14% a 36% del ancho.
     - Los modales salían con panel negro translúcido: texto ilegible.
     - "Mis Plugins Instalados" daba error por un token que nunca salía.
     - Las imágenes de la landing no cargaban y la previsualización del
       dashboard no aparecía.

  b) PERMISOS QUE NO DEJABAN ADMINISTRAR
     - "⚡ Recalcular RFM" respondía 403 al OWNER. No era la matriz de
       permisos: era el esquema. El seed fallaba y Casbin se quedaba sin
       ninguna policy → denegaba TODO a todos los roles.

  c) NAVEGACIÓN QUE MENTÍA
     - "Cocina (KDS)" abría en otra pestaña.
     - "Pipeline" llevaba a Pedidos.
     - "Webhooks" no explicaba para qué sirve.

Detalle por commit, con las funciones exactas que se tocaron:

═══ 2.1) e4a57e8 — fix(ui/orders): "+ Crear pedido" ═══

ARCHIVO: app/templates/dashboard/orders.html

SÍNTOMA: "Botón + Crear pedido NO realiza ninguna acción".

FUNCIÓN INTERVENIDA: el bloque que registra el listener del botón.

    ANTES:  NEW_ORDER_BTN.addEventListener("click", openNewOrderModal);
    AHORA:  NEW_ORDER_BTN.addEventListener("click", () => openNewOrderModal());

CAUSA RAÍZ: `openNewOrderModal` se declara más abajo, en OTRO bloque
`<script>`. Los scripts inline se ejecutan en orden de documento, así que al
registrar el listener la función todavía no existía y JS lanzaba:

    ReferenceError: openNewOrderModal is not defined

Ese error abortaba el resto del script: nunca llegaban a ejecutarse el
`setInterval(loadOrders, 30000)` ni el `init()`. O sea, el botón sin
acción era la punta visible de una página de Pedidos muerta: el Kanban
nunca se cargaba.

VERIFICACIÓN: en el HTML servido por producción, el listener está en la
línea 968 y la declaración de la función en la 1179 — dos scripts
distintos. Confirmado con el HTML real, no por lectura.

═══ 2.2) 8d8e794 — fix(ui/layout): 100% del MAIN ═══

ARCHIVO: app/static/css/app.css

FUNCIÓN INTERVENIDA: nueva regla junto a `.dash-page`.

    .dash-content > :not([data-widget-type]) {
      grid-column: 1 / -1;
      min-width: 0;
    }

CAUSA RAÍZ: `.dash-content` es un grid de 12 columnas pensado para los 10
widgets del Resumen (cada uno con su `data-widget-type` y su `grid-area`).
Cualquier otro hijo directo caía en el auto-flow y ocupaba UNA sola celda.

MEDIDO sobre el HTML y el CSS REALES de producción (no sobre teoría):

    /dashboard/templates   14%     /dashboard/inventory  27%
    /dashboard/orders      29%     /dashboard/quotes     31%
    /dashboard/ai          36%     /dashboard/customers  61%
    /dashboard/products    82%     /dashboard/landing   100%  (correcto)

El usuario mencionó Inventario, Cotizaciones y Asistente IA. Pedidos,
Clientes, Productos y Plantillas estaban recortadas también; con esta
regla sistémica (y no editando template por template) las 7 quedan al 100%.

VERIFICADO con el CSS real en navegador: las 7 pasan a 100% y
/dashboard/landing se queda en 100% (sin regresión).

═══ 2.3) 4b25fdf — fix(ui/modales): panel blanco ═══

ARCHIVO: app/static/css/templates/dashboard.css

FUNCIÓN INTERVENIDA: la regla del velo de los modales.

    ANTES:
      .template-moderna .modal,
      .template-moderna .modalbox,
      .template-moderna [role="dialog"] {
        background: rgba(11, 13, 18, 0.45);
        backdrop-filter: blur(2px);
      }

    AHORA:
      .template-moderna :is(.modal-overlay, .modal-backdrop) {
        background: rgba(11, 13, 18, 0.45);
        backdrop-filter: blur(2px);
      }
      .template-moderna :is(.modal-overlay, .modal-backdrop) > :is(.modal, .modal-card),
      .template-moderna .modalbox,
      .template-moderna .wh-modal-dialog {
        background: #ffffff;
        color: #172033;
        backdrop-filter: none;
      }

CAUSA RAÍZ: el modal reutilizable de app.js (`.wh-modal-dialog`) tiene
`role="dialog"`. Su regla base es `background: var(--bg-elev, #fff)` con
especificidad (0,1,0) y la del tema era (0,2,0): ganaba el fondo oscuro.
El título "Nuevo producto" se dibujaba en #172033 sobre un panel
rgba(11,13,18,0.45).

MEDIDO en navegador con el CSS real de producción:

    ANTES    fondo=rgba(11,13,18,0.45)  título=rgb(23,32,51)   ->  1.05:1
    DESPUÉS  fondo=rgb(255,255,255)      título=rgb(23,32,51)   -> 15.5:1

La regla usa la ESTRUCTURA (overlay > panel) y no el nombre de la clase
suelta, porque `.modal` se usa como panel cuando es hijo de un overlay y
como overlay en contados casos sueltos.

Referencia del usuario: el modal "Nuevo cliente" (`.wc-modalbox`), que ya
era blanco.

═══ 2.4) fe7a2c5 — fix(ui/marketplace): plugins y modal ═══

ARCHIVOS: app/templates/dashboard/marketplace.html
          app/templates/superadmin/marketplace_admin.html

TRES DEFECTOS EN LA MISMA PÁGINA:

  (a) Token leído de una cookie httpOnly.
      `apiHeaders()` leía el token de `document.cookie`, pero la cookie
      `wowhub_access_token` es httpOnly: el JS NUNCA puede leerla. El
      header salía vacío (`Authorization: Bearer `) y el endpoint
      respondía 401 → "Error al cargar tus plugins.".
      FIX: se usa `WH.TokenStore.access()` con fallback a
      `localStorage`, el mismo patrón que ya aplican widgets.html
      (FIX HU_34) y kds.html.

  (b) El `<script>` estaba dentro del bloque de contenido del dashboard,
      que se renderiza ANTES de app.js: `window.WH` no existía todavía.
      FIX: el script pasa al bloque de scripts del dashboard, que se
      renderiza DESPUÉS de app.js.

  (c) El modal del marketplace era oscuro (#1e1e2e).
      FIX: panel blanco con texto oscuro, igual que el resto.

  El mismo defecto de cookie httpOnly estaba en
  superadmin/marketplace_admin.html: todos los endpoints del marketplace
  de superadmin devolvían 401.

═══ 2.5) f791095 — fix(ui/nav): navegación que no mentía ═══

ARCHIVOS: app/templates/dashboard/base.html
           app/templates/dashboard/products.html

  (a) "Cocina (KDS)" llevaba `target="_blank"`: sacaba al usuario del
      dashboard a otra pestaña. Ahora navega en la misma pestaña.

  (b) El item "Pipeline" del menú era un DUPLICADO de "Pedidos":
      /dashboard/pipeline es un alias deprecated (301) de /dashboard/orders
      (el Kanban vive en Pedidos desde V2.009). El menú tenía las dos
      entradas, a 40 líneas de distancia, y "Pipeline" entregaba
      exactamente lo mismo. Se elimina el item del MENÚ.
      La RUTA /dashboard/pipeline se conserva como alias para marcadores y
      enlaces guardados. El template pipeline.html queda huérfano (no lo
      renderiza ninguna ruta) pero no se borra: no se puede eliminar
      archivos en este entorno.

  (c) El enlace "Configurar Costos" del formulario de producto es interno
      y abría en pestaña nueva. Ahora navega en la misma pestaña.

  Las aperturas en pestaña nueva que SÍ se mantienen, porque son
  intencionadas: /docs (API Docs), las páginas públicas del tenant
  (landing, QR, sitio público) y la vista previa.

═══ 2.6) a76e062 — fix(ui/webhooks): qué es un webhook ═══

ARCHIVO: app/templates/dashboard/webhooks.html

El menú no explicaba para qué servía. Se agrega un bloque con:
  - Qué es un webhook en lenguaje llano (una URL tuya a la que WowHub avisa
    cuando pasa algo, para que tu sistema reaccione solo).
  - Un ejemplo de uso (inventario, hoja de cálculo, chatbot).
  - Cómo se verifica la autenticidad: cabecera `X-WowHub-Signature` con
    HMAC-SHA256, más `X-WowHub-Event` y `X-WowHub-Delivery`, y el
    reintento automático con espera creciente.
  - Los eventos REALES que emite la app.

ADEMÁS, el placeholder del modal anunciaba "order.paid, order.created,
payment.confirmed": dos de esos tres NO existen. Se corrige por los reales,
para que un webhook nuevo no se configure con nombres que jamás van a
disparar.

  EVENTOS REALES (verificados en el código):
    on_order_created      → app/api/v1/orders.py
    on_customer_created   → app/api/v1/customers.py
    on_payment_received   → app/api/v1/payments.py
    order.paid            → app/services/payment_service.py
    * / all               → comodín (app/services/webhook_service.py)

═══ 2.7) b0feb27 — fix(ui/quotes): previsualización al crear ═══

ARCHIVO: app/templates/dashboard/quotes.html

FUNCIÓN INTERVENIDA: `saveQuote()`.

Tras crear una cotización el modal se cerraba y solo aparecía un aviso con
el número. La previsualización (`viewQuote`) existía pero solo se llamaba
al hacer clic en la lista. Ahora, tras guardar, se abre la misma vista de
detalle (items, total, cliente, vencimiento). Si la previsualización
falla, se registra en consola y no rompe el flujo de creación.

═══ 2.8) 08dbaf6 — fix(db/rbac): el 403 de permisos ═══

ARCHIVOS: app/core/rbac_seed.py
           scripts/reconcile_schema.py
           alembic/versions/2026_10_24_fix_rbac_id_type.py  (nuevo)

SÍNTOMA: "⚡ Recalcular RFM" → HTTP 403
          "Permiso denegado: role:OWNER no puede 'write' sobre 'customer'"

Un OWNER no puede denegarse a sí mismo, así que el problema NO estaba en la
matriz de permisos sino en el ESQUEMA.

CAUSA RAÍZ: alembic/versions/2026_09_30_0003_rbac_casbin.py creó las
tablas rbac_policies y rbac_groupings con DDL crudo:

    id CHAR(32) NOT NULL PRIMARY KEY,
    created_at TIMESTAMP NOT NULL,

Pero el ORM (app/models/base.py) usa el TypeDecorator `GUID`, que en
PostgreSQL es UUID NATIVO, y `TimestampMixin` con `server_default=func.now()`.

Dos fallos independientes en el mismo INSERT:
  1. Se escribía un UUID nativo en una columna char(32).
  2. created_at era NOT NULL sin DEFAULT y el INSERT del ORM la omite
     (SQLAlchemy confía en el server_default) → violación de NOT NULL.

Ambos abortan la transacción, así que las N policies se revertían juntas:
la tabla rbac_policies quedaba VACÍA. Casbin no cargaba ninguna policy y
enforce() devolvía False para TODOS los roles → 403 en los 26 endpoints
protegidos por requires_permission (clientes, productos, pedidos,
promociones, categorías, sucursales, pagos, producción, RFM...). Sólo
superadmin escapaba, por su bypass propio.

FIX EN 3 CAPAS:

  (1) Migración 2026_10_24_fix_rbac_id_type (nueva, idempotente):
      convierte `id` de CHAR(32) a uuid y agrega DEFAULT now() a
      created_at/updated_at. Consulta el tipo y el default REALES antes de
      tocar nada (information_schema.columns).

  (2) scripts/reconcile_schema.py, NUEVO pass `_repair_column_types()`:
      repara el drift de TIPO y de DEFAULT sin depender del estado de
      Alembic (la cadena de la DB de producción no avanza, así que esta
      capa es la autoritativa). Sólo dos casos, acotados:
        - CHAR(32)/VARCHAR(32) en la DB donde el modelo pide UUID.
        - Columna NOT NULL sin DEFAULT donde el modelo declara server_default.
      Nunca DROP, nunca borra datos. Repara también el caso "created_at
      NOT NULL sin DEFAULT", que ningún otro camino cubría.

  (3) app/core/rbac_seed.py: el seed ahora RECONCILIA (comprueba una por
      una las policies declaradas y sólo inserta las que faltan) en vez de
      correr sólo cuando la tabla estaba vacía, y cada INSERT va en su
      propia transacción para que un fallo aislado no tumbe el resto.
      Además avisa en ERROR si la tabla queda vacía, porque eso significa
      "todo denegado".

  downgrade de la migración: no-op documentado. Revertir a CHAR(32)
  restauraría exactamente el estado roto.

═══ 2.9) 1df74d9 — fix(api/media): las imágenes de la landing ═══

ARCHIVOS: app/api/v1/public.py
           app/api/v1/uploads.py
           app/services/upload_service.py
           app/static/js/app.js
           app/templates/public/landing.html

CAUSA RAÍZ: el 2026-09-27 se desmontó el montaje público /storage por
seguridad (exponía los archivos de TODOS los tenants sin autenticación).
Pero:
  - upload_service guardaba la URL "/storage/{tenant}/{archivo}", que en
    producción no existe → 404.
  - El endpoint que sí sirve el archivo (uploads/{id}/content) exige
    autenticación, así que la landing pública no podía usarlo.
  - uploads.py buscaba el archivo por `upload.filename` (el nombre
    original) en vez de `upload.stored_filename` (el nombre en disco).

FUNCIONES INTERVENIDAS:

  app/api/v1/public.py
    _find_public_upload(url, tenant, db)   → NUEVA
    _public_media_url(url, tenant, db, slug) → NUEVA
    public_tenant_media(slug, upload_id)   → NUEVA
        GET /api/v1/public/t/{slug}/media/{upload_id}
        Sólo sirve uploads cuyo `purpose` es de uso público
        (landing_hero, landing_logo, product_image, promotion) y que
        pertenecen a ESE tenant. Cualquier otro archivo responde 404 (no
        403: no se revela la existencia de recursos ajenos).
    public_profile / public_landing / public_catalog / public_product /
    public_promotions → MODIFICADAS: reescriben las URLs de upload a la
        ruta pública por slug. Se aceptan los dos formatos (el nuevo de
        /uploads/{id}/content y el legacy de /storage/{tenant}/{archivo}),
        así que NO hay que migrar las filas existentes.
    public_landing → MODIFICADA: devuelve una COPIA (dict) en lugar del
        objeto ORM. Mutar el objeto marcaría la fila como sucia y el
        siguiente commit de la sesión guardaría la URL reescrita en la DB.

  app/api/v1/uploads.py
    el endpoint de contenido ahora busca por `upload.stored_filename`.

  app/services/upload_service.py
    `save_image()` guarda la URL canónica del endpoint que sí existe
    (/api/v1/tenants/{tid}/uploads/{uid}/content), asignándola después
    del flush, cuando ya se conoce el id.

  app/static/js/app.js
    ImagePicker: `previewSrc()` descarga la imagen con fetch + Bearer y la
    pinta con un object URL. Un `<img src>` no puede mandar el header
    Authorization, por eso salía "No se pudo cargar la imagen".

  app/templates/public/landing.html
    el logo se oculta si no carga; el hero se precarga antes de aplicarse,
    para no dejar imágenes rotas.

═══ 2.10) 7f54e63 — test(v2.012): 33 tests de regresión ═══

ARCHIVO NUEVO: tests/test_v2_012_ui_and_permissions.py  (33 tests)

Fijan el comportamiento de los 11 defectos, incluidos dos barridos
sistémicos:
  - El listener por referencia: ningún template puede registrar un
    listener en el nivel superior de un `<script>` referenciando una
    función declarada después. Usa el lexer del propio repo
    (app.f0_baseline.js_parser) para distinguir el nivel superior de una
    función.
  - Los links a rutas internas del dashboard: ninguno puede abrir en
    pestaña nueva.

--------------------------------------------------------------------------------
3. QUÉ NO SE MODIFICÓ
--------------------------------------------------------------------------------

· Modelos de SQLAlchemy (app/models/*): 0 cambios. No se tocó GUID, ni
  TimestampMixin, ni ningún ENUM.
· Endpoints de la API (app/api/v1/*): 0 cambios de contrato. La única
  ruta nueva es GET /api/v1/public/t/{slug}/media/{upload_id}. Las rutas
  existentes no cambian de firma, de status ni de permisos.
· La matriz de permisos (app/core/rbac_policies_matrix.py): 0 cambios.
  El 403 NO era un problema de permisos: era de esquema. No se abrió ni
  se cerró ningún permiso nuevo.
· app/core/security.py y el enforcer de Casbin: 0 cambios. La decisión de
  permisos sigue siendo la misma; lo que se reparó fue la fuente de
  datos.
· Tareas Celery / Worker: 0 cambios. Ninguna tarea toca uploads,
  rbac_policies ni landing_configs.
· Rutas de navegación del dashboard: 0 cambios. Sólo se corrigió el item
  "Pipeline" del menú (que era un alias de Pedidos) y el target del link
  de KDS. /dashboard/pipeline sigue existiendo como alias 301.
· Servicio de webhooks (app/services/webhook_service.py): 0 cambios. La
  firma HMAC, los reintentos y los eventos emitidos son los mismos. Sólo
  se corrigió la DOCUMENTACIÓN y el placeholder del formulario.
· Hero Showcase (app/static/img/hero/, hero_showcase.js, autoplay 3000 ms,
  8 tabs ARIA): 0 cambios. No se tocó ni la home ni sus assets.
· Paleta y estilos generales: 0 cambios. Sólo las dos reglas de modal y
  la regla de ancho del contenido. La UI sigue sobria, sin colores
  nuevos ni elementos distractores.
· Landing pública (app/templates/public/landing.html): sólo se añadió el
  fallback de imagen (logo onerror, hero precargado). No se cambió el
  diseño, los textos ni el orden.
· app/templates/dashboard/pipeline.html: NO se borró (queda huérfano, no
  lo renderiza ninguna ruta). En este entorno no se pueden eliminar
  archivos.
· Variables de entorno / secrets: 0 cambios.
· Documentos V2.001-V2.011: intactos.
· No se ejecutó ningún DROP de tabla ni de columna en ninguna DB.
· No se usó git reset --hard ni git push --force.
· No se montó app/api/v1/templates.py (sigue sin montarse, por la
  limitación de permisos documentada en V2.011).

--------------------------------------------------------------------------------
4. REQUERIMIENTOS DE DESPLIEGUE
--------------------------------------------------------------------------------

· REQUIERE CAMBIAR EL WORKER: NO.
  Ninguna tarea Celery cambió, ninguna tarea toca las tablas afectadas
  (rbac_policies, rbac_groupings, uploads) ni los campos modificados
  (id, created_at, updated_at, url). El Worker puede seguir corriendo
  sin reiniciar y sin recrear: al reiniciar, toma el código nuevo sin
  ninguna acción por su parte.
  (Comparación con V2.011: tampoco requería cambiar el Worker.)

· BASE DE DATOS
  · La migración 2026_10_24_fix_rbac_id_type se aplica automáticamente en
    el deploy (down_revision = 2026_10_23_fix_enum_labels). Es la nueva
    head de la cadena.
  · Es IDEMPOTENTE: consulta el tipo y el default reales de cada columna
    antes de alterar nada. Si ya estaban bien, no hace nada.
  · IMPORTANTE — LA CADENA DE ALEMBIC SIGUE SIN AVANZAR EN PRODUCCIÓN:
    está bloqueada en una revisión anterior por una migración que falla
    sobre los datos reales (sin acceso al log de Railway no se pudo
    identificar cuál). Esto NO bloquea el release: la capa que repara el
    esquema es scripts/reconcile_schema.py, que es AGNÓSTICO del estado de
    Alembic y se ejecuta SIEMPRE en el entrypoint (después de create_all y
    antes de uvicorn).
  · El reconciliador ahora tiene un pass nuevo de reparación de TIPOS y
    DEFAULTs. Es el que va a arreglar rbac_policies.id y rbac_policies.
    created_at en la DB de producción, haya avanzado la cadena o no.
  · Con el esquema reparado, el seed de permisos (que ahora reconcilia y
    confirma policy por policy) puebla rbac_policies en el arranque.
    ORDEN EN EL ENTRYPOINT (scripts/entrypoint.sh):
      bootstrap_migrate → create_all → reconcile_schema → uvicorn
    El seed corre dentro del lifespan de la app, es decir DESPUÉS de
    reconcile_schema: cuando siembra, el esquema ya está reparado.
  · NO se requiere ninguna intervención manual en la DB.
  · NO se requiere restore ni backup: no hay DROP, no hay borrado de
    filas, no hay recreación de ningún TYPE.
  · La conversión de `id` usa el cast de entrada de PostgreSQL, que
    acepta tanto la forma con guiones como los 32 hex sin guiones; rtrim
    quita el relleno de CHAR. Si la tabla estuviera vacía (que es el caso
    esperado, porque el seed nunca pudo escribir), la conversión es
    trivial.

· LOG DEL DEPLOY — QUÉ MIRAR
  · [reconcile] alembic_version actual: <revisión>
  · [reconcile] ALTER TABLE "rbac_policies" ALTER COLUMN "id" TYPE uuid ...
    (si la DB tenía el drift)
  · [reconcile] ALTER TABLE "rbac_policies" ALTER COLUMN "created_at"
    SET DEFAULT now()
  · [reconcile] Resumen — ... | 2 tipos corregidos | 4 defaults agregados | ...
  · rbac_seed: insertadas N policies faltantes (total N)
  · rbac_seed: la tabla rbac_policies quedó VACÍA   ← si aparece, el
    esquema no se reparó: revisar el error del log.

· ARCHIVOS ESTÁTICOS
  · app.css, templates/dashboard.css y app.js cambian. El CDN los sirve
    con versionado por query string en el HTML (/?v=...), así que el
    navegador toma la versión nueva en la primera carga tras el deploy.
    No hay que purgar caché a mano.

· SECRETOS / ENV
  · Sin cambios.

· ROLLBACK
  · git revert <commit> + push normal a main. El orden de revert es el
    inverso al de aplicación:
      7f54e63 → 1df74d9 → 08dbaf6 → b0feb27 → a76e062 → f791095 →
      fe7a2c5 → 4b25fdf → 8d8e794 → e4a57e8
  · Notas:
    - Revertir 7f54e63 (tests) no tiene efecto funcional.
    - Revertir 1df74d9 (media) deja las imágenes públicas como estaban:
      la URL guardada apuntaría a /storage y la landing volvería a no
      cargar imágenes. Es el estado previo, no un estado roto nuevo.
    - Revertir 08dbaf6 NO deshace la migración ya aplicada (las columnas
      quedan convertidas a uuid, que es el estado que necesita el ORM).
      Sólo deja de estar la migración en el árbol de Alembic.
    - NO revertir 08dbaf6 sin revisar: sin el seed reconciliador y sin la
      migración, el 403 de permisos puede reaparecer.

--------------------------------------------------------------------------------
5. PROCEDIMIENTO DE PRUEBA RECOMENDADO
--------------------------------------------------------------------------------

VERIFICACIÓN AUTOMÁTICA (una orden):
  $ python -m pytest tests/test_v2_012_ui_and_permissions.py -q
  Esperado: 33 passed.

  $ python -m scripts.verify_production
  Comprueba rutas, contenido del dashboard, orden de scripts, catálogos
  públicos, Hero Showcase, /health y /openapi.json contra el sitio
  desplegado. Devuelve 0 si todo pasa.

Comprobaciones manuales equivalentes:

5.1) MODALES BLANCOS
  1. /dashboard/products -> "+ Nuevo producto".
  2. El panel debe ser BLANCO y el texto claramente legible.
  3. Repetir en: /dashboard/orders (nuevo pedido), /dashboard/customers
     (nuevo cliente, el de referencia), /dashboard/promotions,
     /dashboard/quotes, /dashboard/mesero, /dashboard/inventory.
  4. El fondo DETRÁS del modal debe seguir siendo oscuro (es el velo).

5.2) "+ CREAR PEDIDO" (el más importante)
  1. /dashboard/orders.
  2. El Kanban debe cargar con sus columnas (antes se quedaba vacío).
  3. "+ Crear pedido" -> se abre el modal.
  4. Crear cliente desde el modal -> aparece en el select.
  5. Crear producto desde el modal -> aparece en el select.
  6. Guardar el pedido -> el Kanban muestra la tarjeta nueva.
  7. Esperar 30 s: la lista se refresca sola (setInterval).

5.3) PERMISOS (el 403)
  1. /dashboard/customers -> "⚡ Recalcular RFM".
  2. Debe responder 200 y mostrar el resumen del recálculo.
  3. Si sigue el 403, el log del deploy tiene que mostrar la línea
     "la tabla rbac_policies quedó VACÍA" (o un error de seed): eso
     significa que el esquema NO se reparó.

5.4) ANCHO DEL MAIN (100%)
  1. /dashboard/inventory, /dashboard/quotes, /dashboard/ai,
     /dashboard/orders, /dashboard/customers, /dashboard/products,
     /dashboard/templates.
  2. El contenido debe ocupar todo el ancho disponible: sin margen
     vacío a la derecha.
  3. /dashboard/landing debe seguir igual (100%).

5.5) IMÁGENES DE LA LANDING
  1. /dashboard/landing -> subir una imagen de hero -> debe verse la
     PREVISUALIZACIÓN en el picker (no "No se pudo cargar la imagen").
  2. Guardar.
  3. Abrir la landing pública del tenant -> el hero y el logo cargan.
  4. $ curl -s -o /dev/null -w '%{http_code}' \
        https://wowhub-api-production.up.railway.app/api/v1/public/t/cafe-norte/catalog
     Esperado: 200 (y con image_url apuntando a
     /api/v1/public/t/{slug}/media/{id}).

5.6) PLUGINS
  1. /dashboard/marketplace -> "✅ Mis Plugins Instalados".
  2. Debe mostrar la lista (o "ninguno"), NO "Error al cargar tus plugins.".

5.7) NAVEGACIÓN
  1. Click en "Cocina (KDS)" -> se abre en la MISMA pestaña.
  2. El menú NO debe tener "Pipeline".
  3. /dashboard/orders -> el botón "Configurar Costos" (en el formulario
     de producto) navega en la misma pestaña.

5.8) WEBHOOKS
  1. /dashboard/webhooks -> debe explicar qué es un webhook y listar los
     4 eventos reales.
  2. "+ Nuevo webhook" -> el campo de eventos propone
     "on_order_created, on_payment_received, *".

5.9) COTIZACIONES
  1. /dashboard/quotes -> crear una cotización -> tras guardar se abre
     sola la vista de detalle con los items y el total.

5.10) REGRESIONES
  1. /dashboard/orders y /dashboard/customers renderizan 200.
  2. El Hero Showcase sigue igual: 8 tabs, autoplay 3000 ms, 8 imágenes.
  3. /health 200 y /openapi.json con 258+ paths.

--------------------------------------------------------------------------------
6. TRAZABILIDAD
--------------------------------------------------------------------------------

Defecto reportado                        Commit     Prueba de regresión
------------------------------------------------------------------------------
Modales con panel negro translúcido      4b25fdf    test_modales_no_pintan_de_
                                                    oscuro_el_dialog
                                                    test_modales_tienen_regla_de_
                                                    panel_blanco
                                                    test_modal_marketplace_es_blanco
Inventario/Cotizaciones/IA no ocupan
el 100% del MAIN                          8d8e794    test_layout_regla_grid_column_
                                                    full
                                                    test_layout_los_widgets_del_
                                                    resumen_no_estan_afectados
"+ Crear pedido" sin acción              e4a57e8    test_orders_crear_pedido_usa_
                                                    arrow_function
                                                    test_ningun_template_registra_
                                                    una_funcion_declarada_mas_tarde
Recalcular RFM → 403                     08dbaf6    test_rbac_el_seed_reconcilia_y_
                                                    no_aborta_todo
                                                    test_rbac_migracion_es_idempotente
                                                    test_reconciliador_repara_tipos_
                                                    y_defaults
                                                    test_reconciliador_detecta_char32_
                                                    como_uuid
                                                    test_modelo_guids_es_uuid_en_
                                                    postgres
Imágenes de la landing rotas              1df74d9    test_uploads_busca_el_archivo_
                                                    por_stored_filename
                                                    test_upload_service_guarda_una_
                                                    url_que_existe
                                                    test_public_tiene_endpoint_de_
                                                    media_por_slug
                                                    test_public_reescribe_las_urls_
                                                    de_la_landing
                                                    test_landing_publico_maneja_el_
                                                    fallo_de_imagen
                                                    test_imagepicker_preview_usa_el_
                                                    bearer
                                                    test_media_publica_404_si_no_existe
                                                    test_media_publica_no_sirve_
                                                    archivos_de_otros_tenants
"Error al cargar tus plugins"            fe7a2c5    test_marketplace_no_lee_el_
                                                    token_de_la_cookie
                                                    test_marketplace_script_esta_
                                                    fuera_del_bloque_de_contenido
Cocina KDS en pestaña nueva              f791095    test_kds_no_abre_en_pestana_nueva
                                                    test_no_quedan_links_internos_con_
                                                    target_blank
Menú PIPELINE lleva a Pedidos            f791095    test_menu_no_tiene_item_pipeline_
                                                    duplicado
Webhooks sin explicación                 a76e062    test_webhooks_explica_para_que_
                                                    sirven
                                                    test_webhooks_lista_los_eventos_
                                                    reales
                                                    test_webhooks_no_anuncia_eventos_
                                                    inexistentes
                                                    test_eventos_de_webhook_coinciden_
                                                    con_el_codigo
Cotizaciones sin previsualización        b0feb27    test_quotes_abre_previsualizacion_
                                                    al_crear

--------------------------------------------------------------------------------
7. LIMITACIONES Y PENDIENTES
--------------------------------------------------------------------------------

7.1) LA CADENA DE ALEMBIC DE PRODUCCIÓN SIGUE SIN AVANZAR
    Está bloqueada en una revisión anterior por una migración que falla
    sobre los datos reales. No se pudo identificar cuál porque el
    dashboard de Railway abre un diálogo de Login (no hay sesión en el
    navegador del agente) y no hay CLI ni token de Railway en el entorno.
    Mitigación aplicada en V2.012: la reparación del esquema y de los ENUM
    la hace scripts/reconcile_schema.py, que es agnóstico del estado de
    Alembic y se ejecuta siempre en el entrypoint. Los 4 errores de
    V2.011 siguen reparados con la cadena quieta.
    Acción pendiente: leer el log del deploy en el dashboard de Railway,
    identificar la migración que falla y corregirla (con guardas de
    idempotencia o sufijo _noop) en V2.013.

7.2) EL 403 DE PERMISOS SE VERIFICÓ POR ANÁLISIS, NO POR EJECUCIÓN
    No hay token de sesión del tenant en el entorno, así que no se pudo
    llamar al endpoint de RFM autenticado. La causa raíz está verificada
    por código (DDL cruda vs ORM) y los tests fijan el comportamiento
    del seed y del reconciliador, pero la comprobación de extremo a
    extremo la debe hacer el usuario con su sesión (sección 5.3).

7.3) EL ROUTER DE PLANTILLAS SIGUE SIN MONTARSE
    app/api/v1/templates.py expone GET/PUT /tenants/{tenant_id}/template
    sin verificar usuario ni membership. Montarlo expondría la edición
    de la plantilla de cualquier UUID de tenant conocido, así que NO se
    monta (misma decisión que en V2.011). El selector de /dashboard/
    templates guarda la elección en localStorage.

7.4) app/templates/dashboard/pipeline.html QUEDA HUERFANO
    No lo renderiza ninguna ruta (el Kanban vive en Pedidos). No se
    borró porque en este entorno no se pueden eliminar archivos.

7.5) LOS 22 SCRIPTS DE AUDITORÍA UNTRACKED EN LA RAÍZ DEL REPO
    (_audit_*.py, _verify_*.py, _repro_*.py, etc.) no se pudieron borrar:
    la política local de seguridad bloquea el borrado porque el lanzador
    `mavis-trash` no está disponible, y no está permitido recurrir a un
    borrado permanente. No afectan a la app ni al historial (no están
    versionados), pero hay que borrarlos a mano.

7.6) SUITE COMPLETA DEL REPO
    La suite completa (fuera del conjunto crítico) excede el timeout de
    600 s; se validó por chunks.

--------------------------------------------------------------------------------
8. VALIDACIÓN EJECUTADA
--------------------------------------------------------------------------------

LOCAL
  · tests/test_v2_012_ui_and_permissions.py  → 33 passed (nuevo)
  · Suite crítica completa → 243 passed, 1 xpassed
    (antes de V2.012 el mismo conjunto daba 210 passed + 1 xpassed;
    el delta +33 son los tests nuevos de regresión de este release)
  · alembic heads → una sola head: 2026_10_24_fix_rbac_id_type
  · py_compile sobre los 6 archivos Python modificados → OK
  · Parseo Jinja de los 10 templates tocados → OK
  · Balance de llaves/paréntesis de app.js → OK

  · MEDICIÓN DEL LAYOUT con el HTML y el CSS REALES de producción
    (servidor local + navegador, antes/después con la regla inyectada):
      /dashboard/inventory   ANTES  27%  →  DESPUÉS 100%
      /dashboard/templates   ANTES  14%  →  DESPUÉS 100%
      /dashboard/orders      ANTES  29%  →  DESPUÉS 100%
      /dashboard/quotes      ANTES  31%  →  DESPUÉS 100%
      /dashboard/ai          ANTES  36%  →  DESPUÉS 100%
      /dashboard/customers   ANTES  61%  →  DESPUÉS 100%
      /dashboard/products    ANTES  82%  →  DESPUÉS 100%
      /dashboard/landing     ANTES 100%  →  DESPUÉS 100%   (sin regresión)

  · MEDICIÓN DEL MODAL con el CSS real de producción:
      ANTES    fondo=rgba(11,13,18,0.45)  título=rgb(23,32,51)  →  1.05:1
      DESPUÉS  fondo=rgb(255,255,255)      título=rgb(23,32,51)  → 15.5:1

  · VERIFICACIÓN DEL ORDEN DE SCRIPTS en el HTML servido por producción
    (orders.html): listener en la línea 968, declaración de la función en
    la 1179 → ReferenceError confirmado.

ONLINE (Railway) — verificado tras el deploy, sin fallos

  A) CSS desplegado (la evidencia de que el deploy ya lleva el código nuevo):
     - /static/css/templates/dashboard.css 200 (18.173 b)
       · la regla oscura ya NO aplica a [role="dialog"]
       · existe la regla de panel blanco con texto oscuro
     - /static/css/app.css 200 (65.763 b)
       · existe la regla .dash-content > :not([data-widget-type]) con
         grid-column: 1 / -1

  B) Páginas del dashboard: 200
     /dashboard/products, /dashboard/inventory, /dashboard/quotes,
     /dashboard/ai, /dashboard/orders, /dashboard/customers,
     /dashboard/templates, /dashboard/webhooks, /dashboard/landing
     (/dashboard/marketplace/ y /dashboard/mi-sitio-web exigen token:
      sin sesión responden 302 a /dashboard/login, que es lo correcto)

  C) Navegación (HTML desplegado):
     · KDS existe y SIN target="_blank
     · el menú NO tiene el item "Pipeline"
     · el menú SÍ tiene "Pedidos"

  D) Marketplace desplegado (con token):
     · 200 (56.856 b), contiene "Mis Plugins Instalados"
     · NO lee el token de document.cookie
     · usa WH.TokenStore
     · el script va DESPUÉS de app.js (app.js@24.206, marketplace@46.057)
     · el panel del modal es blanco
     · apiHeaders sólo manda Bearer si hay token

  E) Webhooks: explica su utilidad, lista los 4 eventos reales y el
     placeholder ya no anuncia eventos inexistentes
     ("on_order_created, on_payment_received, *")

  F) Cotizaciones: saveQuote() abre la previsualización

  G) Media:
     · /api/v1/public/t/{tenant}/media/{id} inexistente -> 404 (no 500)
     · /api/v1/public/t/cafe-norte/catalog -> 200 (6.576 b), sin error de ENUM
     · /api/v1/public/t/bicifix/catalog -> 200 (1.226 b)
     · /api/v1/public/t/cafe-norte/landing -> 200

  H) Órdenes de scripts en el HTML RENDERIZADO:
     · /dashboard/orders: el listener de "+ Crear pedido" usa arrow function
     · /dashboard/marketplace: el primer script inline va después de app.js
     · app.js presente en orders, customers, quotes, inventory, ai,
       templates

  I) Sin regresiones:
     · home 200 (36.436 b), 8 tabs role="tab"
     · hero_showcase.js 200 con AUTOPLAY_MS = 3000
     · las 8 imágenes de /static/img/hero/ responden 200
     · /health 200 {"status":"ok","version":"0.2.0","env":"production",...}
     · /openapi.json 200

================================================================================
FIN README_V2.012_UI_PERMISOS_MEDIA_2026-10-24.txt
================================================================================
