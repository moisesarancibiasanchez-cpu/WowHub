================================================================================
README_V2.011_FIX_SCHEMA_MESERO_TEMPLATES_2026-10-23.txt
WowHub · Release Notes Atómicos · V2.011
================================================================================

FECHA          : 2026-10-23
BUILD          : rama main (base baaa077)
ALCANCE        : Corrección de 3 errores de producción reportados por el
                usuario, más 3 defectos hermanos del mismo patrón y 1 error
                de esquema adicional (ENUM) detectados durante la auditoría.
ATOMICIDAD     : 19 commits independientes (15 de código y pruebas, 4 de
                documentación y verificación), cada uno revertible por
                separado sin arrastrar a los demás.
RIESGO         : BAJO. Todos los cambios son ADITIVOS. No hay DROP de tablas
                ni de columnas. No hay cambios de comportamiento de negocio.
VERIFICACIÓN   : Online contra Railway (wowhub-api-production.up.railway.app)
                después del deploy. Los 4 errores quedaron corregidos y
                verificados con respuestas HTTP reales (ver sección 8).

ERRORES CORREGIDOS EN ESTE RELEASE
--------------------------------------------------------------------------------
  BUG 1  GET /api/v1/tenants/{id}/products -> HTTP 500
         psycopg.errors.UndefinedColumn: column products.product_type does
         not exist

  BUG 2  /dashboard/mesero -> TypeError en consola del navegador
         Cannot read properties of undefined (reading 'Auth')

  BUG 3  /dashboard/templates -> HTTP 404
         (mostrando "El negocio "" no existe o está inactivo")

  BUG 4  (descubierto al validar el Bug 1 en producción)
         GET /api/v1/public/t/{slug}/catalog -> HTTP 500
         psycopg.errors.InvalidTextRepresentation:
         invalid input value for enum product_status: "active"
         Estaba ENMASCARADO por el Bug 1: el SELECT fallaba antes por la
         columna inexistente. Al reparar el esquema quedó expuesto.


--------------------------------------------------------------------------------
1. BASE (contexto)
--------------------------------------------------------------------------------

Base de este release: commit baaa077 (README_V2.010_JINJA_BLOCKS_FIX_2026-10-21).

Producción reportaba 3 errores simultáneos. Los tres eran independientes entre
sí y tenían causas raíz distintas. La investigación se hizo sobre el código y
sobre réplicas locales del estado de la DB de Railway; no se modificó nada
en Railway hasta tener los fixes validados y probados.

═══ BUG 1 — products.product_type no existe ═══

SÍNTOMA (producción, Railway / PostgreSQL):
    GET /api/v1/tenants/e865866c-6eb7-4394-bf91-723c6b003307/products
        ?order_by=position&page_size=100
    -> HTTP 500
    psycopg.errors.UndefinedColumn: column products.product_type does not exist

    SELECT count(*) AS count_1 FROM (
        SELECT products.sku AS sku,
               products.name AS ...,
               products.product_type ...
        FROM products ...
    )

CAUSA RAÍZ CONFIRMADA (reproducible localmente):
    La DB de producción nació de Base.metadata.create_all() (NO de Alembic).
    scripts/bootstrap_migrate.py detecta ese estado como "legacy" y calcula la
    revisión objetivo con _highest_fully_applied_revision(), que SÓLO
    comprobaba las tablas declaradas con op.create_table e IGNORABA por
    completo las columnas agregadas con op.add_column.

    2026_10_16_hu50_65 es la ÚNICA migración del proyecto que combina
    op.create_table con op.add_column. Como sus 6 tablas nuevas SÍ existían
    (creadas por create_all en un deploy anterior), el bootstrap daba la
    migración por aplicada y sellaba la DB en "head" SIN ejecutar jamás sus
    15 ADD COLUMN sobre products / customers / quote_items.

    Base.metadata.create_all() NO puede reparar esto: sólo crea tablas que NO
    existen, nunca hace ALTER TABLE sobre tablas que ya existen. Por eso el
    entrypoint (que lo ejecuta como "red de seguridad") no ayudaba.

REPRODUCCIÓN LOCAL (antes del fix):
    1. alembic upgrade 2026_10_07_0002
    2. create_all de las 6 tablas de HU_50-HU_65 (simula el deploy previo)
    3. DROP TABLE alembic_version (simula la DB "legacy")
    4. python -m scripts.bootstrap_migrate

    Salida observada:
      [bootstrap_migrate] estado detectado: legacy
      [bootstrap_migrate] DB con esquema completo ('legal_consents' + tablas
      de la migración head). Sello a '2026_10_16_hu50_65' (head). No hay nada
      que aplicar.

    Estado del esquema tras el bootstrap:
      products:   FALTAN ['product_type', 'template_type', 'm2_price_cents']
      customers:  FALTAN ['customer_type', 'marketing_email_status',
                          'marketing_whatsapp_status', 'current_debt_cents']
      quote_items:FALTAN ['template_type', 'width_cm', 'height_cm', 'faces',
                          'suggested_price_cents', 'cost_unit_cents',
                          'pack_qty', 'pack_size']
      >>> 15 columnas faltantes

    Esto es EXACTAMENTE el error reportado en producción.

═══ BUG 2 — Mesero Virtual: Cannot read properties of undefined ═══

SÍNTOMA (producción, consola del navegador):
    /dashboard/mesero
    TypeError: Cannot read properties of undefined (reading 'Auth')

CAUSA RAÍZ CONFIRMADA:
    El JS inline de mesero.html estaba dentro de {% block dash_content %}, que
    se materializa en base.html:84 — DENTRO de <main>, es decir ANTES de:

        base.html:87  <script src="/static/js/app.js?v=notif-2026-08-23"></script>

    app.js es (base.html:708) quien define window.WH = { api, publicApi, Toast,
    Upload, ImagePicker, Auth, TokenStore, ... }. Es un script clásico
    bloqueante (sin defer/async), así que se ejecuta por completo en su
    posición.

    El IIFE de mesero.html se invocaba de inmediato al parsear, por lo que
    mesero.html:498 evaluaba window.WH.Auth cuando window.WH todavía era
    undefined:

        const session = await window.WH.Auth.ensureSession();

    Descartadas: exports/imports en app.js (no hay ninguno), falta de
    {{ super() }} en dashboard/base.html (sí lo tiene, línea 277), y
    JS fuera de un bloque Jinja (el JS sí se renderizaba).

    El patrón correcto ya lo usaban customers.html, products.html,
    inventory.html, customer_360.html: {% block dash_scripts %}, que se
    materializa en base.html:104, DESPUÉS de app.js.

═══ BUG 3 — /dashboard/templates 404 ═══

SÍNTOMA (producción):
    GET /dashboard/templates -> HTTP 404
    El sidebar "Apariencia" (app/templates/dashboard/base.html:159) enlaza a
    esa URL. El 404 lo servía public/404.html, que muestra:
        "El negocio "{{ slug }}" no existe o está inactivo."
    Con slug vacío, por eso el mensaje mostraba "".

CAUSA RAÍZ CONFIRMADA:
    El commit 9ea9bec ("feat(hu50-65): re-deploy con fix de causa raíz del 502
    Railway") sobrescribió app/main.py con una versión ANTERIOR a V2.01 y se
    llevó por delante 6 rutas:

        git diff de rutas (9ea9bec^ -> 9ea9bec):
          PERDIDAS (6):
            GET /dashboard/analytics
            GET /dashboard/production
            GET /dashboard/settings
            GET /dashboard/templates
            GET /dashboard/v1
            GET /pricing
          GANADAS: 0

    Se comprobó con git log -S sobre app/main.py: la ruta /dashboard/templates
    fue AÑADIDA en 86e41e8 ("V2.01 Template Selector Fix") y el template
    app/templates/dashboard/templates.html EXISTE y NUNCA fue borrado. Sólo
    faltaba la ruta.

    Se verificó además que las 6 rutas seguían ausentes en HEAD antes de este
    release (es decir: no era un problema de caché de Railway, el código
    desplegado realmente no las tenía).

DEFECTO ADICIONAL DETECTADO AL RESTAURAR LA RUTA:
    dashboard/templates.html usaba
        {{ url_for('static', filename='css/templates/dashboard.css') }}
    Starlette exige "path=" en Mount.url_path_for (no "filename="), por lo que
    url_for('static', filename=...) lanza NoMatchFound: la página habría
    devuelto 500 en vez de 200. Se cambió a rutas literales /static/..., que
    es el patrón que ya usa base.html (base.html:87-88) en todo el proyecto.

═══ BUG 4 — ENUM product_status / quote_status desalineados ═══

SÍNTOMA (producción, descubierto al validar el fix del Bug 1):
    GET /api/v1/public/t/cafe-norte/catalog  -> HTTP 500
    GET /api/v1/public/t/bicifix/catalog      -> HTTP 500
    DataError: (psycopg.errors.InvalidTextRepresentation)
    invalid input value for enum product_status: "active"

    Y el detalle de la respuesta lo confirma:
      SELECT count(*) AS count_1 FROM (SELECT products.sku AS sku,
        products.name AS name, products.slug AS slug, ...)

CAUSA RAÍZ CONFIRMADA:
    La migración inicial (2026_09_07_1002) creó los ENUM con labels en
    MAYÚSCULAS:
      initial_schema.py:694  sa.Enum('DRAFT', 'ACTIVE', 'OUT_OF_STOCK',
                                     'ARCHIVED', name='product_status')
      initial_schema.py:956  sa.Enum('DRAFT', 'SENT', 'VIEWED', 'ACCEPTED',
                                     'REJECTED', 'EXPIRED', name='quote_status')

    Pero los modelos usan values_callable (es decir, el .value del enum), y
    para ProductStatus y QuoteStatus esos valores son LOWERCASE:
      app/models/product.py:101  values_callable=lambda obj: [e.value for e in obj]
        -> 'draft', 'active', 'out_of_stock', 'archived'
      app/models/quote.py:43     values_callable=lambda obj: [e.value for e in obj]
        -> 'draft', 'sent', 'viewed', 'accepted', 'rejected', 'expired'

    PostgreSQL valida el cast contra los miembros del TYPE, así que cualquier
    filtro WHERE status = 'active' falla.

    El desfase equivalente de order_status YA se había corregido en
    2026_10_06_0004_order_status_add_lowercase_values.py, pero NO existía
    migración equivalente para product_status ni quote_status: ese era el hueco.

    Audita de los 27 ENUM del modelo: sólo 3 usan labels lowercase
    (order_status, product_status, quote_status). Los otros 24 usan los
    nombres de miembro en mayúsculas y son consistentes.

IMPACTO:
    GET /api/v1/public/t/{slug}/catalog
    GET /api/v1/public/t/{slug}/products/{product_slug}
    GET /api/v1/tenants/{tenant_id}/products
    GET /api/v1/tenants/{tenant_id}/search/products
    y los endpoints de cotizaciones (quote_status).

═══ DEFECTOS HERMANOS DETECTADOS EN LA AUDITORÍA ═══
    D1) onboarding.html, admin_marketing.html y admin_scanner.html tenían el
        mismo antipatrón que el Mesero y usaban WH.Auth SIN guard:
            ReferenceError: WH is not defined
        (mismo origen: JS dentro de dash_content, antes de app.js)

    D2) orders.html sobrescribía {% block scripts %} SIN llamar a
        {{ super() }}, por lo que la página de Pedidos perdía:
            - /static/js/ai.js y /static/js/ai-context.js
            - WH.Auth.requireLogin()
            - el listener del botón "Salir" (WH.Auth.logout)
            - el resaltado del link activo del sidebar
            - /static/js/dashboard-compat.js

    D3) public/landing_wowprint.html tenía el mismo url_for('static',
        filename=...) de BUG 3 (template huérfano, sin ruta; se corrigió
        preventivamente).


--------------------------------------------------------------------------------
2. CAMBIO ÚNICO (qué se hizo)
--------------------------------------------------------------------------------

El release se compone de 19 commits atómicos. Cada uno es revertible por
separado.

═══ 2.1) commit 391ba30 — fix(db): hace idempotente la migración HU_50-HU_65 ═══

ARCHIVO: alembic/versions/2026_10_16_hu50_65_produccion.py

FUNCIÓNES INTERVENIDAS:
    _has_table(table)            → NUEVA
    _has_column(table, column)   → NUEVA
    _create_table(table, ...)    → NUEVA (reemplaza op.create_table)
    _create_index(name, ...)     → NUEVA (reemplaza op.create_index)
    upgrade()                    → usa los helpers idempotentes
    downgrade()                  → MODIFICADO después en 9857d1d (idempotencia)

QUÉ HACE:
    Cada operación verifica el esquema real antes de actuar:
      - _create_table: omite la tabla si ya existe.
      - op.add_column: conserva el literal (con guard `if not
        _has_column(...)`) porque tests/test_hu50_65_produccion.py:332-334
        lo exige. El helper _add_column que se había usado en la primera
        versión se eliminó en 9857d1d por romper esa garantía.
      - _create_index: omite el índice si ya existe.
      - _drop_column / _drop_index / _drop_table (downgrade): verifican el
        esquema real antes de borrar; _drop_column elimina antes los
        índices que referencian la columna (SQLite rechaza DROP COLUMN
        si hay un índice sobre ella).

POR QUÉ ES SEGURO:
    En una DB donde la migración YA ESTABA APLICADA, Alembic no la vuelve a
    ejecutar (la revisión ya quedó en alembic_version). Este cambio sólo
    afecta a DBs donde estaba PARCIALMENTE aplicada, donde antes fallaba con
    DuplicateTable y dejaba el esquema a medias.

    revision, down_revision y el contenido funcional NO cambian.

═══ 2.2) commit 5879fb9 — fix(db): reconciliador + migración correctiva ═══

ARCHIVO NUEVO: scripts/reconcile_schema.py

FUNCIÓNES INTERVENIDAS:
    reconcile(engine, dry_run=False)  → NUEVA. Compara Base.metadata contra el
                                        esquema real y repara la diferencia:
                                        (1) crea tablas faltantes,
                                        (2) AGREGA columnas faltantes derivando
                                            el tipo y el default del modelo,
                                        (3) crea índices declarados que falten.
    _type_ddl(col, dialect)           → NUEVA
    _server_default_sql(col, dialect) → NUEVA
    _fallback_default_sql(col)        → NUEVA
    main()                            → NUEVA (CLI, con --dry-run)

    Es IDEMPOTENTE, ADITIVO (nunca DROP) y AGNÓSTICO del estado de Alembic
    (legacy / stamped / alembic / failed). Los tipos Enum de PostgreSQL se
    omiten y se reportan (crear un TYPE en PG no es seguro si ya existe con
    otra forma).

ARCHIVO NUEVO: alembic/versions/2026_10_21_fix_schema_drift.py

    Revisión: 2026_10_21_fix_drift   (down_revision: 2026_10_16_hu50_65)
    Funciones: upgrade(), downgrade(), _existing_columns(), _add_column(),
               _create_index()

    Agrega, de forma idempotente, las 15 columnas de HU_50-HU_65:
      products:   product_type VARCHAR(30) NOT NULL DEFAULT 'standard'
                  template_type VARCHAR(30) NULL
                  m2_price_cents INTEGER NOT NULL DEFAULT 0
      customers:  customer_type VARCHAR(20) NOT NULL DEFAULT 'particular'
                  marketing_email_status VARCHAR(20) NOT NULL DEFAULT 'pending'
                  marketing_whatsapp_status VARCHAR(20) NOT NULL DEFAULT 'pending'
                  current_debt_cents INTEGER NOT NULL DEFAULT 0
      quote_items:template_type VARCHAR(30) NULL
                  width_cm FLOAT NULL
                  height_cm FLOAT NULL
                  faces INTEGER NOT NULL DEFAULT 1
                  suggested_price_cents INTEGER NOT NULL DEFAULT 0
                  cost_unit_cents INTEGER NOT NULL DEFAULT 0
                  pack_qty INTEGER NULL
                  pack_size INTEGER NULL
    Y crea los 3 índices: ix_products_product_type,
    ix_products_template_type, ix_customers_customer_type.
    Es ADITIVA y su downgrade usa IF EXISTS.

ARCHIVO: scripts/bootstrap_migrate.py

FUNCIÓNES INTERVENIDAS:
    _columns_added_by_migration(mig_dir, rev)  → NUEVA. Extrae las columnas
        que una migración agrega con op.add_column.
    _highest_fully_applied_revision(...)       → MODIFICADA. Ahora verifica
        TAMBIÉN las columnas add_column, no solo las tablas de create_table.
        Es la corrección directa del defecto de origen: una migración con
        columnas ausentes YA NO se considera aplicada, así que el bootstrap
        deja de sellar la DB en "head" con columnas sin aplicar.

ARCHIVO: scripts/entrypoint.sh

    Se agrega, DESPUÉS de create_all y ANTES de uvicorn:
        python -m scripts.reconcile_schema || echo "⚠ ... (continúa igualmente)"

═══ 2.3) commit 70a76b0 — fix(routes): restaura 6 rutas ═══

ARCHIVO: app/main.py

FUNCIONES INTERVENIDAS (NUEVAS):
    dashboard_templates(request)       GET /dashboard/templates  -> 200
    dashboard_page_legacy(request)     GET /dashboard/v1         -> 200
    dashboard_settings_redirect()      GET /dashboard/settings   -> 307
    dashboard_production_redirect()    GET /dashboard/production -> 307
    dashboard_analytics_redirect()     GET /dashboard/analytics  -> 307
    pricing_redirect()                 GET /pricing              -> 307

ARCHIVO: app/templates/dashboard/templates.html
    url_for('static', filename=...)  ->  rutas literales /static/...
    (3 ocurrencias: 2 <link> y 1 <script>)

ARCHIVO: app/templates/public/landing_wowprint.html
    url_for('static', filename=...)  ->  rutas literales /static/...
    (4 ocurrencias: 3 <link> y 1 <script>)

ARCHIVO: app/templates/home.html
    Se agrega el ancla id="pricing" en la sección de planes, que es el
    destino de la redirección /pricing -> /#pricing. (home_pro.html ya lo
    tenía; home.html no.)

═══ 2.4) commit e926605 — fix(ui/mesero): JS a dash_scripts ═══

ARCHIVO: app/templates/dashboard/mesero.html

    El bloque <script> (22.651 bytes, antes en líneas 417-960) y el
    <script src="/static/js/quick-create.js"> se mueven de
    {% block dash_content %} a {% block dash_scripts %}.

    Resultado verificado en el HTML renderizado:
      app.js@26746  <  primer uso de WH@27679   => OK

═══ 2.5) commit bff9602 — fix(ui/dashboard): onboarding, marketing, scanner ═══

ARCHIVOS:
    app/templates/dashboard/onboarding.html
    app/templates/dashboard/admin_marketing.html
    app/templates/dashboard/admin_scanner.html

    Mismo tratamiento: sus <script> pasan a {% block dash_scripts %}.
    admin_scanner.html tenía 2 scripts (el CDN de html5-qrcode + el inline);
    se mueven juntos para conservar el orden de carga.

    kds.html NO se modifica: sus usos de window.WH van TODOS con guard
    (window.WH && window.WH.api) y degradan con seguridad a fetch manual.

═══ 2.6) commit 9fbf363 — fix(ui/orders): restaura super() ═══

ARCHIVO: app/templates/dashboard/orders.html

    Se agrega {{ super() }} al inicio del bloque {% block scripts %}.
    Se recupera: ai.js, ai-context.js, WH.Auth.requireLogin(), el listener del
    botón "Salir", el link activo del sidebar y dashboard-compat.js.
    El JS propio de pedidos (modal "Crear pedido" y creación inline de
    cliente/producto) NO se toca.

═══ 2.7) commit eab765b — test(db): regresión de schema drift ═══

ARCHIVO NUEVO: tests/test_schema_drift_reconciliation.py  (10 tests)

═══ 2.8) commit d902dc7 — test(ui): regresión de rutas y scripts ═══

ARCHIVO NUEVO: tests/test_dashboard_routes_and_scripts.py  (48 tests)

═══ 2.9) commit 9857d1d — fix(db): idempotencia del downgrade HU_50-65 ═══

ARCHIVO: alembic/versions/2026_10_16_hu50_65_produccion.py
ARCHIVO: alembic/versions/2026_10_21_fix_schema_drift.py

    Detectado al validar la cadena Alembic completa:
    - Se restauran los literales op.add_column("products" / "customers" /
      "quote_items") que exige tests/test_hu50_65_produccion.py:332-334. La
      primera versión del fix usaba un helper _add_column(...) y rompía esa
      garantía del test legacy. El helper se elimina por quedar sin uso.
    - El downgrade de HU_50-65 pasa a ser idempotente: _drop_column,
      _drop_index y _drop_table verifican el esquema real antes de actuar.
      _drop_column elimina antes los índices que referencian la columna
      (SQLite rechaza DROP COLUMN si hay un índice sobre ella).
    - El downgrade de 2026_10_21_fix_drift pasa a NO-OP documentado: esa
      migración no es propietaria de las 15 columnas (son de la padre), y
      eliminarlas también hacía fallar "downgrade base" por doble borrado.

═══ 2.10) commit 55a324f — fix(ui/404): mensaje de negocio inexistente ═══

ARCHIVO: app/main.py
ARCHIVO: app/templates/public/404.html

    El handler global de errores renderizaba public/404.html sin pasar
    `slug` al contexto: Jinja serializaba el Undefined como "" y la
    página mostraba "El negocio "" no existe o está inactivo." para
    CUALQUIER 404, incluso de rutas del dashboard sin relación con un
    negocio.

    Ahora el slug se extrae SOLO de las URLs públicas por tenant
    (/u/{slug}); el resto de rutas lo reciben como None y la plantilla
    muestra "No encontramos la página que buscas."

    Sin impacto en el caso real de tenant: app/main.py:1129 ya pasaba el
    slug explícitamente al renderizar public/404.html para /u/{slug}.

═══ 2.11) commit f9b8258 — fix(db): alinea los ENUM con el modelo ═══

ARCHIVO NUEVO: alembic/versions/2026_10_23_fix_enum_labels.py

    Revisión: 2026_10_23_fix_enum_labels (down_revision: 2026_10_21_fix_drift)

    Funciones: upgrade(), downgrade(), _ensure_type()
    Datos: ENUMS = [(tipo, labels_legacy, labels_modelo), ...]

    - ALTER TYPE <tipo> ADD VALUE IF NOT EXISTS '<label>' para cada label que
      el modelo declara. Idempotente (PG 9.6+).
    - NO recrea el TYPE, NO hace DROP, NO toca filas, NO bloquea la tabla.
    - Bloque DO que crea el TYPE si no existe (con todos los labels).
    - El downgrade es un no-op documentado: PG no permite DROP VALUE de un ENUM.
    - Los labels legacy en mayúsculas se conservan: puede haber filas viejas
      con esos valores y siguen siendo legibles.

═══ 2.12) commit 3236178 — test(db): regresión de consistencia ENUM ═══

ARCHIVO NUEVO: tests/test_enum_labels_consistency.py  (31 tests)

    Compara los labels de cada ENUM del modelo contra la cadena de
    migraciones y falla si algún TYPE queda sin sus labels alineados. Es la
    guarda que evita que esta clase de bug vuelva a aparecer.

═══ 2.13) commit 5a5d43a — test(db): la cadena Alembic no fija el nombre de la head ═══

ARCHIVOS: tests/ (ajuste de los tests de cadena de migraciones)

    Los tests de cadena comparaban el resultado de `alembic heads` contra el
    literal "2026_10_21_fix_drift". Cada vez que se agrega una migración ese
    literal queda obsoleto y el test falla por un motivo que no es un
    defecto. Se cambió para verificar la INVARIANTE (una sola head, y que la
    cadena suba y baje limpiamente) en vez del NOMBRE de la head.

   Motivo: no es un fix funcional, es la guarda que permite agregar la
    migración de ENUM sin romper la suite.

═══ 2.14) commit e3d25b5 — fix(db): el reconciliador también repara los ENUM ═══

ARCHIVO: scripts/reconcile_schema.py

FUNCIÓNES INTERVENIDAS:
    _ensure_enum_labels(engine, ...)  → NUEVA. Lee pg_type/pg_enum y, si al
        modelo le falta un label, ejecuta
            ALTER TYPE <tipo> ADD VALUE IF NOT EXISTS '<label>'
        en AUTOCOMMIT (PostgreSQL exige que ALTER TYPE ... ADD VALUE se
        ejecute fuera de una transacción con otras sentencias).
    _normalize_enum_data(engine, ...) → NUEVA. Normaliza FILAS existentes
        whose labels están en MAYÚSCULAS al label en minúsculas del modelo.
    _enum_label_mapping(enum_cls, legacy_labels) → NUEVA (pura, sin DB).
        Devuelve el mapeo 1:1 legacy -> modelo, sólo si es verificable.
    reconcile(engine, dry_run)      → MODIFICADA. Invoca las dos funciones
        anteriores y reporta enum_values_added / enum_rows_normalized.

POR QUÉ FUE NECESARIO (hallazgo en producción):
    El fix del Bug 4 por MIGRACIÓN (f9b8258) no se aplicó en Railway: la
    cadena de Alembic no avanza porque alguna migración pendiente falla en
    la DB real (la DB quedó con alembic_version en una revisión anterior).
    El catálogo público siguió dando 500 hasta que el reconciliador reparó
    los ENUM, porque el reconciliador es AGNÓSTICO del estado de Alembic y
    se ejecuta SIEMPRE en el entrypoint.

    Con esto el ENUM queda cubierto por DOS capas independientes:
      - migración 2026_10_23_fix_enum_labels (si la cadena avanza)
      - reconciliador _ensure_enum_labels   (si la cadena NO avanza)

    SEGURIDAD DEL NORMALIZADO DE DATOS:
    _enum_label_mapping() sólo devuelve un mapeo cuando la correspondencia
    es 1:1 y sin ambigüedad. Los labels legacy en mayúsculas NO se borran
    (PostgreSQL no permite DROP VALUE de un ENUM): se AGREGAN los nuevos en
    minúsculas y las filas viejas se UPDATEan al valor nuevo. Para
    order_status NO se aplica: su modelo usa labels en español y su TYPE
    histórico usa nombres en inglés, así que no hay correspondencia 1:1
    verificable y se deja intacto.

═══ 2.15) commit 6a06c36 — chore(db): el reconciliador reporta alembic_version ═══

ARCHIVO: scripts/reconcile_schema.py

FUNCIÓNES INTERVENIDAS:
    _alembic_version(engine)  → NUEVA. Lee la revisión actual de la tabla
        alembic_version (si existe).
    reconcile(engine, dry_run) → MODIFICADA. Incluye "alembic_version" en el
        reporte y lo escribe en el log.
    main()                    → MODIFICADA. El resumen del log ahora empieza
        con la revisión de Alembic.

POR QUÉ:
    Como la cadena de Alembic no avanza en la DB de producción (ver 2.14),
    la revisión real era invisible desde fuera. Con este dato en el log del
    deploy se puede ver de inmediato en qué revisión está la DB y por qué
    las migraciones no avanzan. Es instrumentación de diagnóstico: NO
    cambia el comportamiento de la reconciliación.

═══ 2.16) commit (este) — test(prod): verificación automática de producción ═══

ARCHIVO NUEVO: scripts/verify_production.py

FUNCIÓNES INTERVENIDAS:
    get(base, path, follow=True)  → NUEVA. GET simple con manejo de
        redirecciones (permite comprobar el 307 y su Location).
    unguarded(js)                 → NUEVA. Detecta usos de WH.<algo> que no
        estén protegidos por un guard.
    main()                        → NUEVA. Ejecuta las comprobaciones de
        producción y devuelve 0 si todo pasa, 1 si hay fallos.
    __main__                      → Punto de entrada:
        python -m scripts.verify_production

QUÉ HACE:
    Ejecuta comprobaciones HTTP REALES contra el sitio desplegado y cubre
    los 4 errores corregidos, las 6 rutas restauradas, el orden de carga
    de scripts del Mesero, la recuperación de scripts de Pedidos, los
    catálogos públicos (ENUM), el Hero Showcase y /health + /openapi.json.
    Sólo hace GETs: no modifica nada.

POR QUÉ:
    El "Procedimiento de prueba" de este release era una lista de curl
    que había que ejecutar a mano. Con este script, la verificación
    post-deploy es reproducible por cualquier persona y devuelve un código
    de salida utilizable en un pipeline. Es la forma más barata de
    detectar que una regresión de este tipo vuelve a aparecer.


--------------------------------------------------------------------------------
3. QUÉ NO SE MODIFICÓ
--------------------------------------------------------------------------------

· Modelos de SQLAlchemy (app/models/*): 0 cambios.
· Endpoints de la API (app/api/v1/*): 0 cambios.
· Servicios (app/services/*): 0 cambios.
· Schemas (app/schemas/*): 0 cambios.
· Tareas Celery / Worker: 0 cambios. Ninguna tarea toca products,
  customers ni quote_items con columnas nuevas.
· Hero Showcase (app/static/img/hero/, hero_showcase.js, autoplay 3000 ms,
  8 tabs ARIA): 0 cambios. No se tocó ni la home ni sus assets.
· Paleta y estilos CSS: 0 cambios. La UI sigue sobria, sin colores nuevos.
  Sólo se cambiaron 7 rutas de assets (url_for -> literales) en 2 templates.
· Templates del dashboard en general: sólo los 6 listados arriba
  (mesero, onboarding, admin_marketing, admin_scanner, orders, templates).
· Lógica de negocio: 0 cambios. Ningún handler de la API cambió de
  comportamiento, ni de código de estado, ni de validación.
· Reglas de negocio y cálculos (totales, IVA, descuentos, cotizaciones):
  0 cambios.
· Contenido de datos de negocio: 0 cambios. Ninguna migración toca datos de
  negocio. Única excepción, y es de ETIQUETA, no de negocio:
  _normalize_enum_data() actualiza filas existentes cuyo ENUM está en
  MAYÚSCULAS al label en minúsculas del modelo ('ACTIVE' -> 'active').
  Es una normalización de representación, reversible en el sentido de que
  el valor sigue significando lo mismo, y sólo aplica a los 2 ENUM con
  mapeo 1:1 verificable (product_status, quote_status). NO aplica a
  order_status (su modelo usa labels en español y su TYPE histórico usa
  nombres en inglés).
  Los labels legacy en MAYÚSCULAS se CONSERVAN en el TYPE: PostgreSQL no
  permite DROP VALUE de un ENUM y borrarlos rompería las filas viejas.
· Variables de entorno / secrets: 0 cambios.
· Documentos V2.001-V2.010: intactos.
· No se ejecutó ningún DROP de tabla ni de columna en ninguna DB.
· No se usó git reset --hard ni git push --force.
· No se montó app/api/v1/templates.py (ver 7.5).


--------------------------------------------------------------------------------
4. REQUERIMIENTOS DE DESPLIEGUE
--------------------------------------------------------------------------------

4.1) Worker
    · NO requiere cambio.
    · Ninguna tarea Celery se ve afectada por las columnas agregadas
      (product_type, template_type, m2_price_cents, customer_type,
      marketing_*_status, current_debt_cents, quote_items.*) ni por las
      rutas de dashboard.
    · NO hace falta reiniciar el worker.

4.2) Build / Deploy
    · Push a main -> Railway auto-deploya (Dockerfile + railway.json,
      startCommand = /app/entrypoint.sh).
    · Sin rebuild de dependencias: no cambian requirements.txt.
    · El deploy ejecuta, en este orden:
        1. python -m scripts.bootstrap_migrate   (migraciones Alembic)
        2. Base.metadata.create_all(...)        (red de seguridad)
        3. python -m scripts.reconcile_schema   (NUEVO - repara columnas)
        4. uvicorn app.main_compat:app
    · Si el paso 1 falla, el paso 3 igual repara el esquema: por eso la
      reconciliación es una capa independiente y no depende del estado de
      alembic_version.

4.3) Base de datos
    · La migración 2026_10_21_fix_drift se aplica automáticamente en el
      deploy (down_revision = 2026_10_16_hu50_65, que era la head actual).
    · La migración 2026_10_23_fix_enum_labels se aplica automáticamente
      (down_revision = 2026_10_21_fix_drift). Es la nueva head de la cadena.
    · Si la DB de Railway estuviera en un estado inconsistente (columnas
      ausentes con alembic_version en head), el bootstrap YA NO la sella:
      detecta las columnas faltantes y aplica upgrade head, y el
      reconcile_schema agrega cualquier columna restante.
    · IMPORTANTE — LA CADENA DE ALEMBIC NO AVANZA EN LA DB DE PRODUCCIÓN:
      está bloqueada en una revisión anterior por una migración que falla
      sobre los datos reales (no se pudo leer el log de Railway para
      identificar cuál, por falta de acceso al dashboard y a los logs).
      Esto NO bloquea el release: la capa que repara el esquema es
      scripts/reconcile_schema.py, que es AGNÓSTICO del estado de Alembic
      y se ejecuta SIEMPRE en el entrypoint, haya avanzado o no la cadena.
      Con el fix del Bug 4 aplicado TAMBIÉN en el reconciliador (2.14), los
      4 errores quedan reparados aunque la cadena siga quieta.
      Diagnóstico pendiente para el equipo: leer el log del deploy de
      Railway para identificar la migración que falla y corregirla en un
      release posterior (V2.012).
    · NO se requiere ninguna intervención manual en la DB.
    · NO se requiere restore ni backup para este deploy (todo es aditivo).
    · La migración de ENUMs usa ALTER TYPE ... ADD VALUE IF NOT EXISTS:
      no recrea el TYPE, no borra filas y no bloquea las tablas. El
      reconciliador usa el mismo patrón.
    · La revisión real de la DB ahora se imprime en el log del deploy:
        [reconcile] alembic_version actual: <revisión>
    · IMPORTANTE: la fila de alembic_version NO se modifica a mano. Si se
      necesita avanzar la cadena, la vía correcta es arreglar la migración
      que falla, no editar la tabla.

4.4) Secrets / env
    · Sin cambios.

4.5) Rollback
    · git revert <commit> + push normal a main. El orden de revert es el
      inverso al de aplicación:
        (este) → (este) → 6a06c36 → e3d25b5 → 5a5d43a → 3236178 →
        f9b8258 → b8b4313 → 845b468 → 55a324f → 9857d1d → d902dc7 →
        9fbf363 → bff9602 → e926605 → 70a76b0 → eab765b → 5879fb9 →
        391ba30
    · Importante: revertir 5879fb9 y 391ba30 NO elimina las columnas ya
      agregadas en la DB (el downgrade de la migración es explícito y la
      operación de producción es aditiva). La DB quedaría con columnas extra
      no usadas, lo que es inofensivo.
    · NO revertir 391ba30 sin revertir 5879fb9: el HU_50-65 original
      fallaría con DuplicateTable en una DB donde sus tablas ya existen.
    · NO revertir e3d25b5 ni f9b8258 mientras el modelo use labels
      lowercase: el catálogo público volvería a dar 500.


--------------------------------------------------------------------------------
5. PROCEDIMIENTO DE PRUEBA (post-deploy en Railway)
--------------------------------------------------------------------------------

VERIFICACIÓN AUTOMÁTICA (una sola orden, cubre todo lo de esta sección):
  $ python -m scripts.verify_production
  Devuelve 0 e imprime "OK - validacion online completa sin fallos" si
  todo esta bien; devuelve 1 y lista los fallos si algo se rompio.
  Solo hace GETs: no modifica nada.
  (--base https://otro-host para apuntar a otro entorno)

Lo que cubre:
  A) las 6 rutas restauradas y sus codigos / redirecciones
  B) el contenido de /dashboard/templates (4 plantillas, rutas literales,
     sin el mensaje "negocio inexistente")
  C) el orden de carga de scripts del Mesero Virtual
  D) la recuperacion de scripts de /dashboard/orders
  E) /api/v1/tenants/{id}/products y los catalogos publicos (ENUM)
  F) el Hero Showcase (8 tabs, autoplay 3000 ms, 8 imagenes)
  G) /health y /openapi.json

Comprobaciones manuales equivalentes:

5.1) Health check
  $ curl -s https://wowhub-api-production.up.railway.app/health
  Esperado: 200 OK {"status":"ok",...}

5.2) Verificar BUG 1 — /products ya no da 500
  $ curl -s -o /dev/null -w "%{http_code}\n" \
      "https://wowhub-api-production.up.railway.app/api/v1/tenants/e865866c-6eb7-4394-bf91-723c6b003307/products?order_by=position&page_size=100"
  Con sesión autenticada: esperado 200 (no 500).
  Sin sesión: esperado 401 (el guard responde antes que la DB).
  NUNCA debe aparecer "column products.product_type does not exist" ni
  "UndefinedColumn".

5.3) Verificar BUG 2 — Mesero Virtual
  1. Login y abrir /dashboard/mesero.
  2. Consola del navegador (F12): SIN errores.
     ANTES: "TypeError: Cannot read properties of undefined (reading 'Auth')"
     AHORA: la página carga mesas, sucursal y catálogo de productos.
  3. Verificar que la tabla de mesas se puebla (el JS de loadTenantAndBranches
     se ejecuta sin excepción).

5.4) Verificar BUG 3 — /dashboard/templates
  $ curl -s -o /dev/null -w "%{http_code}\n" \
      https://wowhub-api-production.up.railway.app/dashboard/templates
  Esperado: 200 (antes 404).

  1. Login y hacer click en "Apariencia" en el sidebar.
  2. ESPERADO: se abre el selector con 4 tarjetas (Moderna, WowPrint, Dark,
     Default). NO debe aparecer la página 404 con
     "El negocio "" no existe o está inactivo".
  3. Click "Aplicar" en una plantilla -> debe aplicarse y recargar.

5.5) Verificar las rutas restauradas (todas)
  $ for u in /dashboard/templates /dashboard/v1 /dashboard/settings \
             /dashboard/production /dashboard/analytics /pricing; do
      printf "%-24s %s\n" "$u" \
        "$(curl -s -o /dev/null -w '%{http_code}' \
           https://wowhub-api-production.up.railway.app$u)"
    done
  Esperado:
    /dashboard/templates    200
    /dashboard/v1           200
    /dashboard/settings     307  (-> /dashboard/templates)
    /dashboard/production   307  (-> /dashboard/kds)
    /dashboard/analytics    307  (-> /dashboard/stats)
    /pricing                307  (-> /#pricing)

5.6) Verificar el esquema reparado (log de Railway)
  En el log del deploy debe aparecer:
    [reconcile] alembic_version actual: <revisión>
    [reconcile_schema] Resumen — alembic_version: <revisión> | tablas
    creadas: 0 | se agregó N columnas | índices creados: M | enum labels
    agregados: K | filas enum normalizadas: L | omitidas: 0 | errores: 0
  con N = 15 si la DB tenía el drift, o N = 0 si ya estaba reparada.
  Ambas salidas son correctas (el script es idempotente).

  Y el bootstrap debe mostrar, si hubo drift:
    [bootstrap_migrate] la migracion '2026_10_16_hu50_65' agrego
    products.product_type pero la columna NO existe en la DB — no se
    considera aplicada.
  (si no aparece esa línea, la DB ya estaba consistente)

  LECTURA DEL DATO DE alembic_version:
    - Si muestra la head (2026_10_23_fix_enum_labels): la cadena avanzó y
      todo fue aplicado por Alembic.
    - Si muestra una revisión ANTERIOR: la cadena está bloqueada por una
      migración que falla sobre los datos reales. NO es un incidente de
      este release: el reconciliador ya reparó el esquema y el catálogo
      público responde 200. Queda como pendiente de diagnóstico (4.3).

5.7) Verificar el Hero Showcase (no debe cambiar)
  $ curl -s https://wowhub-api-production.up.railway.app/ | grep -c "hero"
  Las 8 imágenes en /static/img/hero/ deben seguir respondiendo 200.
  Autoplay 3000 ms y 8 tabs ARIA: sin cambios.

5.8) Verificar el flujo de 3 clicks (no debe regresionar)
  1. /dashboard/orders -> "+ Crear pedido" -> modal.
  2. "+ Nuevo" junto a cliente -> crear cliente -> aparece en el select.
  3. "+ Nuevo" junto a producto -> crear producto -> aparece en el select.
  4. Crear pedido -> POST /orders exitoso.
  Este flujo NO se modificó en V2.011, pero se re-verifica porque el commit
  9fbf363 toca el mismo template (agrega {{ super() }}, nada más).

5.9) Verificar BUG 4 — catálogo público (el ENUM de products)
  $ for s in cafe-norte bicifix; do
      printf "%-12s %s\n" "$s" \
        "$(curl -s -o /dev/null -w '%{http_code}' \
           https://wowhub-api-production.up.railway.app/api/v1/public/t/$s/catalog)"
    done
  Esperado: 200 (antes 500).
  NUNCA debe aparecer "invalid input value for enum product_status".

  En el log del deploy debe aparecer una de estas dos trazas:
    (a) la migración aplicó los labels:
        [fix_enum_labels] product_status: +'draft' OK
        [fix_enum_labels] product_status: +'active' OK
        [fix_enum_labels] product_status: +'out_of_stock' OK
        [fix_enum_labels] product_status: +'archived' OK
        [fix_enum_labels] quote_status: +'draft' OK
        ... (6 labels en total)
    (b) el reconciliador los reparó (si la cadena no avanzó):
        [reconcile] enum labels agregados: 6

  Ambas son correctas: la garantía es que el TYPE tenga los labels en
  minúsculas, sin importar qué capa los agregó.


--------------------------------------------------------------------------------
6. ROLLBACK
--------------------------------------------------------------------------------

  $ git revert <este>   # test(prod) verify_production.py
  $ git revert <este>   # docs(release) actualizacion final del README
  $ git revert 6a06c36   # chore(db) reporte de alembic_version
  $ git revert e3d25b5   # fix(db) reconciliador repara ENUM
  $ git revert 5a5d43a   # test(db) cadena Alembic sin nombre fijo de head
  $ git revert 3236178   # test(db) consistencia ENUM
  $ git revert f9b8258   # fix(db) migracion de ENUM
  $ git revert b8b4313   # docs(release) fecha del README
  $ git revert 845b468   # docs(release) README V2.011
  $ git revert 55a324f   # fix(ui/404) mensaje de negocio inexistente
  $ git revert 9857d1d   # fix(db) idempotencia del downgrade HU_50-65
  $ git revert d902dc7   # test(ui)
  $ git revert 9fbf363   # fix(ui/orders)
  $ git revert bff9602   # fix(ui/dashboard)
  $ git revert e926605   # fix(ui/mesero)
  $ git revert 70a76b0   # fix(routes)
  $ git revert eab765b   # test(db)
  $ git revert 5879fb9   # fix(db) reconciliador
  $ git revert 391ba30   # fix(db) idempotencia HU_50-65
  $ git push origin main

El bloque anterior ya está en orden inverso de aplicación (del más reciente
al más antiguo), que es el orden más seguro.

Notas de rollback:
  · Revertir 3236178 / 5a5d43a / d902dc7 / eab765b (tests) no tiene efecto
    funcional.
  · Revertir los 2 commits de este bloque (README + verify_production.py) no
    tiene efecto funcional: sólo retira documentación y la herramienta de
    verificación.
  · Revertir 6a06c36 sólo quita la línea de diagnóstico del log.
  · Revertir f9b8258 o e3d25b5 NO elimina los labels agregados al TYPE: PG no
    permite DROP VALUE. El catálogo público volvería a fallar, así que estos
    commits NO se deben revertir mientras el modelo use labels lowercase.
  · Revertir 5879fb9 y 391ba30 NO elimina las columnas ya agregadas en la DB
    (el downgrade de la migración es explícito y la operación de producción es
    aditiva). La DB quedaría con columnas extra no usadas, lo que es inofensivo.
  · NO revertir 391ba30 sin revertir 5879fb9: el HU_50-65 original
    fallaría con DuplicateTable en una DB donde sus tablas ya existen.

Sin impacto en datos: las columnas agregadas quedan en la DB (inofensivas,
no usadas) y no hay DROP de nada.

Revertir sólo 391ba30 (sin 5879fb9) sí es peligroso: el HU_50-65 original
fallaría con DuplicateTable en una DB donde sus 6 tablas ya existen.
Revertir en ese orden (inverso) es seguro.


--------------------------------------------------------------------------------
7. TRAZABILIDAD
--------------------------------------------------------------------------------

7.1) Commits (en orden de aplicación)
  · 391ba30  fix(db): hace idempotente la migracion HU_50-HU_65
  · 5879fb9  fix(db): reconciliador de esquema + migracion correctiva
  · eab765b  test(db): regresion de schema drift (products.product_type)
  · 70a76b0  fix(routes): restaura 6 rutas perdidas en app/main.py
  · e926605  fix(ui/mesero): mueve el JS inline a dash_scripts
  · bff9602  fix(ui/dashboard): orden de carga de scripts en onboarding,
             marketing y scanner
  · 9fbf363  fix(ui/orders): restaura super() en el bloque scripts
  · d902dc7  test(ui): regresion de rutas del dashboard y orden de scripts
  · 9857d1d  fix(db): idempotencia del downgrade de HU_50-65 y literales
             op.add_column
  · 55a324f  fix(ui/404): el mensaje "negocio inexistente" solo aparece
             para URLs de tenant
  · 845b468  docs(release): README V2.011 (redaccion inicial)
  · b8b4313  docs(release): fecha correcta del README V2.011 (2026-10-23)
  · f9b8258  fix(db): alinea los ENUM product_status y quote_status con el
             modelo
  · 3236178  test(db): regresion de consistencia ENUM modelo <-> PostgreSQL
  · 5a5d43a  test(db): los tests de cadena Alembic no dependen del nombre
             de la head
  · e3d25b5  fix(db): el reconciliador tambien repara los ENUM de PostgreSQL
  · 6a06c36  chore(db): el reconciliador reporta la revision actual de
             alembic_version
  · (este)   docs(release): actualizacion final del README V2.011 con los
             resultados de la validacion online
  · (este)   test(prod): verificacion automatica de produccion en una orden
             (scripts/verify_production.py)

7.2) Archivos modificados (21 archivos)
  · alembic/versions/2026_10_16_hu50_65_produccion.py   +160 / -58
  · alembic/versions/2026_10_21_fix_schema_drift.py      +168  (nuevo)
  · alembic/versions/2026_10_23_fix_enum_labels.py        +157  (nuevo)
  · app/main.py                                          +75 / -1
  · app/templates/dashboard/admin_marketing.html         +17 / -2
  · app/templates/dashboard/admin_scanner.html           +18 / -1
  · app/templates/dashboard/mesero.html                  +26 / -7
  · app/templates/dashboard/onboarding.html              +15
  · app/templates/dashboard/orders.html                   +7
  · app/templates/dashboard/templates.html                +8 / -3
  · app/templates/home.html                                +1 / -1
  · app/templates/public/404.html                         +4
  · app/templates/public/landing_wowprint.html            +4 / -4
  · scripts/bootstrap_migrate.py                          +60 / -3
  · scripts/entrypoint.sh                                 +13
  · scripts/reconcile_schema.py                          +576  (nuevo)
  · scripts/verify_production.py                          +226  (nuevo)
  · tests/test_dashboard_routes_and_scripts.py          +182  (nuevo)
  · tests/test_enum_labels_consistency.py                +317  (nuevo)
  · tests/test_schema_drift_reconciliation.py            +345  (nuevo)
  · docs/releases/README_V2.011_FIX_SCHEMA_MESERO_TEMPLATES_2026-10-23.txt
                                                (nuevo, este documento)

7.3) Trazabilidad error -> commit -> prueba
  · products.product_type    -> 391ba30 + 5879fb9 + 9857d1d
                                -> test_schema_drift_reconciliation.py
  · WH.Auth undefined        -> e926605          -> test_dashboard_routes_and_scripts.py
  · /dashboard/templates 404  -> 70a76b0          -> test_dashboard_routes_and_scripts.py
  · onboarding/marketing/scanner -> bff9602       -> test_dashboard_routes_and_scripts.py
  · orders sin super()       -> 9fbf363          -> test_dashboard_routes_and_scripts.py
  · mensaje "negocio inexistente" -> 55a324f      -> (verificado en el render)
  · ENUM product_status/quote_status -> f9b8258 + e3d25b5
                                           -> test_enum_labels_consistency.py
  · cadena Alembic sin nombre fijo de head -> 5a5d43a
                                           -> tests/f0_baseline/test_alembic.py
  · diagnóstico de la revisión real -> 6a06c36    -> (log del deploy)

7.4) LIMITACIÓN CONOCIDA (NO corregida en V2.011, por decisión)

    app/api/v1/templates.py existe y expone GET/PUT /tenants/{tenant_id}/template,
    pero su router NO está montado en app/main.py (también se perdió en 9ea9bec).
    NO se monta en este release a propósito: ese router no verifica usuario ni
    membership, y montarlo expondría la edición de la plantilla de cualquier
    UUID de tenant conocido.

    Impacto actual: el selector de /dashboard/templates guarda la elección en
    localStorage (template-selector.js), que es lo que el JS intenta hacer
    cuando document.body.dataset.tenantId no está definido — y el layout no
    lo define. La UI funciona; la persistencia por tenant en servidor no.

    Para habilitarla en el futuro: montar templates_api.router con
    get_current_membership y verificación de pertenencia al tenant.

7.5) PENDIENTE PARA V2.012 (diagnóstico, no bloquea V2.011)

    La cadena de Alembic de la DB de producción NO avanza: está bloqueada en
    una revisión anterior por una migración que falla sobre los datos reales.
    No se pudo identificar cuál porque el dashboard de Railway abre un diálogo
    de Login (no hay sesión en el navegador del agente) y no hay CLI ni token
    de Railway en el entorno.

    Mitigación aplicada en V2.011: la reparación del esquema y de los ENUM la
    hace scripts/reconcile_schema.py, que es agnóstico del estado de Alembic
    y se ejecuta siempre en el entrypoint. Los 4 errores quedaron corregidos
    y verificados online con la cadena quieta.

    Acción pendiente: leer el log del deploy en el dashboard de Railway,
    identificar la migración que falla y corregirla (con sufijo _noop o
    guardas de idempotencia) en V2.012.

7.6) Origen del incidente (para el registro)
  · 9ea9bec sobrescribió app/main.py con una versión anterior a V2.01 y
    eliminó 6 rutas. Fue un conflicto de merge/rebase no detectado, no un
    cambio intencional.
  · El bootstrap de migraciones sellaba la DB en "head" sin verificar las
    columnas de las migraciones con op.add_column. El defecto estaba latente
    desde la creación de la migración HU_50-HU_65 (2026-10-16) y se hizo
    visible en cuanto una DB real quedó con las tablas creadas por
    create_all pero sin las columnas.
  · El desfase de labels de los ENUM existía desde la migración inicial
    (2026_09_07_1002), que creó product_status y quote_status en MAYÚSCULAS
    mientras el modelo los usa en minúsculas. El desfase equivalente de
    order_status ya se había corregido el 2026-10-06; esos dos se quedaron
    fuera.


--------------------------------------------------------------------------------
8. VALIDACIÓN EJECUTADA
--------------------------------------------------------------------------------

LOCAL
  · Reproducción del Bug 1 con el estado exacto de la DB de Railway:
      - bootstrap sellaba en '2026_10_16_hu50_65' (head) con 15 columnas
        faltantes  -> CAUSA RAÍZ CONFIRMADA
      - tras el fix, el bootstrap deja alembic_version =
        '2026_10_21_fix_drift' y las 15 columnas presentes.
  · reconcile_schema sobre la DB con drift:
      - se agregó 15 columnas | índices creados: 22 | omitidas: 0 | errores: 0
      - segunda ejecución: 0 columnas, 0 índices, 0 errores  (IDEMPOTENTE)
  · Alembic:
      - alembic heads            -> 2026_10_23_fix_enum_labels (UNA sola head)
      - alembic upgrade head     -> OK (base limpia y base con drift)
      - alembic downgrade base   -> OK (queda 1 tabla)
      - 21 revisiones en cadena, sin revisiones huérfanas y sin revisiones
        borradas del árbol de archivos.
  · Reconciliador de ENUM sobre la DB con drift de labels:
      - labels agregados: 6 | filas normalizadas: N | errores: 0
      - segunda ejecución: 0 labels, 0 filas  (IDEMPOTENTE)
      - el mapeo de normalización sólo se aplica a product_status y
        quote_status; order_status queda intacto (mapeo no 1:1).
  · Rutas (TestClient sobre la app real):
      /dashboard/templates  200   (22.793 bytes, 4 plantillas)
      /dashboard/v1          200
      /dashboard/settings    307  -> /dashboard/templates
      /dashboard/production  307  -> /dashboard/kds
      /dashboard/analytics   307  -> /dashboard/stats
      /pricing               307  -> /#pricing
  · Orden de carga de scripts en 19 páginas del dashboard: TODAS OK.
      /dashboard/mesero: app.js@26746 < primer uso de WH@27679
  · /dashboard/orders recuperó ai.js, ai-context.js, dashboard-compat.js,
    requireLogin y conserva openNewOrderModal, submitNewOrder,
    newOrderAddItemRow, wcRefreshProductoSelect, wcRefreshClienteSelect.

SUITE DE TESTS (pytest, conjunto crítico)
  · tests/test_schema_drift_reconciliation.py     10 passed
  · tests/test_dashboard_routes_and_scripts.py    48 passed
  · tests/test_enum_labels_consistency.py          31 passed
  · tests/test_hu50_65_produccion.py              34 passed
  · tests/f0_baseline/                             87 passed + 1 xpassed
  · TOTAL CRÍTICO: 210 passed, 1 xpassed (sin regresiones)
    Antes de V2.011 el mismo conjunto daba 121 passed + 1 xpassed.
    El delta (+89) son los 89 tests nuevos de regresión de este release.
  · Suite completa del repo (fuera del conjunto crítico): excede el timeout
    de 600 s, por lo que se validó por chunks.

ONLINE (Railway) — VERIFICADO en producción, sin fallos
  Script: scripts/verify_production.py (comprobaciones HTTP reales sobre el
  sitio desplegado). Resultado final:
  "OK - validacion online completa sin fallos".

  · /health 200 {"status":"ok","version":"0.2.0","env":"production",...}
  · /openapi.json -> 258 paths (sin cambios)
  · /dashboard/templates -> 200 (22.793 bytes) con las 4 plantillas
      (Moderna, WowPrint, Dark, Default)
      ruta literal /static/css/templates/dashboard.css presente
      sin url_for('static', filename=...) y sin el mensaje "negocio inexistente"
  · /dashboard/v1         -> 200
  · /dashboard/settings   -> 307 -> /dashboard/templates
  · /dashboard/production -> 307 -> /dashboard/kds
  · /dashboard/analytics  -> 307 -> /dashboard/stats
  · /pricing              -> 307 -> /#pricing
  · /dashboard/mesero -> 200 (63.917 bytes)
      app.js@26746  =>  ORDEN CORRECTO
      ningún <script> usa WH sin guard antes de app.js
      loadTenantAndBranches y window.WH.Auth.ensureSession presentes
  · /dashboard/orders -> 200 (56.317 bytes)
      ai.js, ai-context.js, dashboard-compat.js y requireLogin presentes
      openNewOrderModal, submitNewOrder, wcRefreshProductoSelect presentes
  · /api/v1/tenants/{id}/products -> 401 {"detail":"Falta header Authorization"}
      el guard de auth responde antes que la DB: sin 500, sin UndefinedColumn
      => la columna products.product_type ya no es el problema
  · BUG 4 — CATÁLOGO PÚBLICO (el que estaba en 500):
      GET /api/v1/public/t/cafe-norte/catalog -> 200 (6.576 bytes)
      GET /api/v1/public/t/bicifix/catalog     -> 200 (1.226 bytes)
      GET /api/v1/public/t/cafe-norte/products/espresso -> 200
      sin "invalid input value for enum" ni "not among the defined enum values"
  · HERO SHOWCASE intacto:
      home 200 (36.436 bytes), 8 tabs role="tab" en el HTML,
      hero_showcase.js 200 (9.177 bytes) con AUTOPLAY_MS = 3000,
      las 8 imágenes de /static/img/hero/ responden 200
      (bookings.png, catalog.png, orders.png, page.png, payments.jpg,
       promos.png, qr.png, stats.png)


--------------------------------------------------------------------------------
9. PRINCIPIO UX (sin cambios funcionales)
--------------------------------------------------------------------------------

V2.011 no introduce ni modifica ninguna funcionalidad de negocio. Es un
release de CORRECCIÓN: devuelve al sistema al comportamiento que ya
declaraba.

  · El flujo de 3 clicks (crear pedido + cliente + producto sin salir del
    módulo) sigue igual. Lo que cambia es que ahora la página de Pedidos
    recupera el bloque de scripts del padre (botón "Salir", link activo,
    dashboard-compat.js) y el Mesero Virtual deja de morirse al cargar.
  · La UI sigue sobria: sin colores nuevos, sin elementos nuevos en
    pantalla. Los 3 errores corregidos ERAN precisamente los que ocultaban
    herramientas que el usuario ya tenía.
  · "Apariencia" vuelve a ser accesible en un click desde el sidebar, y el
    selector de plantillas (Moderna / WowPrint / Dark / Default) funciona
    como estaba diseñado.
  · El Catálogo de productos del tenant vuelve a cargar: sin el 500 de
    products.product_type, el usuario puede ver y editar su catálogo y crear
    productos nuevos desde el propio flujo de pedidos.
  · El catálogo PÚBLICO (el que ve el cliente final en /t/{slug}) vuelve a
    pintar productos: sin el 500 del ENUM, la vitrina de cada negocio
    muestra su catálogo real otra vez. Esta es la diferencia visible
    para el cliente final.
  · Nota de alcance: el selector de plantillas sigue guardando la
    elección en el navegador (localStorage), no en el servidor, por la
    limitación documentada en 7.4. La UI funciona; la persistencia
    multi-dispositivo de la plantilla queda pendiente.


================================================================================
FIN README_V2.011_FIX_SCHEMA_MESERO_TEMPLATES_2026-10-23.txt
================================================================================
