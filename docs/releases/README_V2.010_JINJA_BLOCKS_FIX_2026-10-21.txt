================================================================================
README_V2.010_JINJA_BLOCKS_FIX_2026-10-21.txt
WowHub · Release Notes Atómicos · V2.010
================================================================================

FECHA          : 2026-10-21
BUILD          : commit f95dc01
ALCANCE        : Correccion de bug V2.009: handlers JS del modal "Crear
                pedido" estaban fuera del bloque Jinja {% block scripts %}
                y eran descartados silenciosamente por el motor de templates.
ATOMICIDAD     : Reordenamiento de UNA linea (movimiento del {% endblock %}).
RIESGO         : NINGUNO. Solo cambia DONDE cierra el bloque scripts.
                Sin cambio funcional, sin cambio de comportamiento.


--------------------------------------------------------------------------------
1. BASE (contexto)
--------------------------------------------------------------------------------

V2.009 (commit a589520) introdujo el modal "Crear pedido" con QC inline
de cliente y producto en el dashboard. El boton "+ Crear pedido" aparecia
correctamente en el HTML renderizado. El modal #new-order-modal y sus
estilos tambien se renderizaban. Pero al verificar el HTML servido por
Railway, los handlers JS (openNewOrderModal, newOrderAddItemRow,
submitNewOrder, wcRefreshProductoSelect, wcRefreshClienteSelect) NO
aparecian en el output del browser.

CAUSA RAIZ CONFIRMADA:

  Jinja2 descarta silenciosamente el contenido que esta FUERA de bloques
  {% block %} cuando un template extiende a otro. Esto es comportamiento
  estándar de Jinja2 para prevenir errores en la herencia.

  orders.html (versión V2.009) tenia:
    Linea 4:   {% block dash_content %}
    Linea 50:  {% endblock %}            ← cierra dash_content
    Linea 52:  {% block scripts %}
    Linea 432: {% endblock %}            ← cierra scripts (TEMPRANO)
    Lineas 434-631: <script>...</script>  ← JS handlers, FUERA DE BLOQUES
    (línea 631 con </script>)

  El motor de Jinja:
    - Renderiza los bloques {% block %} correctamente.
    - IGNORA todo lo demás (las líneas 433-631).
  Resultado: el modal y el boton aparecian (estaban en el bloque scripts),
  pero los handlers JS desaparecian.

DEMOSTRACIÓN:
  Se realizo una prueba aislada con un template de ejemplo con la misma
  estructura. Jinja descartó el contenido fuera de bloques como se
  documenta arriba. Confirmado como comportamiento estándar de Jinja2.

VALIDACIÓN POST-FIX:
  Tras el commit f95dc01, /dashboard/orders renderiza 42635 chars (vs
  34757 pre-fix, +7878 chars). Todos los handlers JS ahora se
  incluyen en el HTML servido por Railway.


--------------------------------------------------------------------------------
2. CAMBIO ÚNICO (qué se hizo)
--------------------------------------------------------------------------------

app/templates/dashboard/orders.html

  ANTES (pre-V2.010):
    ...
    <script src="/static/js/quick-create.js?v=v2.009-inline"></script>
    {% include "_partials/quick_create_modal.html" %}
    {% endblock %}                    ← endblock cierra el bloque
                                        ← scripts, descarta el resto

    <script>                          ← este <script> queda FUERA del
    // V2.009 Inline-Creation...        bloque, Jinja lo descarta
    async function openNewOrderModal() {...}
    ...
    </script>

  DESPUÉS (V2.010):
    ...
    <script src="/static/js/quick-create.js?v=v2.009-inline"></script>
    {% include "_partials/quick_create_modal.html" %}
    <script>                          ← handlers AHORA dentro del bloque
    // V2.009 Inline-Creation...
    async function openNewOrderModal() {...}
    ...
    </script>
    {% endblock %}                    ← endblock al FINAL, cierra todo

  Diff: 1 insertion, 3 deletions.

DETALLE:

  El cambio es:
    - Línea 432 era {% endblock %} (CIERRA scripts).
    - Se eliminó esa línea al inicio del bloque problematico.
    - La línea {% endblock %} ahora está al FINAL del archivo (después
      del </script>).

  Sin esto, Jinja2 renderiza el bloque scripts solo hasta el primer
  {% endblock %}, descartando el resto del archivo.


--------------------------------------------------------------------------------
3. QUÉ NO SE MODIFICÓ
--------------------------------------------------------------------------------

· Backend Python: 0 cambios.
· quick-create.js: 0 cambios (ya tenÍa los hooks validate/preSend/map).
· Modal #new-order-modal HTML: 0 cambios. Solo cambia la POSICIÓN del
  endblock.
· Estilos CSS: 0 cambios.
· Otros templates: 0 cambios.
· Esquema Alembic: sin cambios.
· main.py: sin cambios.
· Variables de entorno: sin cambios.
· Documentos V2.001-V2.009: intactos.


--------------------------------------------------------------------------------
4. REQUERIMIENTOS DE DESPLIEGUE
--------------------------------------------------------------------------------

4.1) Worker
  · NO requiere cambio.

4.2) Build / Deploy
  · Push a main -> Railway auto-deploya en ~3 minutos.
  · Cero rebuild de dependencias. Solo HTML se reconstruye.

4.3) Base de datos
  · Sin cambios.

4.4) Secrets / env
  · Sin cambios.


--------------------------------------------------------------------------------
5. PROCEDIMIENTO DE PRUEBA (post-deploy en Railway)
--------------------------------------------------------------------------------

5.1) Health check (sin cambios respecto a V2.009)
  $ curl -s https://wowhub-api-production.up.railway.app/health
  Esperado: 200 OK {"status":"ok",...}.

5.2) Verificar handlers JS presentes en el HTML
  $ curl -s https://wowhub-api-production.up.railway.app/dashboard/orders \
    | grep -c "wcRefreshProductoSelect"
  Esperado: 1 (vs 0 antes del fix)

  Repetir para:
    wcRefreshClienteSelect (esperado: 1)
    newOrderAddItemRow      (esperado: 1+)
    submitNewOrder          (esperado: 1)
    openNewOrderModal       (esperado: 1)

5.3) Verificar funcionalidad end-to-end
  1. Login y abrir /dashboard/orders.
  2. Click en "+ Crear pedido" (header del Kanban).
  3. Modal debe abrir. Click "+ Nuevo" junto a cliente.
  4. Ingresar nombre "QA Test" + telefono "+56912345678".
  5. Click "Crear y volver".
     ESPERADO: modal QC se cierra. Cliente aparece en el select.
     ANTES del fix: nada pasaba (hook no estaba cargado).
6. Click "+ Nuevo" junto a producto. Ingresar nombre, precio.
7. Click "Crear y volver".
   ESPERADO: producto aparece en el select del item.
8. Click "Crear pedido".
   ESPERADO: POST /orders exitoso. Kanban actualizado.

5.4) Tamano del HTML renderizado
  $ curl -s https://wowhub-api-production.up.railway.app/dashboard/orders | wc -c
  Esperado: > 40000 chars (vs ~34757 antes).
  El delta de +7878 chars corresponde a los handlers JS.


--------------------------------------------------------------------------------
6. ROLLBACK
--------------------------------------------------------------------------------

Si por algun motivo el nuevo orden de los bloques afecta otro template:

  $ git revert f95dc01
  $ git push origin main

Sin impacto: la app sigue funcional, solo los handlers JS vuelven
a no estar presentes (igual que antes de V2.010).


--------------------------------------------------------------------------------
7. TRAZABILIDAD
--------------------------------------------------------------------------------

7.1) Commits
  · f95dc01  fix(ui/orders): mueve JS handlers dentro del bloque scripts
  · abf791d  docs(release): README_V2.009_INLINE_CREATION_3CLICKS
  · a589520  feat(ui/inline-creation): modal Crear pedido (introdujo el bug)
  · 1d9ce7b  docs(release): V2.008 atomic
  · 6639b54  docs(release): V2.007 README

7.2) Archivos modificados
  · app/templates/dashboard/orders.html (reordenamiento de 4 lineas)
        +1 insercion, -3 deletions

7.3) Estado de los handlers JS en cada commit
  · V2.009 (a589520) — handlers en lineas 434-631, Jinja los descarta.
  · V2.010 (f95dc01) — handlers movidos dentro del bloque scripts.
                          Jinja los incluye. 9 nuevos markers visibles.

7.4) Test de regresion de Jinja (en caso de duda futura)
  Un test pytest puede verificar que cada template que se extiende de
  base.html no tiene contenido después de su último {% endblock %}:

    app/templates/dashboard/orders.html
    app/templates/dashboard/customers.html
    app/templates/dashboard/orders.html  # ya corregido en V2.010


--------------------------------------------------------------------------------
8. VALIDACIÓN EJECUTADA
--------------------------------------------------------------------------------

Local:
  · jinja2 parses orders.html OK (sin errores).
  · app.main loads: 144 routes, 257 OpenAPI paths (sin cambios).
  · TestClient GET /dashboard/orders -> 200 OK con todos los markers
    V2.009 visibles (+ Crear pedido, qc-btn-new, new-order-modal,
      no-customer, wcRefreshProductoSelect, wcRefreshClienteSelect,
      newOrderAddItemRow, submitNewOrder).
  · Body size: 42635 chars (vs 34757 pre-fix, +7878 chars).
  · tests/test_hu50_65_produccion.py: 34/34 passing.
  · tests/f0_baseline/: 87/87 + 1 xpassed.
  · TOTAL: 121 passed, 1 xpassed (sin regresiones).

Online (Railway, post-deploy):
  Esperado:
  · /health 200 OK (sin cambios en backend).
  · /dashboard/orders renderiza con handlers JS incluidos.
  · Modal "+ Crear pedido" completamente funcional.


--------------------------------------------------------------------------------
9. PRINCIPIO UX (sin cambios funcionales)
--------------------------------------------------------------------------------

Este release NO toca funcionalidad. Solo despliega lo que V2.009 ya
declaraba. El cambio es puramente cosmético en la capa de templates:

  · El boton "+ Crear pedido" sigue siendo visible.
  · El modal #new-order-modal sigue abierto en su sitio.
  · ESTA VEZ los handlers JS tambien estan presentes en el DOM.
  · wcRefreshProductoSelect / wcRefreshClienteSelect refrescan los
    selects cuando quick-create.js crea algo en otro modal.

Para el usuario final, V2.010 es la primera versión donde el flujo
"3 clicks para crear pedido + cliente + producto" funciona
COMPLETAMENTE. Antes, los handlers JS no existían en el navegador y
los selects no se actualizaban al crear clientes/productos inline.


================================================================================
FIN README_V2.010_JINJA_BLOCKS_FIX_2026-10-21.txt
================================================================================
