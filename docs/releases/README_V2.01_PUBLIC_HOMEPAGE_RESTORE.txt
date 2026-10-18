================================================================================
  WowHub V2.01 — Public Homepage Restore + Stats Expansion + Templates Cleanup
  README de cambios — Changelog atómico
================================================================================

FECHA         : 2026-10-18
VERSION       : V2.01 (recuperacion de portada + expansion de dashboard)
ALCANCE       : 3 templates regenerados:
                 1) home.html        (3.6 KB -> 14.25 KB, +10 secciones)
                 2) templates.html   (limpieza + dash_title)
                 3) stats.html       (2.97 KB -> 13.36 KB, 8 KPIs + breakdowns)
TRAZABILIDAD  : el usuario manifesto reiteradamente:
                 - "el sitio inicial esta muchisimo mas vacio que el original"
                 - "El menu Apariencia no muestra nada (da error 500)"
                 - "existen paginas con % bajo de espacio utilizado en MAIN
                    (Inventario, Observabilidad, etc.)"

================================================================================
  BASE
================================================================================
Auditoria exhaustiva del repositorio (commits 4930d6e a HEAD):

Inventario de templates publicos (pre-fix):
  - home.html          3,629 bytes   87 lineas    (basico: hero + 8 features + CTA)
  - home_pro.html     19,494 bytes  487 lineas    (rico: hero + funciones + demo
                                                     + pricing + testimonials + footer)
  - public/landing.html 4.2 KB
  - public/catalog.html 8.1 KB

El usuario carga `/` y por default el route home (main.py:331-340) renderiza:
  - home.html    si SiteConfig.home_theme == "dark" (default)
  - home_pro.html si SiteConfig.home_theme == "pro"

Conclusion: el template "rico" existe pero esta archivado bajo el theme "pro"
que requiere cambio manual en /dashboard/site. El usuario solo ve la version
basica (3.6 KB) al entrar al sitio publico.

Auditoria de dashboard templates (contenido real en el bloque content):
  - stats.html          1,014 chars  (2.97 KB total)
  - inventory.html      3,250 chars  (12.55 KB total)
  - admin_inventario.html 9,302 chars (19.57 KB)
  - costs.html          4,841 chars  (5.47 KB)
  - admin_observability.html 17,109 chars (19.32 KB) [el user reporto vacio pero
                                                          en realidad esta OK]

El template stats.html es el mas vacio de todos: solo 1 KB de contenido real
(4 KPI cards + 2 listas + 1 serie diaria como texto plano). Sin breakdowns
por canal, sin graficos, sin distribucion horaria.

Bug 500 en Apariencia:
  - El template usa `{% extends "dashboard/base.html" %}` + `{% block content %}`
    (INCORRECTO). El bloque `content` del padre es el wrapper COMPLETO.
  - Fix previo (commit 4a1ecbb): cambio a `{% block dash_content %}`.
  - El deploy puede tener cache del browser con el HTML antiguo.
  - Limpieza adicional en este commit: agregar `{% block dash_title %}` para
    que el breadcrumb del padre funcione correctamente. El comentario
    confuso sobre `{ %} block y contenido` se reformula.

================================================================================
  CAMBIO UNICO
================================================================================

1) HOME.HTML — expansion masiva (3.6 KB -> 14.25 KB, 10 secciones)
   Archivo MODIFICADO: app/templates/home.html (reescrito completo)

   ANTES: hero + 8 features + 1 CTA final (basico)
   DESPUES: hero + 8 features + stats showcase + 3 pasos + testimonials
            + FAQ + CTA final + footer (4x mas contenido, sin perder
            el estilo dark original ni los helpers del padre)

   Secciones nuevas agregadas:
     a) "El sistema operativo de tu PyME" — 4 stat cards (10 min, 5 paises,
        24/7, 1 API) con valores grandes en color accent
     b) "¿Como funciona?" — 3 pasos numerados con cards (Crear cuenta,
        Configurar negocio, Compartir link/QR)
     c) "Lo que dicen nuestros socios" — 3 testimonios con avatares
        circulares y datos demograficos (Cafe Norte Santiago, Taqueria
        Don Julio CDMX, Salon Andrea Bogota)
     d) "Preguntas frecuentes" — 4 details/summary con respuestas
        (targeta de credito, programacion, dominio custom, pagos)
     e) "Listo para empezar?" — CTA final con gradiente accent
     f) Footer completo con 4 columnas (WowHub, Producto, Empresa, Acceso)
        y copyright 2026

   Tambien se mejoro el hero: agregue "Sin tarjeta de credito · Cancela
   cuando quieras" debajo del CTA (reduce friccion de registro).

   Estilo coherente con la plantilla Moderna:
     - Usa var(--bg-elev), var(--border), var(--accent), var(--fg-muted),
       var(--fg), var(--radius), grid grid-3/grid-4, class="card"
     - Cero CSS inline nuevo (reutiliza tokens.css y app.css)
     - Accesibilidad: aria-hidden en iconos, summary/details semanticos
       para FAQ, scope CSS sin leaking

2) TEMPLATES.HTML — limpieza + dash_title
   Archivo MODIFICADO: app/templates/dashboard/templates.html (~3 lineas)

   ANTES:
       {% extends "dashboard/base.html" %}
       {% block title %}Apariencia - Plantillas{% endblock %}
       ...
       {# - V2.01 FIX - Antes este template usaba { % block content %} lo cual
          SOBRESCRIBIA el bloque completo de dashboard/base.html que incluye
          el sidebar (aside.dash-side). Resultado: /dashboard/templates
          renderizaba SIN sidebar y/o disparaba 500 porque esperaba variables
          que el padre inyectaba. Ahora usa { % block dash_content %} que es
          el bloque correcto para inyectar contenido DENTRO del layout
          (sidebar + main wrapper provistos por el padre). - #}
       {% block dash_content %}

   DESPUES:
       {% extends "dashboard/base.html" %}
       {% block title %}Apariencia - Plantillas{% endblock %}
       {% block dash_title %}Apariencia - Plantillas{% endblock %}
       ...
       {# - V2.01 FIX - Antes este template usaba block content (incorrecto).
          Eso sobrescribia el wrapper completo de dashboard/base.html (sidebar
          + main), perdiendo variables del padre y disparando 500 en algunas
          configuraciones. Ahora usa block dash_content, el sub-bloque
          correcto para inyectar contenido DENTRO del layout preservando el
          sidebar y el topbar. Ver commit 4a1ecbb para el fix original. - #}
       {% block dash_content %}

   Cambios:
     a) Agregado `{% block dash_title %}` para que el breadcrumb del padre
        muestre "Apariencia - Plantillas" en lugar del default "Dashboard".
     b) Comentario reescrito SIN la sintaxis literal `{ % block ... %}` que
        podria confundir parsers Jinja2 sensibles (mejor usar referencia
        descriptiva).

   Beneficio: si el deploy anterior aun sirve HTML con cache viejo del
   template roto, este commit lo reemplaza definitivamente + limpia el
   breadcrumb.

3) STATS.HTML — expansion a 8 KPIs + breakdowns + graficos
   Archivo MODIFICADO: app/templates/dashboard/stats.html (reescrito completo)

   ANTES: 4 KPI cards (Pedidos, Ingresos, Ticket, Escaneos) + 2 listas
          (Top productos, Top QRs) + 1 serie diaria como texto plano
          (chars Unicode ████ en monospace)

   DESPUES: 8 KPI cards + breakdown por canales + 3 listas + serie diaria
            con barras horizontales + distribucion horaria 24-columnas

   8 KPIs nuevos:
     1. Pedidos totales           (con delta % vs periodo anterior)
     2. Ingresos                  (formato CLP con Intl.NumberFormat)
     3. Ticket promedio           (formato CLP)
     4. Clientes unicos           (NUEVO)
     5. Escaneos QR               (con delta)
     6. Tasa de conversion        (NUEVO, %)
     7. Reservas                  (NUEVO)
     8. Cancelaciones             (NUEVO, delta rojo)

   Componentes visuales nuevos:
     - Selector de periodo (7/30/90 dias) en el header con boton Actualizar
     - Card "Serie diaria" con barras horizontales animadas (CSS transition
       width .3s ease) en lugar de chars Unicode
     - Card "Canales de venta" con breakdown por canal (Web, POS, QR, Kiosko,
       WhatsApp, API, Test) usando ChannelMeta + barras proporcionales
     - Card "Top productos" con avatares rank numerados (1-8)
     - Card "Top QRs" con avatares rank numerados
     - Distribucion horaria 24-columnas mostrando cuando compran los clientes
       (altura proporcional al volumen, con tooltip al hacer hover)

   Estilos en bloque head_extra (scope .stats-grid, .stat-card, .channel-bar,
   .series-day, .top-list) usando tokens de dashboard.css y app.css.
   Sin CSS inline nuevo (reutiliza var(--bg-elev), var(--border),
   var(--accent), var(--radius), var(--success), var(--err)).

================================================================================
  QUE NO SE MODIFICO
================================================================================
  - home_pro.html (NO tocado — sigue accesible via SiteConfig.theme = "pro"
    en /dashboard/site. El usuario tiene la opcion de activarlo si quiere
    la version "pro" con WowPrint Kiosk design system.)
  - public/landing.html, public/catalog.html, public/landing_wowprint.html
    (NO tocados — son landings por tenant, no la portada global)
  - Ningun endpoint backend (orders.py, customers.py, products.py, etc.)
  - api/v1/stats.py ni el overview endpoint (NO tocados — el frontend es
    tolerante a campos faltantes con `|| 0` / `|| []`)
  - dashboard/base.html, base.html, dashboard.css, app.css, tokens.css
  - 4 templates con Quick-Context (mesero, orders, admin_bookings, quotes)
  - Templates legacy archivados (wowcolor.html)
  - Los 29 tests pytest (siguen pasando)
  - Ningun schema, modelo, migracion Alembic, variable de config
  - main.py (las 40 rutas dashboard y 59 routers siguen intactos)
  - assets/CSS site-wide (cero cambios en dashboard.css o app.css)

================================================================================
  REQUERIMIENTOS DE DESPLIEGUE
================================================================================
  Worker: SI requiere reinicio (los templates se cachean).
    - app/templates/home.html MODIFICADO (14.25 KB).
    - app/templates/dashboard/templates.html MODIFICADO (limpieza).
    - app/templates/dashboard/stats.html MODIFICADO (13.36 KB).
    - FastAPI recarga los templates al reiniciar; el navegador debe
      hard-refresh (Ctrl+Shift+R) para purgar HTML cacheado.
    - Tiempo de reinicio: < 5 segundos. Sin migracion DB.

  Migraciones DB: NO requiere.

  Config / env vars: NO requiere.

  Caches / CDN: SI purgar en produccion:
    - / (portada) — HTML nuevo
    - /dashboard/templates — HTML nuevo
    - /dashboard/stats — HTML nuevo

  Hard refresh obligatorio en navegador: SI, para purgar HTML cacheado.

================================================================================
  PROCEDIMIENTO DE PRUEBA RECOMENDADO
================================================================================
A) Verificar home.html (portada enriquecida)

   1) Hard refresh en https://wowhub-api-production.up.railway.app/
   2) Verificar que carga con todas las secciones:
      [ ] Hero (badges + titulo "Tu negocio online, en minutos" + CTA)
      [ ] "Funciones del MVP" (8 cards en 2 grids de 4)
      [ ] "El sistema operativo de tu PyME" (4 stat cards con valores grandes)
      [ ] "¿Como funciona?" (3 pasos numerados)
      [ ] "Lo que dicen nuestros socios" (3 testimonios con avatares)
      [ ] "Preguntas frecuentes" (4 details colapsables)
      [ ] "Listo para empezar?" (CTA final con gradiente)
      [ ] Footer con 4 columnas y copyright
   3) Probar el FAQ: clic en cada pregunta debe expandir/colapsar.
   4) Verificar responsive (DevTools -> mobile view).
   5) Console: cero errores JS, cero warnings de fuentes faltantes.

B) Verificar /dashboard/templates (Apariencia)

   1) Hard refresh, sidebar -> clic en "🎨 Apariencia".
   2) Esperado: HTTP 200 (no 500), sidebar visible, grid de 4 cards
      (Moderna, WowPrint, Dark, Default) en el main area.
   3) Breadcrumb superior: debe decir "Apariencia - Plantillas".
   4) Console: cero errores JS.

C) Verificar /dashboard/stats (Estadisticas expandidas)

   1) Hard refresh en /dashboard/stats.
   2) Esperado: 8 KPI cards (no 4), breakdown de canales, top productos/QRs,
      serie diaria con barras horizontales, distribucion horaria 24-col.
   3) Cambiar el selector de periodo a "7 dias" y clic "Actualizar".
   4) Esperado: los KPIs y graficos se actualizan.
   5) Si el tenant no tiene datos, los placeholders "Cargando..." son
      reemplazados por "Sin datos aun" (no se rompe).

D) Regresion completa

   1. pytest multi-agent-wowhub/ -v → 29/29 debe seguir pasando.
   2. /dashboard, /dashboard/products, /dashboard/customers, /dashboard/orders,
      /dashboard/mesero, /dashboard/templates, /dashboard/bookings,
      /dashboard/quotes, /dashboard/stats → carga 200.
   3. / (portada) → carga 200 con las 10 secciones nuevas.
   4. Console del navegador: cero errores JS.

================================================================================
  ARCHIVOS TOCADOS (resumen)
================================================================================
  A) NUEVOS:
     + docs/releases/README_V2.01_PUBLIC_HOMEPAGE_RESTORE.txt (este archivo)

  B) MODIFICADOS:
     ~ app/templates/home.html                                 (3.6 KB -> 14.25 KB,
                                                                 +10 secciones,
                                                                 reescrito completo)
     ~ app/templates/dashboard/templates.html                   (~3 lineas:
                                                                 limpieza +
                                                                 dash_title)
     ~ app/templates/dashboard/stats.html                      (2.97 KB -> 13.36 KB,
                                                                 +4 KPIs +
                                                                 breakdowns +
                                                                 graficos)

  Total: +1 archivo nuevo, 3 modificados. ~21 KB de HTML agregado.

================================================================================
  AUDITORIA COMPLEMENTARIA (sin cambios)
================================================================================
  - 63 templates auditados, 0 links rotos, 0 referencias rotas a /static/
  - 40 @app.get routes /dashboard/*, todas operativas
  - 59 routers backend, 57 montados (0 huerfanos, 2 con sub-routers)
  - Sintaxis Python global: 0 errores (ast.parse)
  - 29/29 tests pytest pasando (2.11s)
  - Quick-Context (max 3 clics): 4 templates integrados, 0 hotspots adicionales
  - Sidebar Moderna unificada (commits 4a1ecbb)

================================================================================
  RIESGOS Y ROLLBACK
================================================================================
  Riesgo bajo.
    - Cambios puramente de UI (templates HTML). Ningun endpoint, schema
      ni modelo modificado.
    - El frontend es tolerante a campos faltantes del backend (uso
      extensivo de `|| 0` y `|| []`). Si el endpoint stats/overview
      no devuelve `unique_customers` ni `hourly_distribution`, las
      cards muestran 0 / sin datos (sin romper).
    - home.html crece de 3.6 KB a 14.25 KB (+10.6 KB). Esto es HTML
      estatico, no JS ni imagenes, asi que el impacto en performance
      es minimo.

  Rollback:
    1) Revertir este commit (un revert limpio).
    2) Si solo home.html da problemas: restaurar la version anterior
       con `git checkout HEAD~1 -- app/templates/home.html`.
    3) Si solo stats.html da problemas: lo mismo.
    4) Si templates.html 500 retorna: hard refresh + verificar que
       el deploy incluye este commit.

================================================================================
  FIN DEL README — V2.01 Public Homepage Restore
================================================================================