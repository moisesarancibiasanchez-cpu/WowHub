================================================================================
README_V2.99_HERO_SHOWCASE_HOTFIX.txt
WowHub · Release Notes Atómicos · V2.99
================================================================================

FECHA          : 2026-10-22
BUILD          : post 24d3012 (Hero Showcase) — feedback en producción
ALCANCE        : Hero Showcase · 3 bugs críticos de visibilidad
ATOMICIDAD     : 1 commit único (0f4b422)
RIESGO         : Bajo · Solo modifica CSS visual y la lógica de inyección
                de contenido JS. Cero cambios en backend, schemas, DB.
REVERTIBLE     : Sí · `git revert 0f4b422` deja 24d3012 intacto.


--------------------------------------------------------------------------------
1. BASE (contexto)
--------------------------------------------------------------------------------

Tras el deploy del Hero Showcase (commit 24d3012), el usuario
reportó que la estética NO coincidía con la propuesta gráfica
generada (hero_showcase_v6.png). Inspección visual de la página
en `https://wowhub-api-production.up.railway.app`:

  · Phone screen aparecía TOTALMENTE NEGRO (sin contenido visible)
  · Hero-tooltip se solapaba con el área de la pantalla del teléfono
  · Contenido del hero__left aparecía centrado en lugar de alineado
    a la izquierda (espacio blanco vacío a la izquierda)
  · Las 8 mock variants (.mock-page, .mock-catalog, etc.) no se
    renderizaban visualmente — solo se veía el tooltip verde

Diagnóstico técnico (verificado en código fuente):
  · JS hacía `mockup.innerHTML = visualHTML(tab)` sobre `.phone`
    (background:#1a1d28) en lugar de `.phone__screen`
    (background:#fff). Esto eliminaba el fondo blanco del screen
    y dejaba el contenido sobre el frame oscuro.
  · Viewport del showcase tenía min-height:580px con
    align-items:center → phone (600px) ocupa casi todo → tooltip
    con top:-10px caía dentro del área del screen.
  · `.hero__left` no tenía `text-align:left` explícito; dependía
    de la herencia que algunos navegadores aplican como center.


--------------------------------------------------------------------------------
2. CAMBIO ÚNICO
--------------------------------------------------------------------------------

2.A) ARCHIVO: app/static/js/hero_showcase.js (13,755 → 13,889 bytes)

   Cambio crítico en `activate()`:
   ANTES (BUG):
     mockup.classList.add('is-switching');
     window.setTimeout(function () {
       mockup.innerHTML = visualHTML(tab);  // ← reemplaza TODO .phone
       mockup.setAttribute('data-visual', tab.visual);
       mockup.classList.remove('is-switching');
     }, TRANSITION_MS / 2);

   AHORA (FIX):
     var screen = mockup.querySelector('.phone__screen');
     if (!screen) {
       // Fallback defensivo
       screen = document.createElement('div');
       screen.className = 'phone__screen';
       mockup.appendChild(screen);
     }
     mockup.classList.add('is-switching');
     window.setTimeout(function () {
       screen.innerHTML = visualHTML(tab);  // ← inyecta DENTRO del screen
       mockup.setAttribute('data-visual', tab.visual);
       mockup.classList.remove('is-switching');
     }, TRANSITION_MS / 2);

   EFECTO: `.phone__screen` (background:#fff) se preserva entre
   cambios de tab. El contenido dinámico aparece siempre sobre
   fondo blanco.

2.B) ARCHIVO: app/static/css/templates/landing.css

   B.1) Mock variants (8 selectores) — backgrounds explícitos:
   ANTES:
     .mock-page     { padding: 18px 14px; }
     .mock-catalog  { padding: 14px 12px; display: grid; gap: 10px; }
     ...
   AHORA:
     .mock-page,
     .mock-catalog,
     .mock-qr,
     .mock-orders,
     .mock-payment,
     .mock-bookings,
     .mock-promos,
     .mock-stats {
       background: var(--landing-bg);
       color: var(--landing-fg);
       width: 100%;
       height: 100%;
       box-sizing: border-box;
       min-height: 0;
     }
     /* + las 8 reglas individuales sin cambios */
   EFECTO: defense-in-depth — incluso si el JS inyecta en otro lado,
   el contenido siempre tiene fondo claro.

   B.2) Viewport del showcase — espacio para tooltip arriba:
   ANTES:
     .hero-showcase__viewport {
       position: relative;
       display: flex;
       justify-content: center;
       align-items: center;
       min-height: 580px;
     }
   AHORA:
     .hero-showcase__viewport {
       position: relative;
       display: flex;
       justify-content: center;
       align-items: center;
       min-height: 620px;
       padding-top: 56px;        /* ← NUEVO */
       padding-bottom: 16px;
     }
   EFECTO: el tooltip puede vivir en top:12px sin colisionar con
   el phone (que está debajo).

   B.3) Tooltip position ajustada:
   ANTES:
     .hero-tooltip {
       position: absolute;
       top: -10px;       /* ← causaba solapamiento */
       ...
     }
   AHORA:
     .hero-tooltip {
       position: absolute;
       top: 12px;        /* ← ya no invade el phone */
       ...
     }
   EFECTO: el tooltip "Agenda online / Tus clientes reservan" se
   posiciona ARRIBA del teléfono, no DENTRO.

   B.4) Hero__left alineación:
   ANTES:
     .hero__left { max-width: 540px; justify-self: start; }
   AHORA:
     .hero__left {
       max-width: 540px;
       justify-self: start;
       text-align: left;       /* ← NUEVO */
     }
   EFECTO: garantiza alineación izquierda incluso si el navegador
   hereda text-align:center de algún padre.

   B.5) Mobile media query ajustada:
   ANTES:
       .hero-tooltip { font-size: 11px; padding: 6px 10px; top: -6px; }
       .hero-showcase__viewport { min-height: 520px; }
   AHORA:
       .hero-tooltip { font-size: 11px; padding: 6px 10px; top: 6px; }
       .hero-showcase__viewport { min-height: 560px; padding-top: 44px; }
   EFECTO: en mobile, tooltip arriba del phone sin colisión.


--------------------------------------------------------------------------------
3. QUÉ NO SE MODIFICÓ
--------------------------------------------------------------------------------

· Backend: 0 cambios en routers, schemas, DB, auth, middleware.
· Templates HTML (home.html): 0 cambios.
· landing.js: 0 cambios (el fix es solo en hero_showcase.js).
· components.css: 0 cambios.
· Multi-agent / tests / pytest: 0.
· Hero Showcase feature: ARIA tabs, autoplay, pause on hover, swipe
  mobile, keyboard nav, tooltip contextual — TODO intacto.
· Otros commits previos: 0 cambios.
· Endpoint `POST /api/v1/tenants/{id}/orders/{oid}/customer`: 0.
· Sidebar, Templates Fix, Link Hardening, otros V2.01: 0.


--------------------------------------------------------------------------------
4. REQUERIMIENTOS DE DESPLIEGUE
--------------------------------------------------------------------------------

· Worker: NO requiere cambio. Solo assets estáticos (CSS + JS).
· Cache busting: el HTML incluye `?v=v2.01-landing` y
  `?v=v2.01-hero-showcase` — fuerza reload tras deploy.
· Browser support: sin cambios. Compatible con todos los browsers
  modernos (Chrome 90+, Firefox 88+, Safari 14+, Edge 90+).
· No requiere migraciones Alembic.
· No requiere cambio en variables de entorno.
· No requiere rebuild Docker.

Verificación post-deploy:
  1. Hard refresh en `/` (Ctrl+Shift+R).
  2. Verificar que el phone screen es BLANCO con contenido visible.
  3. Verificar que el tooltip está ARRIBA del phone (no dentro).
  4. Click en cada tab (Página, Catálogo, QR, Pedidos, Pagos,
     Reservas, Promos, Estadísticas) → contenido cambia con fade.
  5. Verificar que el título "Tu negocio online, en minutos." está
     alineado a la IZQUIERDA, no centrado.


--------------------------------------------------------------------------------
5. PROCEDIMIENTO DE PRUEBA RECOMENDADO
--------------------------------------------------------------------------------

5.1 Visual smoke (manual)
  a) Hard refresh / (Ctrl+Shift+R) en desktop ≥1024px.
     - Phone screen debe ser BLANCO con contenido visible
       (avatar "N" Café Norte + 3 líneas + CTA "¡Bienvenido!").
     - Tab activo "Página" debe tener fondo púrpura con texto blanco.
     - Tooltip "Tu negocio presente / Landing con tu marca" debe estar
       ARRIBA del phone, no dentro.
  b) Esperar 4.5 segundos → debe cambiar automáticamente al
     tab "Catálogo" (mockup con 3 productos Latte/Torta/Ensalada).
  c) Click en "Reservas" → mockup con "Miércoles 22 Oct" + 8 slots
     horarios (algunos tachados como busy).
  d) Click en "Estadísticas" → mockup con 7-day bar chart (Lun a Dom).
  e) DevTools responsive: 375px iPhone SE.
     - Tabs son swipe horizontal con scroll-snap.
     - Tooltop compacto (11px, padding 6/10).
     - Phone screen mantiene contenido blanco.

5.2 Tests automatizados
  ```bash
  # Multi-agent (29 tests)
  C:\Python311embed\python.exe -m pytest multi-agent-wowhub -q

  # E2E TestClient
  C:\Python311embed\python.exe multi-agent-wowhub\_e2e_showcase.py
  ```
  Resultado esperado:
    OK data-hero-tabs: 1
    OK data-hero-mockup: 1
    OK data-hero-tooltip: 1
    OK role="tablist": 1
    OK role="tab": 8
    OK role="tabpanel": 1
    OK Beta · v2.01: 1
    OK MVP (should be 0): 0
    OK API Docs (should be 0): 0
    JS: Uses .phone__screen.innerHTML: True
    CSS: text-align: left in .hero__left: True

5.3 Visual regression (opcional, comparación pre/post)
  - Captura screenshot de / antes del fix (debería mostrar phone
    negro + tooltip dentro + contenido no visible).
  - Captura screenshot de / después del fix (debería mostrar phone
    blanco + tooltip arriba + contenido visible).
  - Comparar con hero_showcase_v6.png como referencia de propuesta.

5.4 Rollback
  Si el fix causa regresión visual:
  `git revert 0f4b422` (1 commit) restaura CSS + JS a estado 24d3012.
  El teléfono volverá a verse oscuro (estado buggy original).


--------------------------------------------------------------------------------
6. TRAZABILIDAD
--------------------------------------------------------------------------------

Commits relacionados:
  · 24d3012  feat(public): V2.01 Hero Showcase interactivo (versión
              inicial con los 3 bugs detectados)
  · 02b116c  docs: README_V2.01_AUDIT_BUGFIXES.txt (audit previo
              sin relación al hero)

Commit actual:
  · 0f4b422  fix(public): V2.01 Hero Showcase - contenido del phone
            invisible (3 bugs criticos)


================================================================================
FIN README_V2.99_HERO_SHOWCASE_HOTFIX.txt
================================================================================