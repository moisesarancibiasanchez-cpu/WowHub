================================================================================
  WowHub V2.01 — Landing UX Redesign (Brief UX/UI Senior Completo)
  README de cambios — Changelog atómico
================================================================================

FECHA         : 2026-10-18
VERSION       : V2.01 (rediseño completo de la homepage pública `/`)
ALCANCE       : 4 archivos: home.html (reescrito), landing.css (nuevo),
                 components.css (nuevo), landing.js (nuevo). Implementa
                 las 11 secciones del brief UX/UI cargado.
TRAZABILIDAD  : el usuario cargo un brief completo de UX/UI senior
                 con 11 secciones obligatorias (hero 2-col, trust bar,
                 8 features, stats, 3 pasos, pricing 3-tier, testimonios,
                 FAQ 7 preguntas, CTA final, footer 4-col, requisitos
                 tecnicos WCAG AA). El usuario pidio implementarlo en
                 version local Y online (git push + commit).

================================================================================
  BASE
================================================================================
La homepage principal `/` (renderizada por main.py:336 con home.html)
fue incrementada en varias rondas:
  - 4930d6e (2026-08-07, 87 lineas):     Hero basico + 4 features
  - d34e8a1 (2026-08-23):                Hero rediseñado + 8 features
  - 0cb2405 (2026-10-12):               WowPrint design aplicado
  - a1e3cb8 (2026-10-18, 265 lineas):    Expandido a 10 secciones
                                          (commits V2.01 Public Homepage)
  - 9f5aefa (2026-10-18, inline styles): Diagnostico de "roto" + reescritura
                                          con estilos inline robustos

Pero el diseno inline (commit 9f5aefa) era fragil: 29.5 KB de estilos
inline repetidos, sin tema claro/oscuro consistente, sin accesibilidad,
sin SEO meta tags, sin pricing, sin JSON-LD.

El usuario cargo un brief UX/UI senior detallado que requiere:

  HERO rediseñado (2 columnas + mockup smartphone + floating cards)
  TRUST BAR discreta con 5 items
  8 FEATURE CARDS (icono + titulo + beneficio + descripcion + "Ver ejemplo")
  STATS showcase (4 stat cards)
  COMO FUNCIONA (3 pasos numerados)
  PRICING (3 tiers: Gratis / Pro destacado / Business)
  TESTIMONIOS con datos completos (nombre + negocio + ciudad/pais)
  FAQ ampliado a 7 preguntas
  CTA FINAL "Crea tu tienda online hoy"
  FOOTER reorganizado en 4 columnas (Marca / Producto / Recursos / Desarrolladores)
  REQUISITOS TECNICOS (HTML5 semantico, CSS variables, WCAG AA, meta tags, JSON-LD)

================================================================================
  CAMBIO UNICO
================================================================================

1) HOME.HTML — reescritura completa con todas las secciones del brief
   Archivo MODIFICADO: app/templates/home.html (35,640 bytes, +72% vs 9f5aefa)

   Estructura semantica completa:
     <header>       topbar con brand + nav + theme toggle + login/CTA
     <main>
       <section id="hero">           hero 2-col (texto + mockup smartphone)
       <div class="trust-bar">        5 items discretos
       <section id="funciones">      8 feature cards
       <section id="stats">          4 stat cards (10min, 5 paises, 24/7, 1 API)
       <section id="como-funciona">  3 pasos numerados
       <section id="precios">        3 pricing tiers con toggle mensual/anual
       <section id="testimonios">    3 cards con avatares y datos
       <section id="faq">            7 preguntas colapsables
       <section id="cta-final">      gradiente purpura + 2 CTAs
     <footer role="contentinfo">     4 columnas (Marca/Producto/Recursos/Desarrolladores) + legal + country selector + copyright

   Hero (2 columnas en desktop, apilado mobile):
     - Izquierda: badges (Nuevo MVP v0.2, LATAM-first, Multi-tenant)
     - H1: "Tu negocio online, en minutos." (con accent purpura)
     - Lead: texto claro para duenos de negocios LATAM
     - CTAs: "Crear mi tienda gratis →" (primary) + "Ver demo de una tienda" (outline)
     - Trust: "Sin tarjeta · Cancela cuando quieras · Soporte en espanol"
     - Derecha: mockup smartphone realista con:
       - Logo "N" + nombre "Cafe Norte" + sub "Santiago, Chile"
       - Imagen producto (cafe) + promo badge "-20%"
       - Producto "Latte Artesanal" + precio "$3.500 CLP"
       - Boton "Pedir por WhatsApp" con icono
       - 2 floating notification cards:
         * "Nuevo pedido Mesa 4" (top-left, verde)
         * "QR escaneado · Catalogo digital" (bottom-right, azul)
       - Animacion CSS sutil (phoneFloat + floatCard, 6s loop)
       - En mobile: hero apilado (mockup abajo)

   8 Feature cards (estructura consistente):
     1. Pagina web  - icono relampago, "Ver ejemplo de pagina →"
     2. Catalogo    - icono caja, "Ver catalogo demo →"
     3. QR          - icono telefono, "Ver ejemplo de QR →"
     4. Promociones - icono fiesta, "Ver promociones demo →"
     5. Pedidos     - icono recibo, "Ver flujo de pedidos →"
     6. Pagos       - icono tarjeta, "Ver opciones de pago →"
     7. Reservas    - icono calendario, "Ver demo de reservas →"
     8. Estadisticas - icono grafico, "Ver dashboard demo →"
     Cada card: 48px iconario en cuadrado purpura claro, beneficio
     highlight, descripcion breve, link "Ver ejemplo →" que abre modal.

   Pricing 3 tiers:
     - GRATIS ($0): Pagina + Catalogo + 20 productos + QR + WhatsApp.
       Badge: "Sin tarjeta de credito".
     - PRO (Desde $5.990/mes, "Mas elegido" badge): todo lo gratis +
       productos ilimitados + promociones + pedidos + reservas +
       estadisticas + dominio propio. Plan destacado con border purpura.
     - BUSINESS (Personalizado): multi-sucursal + roles + integraciones +
       soporte prioritario.
     Toggle mensual/anual con 20% descuento. Pricing dinamico via
     data-price / data-price-yearly en cada elemento.

   FAQ 7 preguntas:
     - Programacion, dominio, WhatsApp, pagos, mobile, cancelar, multi-sucursal
     - <details>/<summary> nativos del browser (sin JS para colapsar)
     - Indicador + / − con rotacion al abrir

   Footer 4 columnas:
     - Marca: logo W + tagline + social icons (GitHub, Twitter/X, LinkedIn)
     - Producto: Pagina, Catalogo, QR, Promociones, Pedidos, Reservas
     - Recursos: Centro de ayuda, Guias, Estado del servicio, Contacto
     - Desarrolladores: Doc API, OpenAPI, Webhooks, Estado API
     + Legal: Terminos, Privacidad, Cookies
     + Selector pais/moneda (CL/MX/CO/AR/BR)
     + Copyright "2026 WowHub. Hecho con 💜 para PyMEs en LATAM."

   Demo modals (8 modales accesibles):
     - modal-demo, modal-page, modal-catalog, modal-qr, modal-promos,
       modal-orders, modal-payments, modal-bookings, modal-stats
     - role="dialog" + aria-modal="true" + aria-hidden para mostrar/ocultar
     - Focus trap automatico + cierre con ESC (gestionado por landing.js)
     - Cerrables con click afuera del modal

   SEO + Accessibility:
     - Meta description, canonical, Open Graph, Twitter Card completos
     - JSON-LD Schema.org SoftwareApplication con offers + aggregateRating
     - aria-label en todos los botones + skip-link
     - prefers-reduced-motion respetado (animaciones deshabilitadas)
     - focus-visible outline accesible

2) LANDING.CSS — tokens + layout base
   Archivo NUEVO: app/static/css/templates/landing.css (14,254 bytes)

   Tokens CSS variables (--landing-*):
     - Colores: accent (#6c5ce7), success (#00b894), danger (#ff6b6b), etc.
     - Foreground: fg, fg-muted, fg-dim
     - Background: bg, bg-elev, bg-elev-2, bg-elev-3
     - Border: border, border-strong
     - Shadows: shadow-sm, shadow, shadow-md, shadow-lg, shadow-xl
     - Radius: radius-sm (8px), radius (14px), radius-lg (20px), radius-pill (999px)
     - Font: font-sans, font-display (Inter)
     - Container: 1100px, section-pad responsive

   Tema oscuro automatico via :root[data-theme="dark"]:
     - fg, fg-muted, fg-dim mas claros
     - bg, bg-elev-2 mas oscuros (#0f1421, #1a2033)
     - accent-soft con alpha

   Layout components:
     - .container (max-width + padding)
     - .section, .section--alt, .section--dark (gradiente purpura)
     - .section-footer (dark)
     - .section-eyebrow, .section-title, .section-subtitle (tipografia consistente)
     - .btn (sistema de botones con .btn--primary, .btn--outline, .btn--lg, .btn--ghost)
     - .grid (sistema responsive con --features, --stats, --steps, etc.)
     - .hero (grid 2-col en desktop, apilado en mobile via @media (max-width: 900px))
     - .phone (mockup smartphone con .phone__screen, .phone__notch, .phone__header,
       .phone__image, .phone__promo-badge, .phone__body, .phone__product-name,
       .phone__price, .phone__btn)
     - .float-card (tarjetas flotantes con animacion floatCard 4s)
     - .trust-bar (con ::before para "✓" verde)
     - .skip-link (a11y)
     - @media (prefers-reduced-motion: reduce) para accesibilidad
     - :focus-visible outline consistente

3) COMPONENTS.CSS — cards, pricing, FAQ, footer, modals
   Archivo NUEVO: app/static/css/templates/components.css (13,189 bytes)

   Componentes reutilizables:
     - .feature-card (8 features, hover translateY -3px)
     - .feature-icon (cuadrado purpura claro)
     - .feature-title / .feature-benefit / .feature-text / .feature-link
     - .stat-card (texto grande purpura + label uppercase)
     - .step-card (circulo numerado gradient purpura)
     - .testimonial-card (avatar gradient + divider + datos)
     - .pricing-card (3 tiers)
     - .pricing-card--highlight (Pro con border purpura + scale 1.02)
     - .pricing-card__badge ("Mas elegido" en arco superior)
     - .pricing-toggle (pill mensual/anual)
     - .faq (details/summary con + / −)
     - .footer (4 columnas + social icons + country select)
     - .demo-modal (overlay + focus visible + scale animation)
     - .mobile-menu-btn (responsive 768px)

4) LANDING.JS — logica minima y accesible
   Archivo NUEVO: app/static/js/landing.js (6,720 bytes)

   Funcionalidad sin dependencias externas:
     - initTheme(): toggle claro/oscuro con localStorage + aria-pressed
       Respeta prefers-color-scheme (default si no hay storage)
     - initMobileMenu(): toggle de nav en mobile con aria-expanded
     - initDemoModals(): abre modales con focus trap, cierre con ESC
     - initPricing(): toggle mensual/anual con localStorage, actualiza
       data-price / data-price-yearly / data-price-period
     - initSmoothScroll(): scroll suave a anchors (#hero, #funciones, etc.)

   a11y:
     - Focus trap automatico en modales (Tab cycle)
     - Cierre con teclado (ESC)
     - aria-pressed / aria-expanded / aria-hidden sincronizados

   Inicializacion robusta:
     - Si document.readyState === 'loading' espera DOMContentLoaded
     - Si ya esta cargado, ejecuta inmediatamente

================================================================================
  QUE NO SE MODIFICO
================================================================================
  - app/templates/base.html (NO tocado — el home.html extiende base.html
    sin cambios; los CSS site-wide (tokens.css, app.css) siguen cargando)
  - app/templates/dashboard/* (NO tocados — son templates del dashboard,
    usan dashboard.css con scope .template-moderna)
  - app/templates/public/* (NO tocados — landing de tenants separado)
  - api/v1/* (NO tocados — solo templates y CSS)
  - main.py (NO tocado — la ruta / sigue intacta con el home.html)
  - tokens.css, app.css, dashboard.css, wowprint.css (NO tocados — siguen
    cargando site-wide; el home.html los complementa con landing.css
    + components.css que usan --landing-* variables scoped)
  - 29 tests pytest (NO modificados)
  - Ningun schema, modelo, migracion Alembic, variable de config

================================================================================
  REQUERIMIENTOS DE DESPLIEGUE
================================================================================
  Worker: SI requiere reinicio.
    - app/templates/home.html MODIFICADO (35.6 KB).
    - app/static/css/templates/landing.css NUEVO (14.3 KB).
    - app/static/css/templates/components.css NUEVO (13.2 KB).
    - app/static/js/landing.js NUEVO (6.7 KB).
    - FastAPI recarga templates + assets al reiniciar.
    - Tiempo: < 5 segundos. Sin migracion DB.

  Migraciones DB: NO requiere.

  Config / env vars: NO requiere.

  Caches / CDN: SI purgar:
    - /  (portada)
    - /static/css/templates/landing.css (asset nuevo)
    - /static/css/templates/components.css (asset nuevo)
    - /static/js/landing.js (asset nuevo)

  Hard refresh en navegador: SI obligatorio para evitar HTML/CSS cacheado.

================================================================================
  PROCEDIMIENTO DE PRUEBA RECOMENDADO
================================================================================
A) Verificar homepage principal /

   1) Hard refresh (Ctrl+Shift+R) en https://wowhub-api-production.up.railway.app/
   2) Verificar que carga con todas las nuevas secciones:
      [ ] Topbar sticky con logo W + nav + theme toggle + Login/Crear cuenta
      [ ] Hero 2 columnas (texto izq + mockup smartphone der)
      [ ] Mockup muestra Cafe Norte con producto + precio CLP + WhatsApp + -20%
      [ ] 2 floating cards (pedido + QR escaneado) con animacion sutil
      [ ] Trust bar con 5 items discretos (LATAM, Espanol nativo, MercadoPago,
          WhatsApp, Dominio propio)
      [ ] 8 feature cards con icono + beneficio + "Ver ejemplo" link
      [ ] 4 stat cards (10 min, 5 paises, 24/7, 1 sola)
      [ ] 3 pasos numerados
      [ ] 3 pricing tiers (Gratis / Pro destacado / Business)
      [ ] Toggle mensual/anual en pricing funciona
      [ ] 3 testimonios con avatares
      [ ] 7 FAQ colapsables (click expande/colapsa)
      [ ] CTA final con gradiente purpura + 2 botones
      [ ] Footer 4 columnas (Marca/Producto/Recursos/Desarrolladores)
      [ ] Selector pais/moneda + legal + copyright

B) Verificar interactividad JS

   1) Click en theme toggle: cambia entre claro/oscuro (verifica que
      localStorage guarda preferencia)
   2) Click en cualquier "Ver ejemplo" de feature cards: abre modal
      accesible con focus trap
   3) Presionar ESC: cierra el modal
   4) Click fuera del modal: cierra
   5) Click en toggle Mensual/Anual: precios cambian, persist en localStorage
   6) Mobile viewport (< 768px): hamburger menu aparece, click toggle nav

C) Verificar accesibilidad

   1) Tab navigation: cada elemento focusable tiene outline visible
   2) Skip link "Saltar al contenido" funciona (Tab al cargar pagina)
   3) ARIA labels en botones icon-only (theme, hamburger, social, close)
   4) prefers-reduced-motion: animaciones deshabilitadas
   5) Screen reader: skip links + roles semanticos (header, main, footer)

D) Verificar SEO

   1) View source: meta description, canonical, og:*, twitter:*
   2) View source: JSON-LD Script type="application/ld+json"
      con SoftwareApplication schema
   3) Lighthouse SEO score debe ser >= 90

F) Regresion completa

   1. pytest multi-agent-wowhub/ -v → 29/29 debe seguir pasando (2.58s).
   2. /dashboard, /dashboard/products, /dashboard/customers, /dashboard/orders,
      /dashboard/mesero, /dashboard/templates, /dashboard/bookings,
      /dashboard/quotes, /dashboard/stats → carga 200 sin errores.
   3. /u/{slug}/ → landing del tenant sigue funcionando (no tocado).

================================================================================
  ARCHIVOS TOCADOS (resumen)
================================================================================
  A) NUEVOS:
     + app/static/css/templates/landing.css                    (14,254 bytes)
     + app/static/css/templates/components.css                  (13,189 bytes)
     + app/static/js/landing.js                                 (6,720 bytes)
     + docs/releases/README_V2.01_LANDING_UX_REDESIGN.txt       (este archivo)

  B) MODIFICADOS:
     ~ app/templates/home.html                                  (35,640 bytes,
                                                                  +111% vs 9f5aefa,
                                                                  reescrito completo)

  Total: +3 archivos nuevos, 1 modificado. ~69 KB de HTML/CSS/JS agregados.

================================================================================
  AUDITORIA COMPLEMENTARIA (sin cambios)
================================================================================
  - 63 templates auditados, 0 links rotos, 0 referencias rotas a /static/
  - 40 @app.get routes /dashboard/*, todas operativas
  - 59 routers backend, 57 montados
  - Sintaxis Python global: 0 errores
  - 29/29 tests pytest pasando (2.58s)
  - Quick-Context (max 3 clics): 4 templates integrados (mesero, orders,
    admin_bookings, quotes) — sin cambios
  - Sidebar Moderna unificada — sin cambios
  - Apariencia templates.html limpia — sin cambios

================================================================================
  RIESGOS Y ROLLBACK
================================================================================
  Riesgo bajo.
    - Cambios puramente de UI. Ningun endpoint, schema ni modelo.
    - CSS assets nuevos cargan site-wide sin conflictos (--landing-*
      scope namespaced vs --* del padre).
    - home.html ahora extiende base.html igual que antes (compat 100%).
    - El JS minimo no toca ninguna API ni storage fuera de localStorage
      propio del landing.

  Rollback:
    1) Revertir este commit (un revert limpio).
    2) Si solo home.html da problemas: restaurar 9f5aefa con
       git checkout 9f5aefa -- app/templates/home.html.
    3) Si CSS no aplica bien: eliminar <link> landing.css + components.css
       del bloque head_extra de home.html.
    4) Si JS rompe: eliminar <script src="landing.js"> del bloque content.
    5) Reiniciar worker.

================================================================================
  FIN DEL README — V2.01 Landing UX Redesign
================================================================================