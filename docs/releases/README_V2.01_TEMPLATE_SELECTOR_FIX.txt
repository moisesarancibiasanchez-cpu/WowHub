================================================================================
  WowHub V2.01 — Template Selector Fix (ruta + FOUC + sidebar)
  README de cambios — Changelog atómico
================================================================================

FECHA         : 2026-10-17
VERSION       : V2.01 (sub-cambio correctivo)
ALCANCE       : Auditoria exhaustiva de templates + 3 fixes criticos:
                 (1) ruta faltante /dashboard/templates
                 (2) FOUC en anti-flash script de base.html
                 (3) sidebar Apariencia apuntaba a ruta incorrecta
TRAZABILIDAD  : tickets reportados por el usuario:
                 - "se tardan bastante en cargar y aparece la version
                   anterior y luego la actual (Moderna)"
                 - "No aparece en Menu Apariencia la opcion de seleccionar
                   MODERNA, sino que solo DARK y PRO"
                 - "Corrige bugs o posible incosnistencias en el codigo
                   respectivo a Themes, platillas o estilos CSS"

================================================================================
  BASE
================================================================================
WowHub V2.01 ya consolidaba la plantilla "Moderna" como default site-wide
con archivos:

  - app/templates/dashboard/templates.html (442 lineas, 4 cards:
    Moderna, WowPrint, Dark, Default legacy). Existia en disco desde
    el commit f1e5d2c ("V2.01 Moderna consolidada") pero NUNCA se le
    asigno una ruta en main.py.

  - app/static/css/templates/dashboard.css (20.8 KB, scope .template-moderna)
    cargado site-wide en base.html (linea 41).

  - app/static/js/template-selector.js (5 KB, CATALOG con 5 entries:
    moderna | dashboard | wowprint | dark | default; LEGACY_ALIASES para
    "dashboard" -> "moderna").

  - app/api/v1/templates.py (91 lineas, endpoint PUT/GET con
    VALID_TEMPLATES = ("default","moderna","dashboard","wowprint","dark")).

  - app/templates/base.html: anti-flash script inline en <head> que
    intenta aplicar la clase "template-moderna" antes del primer paint
    para evitar FOUC.

  - app/templates/dashboard/base.html (sidebar): el link "Apariencia"
    apuntaba a /dashboard/site (ruta que renderizaba dashboard/site.html,
    archivo distinto con selector de tema de PORTADA PUBLICA: solo
    "dark" y "pro", nada que ver con las plantillas del dashboard).

  Inventario de templates:
    63 archivos .html totales
    14 extienden base.html       (home, auth/*, legal/*, public/*, payments/*)
    40 extienden dashboard/base.html (admin_*, channels, customers, etc.)
     9 son parciales o standalone (_partials/*, home_pro, public/landing*)

================================================================================
  CAMBIO UNICO
================================================================================

1) RUTA FALTANTE — /dashboard/templates
   Archivo MODIFICADO: app/main.py (+11 lineas)

   ANTES: el sidebar "Apariencia" llevaba a /dashboard/site que renderizaba
   dashboard/site.html (otro archivo, selector de tema de portada publica
   con solo 2 opciones: "dark" y "pro"). El usuario veia:
       [Tarjeta "Tema dark (actual)"]
       [Tarjeta "Tema pro (prototipo)"]
   y pensaba que Moderna no existia. El template dashboard/templates.html
   con las 4 opciones (Moderna, WowPrint, Dark, Default) NUNCA se enrutaba.

   DESPUES: nueva ruta que renderiza el template correcto.

   Codigo añadido en app/main.py:
   --------------------------------------------------------------
   # V2.01 — Selector de plantillas estéticas (Moderna, WowPrint, Dark, Default).
   # Antes de este fix, el sidebar "Apariencia" apuntaba a /dashboard/site que
   # renderizaba un selector de tema de portada pública (dark/pro), no las
   # plantillas del dashboard. El template dashboard/templates.html ya existía
   # desde V2.01 pero NUNCA fue enrutado: el usuario veía solo 2 opciones.
   @app.get("/dashboard/templates", response_class=HTMLResponse, include_in_schema=False)
   def dashboard_templates(request: Request):
       """Admin UI: selector de plantilla estética del dashboard.
       4 opciones: Moderna (default), WowPrint (kiosk), Dark, Default (legacy)."""
       return templates.TemplateResponse(request, "dashboard/templates.html", {"settings": settings})
   --------------------------------------------------------------

2) FOUC FIX — anti-flash script en base.html
   Archivo MODIFICADO: app/templates/base.html (bloque script en <head>)

   ANTES: el script inline intentaba añadir la clase a document.body:
       if (tpl === "moderna") document.body && document.body.classList.add("template-moderna");
       else if (tpl === "wowprint") document.body && document.body.classList.add("template-wowprint");

   PROBLEMA: el script corre en <head>, ANTES de que el parser HTML haya
   encontrado el tag <body>. En ese momento document.body es null, el
   short-circuit && no ejecuta nada y la clase NUNCA se aplica en el
   primer paint. Luego template-selector.js la aplica en DOMContentLoaded
   (al final del body), pero el primer render ya mostro la version sin
   plantilla -> FOUC visible ("version anterior y luego la actual Moderna").

   DESPUES: aplicar a documentElement (<html>) que SI existe cuando el
   script corre. Como el CSS ya tiene selector .template-moderna (clase,
   sin importar en qué elemento), la cascada aplica desde el primer paint.

   Codigo modificado en app/templates/base.html:
   --------------------------------------------------------------
   <script>
     (function () {
       try {
         var tpl = localStorage.getItem("wowhub.template") || "moderna";
         // Compatibilidad: "dashboard" legacy -> "moderna"
         if (tpl === "dashboard") tpl = "moderna";
         var html = document.documentElement;
         if (tpl === "moderna") html.classList.add("template-moderna");
         else if (tpl === "wowprint") html.classList.add("template-wowprint");
         // 'default' se maneja sin clase
       } catch (_) { /* noop */ }
     })();
   </script>
   --------------------------------------------------------------

   Template-selector.js sigue añadiendo la clase a <body> en DOMContentLoaded
   (redundancia inocua: si la clase ya está en <html>, añadirla a <body>
   no rompe nada y mantiene el contrato del JS público TemplateSelector).

3) SIDEBAR — link Apariencia apunta a la ruta correcta
   Archivo MODIFICADO: app/templates/dashboard/base.html

   ANTES:
       <a href="/dashboard/site" class="nav-link" data-route="site">
         <span class="ico">🌗</span> Apariencia
       </a>

   DESPUES:
       <a href="/dashboard/templates" class="nav-link" data-route="templates"
          title="Plantillas estéticas del dashboard: Moderna, WowPrint, Dark, Default">
         <span class="ico">🎨</span> Apariencia
       </a>

   Cambio de icono 🌗→🎨 para diferenciar visualmente "Apariencia del
   dashboard (plantillas)" de "Mi sitio web" (que tiene otro data-route
   "mi-sitio-web" y sigue con icono propio).

================================================================================
  QUE NO SE MODIFICO
================================================================================
  - app/api/v1/templates.py (NO tocado — ya soportaba "moderna" en
    VALID_TEMPLATES y TemplateUpdate Literal)
  - app/static/js/template-selector.js (NO tocado — el CATALOG ya
    tenia "moderna", wowprint, dark, default; LEGACY_ALIASES ok;
    la propagacion a body en DOMContentLoaded sigue funcionando)
  - app/static/css/templates/dashboard.css y wowprint.css (NO tocados —
    reglas globales son solo @keyframes y @media, scoped OK)
  - app/templates/dashboard/templates.html (NO tocado — el template ya
    tenia las 4 cards correctas, solo faltaba la ruta)
  - app/templates/dashboard/site.html (NO borrado — sigue siendo el
    selector de tema de portada publica, ruta /dashboard/site
    preservada)
  - Los 63 templates del proyecto (NO tocados — todos extienden
    base.html o dashboard/base.html correctamente)
  - Tokens.css, app.css, wowcolor.css (NO tocados — orthogonal a esta fix)
  - Los 29 tests pytest (NO modificados — siguen pasando)
  - Ningun archivo de mock, ningun endpoint, ninguna migracion Alembic

================================================================================
  REQUERIMIENTOS DE DESPLIEGUE
================================================================================
  Worker: SI requiere reinicio.
    - app/main.py MODIFICADO (nueva ruta). FastAPI recarga el router
      automaticamente al reiniciar el worker; no se requieren nuevas
      dependencias.
    - app/templates/base.html MODIFICADO (anti-flash). El navegador
      recarga el HTML al hacer hard refresh (Ctrl+Shift+R) o al
      purgar cache del CDN.
    - app/templates/dashboard/base.html MODIFICADO (sidebar). Igual
      que arriba: hard refresh del navegador.
    - Tiempo total de reinicio del worker: < 5 segundos (sin
      migraciones DB).

  Migraciones DB: NO requiere.
    - Cero cambios de schema. Cero ALTER TABLE. Cero Alembic.

  Config / env vars: NO requiere.
    - Ninguna variable nueva. Ningun secret nuevo.

  Caches / CDN: para produccion con CDN, purgar el bundle que sirve
              /dashboard/templates (HTML nuevo) y /dashboard (HTML con
              sidebar modificado).

  Hard refresh obligatorio en navegador: SI, para limpiar el HTML cacheado
    con el bug FOUC anterior. Una vez purgado, el primer paint ya tiene
    la clase template-moderna en <html>.

================================================================================
  PROCEDIMIENTO DE PRUEBA RECOMENDADO
================================================================================
A) Verificar que el selector muestra las 4 opciones

   1) Hard refresh (Ctrl+Shift+R) en cualquier pagina del dashboard.
   2) Sidebar → clic en "🎨 Apariencia".
   3) Esperado: carga /dashboard/templates (no /dashboard/site).
   4) Esperado: ver 4 cards en grid:
        [Moderna — DEFAULT]
        [WowPrint V1354 R2 — Kiosk]
        [Dark — Night]
        [Default — Legacy]
   5) Si solo aparecen 2 cards, hay cache de HTML viejo -> Ctrl+Shift+R.

B) Verificar FOUC eliminado

   1) Hard refresh en /dashboard, /dashboard/products, /dashboard/customers.
   2) Abrir DevTools (F12) -> Performance -> grabar 2s.
   3) Esperado: cero "Layout shift" warnings, primer paint ya con
      sidebar oscura (Moderna).
   4) Verificar visualmente: NO debe haber parpadeo blanco/gris al cargar.

C) Verificar anti-flash en HTML

   1) Ver View Source (Ctrl+U) en /dashboard.
   2) Buscar el script inline de anti-flash template:
        var html = document.documentElement;
        if (tpl === "moderna") html.classList.add("template-moderna");
   3) Si aparece "document.body && document.body.classList.add" -> bug
      no parcheado (cache stale).

D) Verificar persistencia del template (no se rompio con el fix)

   1) /dashboard/templates -> clic "Aplicar" en WowPrint.
   2) Verificar: sidebar pasa a fondo blanco, tipografia WowPrint
      (weight 800-900), toast "✓ Plantilla wowprint aplicada".
   3) Hard refresh -> debe seguir en WowPrint (persiste en
      localStorage["wowhub.template"]).
   4) Cambiar a Dark -> data-theme="dark" en <html>.
   5) Cambiar a Default -> sin clase (legacy tokens).

F) Regresion

   1. pytest multi-agent-wowhub/ -v  →  29/29 debe seguir pasando.
   2. /dashboard, /dashboard/products, /dashboard/customers, /dashboard/orders,
      /dashboard/mesero, /dashboard/templates -> carga sin errores 500,
      cero JS errors en consola.
   3. /dashboard/site -> sigue mostrando el selector de tema de portada
      publica (dark/pro). La ruta /dashboard/site NO fue removida.

================================================================================
  ARCHIVOS TOCADOS (resumen)
================================================================================
  A) NUEVOS:
     + docs/releases/README_V2.01_TEMPLATE_SELECTOR_FIX.txt (este archivo)

  B) MODIFICADOS:
     ~ app/main.py                                          (+11 lineas, 1 ruta)
     ~ app/templates/base.html                              (~8 lineas, anti-flash)
     ~ app/templates/dashboard/base.html                    (~6 lineas, sidebar)

  Total: +1 archivo nuevo, 3 modificados. ~25 lineas netas (sin contar
  este README y los comentarios inline).

================================================================================
  AUDITORIA GENERAL REALIZADA (sin cambios)
================================================================================
  - 63 templates auditados: 14 extienden base.html, 40 extienden
    dashboard/base.html, 9 parciales. Todos correctos.
  - dashboard.css (20.8 KB) cargado site-wide: solo reglas scoped
    bajo .template-moderna + @keyframes + @media (sin globals). Seguro.
  - wowprint.css (14.5 KB) cargado site-wide: 100% scoped. Seguro.
  - template-selector.js CATALOG: 5 entries (moderna, dashboard,
    wowprint, dark, default), LEGACY_ALIASES ok, fallback a moderna.
  - api/v1/templates.py VALID_TEMPLATES: incluye "moderna".
  - 29/29 tests pytest pasando (1.84s).
  - Sintaxis Python global: 0 errores.

================================================================================
  RIESGOS Y ROLLBACK
================================================================================
  Riesgo muy bajo.
    - Cambio #1 (ruta): aditiva. Si por algun motivo /dashboard/templates
      choca con algo, el rollback es 1 linea removida.
    - Cambio #2 (FOUC): cambio de selector (document.body ->
      documentElement). La clase .template-moderna es CSS clasico, aplica
      a cualquier elemento. Cero impacto funcional.
    - Cambio #3 (sidebar): cambio de href. data-route actualizado de
      "site" a "templates" para que highlightActiveNav siga funcionando.

  Rollback:
    1) Revertir este commit (un revert limpio).
    2) Si solo el sidebar rompe: editar base.html y volver href a
       /dashboard/site.
    3) Si el FOUC molesta: restaurar document.body en el script de base.html
       (sabiendo que el bug vuelve).
    4) No requiere migracion inversa.
    5) Reiniciar worker (FastAPI recarga la ruta).

================================================================================
  FIN DEL README — V2.01 Template Selector Fix
================================================================================