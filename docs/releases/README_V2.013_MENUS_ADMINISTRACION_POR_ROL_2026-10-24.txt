================================================================================
README V2.013 — MENÚS DE ADMINISTRACIÓN POR ROL
Restitución de los menús "Administración" y "SUPER ADMIN" para el rol que
corresponde
================================================================================

VERSIÓN         : V2.013
FECHA           : 2026-10-24
VENTANA         : 2026-10-24 (Chile)
BUILD           : rama main (base 916d5b1, cierre de V2.012)
ALCANCE         : 2 defectos reportados por el usuario (menú de administración
                  del tenant y menú SUPER ADMIN que nunca se mostraban), más
                  1 defecto preexistente de la suite de tests y 1 defecto
                  hermano del mismo patrón (banner de impersonación).
ATOMICIDAD      : 4 commits independientes, cada uno revertible por separado
                  sin arrastrar a los demás.
REVERSIÓN       : 4 commits, 6 archivos, +731 / -42
RIESGO          : BAJO. No hay migraciones, ni DROP, ni cambios de contrato
                  de la API. No se abre acceso a ningún rol nuevo: los
                  guards server-side siguen exigiendo los mismos roles.

--------------------------------------------------------------------------------
1. BASE
--------------------------------------------------------------------------------

Rama          : main
Base          : 916d5b1 (cierre de V2.012)
Commits       : 4, en orden de aplicación:

  cc44b69  fix(ui/sidebar): restaura los menus Administracion y SUPER ADMIN
           por rol real
  0a0e2f0  fix(api/rbac): resuelve el rol de administracion desde la
           membresia del tenant
  b4d483d  test(v2.013): regresion de los menus Administracion y SUPER ADMIN
           por rol
  d7b5e4d  test(dashboard/layout): actualiza la expectativa del layout default
           (12 widgets)

Archivos modificados (6, +731 / -42):

  app/deps.py                           +64
  app/main.py                           +28 / -6
  app/static/js/app.js                  +23 / -1
  app/templates/dashboard/base.html    +108 / -30
  tests/test_dashboard_layout.py        +12 / -6
  tests/test_v2_013_admin_menu_roles.py  +532   (nuevo)
  docs/releases/README_V2.013_MENUS_ADMINISTRACION_POR_ROL_2026-10-24.txt
                                        (nuevo)

--------------------------------------------------------------------------------
2. CAMBIO ÚNICO
--------------------------------------------------------------------------------

Una sola idea: **el menú de administración existe y ahora se le muestra a
quien corresponde**.

El reporte fue "en el proceso anterior se eliminó el menú de Administración y
SUPER ADMIN, debes agregarlos para el rol que corresponda". La investigación
mostró que esos menús NO fueron eliminados: siempre estuvieron en el
template, pero ocultos, y tres defectos distintos los hacían invisibles
para todos. El de SUPER ADMIN, además, estaba roto para siempre: el claim
`is_superuser` no se podía leer nunca.

Lo que había que arreglar eran TRES fuentes de verdad distintas del rol, y
las tres apuntaban al lugar equivocado:

  a) EL ROL EFECTIVO NO SE LEÍA DE LA MEMBRESÍA
     La fuente de verdad del rol de una persona dentro de un negocio es
     `TenantMembership.role` (y el flag `is_owner`). `User.default_role` es
     sólo "el rol por defecto que hereda una membresía nueva" y su default
     es STAFF. El modelo lo dice explícitamente en su comentario.
     El sidebar leía `user.default_role`: el dueño del negocio quedaba con
     rol "staff", no calificaba para owner/admin y sus items se iban.

  b) EL CLAIM is_superuser NUNCA SE PODÍA LEER
     El payload de un JWT va en base64url: usa '-' y '_' en vez de '+' y '/'
     y NO lleva relleno (=). El código hacía:
         atob(parts[1].replace(/-/g,"+").replace(/_/g,"/"))
     Si el largo % 4 != 0 — que es la norma, porque base64url no rellena —
     el navegador lanza InvalidCharacterError. El `catch (_) {}` se lo
     comía y `isSuperuser` quedaba SIEMPRE en false. Por eso el item
     SUPERADMIN no aparecía ni para un superusuario real.

  c) EL GUARD BORRABA EL MENÚ EN VEZ DE OCULTARLO
     Cuando el rol no calificaba, el guard hacía `el.remove()`: eliminaba
     el nodo del DOM. Un fallo transitorio de sesión (o un token expirado
     durante la rehidratación) dejaba el menú mutilado de forma
     permanente, sin forma de recuperarlo sin recargar a mano.

Detalle por commit, con las funciones exactas que se tocaron:

═══ 2.1) cc44b69 — fix(ui/sidebar): los menús y su guard ═══

ARCHIVO: app/templates/dashboard/base.html

SÍNTOMA: el menú "Administración" (Admin IA + Observabilidad) no le aparecía
al dueño ni al admin del tenant; el de "SUPER ADMIN" no le aparecía a
nadie.

FUNCIÓN INTERVENIDA: `applyRoleGuards()` (IIFE inline del sidebar).

    ANTES:
        const user = session.user || WH.Auth.user();
        const role = (user && (user.default_role || user.role)) || "";
        const roleStr = String(role).toLowerCase();
        ...
        const payload = JSON.parse(atob(parts[1].replace(/-/g,"+").replace(/_/g,"/")));
        isSuperuser = !!payload.is_superuser;
        ...
        if (allowed.length === 0 || allowed.includes(roleStr)) {
            el.style.display = "";
        } else {
            el.remove();          // ← borraba el item del DOM
        }

    AHORA:
        const tenant = session.tenant || WH.Auth.tenant();
        let claims = WH.Jwt.decode(tk);        // base64url con padding
        let roleStr = "";
        if (tenant) {
            if (tenant.is_owner) roleStr = "owner";
            else if (tenant.role) roleStr = String(tenant.role).toLowerCase();
        }
        if (!roleStr && claims && claims.role) roleStr = ...;
        if (!roleStr && user) roleStr = String(user.default_role || ...);
        let isSuperuser = !!(claims && claims.is_superuser);
        if (!isSuperuser && user) isSuperuser = !!(user.is_superuser || ...);
        ...
        el.style.display = visible ? "" : "none";   // oculta, no elimina

Orden de resolución del rol en el cliente (de más a menos específico):
  1) `current_tenant.is_owner` → "owner"
  2) `current_tenant.role` → el rol de la membresía del tenant activo
  3) claim `role` del JWT (lo emite el login/refresh)
  4) `user.default_role` (último recurso)

`current_tenant` lo expone `/api/v1/auth/me/session` (campo `current_tenant`
con `role` e `is_owner`) y queda cacheado en `TokenStore.currentTenant()`.

ESTRUCTURA DEL SIDEBAR (nueva):

    Negocio
    Gestión interna
    Avanzado
      Asistente IA · Marketplace · Estadísticas · Pagos · Webhooks · API Docs
    ADMINISTRACIÓN          ← encabezado <h4> gate owner,admin
      🛡️ Admin IA              → /admin/ai
      📊 Observabilidad        → /dashboard/admin-observability
    SUPER ADMIN             ← encabezado <h4> gate superuser
      👑 Panel de plataforma   → /admin/superadmin

  · El encabezado de cada sección lleva el MISMO gate que sus items, para que
    un rol sin permisos no vea un título suelto sin contenido debajo.
  · Todo nace con `style="display:none;"`: si el JS no corre, el menú queda
    CERRADO (fail-closed), nunca abierto por error.
  · "API Docs" sube por encima de los dos encabezados con gate: si
    quedara abajo, un superusuario lo vería colgando de "SUPER ADMIN" y un
    owner colgando de "Administración".
  · El item de plataforma se rotuló "Panel de plataforma" (con "SUPERADMIN"
    en el title) para no duplicar el texto del encabezado.

FUNCIÓN INTERVENIDA: `decodeJwtPayload()` (banner de impersonación).

    El mismo bug de base64url afectaba al banner de impersonación: el claim
    `imp` nunca se leía y el banner nunca aparecía. Ahora delega en
    `WH.Jwt.decode` (con fallback propio que también restaura el padding).

ARCHIVO: app/static/js/app.js

FUNCIÓN INTERVENIDA: nuevo helper `Jwt.decode(token)`.

    base64url → base64 con padding, y decodificación UTF-8 (para que los
    nombres con tildes no se rompan):

        let b64 = parts[1].replace(/-/g, "+").replace(/_/g, "/");
        while (b64.length % 4 !== 0) b64 += "=";
        const bin = atob(b64);
        const bytes = Uint8Array.from(bin, (c) => c.charCodeAt(0));
        return JSON.parse(new TextDecoder().decode(bytes));

  Exportado en `window.WH` como `WH.Jwt`. app.js se carga en el layout raíz
  ANTES del bloque `{% block scripts %}` del dashboard, así que el sidebar
  siempre lo encuentra disponible.

═══ 2.2) 0a0e2f0 — fix(api/rbac): el rol de la membresía en el servidor ═══

 Aunque el menú apareciera, la página de destino igual rechazaba al dueño:
 el guard server-side comparaba contra el mismo campo equivocado.

ARCHIVO: app/main.py

FUNCIÓN INTERVENIDA: `admin_ai_page()` (ruta GET /admin/ai).

    ANTES:
        role = getattr(user, "default_role", None) or getattr(user, "role", None)
        if role not in (UserRole.OWNER, UserRole.ADMIN):
            return RedirectResponse(url="/dashboard?reason=admin_forbidden", ...)

    AHORA:
        role = resolve_effective_tenant_role(db, user, payload)
        is_superuser = bool(getattr(user, "is_superuser", False)
                            or payload.get("is_superuser"))
        if role not in (UserRole.OWNER.value, UserRole.ADMIN.value) and not is_superuser:
            return RedirectResponse(url="/dashboard?reason=admin_forbidden", ...)

FUNCIÓN INTERVENIDA: `admin_observability_page()`
  (ruta GET /dashboard/admin-observability) — mismo cambio.

Criterio resultante (idéntico al de `require_platform_admin`, que ya existía
en el repo): superusuario de plataforma, o OWNER/ADMIN del tenant activo.

ARCHIVO: app/deps.py

FUNCIÓN INTERVENIDA: nueva `resolve_effective_tenant_role(db, user, payload)`.

    Orden de resolución:
      1) claim `tid` del JWT → la membresía activa de ese tenant
      2) sin `tid` → la membresía activa más privilegiada (owner > admin)
      3) claim `role` del JWT (emitido en el login/refresh)
      4) `User.default_role` (último recurso)

    Helper auxiliar `_membership_role_value()`: `is_owner=True` implica
    "owner" aunque el campo `role` diga otra cosa (mismo criterio que
    `require_role`).

    Sólo cuenta membresías con `is_active = True`.

═══ 2.3) b4d483d — test(v2.013): 32 tests de regresión ═══

ARCHIVO: tests/test_v2_013_admin_menu_roles.py (nuevo, 32 tests)

  · Sidebar (8): existen las secciones "Administración" y "SUPER ADMIN" con
    sus gates y nacen ocultas; Admin IA, Observabilidad y el link a
    /admin/superadmin conservan el gate; API Docs no queda colgando de una
    sección privilegiada.
  · Cliente (5): el guard usa el rol de la membresía del tenant; ya no
    llama `el.remove()`; decodifica el token con WH.Jwt; el decoder restaura
    el padding base64url; el banner de impersonación usa el mismo decoder.
  · Servidor (4): app.deps expone el helper canónico; app/main.py ya no
    autoriza con `user.default_role`; los dos guards usan el helper; el
    guard de /admin/superadmin sigue exigiendo superuser.
  · Funcional contra la BD (7): el dueño con default_role=STAFF resuelve
    "owner"; el admin resuelve "admin"; staff y viewer no califican; la
    membresía del tenant activo manda sobre las demás; `is_owner` gana al
    campo `role`; una membresía dada de baja no habilita nada; sin membresía
    se cae al claim del JWT y luego al default_role.
  · Funcional HTTP (8): el dueño y el admin abren /admin/ai (200) y
    /dashboard/admin-observability (200); el empleado y el lector reciben
    302 con reason=admin_forbidden; las rutas sin sesión reciben 302 con
    reason=admin_auth; /admin/superadmin abre para un superusuario (200) y
    bloquea a un admin normal (302 con reason=superadmin_forbidden).

═══ 2.4) d7b5e4d — test(dashboard/layout): expectativa desactualizada ═══

ARCHIVO: tests/test_dashboard_layout.py

SÍNTOMA: `test_default_layout_when_no_saved` fallaba con `assert 12 == 10`.

  Es un defecto PREEXISTENTE a V2.013, reproducido sobre 916d5b1 sin los
  cambios de este release: la app devuelve 12 widgets default (su propio
  endpoint lo documenta como "los 12 widgets") desde que se agregaron
  `inventory_alerts` y `campaigns_active`, y el test seguía afirmando 10.

  El producto es el que está bien; la expectativa del test estaba atrasada.
  Se actualizó SOLO la expectativa (cantidad y conjunto de tipos). No se
  tocó la definición del layout default ni ningún endpoint.

  Con esto la suite crítica queda en verde y cualquier regresión futura del
  layout se vuelve a ver en lugar de quedar tapada por un fallo viejo.

--------------------------------------------------------------------------------
3. QUÉ NO SE MODIFICÓ
--------------------------------------------------------------------------------

· Modelos de SQLAlchemy (app/models/*): 0 cambios. No se tocó User,
  TenantMembership ni ningún ENUM.
· Migraciones de Alembic: 0. No hay revisión nueva, ni siquiera aditiva.
  La head de la cadena sigue siendo 2026_10_24_fix_rbac_id_type.
· La matriz de permisos (app/core/rbac_policies_matrix.py) y el seed de
  Casbin (app/core/rbac_seed.py): 0 cambios. No se abrió ni se cerró ningún
  permiso: lo que estaba mal era de dónde se leía el rol.
· Endpoints de la API (app/api/v1/*): 0 cambios de contrato. Ninguna ruta
  nueva, ninguna firma nueva, ningún status nuevo.
· Los guards de las rutas: no se relajaron. /admin/ai y
  /dashboard/admin-observability siguen exigiendo OWNER/ADMIN del tenant
  (más superusuario, como ya hacía require_platform_admin en el resto de la
  plataforma), y /admin/superadmin sigue exigiendo superusuario. Un
  empleado o un lector siguen recibiendo 302.
· La semántica de la impersonación en las páginas de administración: sin
  cambios. El `sub` del JWT sigue siendo el admin real y el claim `imp` el
  del usuario impersonado; este release no altera ese contrato.
· app/api/v1/auth.py, app/schemas/auth.py, app/services/auth_service.py:
  0 cambios. No se tocó la emisión de tokens ni sus claims.
· El resto de los guards de app/deps.py: 0 cambios. Se AÑADIÓ un helper
  (resolve_effective_tenant_role) y un auxiliar; no se modificó
  get_current_user, get_current_membership, require_role ni
  require_platform_admin.
· Rutas de navegación del dashboard: 0 cambios. Sólo se reorganizó el orden
  del item "API Docs" dentro del sidebar y se añadieron los dos
  encabezados de sección. Ninguna URL cambió.
· Los estilos (app/static/css/*): 0 cambios. Los encabezados usan el `<h4>`
  ya estilizado del sidebar. La UI sigue sobria, sin colores nuevos.
· Hero Showcase (app/static/img/hero/, hero_showcase.js, autoplay 3000 ms,
  8 tabs ARIA): 0 cambios. No se tocó la home ni sus assets.
· Tareas Celery / Worker: 0 cambios. Ninguna tarea toca membresías, roles ni
  el sidebar.
· Variables de entorno / secrets: 0 cambios.
· Documentos V2.001-V2.012: intactos.
· No se ejecutó ningún DROP de tabla ni de columna en ninguna DB.
· No se usó git reset --hard ni git push --force.
· app/templates/dashboard/pipeline.html: NO se borró (sigue huérfano, no lo
  renderiza ninguna ruta). En este entorno no se pueden eliminar archivos.

--------------------------------------------------------------------------------
4. REQUERIMIENTOS DE DESPLIEGUE
--------------------------------------------------------------------------------

· REQUIERE CAMBIAR EL WORKER: NO.
  Ninguna tarea Celery cambió, ninguna toca `tenant_memberships`, `users` ni
  el sidebar. El Worker puede seguir corriendo sin reiniciar y sin recrear:
  al reiniciar toma el código nuevo sin ninguna acción por su parte.
  (Comparación con V2.012: tampoco requería cambiar el Worker.)

· BASE DE DATOS
  · Ninguna migración. La cadena de Alembic no se toca y sigue bloqueada en
    la misma revisión que documenta V2.012 §7.1 (pendiente heredado).
  · NO se requiere ninguna intervención manual en la DB.
  · NO se requiere restore ni backup: no hay DROP, ni borrado de filas, ni
    recreación de ningún TYPE.

· ARCHIVOS ESTÁTICOS
  · app.js cambia. El CDN lo sirve con versionado por query string en el
    HTML (/?v=...), así que el navegador toma la versión nueva en la
    primera carga tras el deploy. No hay que purgar caché a mano.
  · El HTML del dashboard se genera en el servidor: el sidebar nuevo llega
    con la primera respuesta 200 tras el deploy.

· SECRETOS / ENV
  · Sin cambios.

· ROLLBACK
  · git revert <commit> + push normal a main. El orden de revert es el
    inverso al de aplicación:
      d7b5e4d → b4d483d → 0a0e2f0 → cc44b69
  · Notas:
    - Revertir d7b5e4d (test) no tiene efecto funcional: sólo devuelve la
      suite al estado rojo de antes.
    - Revertir b4d483d (tests) no tiene efecto funcional.
    - Revertir 0a0e2f0 (servidor) hace que /admin/ai y
      /dashboard/admin-observability vuelvan a rechazar al dueño del tenant
      (302 admin_forbidden), aunque el menú siga visible. Es el estado
      previo, no un estado roto nuevo.
    - Revertir cc44b69 (cliente) deja el sidebar como estaba: los menús
      vuelven a quedar ocultos para todos.

--------------------------------------------------------------------------------
5. PROCEDIMIENTO DE PRUEBA RECOMENDADO
--------------------------------------------------------------------------------

VERIFICACIÓN AUTOMÁTICA (una orden):
  $ python -m pytest tests/test_v2_013_admin_menu_roles.py -q
  Esperado: 32 passed.

  $ python -m pytest tests/test_v2_012_ui_and_permissions.py \
      tests/test_v2_013_admin_menu_roles.py \
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
  Esperado: 346 tests, 0 fallos.

Comprobaciones manuales equivalentes:

5.1) MENÚ "ADMINISTRACIÓN" (dueño o admin del negocio)
  1. Iniciar sesión con la cuenta que administra el negocio.
  2. En el sidebar, dentro de "Avanzado", debe aparecer el encabezado
     "ADMINISTRACIÓN" y debajo los items "🛡️ Admin IA" y "📊 Observabilidad".
  3. "🛡️ Admin IA" debe abrir /admin/ai y MOSTRAR la página (no redirigir).
  4. "📊 Observabilidad" debe abrir /dashboard/admin-observability y
     mostrar la página.

5.2) MENÚ "SUPER ADMIN" (superusuario de plataforma)
  1. Iniciar sesión con la cuenta superadmin.
  2. Debe aparecer el encabezado "SUPER ADMIN" y debajo
     "👑 Panel de plataforma".
  3. Debe abrir /admin/superadmin y mostrar el panel.
  4. Con una cuenta normal (owner o admin) el encabezado NO debe aparecer.

5.3) QUIENES NO DEBEN VERLOS
  1. Entrar con una cuenta de empleado (staff) o de solo lectura (viewer).
  2. No debe aparecer ni el encabezado "ADMINISTRACIÓN" ni el "SUPER ADMIN".
  3. Si se escribe la URL a mano (/admin/ai), debe redirigir a
     /dashboard?reason=admin_forbidden.

5.4) REGRESIONES
  1. El resto del menú debe seguir igual: "Negocio", "Gestión interna" y
     "Avanzado" con sus items.
  2. "API Docs" debe seguir visible para todos y abrir en pestaña nueva.
  3. Al hacer clic en cualquier item, el resaltado del item activo debe
     seguir funcionando.
  4. El banner de impersonación (superusuario impersonando a un usuario)
     debe aparecer ahora con el nombre del usuario impersonado.

--------------------------------------------------------------------------------
6. TRAZABILIDAD
--------------------------------------------------------------------------------

Defecto reportado                        Commit     Prueba de regresión
------------------------------------------------------------------------------
Menú "Administración" invisible al       cc44b69    test_sidebar_tiene_la_seccion_
dueño del tenant                                   administracion
                                                    test_sidebar_tiene_la_seccion_
                                                    super_admin
                                                    test_items_de_administracion_
                                                    conservan_su_gate
                                                    test_el_guard_usa_el_rol_de_la_
                                                    membresia_del_tenant
                                                    test_el_dueno_con_default_role_
                                                    staff_resuelve_owner
                                                    test_admin_ai_es_accesible_para_
                                                    el_dueno_del_tenant
                                                    test_admin_ai_bloquea_al_empleado
Menú "SUPER ADMIN" invisible             cc44b69    test_item_superadmin_conserva_
(claim is_superuser ilegible)                     su_gate
                                                    test_app_js_expone_el_decoder_jwt
                                                    test_el_decoder_jwt_restaura_el_
                                                    padding_base64url
                                                    test_superadmin_abre_para_un_
                                                    superusuario
                                                    test_superadmin_bloquea_a_un_
                                                    admin_normal
302 admin_forbidden al dueño del          0a0e2f0    test_main_ya_no_autoriza_con_
tenant (mismo criterio, lado servidor)              default_role
                                                    test_los_guards_de_administracion_
                                                    usan_el_rol_de_membresia
                                                    test_el_guard_de_superadmin_sigue_
                                                    exigiendo_superuser
                                                    test_el_admin_de_tenant_resuelve_
                                                    admin
                                                    test_el_empleado_no_califica
                                                    test_el_tenant_activo_manda_sobre_
                                                    las_demas_membresias
                                                    test_el_flag_is_owner_gana_al_rol_
                                                    de_membresia
                                                    test_la_membresia_inactiva_no_
                                                    habilita_nada
                                                    test_sin_membresia_se_usa_el_claim_
                                                    del_jwt
                                                    test_observability_es_accesible_
                                                    para_el_admin_del_tenant
                                                    test_observability_bloquea_al_
                                                    lector
Banner de impersonación nunca visible    cc44b69    test_el_banner_de_impersonacion_
(base64url sin padding)                              usa_el_decoder_con_padding
El guard borraba el menú del DOM          cc44b69    test_el_guard_ya_no_elimina_los_
                                                    items_del_dom
Expectativa del layout default obsoleta  d7b5e4d    test_default_layout_when_no_saved
                                                    (tests/test_dashboard_layout.py)

--------------------------------------------------------------------------------
7. LÍMITES DE LA VERIFICACIÓN
--------------------------------------------------------------------------------

7.1) LA CADENA DE ALEMBIC DE PRODUCCIÓN SIGUE SIN AVANZAR
  Pendiente heredado de V2.012 §7.1, sin cambios en este release: sigue
  bloqueada en una revisión anterior por una migración que falla sobre los
  datos reales. No se pudo leer el log de Railway (el dashboard abre un
  diálogo de login y no hay CLI ni token en este entorno). No bloquea este
  release: no hay migraciones nuevas y `scripts/reconcile_schema.py` se
  ejecuta siempre en el entrypoint.

7.2) LA CUENTA REAL DEL USUARIO NO SE PUDO ABRIR EN EL NAVEGADOR
  En este entorno no hay sesión de WowHub abierta en el navegador del
  Chat (la pestaña tenía un login de Google), así que no se pudo entrar con
  la cuenta real del usuario. Para no dejar la comprobación sin hacer, se
  construyó un banco local que ejecuta el app.js REAL desplegado y el
  HTML REAL desplegado con una sesión sintética por rol: el resultado de
  esa verificación está en la sección 8. La inspección visual con la
  cuenta real queda como paso manual 5.1 y 5.2.

7.3) EL ROL REAL DE LA CUENTA DEL USUARIO NO SE PUDO CONFIRMAR EN LA DB
  La corrección deja de depender de `users.default_role` y pasa a leer
  `tenant_memberships.role`. Si alguna cuenta de la plataforma tuviera el
  rol mal cargado en su membresía (por ejemplo un owner con role=staff),
  el menú seguiría sin aparecerle: eso ya no es un defecto del código sino
  del dato, y se corrige en la fila de la membresía.

7.4) SUITE COMPLETA DEL REPO
  La suite completa del repo excede el timeout de 600 s de este entorno.
  Se validó por el conjunto crítico de 346 tests (sección 5), que incluye
  los 32 tests nuevos, los 33 de V2.012 y los de rutas de dashboard, RBAC,
  auth, tenants, deriva de esquema, labels de enums, HU_50-65 y fixes de
  deprecación.

7.5) LOS 22 SCRIPTS DE AUDITORÍA UNTRACKED EN LA RAÍZ DEL REPO
  Pendiente heredado de V2.012 §7.5, sin cambios: los scripts `_audit_*`,
  `_verify_*`, `_repro_*` y `_routes_extracted.txt` siguen sin versionar.
  El borrado está bloqueado por la política local de este entorno (el
  lanzador `mavis-trash` no está disponible): hay que borrarlos a mano.
  No forman parte de este release.

--------------------------------------------------------------------------------
8. RESULTADOS DE LA VALIDACIÓN
--------------------------------------------------------------------------------

LOCAL (antes del push):
  · tests/test_v2_013_admin_menu_roles.py  → 32 passed (nuevo)
  · Suite crítica completa (346 tests)     → 341 passed, 5 skipped,
                                             0 fallos (6m27s)
                                             (el único fallo que apareció
                                             en la primera corrida,
                                             test_default_layout_when_no_
                                             saved, era preexistente y se
                                             corrigió en d7b5e4d)
  · py_compile sobre app/deps.py y app/main.py → OK
  · Parseo Jinja de los 10 templates del dashboard → OK
  · Balance de llaves/paréntesis de app.js y de los 4 bloques <script>
    inline del sidebar → OK (comparado contra los originales de HEAD con el
    mismo verificador: idéntico)
  · alembic heads → una sola head: 2026_10_24_fix_rbac_id_type (sin cambios)

ONLINE (post-deploy, Railway):
  Script de verificación propio contra el sitio desplegado: 29 OK / 0 FAIL.

  · app.js desplegado (200):
      - trae `const Jwt = {`
      - restaura el padding base64url (`while (b64.length % 4 !== 0)`)
      - exporta `Jwt` en `window.WH`
  · HTML del dashboard desplegado (GET /dashboard/marketplace/, 200):
      - existe el encabezado "Administración" con gate owner,admin y oculto
      - existe el encabezado "SUPER ADMIN" con gate superuser y oculto
      - "Admin IA" (/admin/ai), "Observabilidad"
        (/dashboard/admin-observability) y "Panel de plataforma"
        (/admin/superadmin) presentes, con su gate y ocultos
      - "API Docs" queda antes de los dos encabezados con gate
      - el guard servido NO llama `el.remove()`; usa `tenant.role` /
        `tenant.is_owner` y `WH.Jwt`
  · Rutas: /admin/ai, /dashboard/admin-observability y /admin/superadmin
    responden (no 404 ni 500); /health 200; /openapi.json 200.

VERIFICACIÓN EN NAVEGADOR REAL (bank local, app.js y HTML desplegados):
  Se construyó un banco local que carga el app.js y el sidebar REALES
  desplegados, con una sesión sintética por rol, y se leyó el texto
  visible del `aside.dash-side` con el navegador:

  · owner   → "ADMINISTRACIÓN / Admin IA / Observabilidad" SÍ aparece;
               "SUPER ADMIN" NO aparece.
               (La sesión sintética tiene default_role = "staff": es
               exactamente el caso que antes ocultaba el menú.)
  · staff   → NO aparece "ADMINISTRACIÓN" ni "SUPER ADMIN".
  · super   → aparecen AMBAS: "ADMINISTRACIÓN / Admin IA / Observabilidad"
               y "SUPER ADMIN / Panel de plataforma".

  Es decir: el menú se muestra para el rol que corresponde, y sólo para
  él, con el código ya desplegado en producción.
