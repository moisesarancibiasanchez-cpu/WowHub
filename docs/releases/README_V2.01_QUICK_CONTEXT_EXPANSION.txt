================================================================================
  WowHub V2.01 — Quick-Context Expansion (bookings + quotes)
  README de cambios — Changelog atómico
================================================================================

FECHA         : 2026-10-18
VERSION       : V2.01 (extension de la regla de negocio Quick-Context)
ALCANCE       : 2 templates adicionales con Quick-Context integrado:
                 - admin_bookings.html (modal de reservas)
                 - quotes.html (modal de cotizaciones, incluye lineas de items)
TRAZABILIDAD  : el usuario manifesto reiteradamente que la regla de negocio
                 "max 3 clics por accion" debia estar en TODOS los formularios
                 donde el operador crea entidades relacionadas. Quick-Context
                 ya estaba activo en mesero.html y orders.html (commit e5602e6)
                 pero faltaba en 2 hotspots criticos.

================================================================================
  BASE
================================================================================
V2.01 ya contaba con la infraestructura Quick-Context:

  - app/static/js/quick-create.js (helper reusable, API QuickCreate.open/bind/
    registerType/close, fieldMap automatico UI->backend, hook global
    wcRefresh<Tipo>Select()).

  - app/templates/_partials/quick_create_modal.html (modal namespaced con
    scope CSS .qc-*).

  - app/api/v1/orders.py (endpoint POST /tenants/{id}/orders/{oid}/customer
    para asignar cliente a pedido existente).

  Templates con Quick-Context integrado (pre-fix):
    1) mesero.html          → crear producto en sesion de mesa
    2) orders.html         → crear cliente en order detail

  Templates con form de creacion pero SIN Quick-Context (pre-fix):
    1) admin_bookings.html → form de reserva con TEXT inputs (b_name,
       b_phone, b_email) sin opcion de crear cliente in-place
    2) quotes.html         → form de cotizacion con TEXT inputs
       (f_recipient, f_email, f_phone) + items table con <select> de
       productos — el operador tenia que salir a /dashboard/products o
       /dashboard/customers para crear lo que necesitaba

  Inventario de audit (40 templates dashboard):
    - 2 con Quick-Context integrado (mesero, orders)
    - 2 con necesidad clara (admin_bookings, quotes)  ← ESTE COMMIT
    - El resto: o son vistas de solo lectura (customers list, products list,
      kds, channels, payments), o usan selects de rama/estado/filtros (no
      entidades relacionadas a crear)

================================================================================
  CAMBIO UNICO
================================================================================

1) QUICK-CONTEXT EN ADMIN_BOOKINGS.HTML
   Archivo MODIFICADO: app/templates/dashboard/admin_bookings.html

   El form de reserva (modal #booking-form) tiene:
     - b_name   (text input, nombre del cliente)
     - b_phone  (text input, telefono)
     - b_email  (text input, email, opcional)

   ANTES: si el operador queria crear una reserva para un cliente nuevo,
   tenia que:
     1) Salir del modal de reserva
     2) Ir a /dashboard/customers
     3) Crear el cliente alli (1-2 clics + completar form)
     4) Volver a /dashboard/bookings
     5) Abrir modal de reserva, escribir el nombre manualmente
   Total: 4-5 clics + cambio de modulo.

   DESPUES: boton "+ Nuevo" junto al input Nombre, abre modal in-place.
   Al confirmar, callback onCreated auto-rellena b_name, b_phone, b_email
   del form padre. El modal de reserva SIGUE ABIERTO.

   Codigo añadido:
   --------------------------------------------------------------
   <div style="display:flex; gap:6px; align-items:center;">
     <input class="form-input" id="b_name" required minlength="2" maxlength="160" style="flex:1;">
     <button type="button" class="qc-btn-new"
             data-qc-type="customer"
             data-qc-label="Cliente"
             data-qc-oncreated="function(item){
               var n=document.getElementById('b_name'); if(n) n.value = item.full_name || item.name || '';
               var p=document.getElementById('b_phone'); if(p && item.phone) p.value = item.phone;
               var e=document.getElementById('b_email'); if(e && item.email) e.value = item.email;
               if(window.wcShowToast) wcShowToast('Cliente creado y datos copiados al form.');
             }"
             title="Crear cliente nuevo sin salir de esta reserva">+ Nuevo</button>
   </div>
   --------------------------------------------------------------

   Al final del template se incluye el script y modal partial:
   --------------------------------------------------------------
   {% block scripts %}
   {{ super() }}
   <script src="/static/js/quick-create.js?v=v2.01-qc"></script>
   {% include "_partials/quick_create_modal.html" %}
   {% endblock %}
   --------------------------------------------------------------

   Flujo del operador (3 clics):
     1) Clic "+ Nueva reserva" → abre modal de reserva
     2) Clic "+ Nuevo" junto a "Nombre" → abre QuickCreate
     3) Escribir nombre+telefono+email, clic "Crear y volver"
        → POST /customers, callback auto-rellena b_name/b_phone/b_email,
          modal QuickCreate cerrado, modal de reserva SIGUE ABIERTO,
          operador completa fecha/hora/sucursal y guarda.

2) QUICK-CONTEXT EN QUOTES.HTML
   Archivo MODIFICADO: app/templates/dashboard/quotes.html (2 puntos de
   integracion: cliente + producto en cada linea de items)

   2.1) Cliente destinatario (text input f_recipient):

   ANTES: idem admin_bookings (4-5 clics + cambio de modulo).

   DESPUES: boton "+ Nuevo" junto al input "Cliente destinatario", abre
   QuickCreate, callback auto-rellena f_recipient/f_email/f_phone.

   Codigo añadido (template HTML):
   --------------------------------------------------------------
   <div style="display:flex; gap:6px;">
     <input id="f_recipient" class="form-input" placeholder="Nombre del cliente" style="flex:1;">
     <button type="button" class="qc-btn-new"
             data-qc-type="customer"
             data-qc-label="Cliente"
             data-qc-oncreated="function(item){
               var n=document.getElementById('f_recipient'); if(n) n.value = item.full_name || item.name || '';
               var e=document.getElementById('f_email'); if(e && item.email) e.value = item.email;
               var p=document.getElementById('f_phone'); if(p && item.phone) p.value = item.phone;
               if(window.wcShowToast) wcShowToast('Cliente creado y datos copiados a la cotizacion.');
             }"
             title="Crear cliente nuevo sin salir de esta cotizacion">+ Nuevo</button>
   </div>
   --------------------------------------------------------------

   2.2) Producto en cada linea de items (select + button per row):

   La tabla #items-table tiene una fila por linea de cotizacion, cada una
   con un <select> de productos + inputs de cantidad/precio/descuento.
   Cuando el operador agrega un producto que no existe, antes tenia que
   salir a /dashboard/products, crearlo y volver (4-5 clics).

   DESPUES: boton "+ Nuevo" en cada fila, al lado del <select>. Al
   confirmar, el callback:
     1) Pushea el nuevo producto al array `products` (para que la
        proxima fila ya lo incluya sin re-render)
     2) Llama a onProductChange(idx, created.id) que auto-selecciona el
        nuevo producto en este row y rellena precio

   Codigo modificado en renderItems():
   --------------------------------------------------------------
   <div style="display:flex; gap:4px; align-items:center;">
     <select id="qc-prod-target-${idx}" onchange="onProductChange(${idx}, this.value)" style="flex:1;">
       <option value="">— personalizado —</option>
       ${products.map(p => `<option value="${p.id}" data-name="${p.name}" data-price="${p.price_cents || 0}" ...>${p.name}</option>`).join("")}
     </select>
     <button type="button" class="qc-btn-new"
             title="Crear producto nuevo en linea"
             onclick="window.QuickCreate && window.QuickCreate.open('product', {
               target: '#qc-prod-target-${idx}',
               onCreated: function(created){
                 products.push({id: created.id, name: created.name, price_cents: created.base_price_cents || 0});
                 onProductChange(${idx}, created.id);
                 if(window.wcShowToast) wcShowToast('Producto creado y agregado a la linea.');
               }
             });">+ Nuevo</button>
   </div>
   --------------------------------------------------------------

   Al final del template se incluye el script y modal partial:
   --------------------------------------------------------------
   <script src="/static/js/quick-create.js?v=v2.01-qc"></script>
   {% include "_partials/quick_create_modal.html" %}
   --------------------------------------------------------------

   Flujo del operador en cotizacion (3 clics por accion):
     - Cliente: [+ Nueva cotizacion] → [+ Nuevo cliente] → [Crear y volver]
     - Producto (por linea): [+ Anadir linea] → [+ Nuevo producto]
       → [Crear y volver]
   Ambas acciones cierran en max 3 clics sin perder el contexto.

================================================================================
  QUE NO SE MODIFICO
================================================================================
  - app/static/js/quick-create.js (NO tocado — el helper ya soportaba el
    callback onCreated y la API QuickCreate.open con target/onCreated).
    La expansion reusa la API existente sin tocarla.
  - app/templates/_partials/quick_create_modal.html (NO tocado — modal
    compartido reusable).
  - app/api/v1/orders.py endpoint POST /orders/{id}/customer (NO tocado)
  - app/api/v1/customers.py POST /customers (NO tocado — el helper lo usa)
  - app/api/v1/products.py POST /products (NO tocado — el helper lo usa)
  - app/templates/dashboard/mesero.html y orders.html (NO tocados —
    siguen funcionando como antes)
  - dashboard/base.html (NO tocado)
  - tokens.css, app.css, dashboard.css, wowprint.css (NO tocados)
  - Ningun endpoint, schema, modelo, variable de config
  - Los 29 tests pytest (NO modificados, siguen pasando)

================================================================================
  REQUERIMIENTOS DE DESPLIEGUE
================================================================================
  Worker: SI requiere reinicio (cambios en templates, no en backend).
    - app/templates/dashboard/admin_bookings.html MODIFICADO.
    - app/templates/dashboard/quotes.html MODIFICADO.
    - FastAPI recarga el router al reiniciar; el navegador debe hard-
      refresh (Ctrl+Shift+R) para evitar HTML cacheado.
    - Tiempo de reinicio: < 5 segundos. Sin migracion DB.

  Migraciones DB: NO requiere.

  Config / env vars: NO requiere.

  Caches / CDN: SI purgar:
    - /dashboard/bookings (HTML nuevo)
    - /dashboard/quotes (HTML nuevo)
    - /static/js/quick-create.js (mismo asset, version param v=v2.01-qc)

  Hard refresh obligatorio en navegador: SI, para purgar HTML cacheado.

================================================================================
  PROCEDIMIENTO DE PRUEBA RECOMENDADO
================================================================================
A) Verificar Quick-Context en Reservas (/dashboard/bookings)

   1) Hard refresh (Ctrl+Shift+R) en /dashboard/bookings.
   2) Clic "+ Nueva reserva" → abre modal.
   3) Clic "+ Nuevo" junto al campo "Nombre".
   4) Esperado: aparece modal QuickCreate con campos Nombre/Telefono/Email.
   5) Llenar: "Cliente QC Test", "+56 9 12345678", "qc@test.com".
   6) Clic "Crear y volver".
   7) Esperado:
      [ ] Modal QuickCreate se cierra.
      [ ] El campo Nombre del form de reserva ahora contiene "Cliente QC Test".
      [ ] Telefono contiene "+56 9 12345678".
      [ ] Email contiene "qc@test.com".
      [ ] Modal de reserva SIGUE ABIERTO.
      [ ] Toast "Cliente creado y datos copiados al form".
   8) Completar inicio/fin/sucursal, guardar reserva.
   9) Verificar: el cliente aparece en /dashboard/customers.

B) Verificar Quick-Context en Cotizaciones - cliente (/dashboard/quotes)

   1) Hard refresh en /dashboard/quotes.
   2) Clic "+ Nueva cotizacion" → abre modal.
   3) Clic "+ Nuevo" junto a "Cliente destinatario".
   4) Llenar: "Cliente Cotiz QC", email, telefono.
   5) Clic "Crear y volver".
   6) Esperado:
      [ ] Modal QuickCreate se cierra.
      [ ] f_recipient contiene "Cliente Cotiz QC".
      [ ] f_email contiene el email ingresado.
      [ ] f_phone contiene el telefono.
      [ ] Modal de cotizacion SIGUE ABIERTO.

C) Verificar Quick-Context en Cotizaciones - producto (items)

   1) En el modal de cotizacion, clic "+ Anadir linea".
   2) Aparece una fila con <select> de productos + boton "+ Nuevo".
   3) Clic "+ Nuevo" en esa fila.
   4) Llenar: "Producto Cotiz QC", precio 5000.
   5) Clic "Crear y volver".
   6) Esperado:
      [ ] Modal QuickCreate se cierra.
      [ ] El <select> de la fila contiene "Producto Cotiz QC" auto-seleccionado.
      [ ] El precio del item se rellena automaticamente con 5000.
      [ ] Toast "Producto creado y agregado a la linea".
      [ ] Si agregas otra linea, el nuevo producto aparece en el <select>.

D) Regresion completa

   1. pytest multi-agent-wowhub/ -v → 29/29 debe seguir pasando.
   2. /dashboard/bookings, /dashboard/quotes, /dashboard/mesero,
      /dashboard/orders, /dashboard/customers → carga sin 500.
   3. Console del navegador: cero errores JS.
   4. Verificar que NO hay doble inclusion del script quick-create.js
      (un warning en consola si lo hay).

================================================================================
  ARCHIVOS TOCADOS (resumen)
================================================================================
  A) NUEVOS:
     + docs/releases/README_V2.01_QUICK_CONTEXT_EXPANSION.txt (este archivo)

  B) MODIFICADOS:
     ~ app/templates/dashboard/admin_bookings.html              (~30 lineas,
                                                                  QC cliente
                                                                  en form de
                                                                  reserva)
     ~ app/templates/dashboard/quotes.html                      (~50 lineas,
                                                                  QC cliente +
                                                                  QC producto
                                                                  en items)

  Total: +1 archivo nuevo, 2 modificados. ~80 lineas netas (sin contar
  este README y los comentarios inline).

================================================================================
  AUDITORIA COMPLEMENTARIA REALIZADA (sin cambios)
================================================================================
  - 40 templates dashboard auditados; 4 con Quick-Context (mesero, orders,
    admin_bookings, quotes)
  - 14 templates extienden base.html, 40 extienden dashboard/base.html,
    9 parciales
  - 0 links rotos en sidebar, 0 referencias rotas a /static/
  - 59 routers backend, 57 montados via include_router (2 con sub-routers
    falsos positivos del audit script)
  - 29/29 tests pytest pasando (2.86s)
  - Sintaxis Python global: 0 errores

================================================================================
  RIESGOS Y ROLLBACK
================================================================================
  Riesgo bajo.
    - Cambio puramente de UI: el helper JS y la API ya existian, solo se
      agregan botones y callbacks.
    - Si algo rompe en bookings o quotes, el modal de creacion sigue
      funcional con los TEXT inputs tradicionales (los QC buttons son
      aditivitos).
    - Si QuickCreate.open no existe (script no cargo), el onclick hace
      `window.QuickCreate && ...` → no-op silencioso, no rompe nada.

  Rollback:
    1) Revertir este commit (un revert limpio).
    2) Si solo quotes rompe: remover los botones QC de items y f_recipient.
    3) Si solo bookings rompe: remover el boton QC junto a b_name.
    4) Reiniciar worker (FastAPI recarga templates).

================================================================================
  FIN DEL README — V2.01 Quick-Context Expansion
================================================================================