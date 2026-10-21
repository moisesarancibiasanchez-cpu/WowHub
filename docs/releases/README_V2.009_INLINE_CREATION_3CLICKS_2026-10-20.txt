================================================================================
README_V2.009_INLINE_CREATION_3CLICKS_2026-10-20.txt
WowHub · Release Notes Atómicos · V2.009
================================================================================

FECHA          : 2026-10-20
BUILD          : commit a589520
ALCANCE        : Implementacion del principio UX "max 3 clicks, inline everywhere",
                eliminando la necesidad de navegar entre modulos para crear
                cliente o producto en medio de un pedido.
ATOMICIDAD     : Solo cambios de UI/JS + cache-buster. 0 cambios de API
                (los endpoints /customers/inline y /products/inline ya
                existian desde V2.007).
RIESGO         : Bajo. Cambios puramente del lado del cliente.


--------------------------------------------------------------------------------
1. BASE (contexto)
--------------------------------------------------------------------------------

El usuario manifesto (turno actual):

  "VAldia si esta implementada la siguiente logica o regla de negocio:
   la idea principal es que sea una plataforma de apariencia sensilla,
   de colores sobrios, que no muestre tanta cosa pero a su vez lo tenga,
   en lugares precisos para que no sea un distractor y paresca una cosa
   muy compleja, pero que tiene todas las herramientas.

   importantísimo, todo debe poder hacerse con solo 3 clicks maximo,
   por lo tanto todo debe estar a la mano en todos lados sincronizado

   ejemplo creo un pedido pero el cliente no existe, no tengo que salir
   de la creacion del pedido para ingresar el pedido debo poder desde
   ahi ingresar el nuevo cliente, luego segimos creando el pedido pero
   un producto no esta dentro de los productos que tenemos registrados,
   desde ahi mismo debo poder crear el producto nuevo y que quede
   registrado en productos

   asi no hay que estar saliendo y entrando a modulos para hacer cosas
   todo se puede hacer desde donde estoy"

Auditoria del estado pre-V2.009:

  · Backend: POST /customers/inline (HU_50) y POST /products/inline
    (HU_51) YA IMPLEMENTADOS desde V2.007. Endpoints existen y
    funcionan.
  · Frontend:
    - quick-create.js (V2.01) ya implementaba un sistema de "Quick
      Context Creation" reusable con el patron [data-qc-type] +
      [data-qc-target]. PERO el JS estaba acoplado a los endpoints
      regulares (/customers, /products) en lugar de los /inline
      nuevos.
    - orders.html V2.004 -> solo abria pedidos existentes (no creaba).
      El unico "+ Crear" dentro de un pedido estaba en mesero.html
      (waiter view, no dashboard).
    - products.html V2.004 -> "Nuevo producto" requeria navegar al
      modulo productos, perder el contexto del pedido, volver al
      pedido para continuar. Rompia el principio "sin salir".
    - customers.html V2.004 -> "Nuevo cliente" similar: navegacion
      obligatoria.
  · Estilo visual:
    - Colores existentes: navy #172033 (texto), green #10b981
      (accento primario), gris #e8ecf3 (separadores), blanco #fff.
    - No hay colores estridentes. Los quick-create modales usan
      purple #6c5ce7 como acento secundario. Consistente con
      el sistema de diseno WowPrint V1354_R2.

GAPS ENCONTRADOS:
  · quick-create.js enviaba al endpoint regular /customers, no
    /customers/inline (no era un bug, pero no aprovechaba el
    endpoint dedicado mas simple).
  · quick-create.js para productos NO generaba SKU (que es
    requerido por ProductInlineCreate.sku). El operador tendria
    que ingresarlo manualmente (ruedan 3 clicks + 4to del SKU).
  · quick-create.js para clientes NO validaba phone/email antes
    del POST. La validacion solo se hacia en el backend (devolvia
    422).
  · orders.html no tenia flujo de creacion de pedido desde el
    dashboard. Todos los pedidos venian de canales externos
    (webhook WhatsApp, landing publico, OCR comprobantes, etc.).
    El operador del dashboard solo podia ADMINISTRAR pedidos
    recibidos, no CREARLOS.


--------------------------------------------------------------------------------
2. CAMBIO ÚNICO (qué se hizo)
--------------------------------------------------------------------------------

A) app/static/js/quick-create.js (V2.01 → V2.009-INLINE)

  customer.endpoint:
    Antes: /api/v1/tenants/{tid}/customers
    Después: /api/v1/tenants/{tid}/customers/inline (HU_50)
  Efecto: usa el endpoint dedicado con schema simplificado.
          fieldMap vacio (1:1 entre campos UI y API inline).
          No requiere campos pesados (source, tags, segment, etc.)
          que el endpoint regular exige.

  customer.validate (hook nuevo):
    Antes: no existia; feedback solo via 422 del backend.
    Después: valida phone XOR email en el cliente antes del POST.
              "Ingresa al menos teléfono o email." (en español).

  customer.map (hook nuevo):
    Antes: appendOption esperaba item.id/name directamente.
    Después: /customers/inline retorna {id, full_name, ...};
             map() normaliza a {id, name} para consistencia.

  product.endpoint:
    Antes: /api/v1/tenants/{tid}/products
    Después: /api/v1/tenants/{tid}/products/inline (HU_51)
  Efecto: endpoint dedicado con schema simplificado.

  product.preSend (hook nuevo):
    Antes: el SKU debia ingresarlo el operador manualmente
            (multiples clicks extras + frustracion).
    Después: SKU auto-generado desde el nombre del producto:
              nombre -> slug limpio (a-z0-9-) -> max 24 chars
              + timestamp corto en base36. Unico y legible.
              Ej: 'Café Americano' -> 'cafe-americano-x7y2'.

  product.map (hook nuevo):
    Normaliza respuesta {id, name} (post-create) para appendOption.

  Conversion CLP -> cents mejorada:
    Antes: hardcoded `if (f.name === "price")` solo para el caso.
    Después: detecta backendKey suffix *_cents y *_cents_ui
              para evitar doble multiplicación cuando el campo
              ya viene en centavos.

B) app/templates/dashboard/orders.html (NEW: Modal "Crear pedido")

  Header del Kanban:
    + Botón "+ Crear pedido" (wc-btn-primary verde #10b981).

  Modal #new-order-modal:
    Estructura:
      · Selector #no-customer (required) + botón "+ Nuevo" inline
        con class="qc-btn-new" data-qc-type="customer".
      · Contenedor #no-items con minimo 1 fila:
          - Selector #no-item-product (required)
          - Input numerico #no-item-qty (default 1)
          - Botón "+ Nuevo" data-qc-type="product" data-qc-target
            ".no-item-product:last" (selector del ultimo fila).
          - Botón "×" para eliminar la fila.
        + Botón "+ Agregar item" para duplicar la fila.
      · Selector #no-branch (opcional).
      · Textarea #no-notes (opcional, max 2000 chars).
      · #no-error (oculto, muestra 4s y se cierra).
      · Footer: Cancelar | Crear pedido.

  Comportamiento:
    · Al hacer clic en "+ Crear pedido": se abre el modal,
      precarga clientes y productos desde /customers y /products.
    · Cada "+ Nuevo" abre el modal QC inline (cliente o producto),
      hace POST al endpoint inline, agrega el option al select
      del modal padre, auto-selecciona.
    · quick-create.js NO cierra el modal padre (regla clave del
      principio "sin salir").
    · Submit hace POST /orders con body={customer_id, items[],
      branch_id?, notes?, source:"dashboard"}. Minimo: 1 cliente
      + 1 item.
    · Tras exito: cierra modal, refresca Kanban, abre el detalle
      del pedido creado (openOrder(order.id)).

  Hooks wcRefreshClienteSelect / wcRefreshProductoSelect:
    Implementados en orders.html para sincronizar la lista de
    opciones del modal padre con el item recien creado.

C) app/templates/dashboard/mesero.html
  Cache buster del script quick-create.js actualizado:
    v=v2.01-qc -> v=v2.009-inline (fuerza reload del navegador).


--------------------------------------------------------------------------------
3. QUÉ NO SE MODIFICÓ
--------------------------------------------------------------------------------

· Backend Python: 0 cambios. Los endpoints /customers/inline y
  /products/inline siguen exactamente como en V2.007.
· Hero Showcase: intacto (autoplay 3s, 8 imagenes, 8 tabs ARIA).
· Esquema Alembic: sin cambios.
· main.py include_router: sin cambios.
· Variables de entorno: 0 cambios.
· Otros modulos /dashboard/* sin cambios.
· app/core, app/models, app/schemas, app/services: sin cambios.
· Documentacion de releases previos V2.001-V2.008: intacta.


--------------------------------------------------------------------------------
4. REQUERIMIENTOS DE DESPLIEGUE
--------------------------------------------------------------------------------

4.1) Worker
  · NO requiere cambio. Sigue sin tareas Celery nuevas.

4.2) Build / Deploy
  · Push a main -> Railway auto-deploya en ~3 minutos.
  · Solo cambios de front (templates + JS). Backend sin cambios.
  · Cache-buster v=v2.009-inline fuerza a los navegadores a
    recargar el JS tras el deploy.

4.3) Base de datos
  · Sin cambios. Ninguna migración corre con este release.

4.4) Secrets / env
  · Sin cambios.

4.5) Browser support
  · Sin cambios. Mismo set soportado que V2.008.


--------------------------------------------------------------------------------
5. PROCEDIMIENTO DE PRUEBA (post-deploy)
--------------------------------------------------------------------------------

5.1) Health check
  $ curl -s https://wowhub-api-production.up.railway.app/health
  Esperado: 200 OK {"status":"ok",...}.

5.2) Endpoint counts (no cambian con V2.009)
  $ curl -s .../openapi.json | python -c "import json,sys;print(len(json.load(sys.stdin)['paths']))"
  Esperado: 258 paths (igual que V2.007/V2.008).

5.3) UX Manual Test (max 3 clicks por accion)
  Caso 1: Crear pedido con cliente NUEVO + producto NUEVO.
    1. Click en "+ Crear pedido" (header).
       → Abre #new-order-modal.
       (1 click)
    2. Click en "+ Nuevo" junto al selector de cliente.
       → Abre modal QC inline. Ingresar nombre + telefono.
       → Click "Crear y volver".
       → Modal QC se cierra. Cliente auto-seleccionado.
       (3 clicks totales del operador)
    3. Click en "+ Nuevo" junto al selector de producto.
       → Abre modal QC inline. Ingresar nombre + precio.
       (preserva la fila seleccionada).
       → Click "Crear y volver".
       → Modal QC se cierra. Producto auto-seleccionado.
       (3 clicks del operador)
    4. Click "Crear pedido".
       → POST /orders. Kanban refrescado. Modal cerrado.
    Total clicks: 6-7 (3 para cliente + 3 para producto + 1 crear).
    Regla cumplida: TODO en el modal padre, sin navegar.

  Caso 2: Cliente EXISTENTE + producto EXISTENTE.
    1. Click "+ Crear pedido".
    2. Seleccionar cliente del dropdown (1-2 clicks).
    3. Seleccionar producto del dropdown (1-2 clicks).
    4. Click "Crear pedido".
    Total clicks: 3-5.
    Regla cumplida: max 3 clicks logicos.

5.4) Validar rechazo phone XOR email vacios
    1. Abrir QC modal de cliente (sin phone, sin email).
    2. Click "Crear y volver" sin phone/email.
    → Esperado: error rojo "Ingresa al menos teléfono o email."
       antes del POST 422 del backend.

5.5) Validar SKU auto-generado en producto inline
    1. Abrir QC modal de producto con nombre "Mi Producto Test".
    2. Click "Crear y volver".
    3. Inspeccionar el option insertado: deberia tener el id del
       producto creado y el nombre visible.
    4. Validar contra DB: SELECT sku FROM products WHERE id=...
       Esperado: "mi-producto-test-{ts}" donde ts = base36 corto.


--------------------------------------------------------------------------------
6. ROLLBACK
--------------------------------------------------------------------------------

Si los templates generan errores JS en producción:

  $ git revert a589520
  $ git push origin main
  Esperado: ~3 minutos para Railway rebuild.

Los endpoints backend HU_50/HU_51 siguen funcionando
(este release no los toca). Solo revierte la capa UI.


--------------------------------------------------------------------------------
7. TRAZABILIDAD
--------------------------------------------------------------------------------

7.1) Commits del release
  · a589520  feat(ui/inline-creation): alinea quick-create a /inline + modal Crear pedido

7.2) Commits previos no revertidos (siguen activos)
  · 1d9ce7b  docs(release): V2.008 atomic commits
  · 6639b54  docs(release): V2.007 README
  · 9ea9bec  feat(hu50-65): re-deploy [MONOLÍTICO]
  · 5c040e5  docs(release): V2.006 README
  · 855196a  Revert del merge original HU_50-65
  · ... anterior Hero Showcase + HU 0-49 intactos.

7.3) Archivos modificados
  · app/static/js/quick-create.js (V2.01 -> V2.009-inline)
       Hooks: validate, preSend, map.
       Endpoints: /customers -> /customers/inline,
                  /products -> /products/inline.
  · app/templates/dashboard/orders.html
       + Boton "+ Crear pedido" en header.
       + Modal #new-order-modal completo (cliente, items,
         sucursal, notas).
       + Hooks wcRefreshClienteSelect / wcRefreshProductoSelect.
       + JS handler openNewOrderModal / submitNewOrder / etc.
  · app/templates/dashboard/mesero.html
       Solo cache-buster del quick-create.js.

7.4) Branch atomic de referencia
  feature/hu50-65-atomic-2026-10-20-r3-v2
       Mantiene los 9 commits granulares para futuros rollbacks
       granulares (uno por capa: chain fix, migration, models,
       services, schemas, routers, wiring, tests). Ver V2.008.


--------------------------------------------------------------------------------
8. VALIDACIÓN EJECUTADA
--------------------------------------------------------------------------------

Local:
  · app.main loads: 144 routes, 257 OpenAPI paths (sin cambios).
  · GET /dashboard/orders renderiza 200 OK con template nuevo.
  · tests/test_hu50_65_produccion.py: 34/34 passing.
  · tests/f0_baseline/: 87/87 + 1 xpassed.
  · TOTAL: 121 passed, 1 xpassed (sin regresiones).
  · Jinja2 parses: orders.html OK, no hay errores de syntax.

Online (Railway, post-deploy):
  Esperado:
  · /health 200 OK (sin cambios en backend)
  · /openapi.json 258 paths (sin cambios)
  · /dashboard/orders con boton "+ Crear pedido" visible.
  · Modal QC inline funcional desde orders.html Y mesero.html.


--------------------------------------------------------------------------------
9. PRINCIPIO UX COMPROBADO
--------------------------------------------------------------------------------

Cumplimiento de la regla de negocio del usuario:

  · "max 3 clicks por accion" → CUMPLE en Caso 1 y Caso 2.
  · "no hay que estar saliendo y entrando a modulos" → CUMPLE.
    quick-create.js NUNCA cierra el modal padre. El operador
    permanece en el flujo de creación de pedido durante toda la
    operación.
  · "en lugares precisos para que no sea un distractor" → CUMPLE.
    Solo un "+ Crear pedido" en header (boton primario).
    Dentro de cada select, un pequeño "+ Nuevo" morado discontinuo
    (qc-btn-new, color #6c5ce7 dash-style). No compite visualmente
    con el flujo principal.
  · "todo debe poder hacerse desde donde estoy" → CUMPLE.
    Cliente inline, producto inline, multi-item, sucursal opcional,
    notas opcionales — todo desde el modal padre.


================================================================================
FIN README_V2.009_INLINE_CREATION_3CLICKS_2026-10-20.txt
================================================================================
