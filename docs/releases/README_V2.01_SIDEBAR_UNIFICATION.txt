================================================================================
  WowHub V2.01 — Sidebar Unification + Active State Fix + /dashboard/templates 500
  README de cambios — Changelog atómico
================================================================================

FECHA         : 2026-10-18
VERSION       : V2.01 (sub-cambio correctivo de UI/UX)
ALCANCE       : 3 bugs criticos detectados por screenshot de produccion:
                 (1) sidebar distinto en /dashboard vs resto del sitio
                 (2) hover/active del sidebar invisible (texto blanco sobre blanco)
                 (3) /dashboard/templates devuelve 500
TRAZABILIDAD  : reporte del usuario con 2 screenshots:
                 - Screenshot 1: /dashboard/customers → sidebar NEGOCIO/Widgets/
                   Notificaciones/Productos/etc. con items activos en BLANCO
                 - Screenshot 2: /dashboard → sidebar Dashboard/Clientes/
                   Productos/Inventario/COMERCIAL/... con estética DIFERENTE
                 - Link "Apariencia" da 500 (dashboard/templates)

================================================================================
  BASE
================================================================================
El proyecto WowHub tiene un layout de sidebar definido en
`dashboard/base.html` (extends `base.html`). El bloque `{% block content %}`
del padre envuelve toda la pagina (sidebar + main wrapper), y dentro hay un
sub-bloque `{% block dash_content %}` para inyectar el contenido de la
pagina. La convencion es:

    {% extends "dashboard/base.html" %}
    {% block dash_content %}
        ... contenido de la pagina ...
    {% endblock %}

Inventario de inconsistencias detectadas (estado pre-fix):

1) /dashboard → renderizaba `dashboard/wowcolor.html` (28.7 KB)
   - Sidebar propio: <aside class="wc-side"> + .wc-nav-item
   - Estetica WowColor v2.0 (sidebar oscura, cards azules)
   - El resto: extendian dashboard/base.html con .dash-side + .nav-link
   - RESULTADO: dos sidebars distintos en el mismo producto.

2) Hover/active state del sidebar (todas las paginas excepto /dashboard)
   - JS `highlightActiveNav()` (dashboard/base.html) agrega la clase `.active`
   - CSS `app.css:198-199` define reglas para `.active` usando
     `var(--sb-active)` y `var(--sb-text)` (resueltos en tokens.css)
   - CSS `dashboard.css:163-171` define reglas SOLO para `.is-active`
     usando `var(--mod-accent)` (purple) con `!important`
   - Bug: si `dashboard.css` carga despues de `app.css` (orden actual), las
     reglas con `!important` solo se aplican a `.is-active`, no `.active`.
     En algunos contextos el resultado es texto blanco sobre fondo claro.

3) /dashboard/templates → usaba `{% block content %}` (incorrecto)
   - `dashboard/base.html` define `{% block content %}` como wrapper
     completo (sidebar + main)
   - Usar `{% block content %}` desde un child template reemplaza el wrapper
     entero → sidebar ausente o template no encuentra variables del padre
   - RESULTADO: HTTP 500.

================================================================================
  CAMBIO UNICO
================================================================================

1) UNIFICAR SIDEBAR — /dashboard usa dashboard/index.html
   Archivo MODIFICADO: app/main.py (linea 404)

   ANTES:
       @app.get("/dashboard", response_class=HTMLResponse, ...)
       def dashboard_page(request: Request):
           return templates.TemplateResponse(request, "dashboard/wowcolor.html", ...)
       # Renderizaba wowcolor.html con sidebar wc-side (legacy)

   DESPUES:
       @app.get("/dashboard", response_class=HTMLResponse, ...)
       def dashboard_page(request: Request):
           return templates.TemplateResponse(request, "dashboard/index.html", ...)
       # Renderiza index.html que extiende dashboard/base.html
       # con sidebar dash-side Moderna (mismo que /dashboard/customers,
       # /dashboard/products, etc.)

   `dashboard/index.html` ya existia desde hace varias releases y usa el
   patron correcto: extiende `dashboard/base.html` y override `dash_content`.
   Para volver al legacy WowColor (sidebar wc-side), sigue accesible
   en `/dashboard/v1` (no se elimino, solo se dejo de usar por defecto).

2) HOVER/ACTIVE STATE — soportar .active ademas de .is-active
   Archivo MODIFICADO: app/static/css/templates/dashboard.css (2 selectores)

   ANTES (linea 156):
       .template-moderna .dash-side .nav-link:hover,
       .template-moderna .dash-side a[data-route]:hover,
       .template-moderna .sidebar .nav-item:hover { ... purple soft bg + white text ... }

       .template-moderna .dash-side .nav-link.is-active,
       .template-moderna .dash-side a[data-route].is-active,
       .template-moderna .sidebar .nav-item.is-active,
       .template-moderna .sidebar .nav-item.active { ... purple accent bg + white text ... }

   DESPUES:
       .template-moderna .dash-side .nav-link:hover,
       .template-moderna .dash-side .nav-link.active:hover,    ← NUEVO
       .template-moderna .dash-side a[data-route]:hover,
       .template-moderna .dash-side a[data-route].active:hover,← NUEVO
       .template-moderna .sidebar .nav-item:hover { ... }

       .template-moderna .dash-side .nav-link.is-active,
       .template-moderna .dash-side .nav-link.active,           ← NUEVO
       .template-moderna .dash-side a[data-route].is-active,
       .template-moderna .dash-side a[data-route].active,       ← NUEVO
       .template-moderna .sidebar .nav-item.is-active,
       .template-moderna .sidebar .nav-item.active { ... }

   Razon: el JS `highlightActiveNav()` (dashboard/base.html linea 293) agrega
   la clase `.active` (no `.is-active`). Antes, las reglas de dashboard.css
   no matcheaban el `.active` del JS, y caian a las reglas de app.css que
   usan `var(--sb-active)` (light purple) y `var(--sb-text)` (dark text) —
   contraste OK en light mode pero INVISIBLE en dark mode o cuando las
   variables se sobrecargan. Ahora `.active` y `.is-active` producen
   EXACTAMENTE el mismo estilo: fondo `#6c5ce7` (purpura accent) + texto
   blanco, font-weight 600.

3) FIX 500 — templates.html usa block dash_content
   Archivo MODIFICADO: app/templates/dashboard/templates.html (linea 295-302)

   ANTES:
       {% block content %}
       <div class="page-header">
         <h1>🎨 Apariencia — Plantillas</h1>
         ...

   DESPUES:
       {# ── V2.01 FIX — Antes este template usaba {% block content %} ... #}
       {% block dash_content %}
       <div class="page-header">
         <h1>🎨 Apariencia — Plantillas</h1>
         ...

   Razon: `{% block content %}` en un child template REEMPLAZA el wrapper
   completo del padre (sidebar + main), lo que causa:
     - Sidebar ausente (no se ve el menu)
     - Variables del padre no disponibles → JinjaUndefinedError → HTTP 500
   `{% block dash_content %}` es el sub-bloque correcto para inyectar
   contenido DENTRO del wrapper preservando sidebar + topbar.

================================================================================
  QUE NO SE MODIFICO
================================================================================
  - 39 templates dashboard/* que extienden correctamente dashboard/base.html
    usando {% block dash_content %} — sin cambios
  - dashboard/base.html — sin cambios
  - base.html — sin cambios
  - app.css — sin cambios (sigue definiendo fallback con var(--sb-*))
  - tokens.css — sin cambios
  - api/v1/templates.py — sin cambios
  - Cualquier endpoint backend — sin cambios
  - wowcolor.html — NO se elimino (sigue accesible en /dashboard/v1 como
    legacy/alternativa para quien quiera el sidebar wc-side WowPrint)
  - Los 29 tests pytest — sin cambios, siguen pasando
  - app.js, ai.js, template-selector.js — sin cambios
  - RBAC, schemas, modelos — sin cambios

================================================================================
  REQUERIMIENTOS DE DESPLIEGUE
================================================================================
  Worker: SI requiere reinicio (cambio en main.py).
    - app/main.py MODIFICADO (cambio de template para /dashboard).
    - app/static/css/templates/dashboard.css MODIFICADO (2 selectores).
    - app/templates/dashboard/templates.html MODIFICADO (1 block).
    - FastAPI recarga el router; el navegador debe hard-refresh (Ctrl+Shift+R)
      para evitar HTML/CSS cacheado.
    - Tiempo de reinicio: < 5 segundos. Sin migracion DB.

  Migraciones DB: NO requiere.

  Config / env vars: NO requiere.

  Caches / CDN: SI purgar en produccion:
    - /static/css/templates/dashboard.css (cambio de selectores)
    - /dashboard (HTML nuevo, ahora desde dashboard/index.html)
    - /dashboard/templates (HTML nuevo, ahora con block dash_content)

  Hard refresh obligatorio en navegador: SI, para purgar HTML/CSS cacheado
  con la sidebar inconsistente anterior.

================================================================================
  PROCEDIMIENTO DE PRUEBA RECOMENDADO
================================================================================
A) Verificar sidebar unificado (mismo en todas las paginas)

   1) Hard refresh (Ctrl+Shift+R) en /dashboard.
   2) Esperado: sidebar muestra "Resumen, Widgets, Notificaciones, ..."
      (mismos items que /dashboard/customers).
   3) Hard refresh en /dashboard/customers.
   4) Esperado: MISMO sidebar que /dashboard (mismo color, mismos items,
      mismo item activo "Clientes").
   5) Comparar con /dashboard/products, /dashboard/orders, /dashboard/mesero,
      /dashboard/templates — todos con la MISMA estetica.

B) Verificar active state visible (no blanco sobre blanco)

   1) Hard refresh en /dashboard.
   2) Esperado: "Resumen" (item activo) tiene fondo PURPURA (#6c5ce7)
      + texto BLANCO + font-weight 600 + box-shadow.
   3) Hover sobre cualquier item NO activo.
   4) Esperado: fondo purple soft (rgba(108, 92, 231, 0.10)) + texto blanco.
   5) Click en cualquier item → navegar.
   6) Esperado: el item clickeado queda activo con fondo purpura + texto
      blanco (NO blanco sobre blanco, NO invisible).

C) Verificar /dashboard/templates carga (no 500)

   1) Click en sidebar "🎨 Apariencia" → /dashboard/templates.
   2) Esperado: HTTP 200, sidebar visible a la izquierda, grid de 4 cards
      (Moderna, WowPrint, Dark, Default).
   3) DevTools Network: el request a /dashboard/templates debe devolver 200
      (antes 500).
   4) Console: cero errores JS.

D) Verificar legacy WowColor sigue accesible

   1) Hard refresh en /dashboard/v1.
   2) Esperado: sidebar WowColor (wc-side) con items "Dashboard, Clientes,
      Productos, Inventario, COMERCIAL, Costos y precios, Cotizaciones,
      Pedidos, Ventas y pagos, OPERACIÓN, Producción, KDS, Lealtad,
      Analytics, Configuración". Item activo "Dashboard" en AZUL.

E) Regresion completa

   1. pytest multi-agent-wowhub/ -v → 29/29 debe seguir pasando.
   2. /dashboard, /dashboard/products, /dashboard/customers, /dashboard/orders,
      /dashboard/mesero, /dashboard/templates, /dashboard/kds,
      /dashboard/widgets → carga 200 sin errores 500, sidebar Moderna.
   3. /dashboard/v1 → carga 200 con sidebar WowColor legacy.
   4. Console del navegador: cero errores JS en todas las paginas.

================================================================================
  ARCHIVOS TOCADOS (resumen)
================================================================================
  A) NUEVOS:
     + docs/releases/README_V2.01_SIDEBAR_UNIFICATION.txt (este archivo)

  B) MODIFICADOS:
     ~ app/main.py                                              (~10 lineas,
                                                                  comentario +
                                                                  1 template)
     ~ app/static/css/templates/dashboard.css                    (+4 selectores:
                                                                  2 hover +
                                                                  2 active)
     ~ app/templates/dashboard/templates.html                    (~10 lineas:
                                                                  comentario +
                                                                  1 block rename)

  Total: +1 archivo nuevo, 3 modificados. ~25 lineas netas (sin contar
  este README y los comentarios inline).

================================================================================
  RIESGOS Y ROLLBACK
================================================================================
  Riesgo bajo.
    - Cambio #1 (/dashboard): cambio de un template a otro. El nuevo
      (dashboard/index.html) ya existia y se usaba antes. Si algo se
      rompe en la UI del resumen, /dashboard/v1 sigue como legacy.
    - Cambio #2 (CSS): agregar selectores es estrictamente aditivo. No
      modifica reglas existentes, solo añade reglas para `.active`.
    - Cambio #3 (templates.html): renombrar `block content` a
      `block dash_content`. Patron consistente con el resto del proyecto.
      Si algo no carga, /dashboard/templates sigue accesible via su URL
      y el sidebar se restaura.

  Rollback:
    1) Revertir este commit (un revert limpio).
    2) Si solo /dashboard se rompe: cambiar main.py para usar
       dashboard/wowcolor.html (legacy sidebar wc-side).
    3) Si solo /dashboard/templates se rompe: cambiar templates.html
       para volver a {% block content %} (sidebar ausente pero no 500).
    4) Reiniciar worker.

================================================================================
  FIN DEL README — V2.01 Sidebar Unification
================================================================================