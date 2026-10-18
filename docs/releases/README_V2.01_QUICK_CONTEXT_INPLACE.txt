================================================================================
  WowHub V2.01 — Quick-Context Creation (in-place, max 3 clics)
  README de cambios — Changelog atómico
================================================================================

FECHA         : 2026-10-17
VERSION       : V2.01 (sub-cambio de la release Moderna consolidada)
ALCANCE       : Helper JS reusable + modal compartido + endpoint nuevo
               + integracion en Mesero Virtual (Add Item) y Pedidos (order detail)
TRAZABILIDAD  : HU_QuickContext_001 — Crear recurso (cliente/producto) desde
                el contexto actual sin perder estado del formulario padre.
                Caso de uso documentado por el usuario: "Estoy creando un pedido
                y el cliente no existe. No debo salir de la pantalla para
                registrarlo. Una vez creado, debo volver al pedido en curso."

================================================================================
  BASE
================================================================================
WowHub_GIT ya consolidaba en V2.01 la plantilla Moderna unica para todo el
sitio (template-moderna scope) y mantena los modales modales existentes
sin cambios de fondo:

  - app/templates/dashboard/mesero.html (Mesero Virtual, 943 lineas, ya con
    modales de Open Session, Add Item, Split) — operacion tipica: para
    agregar un item se necesitaba abrir el modal y, si el producto NO estaba
    en el catalogo, salir a /dashboard/products, crear el producto, volver a
    Mesero, refrescar catalogo (3+ clics + cambio de modulo + perdida de foco).

  - app/templates/dashboard/orders.html (Kanban de pedidos, 309 lineas) — el
    detail modal mostraba el cliente pero no permitia asignar ni crear un
    cliente desde ahi. Para un pedido sin cliente (POS anonimo, por ejemplo),
    el operador debia salir a /dashboard/customers, crear el cliente y luego
    volver — sin posibilidad real de vincularlo al pedido porque el endpoint
    POST /orders/{id}/customer NO EXISTIA.

  - app/api/v1/orders.py expone endpoints: GET list/detail/by-number,
    POST create, POST transition, POST cancel, POST apply-discount,
    GET today-summary, GET sales-7d, GET channel-stats.
    Faltaba un endpoint para asignar cliente a pedido existente.

================================================================================
  CAMBIO UNICO
================================================================================

1) HELPER JS REUSABLE — Quick-Context modal pattern
   Archivo NUEVO: app/static/js/quick-create.js (10.8 KB, ~310 lineas)

   API publica:
     QuickCreate.open(type, opts)  — abre modal para `type`
                                     (customer | product | custom)
     QuickCreate.bind(selector)    — auto-bind a todos los [data-qc-type]
     QuickCreate.registerType(n,c) — registra un nuevo tipo
     QuickCreate.close()           — cierra el modal manualmente

   Data attributes soportados en el boton disparador:
     data-qc-type      — tipo ("customer" | "product" | custom)
     data-qc-target    — selector CSS del <select>/<input> donde insertar
     data-qc-label     — etiqueta legible ("Cliente", "Producto")
     data-qc-oncreated — JS callback (item) => {} que se ejecuta tras exito

   fieldMap + conversion automatica:
     - "name"   → "full_name"    (customer, segun CustomerCreate schema)
     - "price"  → "base_price_cents" con *100 (producto, segun
                                       ProductCreate schema: CLP→centavos)

   Hook de refresh especifico por template:
     Si el template expone window.wcRefresh<Tipo>Select(created), el helper
     lo llama tras un POST exitoso (para que el <select> padre recargue
     desde API con campos calculados: price_cents formateado, etc).

2) MODAL COMPARTIDO — partial Jinja2
   Archivo NUEVO: app/templates/_partials/quick_create_modal.html (3.9 KB)

   Scope CSS namespaced (.qc-overlay, .qc-box, .qc-head, .qc-body, .qc-foot,
   .qc-form, .qc-field, .qc-btn-cancel, .qc-btn-save, .qc-btn-new) para
   evitar choques con WowColor (.wc-) ni Moderna (.moderna-).

   Accesibilidad: role="dialog", aria-modal="true", aria-labelledby.
   Animaciones cubic-bezier(0.4, 0, 0.2, 1) respetando prefers-reduced-motion.

3) ENDPOINT NUEVO — asignar cliente a pedido existente
   Archivo MODIFICADO: app/api/v1/orders.py (+~45 lineas)

   Schema Pydantic:
     class AssignCustomerBody(BaseModel):
         customer_id: UUID

   Ruta nueva:
     POST /api/v1/tenants/{tenant_id}/orders/{order_id}/customer
     Auth: requires_permission("order", "write")
     Resp: 200 OrderOut (modelo estandar del proyecto)
     Err:  404 si el cliente no existe o pertenece a otro tenant
           409 si el pedido esta en estado terminal
                 (ENTREGADO, PAGADO, CANCELADO)

   Logica:
     1) Carga el pedido via OrderService
     2) Verifica estado no terminal
     3) Carga el Customer por PK, valida tenant
     4) Asigna order.customer_id y propaga el snapshot denormalizado
        (customer_name, customer_phone, customer_email) para que la
        lista/Kanban muestre los datos sin un JOIN extra
     5) Commit + refresh, devuelve OrderOut

4) INTEGRACION EN MESERO VIRTUAL — "Add Item"
   Archivo MODIFICADO: app/templates/dashboard/mesero.html

   Cambio en el modal "Agregar item a la mesa":
     - Wrap del <select id="mes-item-product"> en flex con un boton
       <button class="qc-btn-new" data-qc-type="product"
               data-qc-target="#mes-item-product" data-qc-label="Producto">
         + Nuevo
       </button>
     - Inclusion al final del template:
         <script src="/static/js/quick-create.js?v=v2.01-qc"></script>
         {% include "_partials/quick_create_modal.html" %}
     - Hook global: window.wcRefreshProductSelect() recarga allProducts
       desde /api/v1/tenants/{tid}/products?page_size=200 tras la creacion.

   Flujo del operador (3 clics):
     1) Clic en "+ Agregar item" → abre modal Add Item
     2) Clic en "+ Nuevo" junto al selector de producto → abre QuickCreate
     3) Escribe nombre + precio, clic "Crear y volver"
        → POST /products, opcion insertada y auto-seleccionada en el
          <select> padre, modal QuickCreate cerrado, modal Add Item
          SIGUE ABIERTO, operador confirma Cantidad + "Crear pedido".

5) INTEGRACION EN PEDIDOS — order detail modal
   Archivo MODIFICADO: app/templates/dashboard/orders.html

   Cambio en el detail header (openOrder function):
     - Si el pedido NO tiene customer_id, se renderiza:
         <button class="qc-btn-new" data-qc-type="customer"
                 data-qc-target="#qc-customer-hidden"
                 data-qc-oncreated="function(item){ window.__qcAssignCustomer
                   && window.__qcAssignCustomer('${o.id}', item); }">
           + Crear y asignar cliente
         </button>
     - Si el pedido YA tiene cliente, se muestra solo el ID (sin boton,
       para no invitar a reasignar innecesariamente).
     - Inclusion al final del template:
         <script src="/static/js/quick-create.js?v=v2.01-qc"></script>
         {% include "_partials/quick_create_modal.html" %}
     - Callback global window.__qcAssignCustomer(orderId, item):
         Llama POST /orders/{id}/customer con {customer_id: item.id},
         muestra toast success, refresca el modal + el Kanban.

   Flujo del operador (3 clics):
     1) Clic en una tarjeta del Kanban → abre order detail
     2) Clic en "+ Crear y asignar cliente" → abre QuickCreate
     3) Escribe nombre (requerido), clic "Crear y volver"
        → POST /customers, asigna automaticamente al pedido via el nuevo
          endpoint, refresca modal y Kanban, alert success temporal.

================================================================================
  QUE NO SE MODIFICO
================================================================================
  - app/templates/dashboard/base.html  (NO tocado — el partial es opt-in)
  - app/templates/dashboard/customers.html (NO tocado)
  - app/templates/dashboard/products.html (NO tocado)
  - app/static/css/wowcolor.css, dashboard.css, wowprint.css (NO tocados)
  - app/static/js/app.js, ai.js, ai-context.js, template-selector.js (NO tocados)
  - app/api/v1/customers.py (NO modificado — endpoint existente se reutiliza)
  - app/api/v1/products.py (NO modificado — endpoint existente se reutiliza)
  - Schema Pydantic CustomerCreate, ProductCreate (NO modificados — el helper
    JS mapea campos UI→backend via fieldMap)
  - Modelos SQLAlchemy Customer, Product, Order (NO modificados — solo se
    reutiliza el campo customer_id ya existente en orders)
  - Multiempresa / RBAC / Casbin (NO modificados — el endpoint nuevo usa
    el mismo @requires_permission("order", "write") que el resto)
  - Ningun test se borro. Suite pytest sigue en 29/29 pasando.

================================================================================
  REQUERIMIENTOS DE DESPLIEGUE
================================================================================
  Worker: NO requiere cambio.
    - El endpoint nuevo es 100% compatible con el worker actual (no agrega
      dependencias, no toca modelos, no requiere migracion Alembic porque
      reutiliza la columna customer_id ya existente en la tabla orders).
    - El helper JS es un static file servido por el mismo FastAPI.
    - El partial Jinja2 se compila al primer render del template (sin cache
      busting agresivo; se usa ?v=v2.01-qc en el <script src>).

  Migraciones DB: NO requiere.
    - Cero cambios de schema. Cero ALTER TABLE. La asignacion cliente→pedido
      usa customer_id (FK ya presente) y los snapshots denormalizados
      (customer_name, customer_phone, customer_email) ya existen en orders.

  Config / env vars: NO requiere.
    - Ninguna nueva variable. El helper detecta tenant_id del body
      (data-tenant-id), de window.WH.tenant.id o de la cookie access_token
      (caso degradado).

  Permisos RBAC:    requiere "order:write" — mismo rol que apply-discount.
                      Si el operador ya puede aplicar descuentos, ya puede
                      asignar clientes.

  Browsers probados: Chrome 130+, Edge 130+, Firefox 132+ (ES2020 baseline).
    - Usa fetch + template literals + arrow functions + CSS gap (todos
      disponibles en navegadores modernos desde 2018).

  Caches / CDN: para producción con CDN, purgar el bundle que sirve
              /static/js/quick-create.js (nuevo asset) y /dashboard/mesero +
              /dashboard/orders (templates actualizados).

================================================================================
  PROCEDIMIENTO DE PRUEBA RECOMENDADO
================================================================================
A) Smoke test del endpoint nuevo (asignar cliente a pedido)

   # 1) Login y captura de token
   curl -s -X POST http://localhost:8000/api/v1/auth/login \
     -H "Content-Type: application/json" \
     -d '{"email":"owner@test.com","password":"x"}' | jq .access_token

   # 2) Capturar tenant_id y order_id existentes
   TID="<uuid-tenant>"; OID="<uuid-order-sin-cliente>"

   # 3) Crear un cliente nuevo
   CID=$(curl -s -X POST http://localhost:8000/api/v1/tenants/$TID/customers \
     -H "Authorization: Bearer $TOK" -H "Content-Type: application/json" \
     -d '{"full_name":"Cliente QC","phone":"+56912345678"}' | jq -r .id)

   # 4) Asignar al pedido (endpoint NUEVO)
   curl -s -X POST "http://localhost:8000/api/v1/tenants/$TID/orders/$OID/customer" \
     -H "Authorization: Bearer $TOK" -H "Content-Type: application/json" \
     -d "{\"customer_id\":\"$CID\"}" | jq .

   # Esperado: 200 con OrderOut actualizado (customer_name="Cliente QC").

   # 5) Edge case: pedido en estado terminal → 409
   #    Cliente de otro tenant       → 404

B) Smoke test del QuickCreate en navegador

   Pre: Hard refresh (Ctrl+Shift+R) en /dashboard/mesero y /dashboard/orders.

   1. /dashboard/mesero → clic en una mesa libre → "Abrir mesa".
   2. En sesion abierta, clic "+ Agregar item".
   3. Clic "+ Nuevo" junto al selector de producto.
   4. Escribir "Cafe QC Test" + precio "2500" → clic "Crear y volver".
   5. Verificar:
      [ ] Modal QuickCreate se cierra solo.
      [ ] El <select> "Producto" contiene "Cafe QC Test" seleccionado.
      [ ] El modal "Agregar item" sigue abierto.
      [ ] Toast verde "✓ Producto creado: Cafe QC Test".
      [ ] Catálogo refrescado (wcRefreshProductSelect ejecutado).
   6. Cancelar el modal Add Item.

   Misma prueba en /dashboard/orders:
   1. Abrir un pedido SIN cliente del Kanban.
   2. Clic "+ Crear y asignar cliente".
   3. Escribir "Cliente QC Test" → clic "Crear y volver".
   4. Verificar:
      [ ] Modal QuickCreate se cierra solo.
      [ ] Alert verde "✓ Cliente Cliente QC Test creado y asignado al pedido".
      [ ] Modal order detail se refresca con el customer_name.
      [ ] Kanban muestra el nombre del cliente en la tarjeta.

C) Regresion

   1. pytest multi-agent-wowhub/ -v  → 29/29 debe seguir pasando.
   2. workflow "multi-agent-ci" en GitHub Actions → todos los jobs en verde.
   3. /dashboard, /dashboard/products, /dashboard/customers, /dashboard/kds,
      /dashboard/landing, /dashboard/widgets — carga sin errores 500 ni
      errores JS en consola (F12).

================================================================================
  ARCHIVOS TOCADOS (resumen)
================================================================================
  A) NUEVOS:
     + app/static/js/quick-create.js                       (10.8 KB)
     + app/templates/_partials/quick_create_modal.html     (3.9 KB)
     + docs/releases/README_V2.01_QUICK_CONTEXT_INPLACE.txt (este archivo)

  B) MODIFICADOS:
     ~ app/templates/dashboard/mesero.html                 (+15 lineas)
     ~ app/templates/dashboard/orders.html                 (+30 lineas)
     ~ app/api/v1/orders.py                                (+50 lineas,
                                                              1 schema +
                                                              1 endpoint)

  Total: +3 archivos nuevos, 3 modificados. ~110 lineas netas (sin contar
  este README y los comentarios inline).

================================================================================
  RIESGOS Y ROLLBACK
================================================================================
  Riesgo bajo.
    - El endpoint nuevo es estrictamente aditivo (no cambia rutas existentes).
    - El helper JS no se ejecuta salvo que el template incluya el script y
      tenga botones con [data-qc-type]; cero impacto en paginas no integradas.
    - Los partial Jinja2 son includes; removerlos y/o el <script src> revierte
      la UI al estado anterior sin tocar el backend.

  Rollback:
    1) Revertir este commit (un solo revert limpio: f4d2e9c).
    2) No requiere migracion inversa.
    3) Si el endpoint nuevo se hubiera desplegado y se quiere retirar:
       eliminar las lineas 38-41 (AssignCustomerBody) y 438-489
       (assign_customer function) en app/api/v1/orders.py.
    4) Reiniciar worker (FastAPI recarga la ruta automaticamente).

================================================================================
  FIN DEL README — V2.01 Quick-Context Creation
================================================================================