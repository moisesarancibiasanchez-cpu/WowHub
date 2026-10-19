================================================================================
README_V2.01_HERO_SHOWCASE.txt
WowHub · Release Notes Atómicos · V2.01
================================================================================

FECHA          : 2026-10-22
BUILD          : post 90b8e6e (Hero improvements)
ALCANCE        : Landing pública · Hero interactivo
ATOMICIDAD     : 1 commit único
RIESGO         : Bajo · No toca backend, routers, DB ni auth.
                Sólo impacta app/templates/home.html,
                app/static/js/hero_showcase.js (nuevo) y
                app/static/css/templates/landing.css.
REVERTIBLE     : Sí · `git revert <commit>` deja home.html como
                estaba antes (mockup estático + navbar duplicada ya
                corregida en 90b8e6e).


--------------------------------------------------------------------------------
1. BASE (contexto)
--------------------------------------------------------------------------------

A partir de V2.01, WowHub necesita demostrar visualmente sus 8
funcionalidades centrales (Página, Catálogo, QR, Pedidos, Pagos,
Reservas, Promos, Estadísticas) en el Hero de la landing pública,
sustituyendo el mockup estático del café "Café Norte" que sólo
mostraba un producto.

El brief UX/UI senior (multi-agente) especificó:

  · 8 tabs navegables con iconos
  · Autoplay cada 4-5s con pausa en hover
  · Transición suave (fade + scale)
  · Responsive mobile: swipe horizontal con scroll-snap
  · Accesibilidad WCAG AA: ARIA tabs pattern + keyboard navigation
  · Sin terminología interna ("MVP", "API Docs") en el Hero del
    usuario final (directiva QA Agente 4)

Estado previo al cambio:
  · app/templates/home.html: hero estático con `<div class="hero__mockup">`
    que sólo mostraba el producto "Latte Artesanal".
  · app/static/js/hero_showcase.js: NO EXISTÍA.
  · landing.css: NO contenía estilos para tabs ni mockup dinámico.
  · Badge visible: "Nuevo · MVP v0.2" (PROHIBIDO por directiva QA).


--------------------------------------------------------------------------------
2. CAMBIO ÚNICO
--------------------------------------------------------------------------------

A) ARCHIVO NUEVO: app/static/js/hero_showcase.js (13,755 bytes)
   · IIFE vanilla JS, sin dependencias.
   · Array TABS[8] con id, label, icon, title, subtitle, visual.
   · Función `visualHTML(tab)` retorna markup distinto para cada tab:
       - page     : avatar + nombre tienda + líneas decorativas + CTA
       - catalog  : 3 productos (Latte, Torta, Ensalada) con gradient
       - qr       : patrón 3x3 con scan line animada
       - orders   : 4 órdenes con status dots (ok / proc animado)
       - payments : SVG tarjeta + monto + status + método
       - bookings : 8 slots horarios (algunos "busy" tachados)
       - promos   : 2 cards con badges (-30%, 15%) + códigos
       - stats    : 7-day bar chart con bars animadas
   · `init()` busca `[data-hero-tabs]`, `[data-hero-panel]`,
     `[data-hero-mockup]`. Si no existen, sale silenciosamente
     (no-op en otras páginas).
   · Autoplay 4500ms con setInterval.
   · Pausa en: mouseenter sobre showcase/tabs, focus sobre tabs,
     touchstart (mobile), visibilitychange (tab oculto).
   · Keyboard ARIA tabs: ArrowLeft/Up (anterior), ArrowRight/Down
     (siguiente), Home (primero), End (último).
   · Swipe móvil: touchstart/touchend con threshold 50px.
   · Transición: añade `is-switching` durante 175ms, luego inyecta
     el nuevo HTML en `.phone__screen`.

B) ARCHIVO MODIFICADO: app/templates/home.html (33,338 → 36,935 bytes)
   · Badge "Nuevo · MVP v0.2" → "Beta · v2.01" (cumple QA Agente 4).
   · Bloque `<div class="hero__mockup">` REEMPLAZADO por:
       <div class="hero-showcase" role="region" aria-label="...">
         <div class="hero-showcase__tabs" role="tablist" data-hero-tabs>
           <button role="tab" id="hero-tab-page" aria-selected="true">
           × 8 tabs (page, catalog, qr, orders, payments, bookings,
                    promos, stats) con icon emoji + label
         </div>
         <div class="hero-showcase__viewport">
           <div class="float-card float-card--top">Notificación</div>
           <div class="hero-tooltip" data-hero-tooltip aria-live="polite">
             <div class="hero-tooltip__title">…</div>
             <div class="hero-tooltip__subtitle">…</div>
           </div>
           <div class="phone" data-hero-mockup role="tabpanel"
                id="hero-panel-page" aria-labelledby="hero-tab-page"
                tabindex="0">
             <div class="phone__notch"></div>
             <div class="phone__screen"></div>
           </div>
           <div class="float-card float-card--bottom">QR escaneado</div>
         </div>
       </div>
   · Script tag agregado en `{% block scripts %}`:
       <script src="/static/js/hero_showcase.js?v=v2.01-hero-showcase"
               defer></script>

C) ARCHIVO MODIFICADO: app/static/css/templates/landing.css (15,991 → 26,754 bytes)
   · Nueva variable `--landing-success-soft: #d4f4ea` (light) y
     `rgba(0,184,148,0.18)` (dark).
   · Bloque "HERO SHOWCASE INTERACTIVO" agregado con:
       .hero-showcase              (flex column contenedor)
       .hero-showcase__tabs        (píldoras con shadow)
       .hero-tab                   (button reset + transitions)
       .hero-tab:hover             (background accent-soft)
       .hero-tab:focus-visible     (outline 2px)
       .hero-tab.is-active         (background accent + shadow)
       .hero-tab__icon / __label
       .hero-showcase__viewport    (relative + min-height 580px)
       .hero-tooltip               (absolute top, pill con flecha)
       .hero-tooltip__title / __subtitle
       [data-hero-mockup].is-switching .phone__screen
                                   (fade out 175ms)
       [data-hero-mockup] .phone__screen (fade in 175ms)
   · 8 factories visuales (.mock-page, .mock-catalog, .mock-qr,
     .mock-orders, .mock-payment, .mock-bookings, .mock-promos,
     .mock-stats) con sus sub-elementos (.mock-product, .qr-cell,
     .mock-order, .slot, .mock-promo-card, etc.).
   · Animaciones: @keyframes qrScan (scan line vertical), @keyframes
     pulse (status dots de processing), transitions para tab activo
     y fill bars de stats.
   · Responsive `@media (max-width: 900px)`:
       .hero-showcase__tabs → flex-wrap: nowrap
                              overflow-x: auto
                              scroll-snap-type: x mandatory
       .hero-tab → scroll-snap-align: start
       .hero-tooltip → más compacto (11px, padding 6/10)
       .hero-showcase__viewport → min-height 520px


--------------------------------------------------------------------------------
3. QUÉ NO SE MODIFICÓ
--------------------------------------------------------------------------------

· Backend FastAPI: CERO cambios en routers, schemas, DB, auth, ni
  middleware. hero_showcase.js es 100% client-side.
· app/main.py: sin cambios.
· app/templates/public/landing.html: sin cambios (la landing pública
  sigue usando su propio showcase del peak 7ce25ea).
· app/templates/dashboard/*: sin cambios (sólo aplica a home pública).
· Otros componentes: feature-card grid, pricing, FAQ, footer,
  testimonials, trust bar: sin cambios.
· Mockup SVG inline previo (taza con vapor): eliminado en favor
  del sistema dinámico, pero el visual `mock-page` mantiene la
  identidad de marca con avatar "N" + "Café Norte".
· Endpoint `POST /api/v1/tenants/{id}/orders/{oid}/customer` (V2.01
  Quick-Context): sin cambios.
· Sidebar Moderna unificada: sin cambios.
· templates.router (registrado en 15be007): sin cambios.
· 3 redirects stub (production/analytics/settings de b68eee5):
  sin cambios.


--------------------------------------------------------------------------------
4. REQUERIMIENTOS DE DESPLIEGUE
--------------------------------------------------------------------------------

· Worker: NO requiere cambio. El JS es asset estático servidolight por
  StaticFiles de FastAPI.
· Cache busting: el script tag incluye `?v=v2.01-hero-showcase` para
  forzar reload tras deploy. Si los usuarios tenían caché vieja del
  landing.css, el nuevo CSS también incluye el sufijo
  `?v=v2.01-landing` (pre-existente) + las nuevas reglas se sirven
  automáticamente con el nuevo archivo.
· Browser support: requiere JS ES5+ (compatible IE11+). El markup
  ARIA funciona en NVDA/JAWS/VoiceOver.
· No requiere rebuild Docker ni cambio de variables de entorno.
· No requiere migraciones Alembic.
· No requiere cambio en package.json/pyproject.toml (vanilla JS).

Acciones post-deploy recomendadas:
  1. Verificar carga de `/` en navegador desktop (Chrome/Firefox/Safari).
  2. Verificar carga en mobile (DevTools responsive 375px iPhone SE).
  3. Validar tab "Estadísticas" → bars animadas correctamente.
  4. Validar swipe en mobile (touch horizontal cambia de tab).
  5. Lighthouse Accessibility ≥ 95 (esperado, no degradado).


--------------------------------------------------------------------------------
5. PROCEDIMIENTO DE PRUEBA RECOMENDADO
--------------------------------------------------------------------------------

5.1 Smoke test (manual)
  a) Abrir `/` en navegador desktop (≥1024px).
     - Verificar que el Hero carga con 8 tabs en píldora superior.
     - Verificar que el primer tab (Página) está activo por default
       con mockup "Café Norte" + 3 líneas + CTA.
     - Verificar que cada 4.5s cambia automáticamente al siguiente tab.
     - Hover sobre el showcase → autoplay pausa.
     - Click sobre "Catálogo" → cambia instantáneamente, mockup muestra
       3 productos (Latte, Torta, Ensalada) con precios.
     - Click sobre "QR" → mockup muestra patrón QR con scan line animada.
     - Click sobre "Estadísticas" → mockup muestra 7-day bar chart.
     - Tecla ArrowRight sobre tab activo → siguiente tab + focus.
     - Tecla Home → primer tab.
  b) DevTools responsive: 375px (iPhone SE).
     - Verificar que tabs son swipe horizontal con scroll-snap.
     - Verificar que tooltip es más compacto (no se sale del viewport).
     - Verificar que el mockup mantiene proporción 19.5:9.
  c) Lighthouse Accessibility:
     - Score ≥ 95 (esperado 98+).
     - Verificar que role="tablist" / role="tab" / role="tabpanel"
       son detectados correctamente.
  d) Lighthouse Performance:
     - Score ≥ 90 (script es ~14KB, ligero).
     - FCP < 1.8s, LCP < 2.5s.

5.2 Test automatizado
  a) `python -m pytest multi-agent-wowhub` → 29/29 passing.
  b) `python -c "import jinja2; env=jinja2.Environment(loader=jinja2.FileSystemLoader('app/templates'),autoescape=True); env.get_template('home.html').render(request=None)"` → renderiza sin excepciones.
  c) Verificación programática de ARIA:
     ```python
     html = open('app/templates/home.html').read()
     assert html.count('role="tab"') == 8
     assert html.count('role="tablist"') == 1
     assert html.count('role="tabpanel"') == 1
     assert 'data-hero-tabs' in html
     assert 'data-hero-mockup' in html
     assert 'data-hero-tooltip' in html
     assert 'Beta · v2.01' in html
     assert 'MVP' not in html
     assert 'API Docs' not in html
     ```
  d) Verificación programática de JS:
     ```python
     js = open('app/static/js/hero_showcase.js').read()
     assert js.count('id:') == 8            # 8 tabs
     assert js.count("case '") == 8         # 8 visual factories
     assert js.count('AUTOPLAY_MS =') == 1
     assert js.count('setInterval') >= 1
     ```

5.3 Rollback
  Si el showcase causa regresión visual o de performance:
  `git revert HEAD` (1 commit) y push. El sitio vuelve al mockup
  estático del café (que ya tenía navbar única por 90b8e6e).


--------------------------------------------------------------------------------
6. TRAZABILIDAD
--------------------------------------------------------------------------------

Commits previos relacionados:
  · 90b8e6e  fix(public): Hero improvements (navbar duplicada, mockup,
              trust pills)
  · 91ac67c  V2.01 Landing UX Redesign (brief UX/UI senior)
  · a1e3cb8  V2.01 Public Homepage Restore (home.html 4x)

Próximo commit planeado:
  · [hash] feat(public): V2.01 Hero Showcase — 8 tabs ARIA + mockup
            dinámico + autoplay 4.5s + responsive mobile


--------------------------------------------------------------------------------
7. MÉTRICAS ESPERADAS POST-DEPLOY
--------------------------------------------------------------------------------

· Hero CTR (crear cuenta): esperado +5-8% por engagement del carrusel.
· Bounce rate: esperado -3-5% por mayor tiempo en página.
· Mobile UX score: esperado +12 puntos (swipe nativo vs scroll).
· Accessibility score: esperado +2 puntos (ARIA roles explícitos).
· Lighthouse Performance: sin cambio (script < 14KB, CSS < 27KB).
================================================================================
FIN README_V2.01_HERO_SHOWCASE.txt
================================================================================