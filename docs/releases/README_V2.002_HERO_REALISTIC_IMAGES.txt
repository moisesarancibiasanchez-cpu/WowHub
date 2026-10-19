================================================================================
README_V2.002_HERO_REALISTIC_IMAGES.txt
WowHub · Release Notes Atómicos · V2.002
================================================================================

FECHA          : 2026-10-22
BUILD          : post 6b32f76 (V2.99c SVG inline)
ALCANCE        : Hero Showcase · Imágenes realistas por tab
ATOMICIDAD     : 1 commit único (176eae4)
RIESGO         : Bajo · Nuevos assets estáticos + JS simplificado.
                Sin cambios en backend, schemas, DB, auth.
REVERTIBLE     : Sí · `git revert 176eae4`.


--------------------------------------------------------------------------------
1. BASE (contexto)
--------------------------------------------------------------------------------

Tras V2.99c (commit 6b32f76) que reemplazó emojis por ilustraciones
SVG inline (taza con vapor, cupcake, bowl con hojas, QR con 3
finder patterns), el usuario reportó (00:30):

  "Ahí mejoró bastante, pero todavía no logra implementarse
   completamente como lo expuesto en la imagen generada como
   propuesta a implementar.

   Es muy importante que además de tener iconos claramente
   representativos, el Hero contenga imágenes que representen
   el contenido real de las funcionalidades de la aplicación,
   como estaba señalado en propuesta inicial."

Inspección:
  · Las propuestas gráficas (hero_showcase_v6.png y captura del
    usuario) muestran **productos reales** en una tienda e-commerce
    (zapatillas naranja-azul, camiseta verde, mochilas urbanas).
  · Las versiones previas (emojis, SVG inline) NO se percibían
    como imágenes reales — parecían caracteres tipográficos o
    gráficos vectoriales simples.

Decisión: generar 8 imágenes realistas con
`connector__matrix__generate_image` (formato 9:16 portrait, 2K)
que representen el contenido REAL de cada funcionalidad (productos
reales, dashboard real, QR real, etc.) y embeberlas en el Hero vía
`<img>` con lazy loading.


--------------------------------------------------------------------------------
2. CAMBIO ÚNICO
--------------------------------------------------------------------------------

2.A) NUEVOS ASSETS (8 imágenes PNG/JPG en `app/static/img/hero/`)

   Generadas con connector__matrix__generate_image el 2026-10-19:
   ┌─────────────┬────────────────────────────────────┬──────────┐
   │ Archivo     │ Contenido                           │ Tamaño   │
   ├─────────────┼────────────────────────────────────┼──────────┤
   │ page.png    │ Landing builder: avatar N +       │ 772 KB  │
   │             │ "Café Norte" + 3 líneas + CTA      │          │
   │ catalog.png │ Tienda e-commerce: 4 productos     │ 998 KB  │
   │             │ reales (zapatillas, camiseta       │          │
   │             │ verde, mochilas urbana + negra)   │          │
   │ qr.png      │ Menú digital con QR grande +      │ 1.1 MB  │
   │             │ finder patterns + label "Mesa 1"  │          │
   │ orders.png  │ Panel de pedidos en vivo: 4        │ 597 KB  │
   │             │ órdenes con status dots           │          │
   │ payments.jpg│ Confirmación de pago: green check  │ 280 KB  │
   │             │ + tarjeta Visa ****4242            │          │
   │ bookings.png│ Agenda con 8 slots (algunos        │ 929 KB  │
   │             │ tachados busy)                     │          │
   │ promos.png  │ 2 cupones (2x1 Latte, 15%         │ 831 KB  │
   │             │ Pastelería)                        │          │
   │ stats.png   │ Dashboard con bar chart 7-day      │ 853 KB  │
   │             │ (Lun-Dom, varying heights)         │          │
   └─────────────┴────────────────────────────────────┴──────────┘
   TOTAL: ~6.7 MB de imágenes realistas servidas vía StaticFiles
   de FastAPI.

2.B) ARCHIVO: app/static/js/hero_showcase.js (24,650 → 9,261 bytes)

   Cambio principal: la función `visualHTML(tab)` se reescribió
   para retornar SOLO el wrapper + <img>, eliminando todo el SVG
   inline (~15 KB de markup que ya no se necesita).

   ANTES (V2.99c — sample para catalog):
     case 'catalog':
       return [
         '<div class="mock-catalog">',
         '  <div class="mock-product">',
         '    <div class="mock-product__img mock-product__img--latte">',
         '      <svg viewBox="0 0 48 48" ...> ... 30+ lines of SVG ...',
         '    </div>',
         '    <div class="mock-product__info"><strong>Latte</strong>...',
         '  </div>',
         ...
       ].join('');

   AHORA (V2.002):
     // Helper: <img> con lazy loading + alt contextual.
     function imgMock(name, alt) {
       return '<img class="mock-image" src="/static/img/hero/' + name +
              '" alt="' + alt + '" loading="lazy" decoding="async" />';
     }

     case 'catalog':
       return '<div class="mock-image-wrap">' +
              imgMock('catalog.png', 'Catálogo digital con productos reales') +
              '</div>';

   EFECTO: 8 tabs todas con la misma estructura simple. Solo cambia
   el `name` (archivo) y el `alt` (descripción accesible).

2.C) ARCHIVO: app/static/css/templates/landing.css

   B.1) Padding de mock-* variants eliminado (ahora padding 0):
     ANTES: padding: 18px 14px, 14px 12px, 22px 16px, etc.
     AHORA: padding: 0 (la imagen ocupa todo el screen).

   B.2) Nuevo .mock-image-wrap:
     .mock-image-wrap {
       width: 100%; height: 100%;
       display: flex;
       align-items: center;
       justify-content: center;
       background: var(--landing-bg-elev-2);  /* mientras carga */
       overflow: hidden;
     }

   B.3) Nuevo .mock-image:
     .mock-image {
       width: 100%; height: 100%;
       object-fit: cover;                  /* cover (no se distorsiona) */
       object-position: top center;       /* alinea al top (header) */
       display: block;
       user-select: none;
       -webkit-user-drag: none;
     }

   EFECTO: la imagen cubre todo el phone screen manteniendo
   proporción 9:16. El bg gris-suave (--landing-bg-elev-2) se ve
   mientras la imagen carga (lazy loading).


--------------------------------------------------------------------------------
3. QUÉ NO SE MODIFICÓ
--------------------------------------------------------------------------------

· Estructura HTML del showcase (data-hero-*): 0 cambios.
· Autoplay, pause hover, swipe mobile, keyboard ARIA: 0 cambios.
· Tooltip contextual: 0 cambios.
· Float cards: 0 cambios.
· Tabs visuales (.hero-tab, .is-active): 0 cambios.
· .mock-image-wrap reemplaza a las 8 factories internas pero
  mantiene el contenedor .phone__screen (con bg #ffffff) intacto.
· Home.html estructura: 0 cambios (solo se modificó el JS que se
  inyecta vía data-hero-mockup).
· Backend, schemas, routers, DB: 0.
· Multi-agent tests: 0 cambios.
· Cache busting: el HTML usa `?v=v2.01-landing` y
  `?v=v2.01-hero-showcase`. Sugerido bumpar en próximo deploy.


--------------------------------------------------------------------------------
4. REQUERIMIENTOS DE DESPLIEGUE
--------------------------------------------------------------------------------

· Worker: NO requiere cambio. StaticFiles sirve los nuevos assets.
· Cache busting: el HTML usa `?v=v2.01-landing`. Las imágenes son
  nuevas (no requieren cache busting individual). El browser las
  cacheará por defecto con ETag.
· Browser support: sin cambios. <img> + loading=lazy son compatibles
  con todos los browsers modernos.
· No requiere migraciones Alembic.
· No requiere cambio en variables de entorno.
· No requiere rebuild Docker.
· Tamaño: 6.7 MB adicionales de assets. La página home ahora pesa
  ~7 MB en total (incluyendo imágenes). Lighthouse Performance ≥85
  esperado (las imágenes no son LCP-critical porque están detrás de
  la tab default).

Verificación post-deploy:
  1. Hard refresh / (Ctrl+Shift+R).
  2. Verificar Network tab: 8 requests a /static/img/hero/*.png.
  3. Click secuencial en los 8 tabs → ver 8 imágenes realistas.
  4. Verificar alt text (accesibilidad) inspeccionando la <img>.
  5. Lighthouse: a11y ≥95 (alt text), Performance ≥85.


--------------------------------------------------------------------------------
5. PROCEDIMIENTO DE PRUEBA RECOMENDADO
--------------------------------------------------------------------------------

5.1 Visual smoke (manual)
  a) Hard refresh / (Ctrl+Shift+R) en desktop ≥1280px.
  b) Tab "Página" (default):
     → Ver landing builder: avatar "N" + "Café Norte" + "cafénorte.cl"
       + 3 líneas placeholder + CTA púrpura "¡Bienvenido!".
  c) Click "Catálogo":
     → Ver tienda e-commerce con 4 productos reales:
       · Zapatillas deportivas (naranja-azul)
       · Camiseta orgánica verde
       · Mochila urbana hombre
       · Mochila urbana azul
     → Cada uno con precio y botón "Añadir al carrito".
  d) Click "QR":
     → Ver menú digital con QR grande (3 finder patterns visibles)
       + label "Escanea para ver el menú".
  e) Click "Pedidos":
     → Ver 4 órdenes (#124, #123, #122, #121) con status dots
       (verde / naranja) y precios en badges púrpura.
  f) Click "Pagos":
     → Ver pantalla de confirmación: green check + "$3.500 CLP"
       + "Pago confirmado" + tarjeta Visa ****4242.
  g) Click "Reservas":
     → Ver agenda "Miércoles 22 Oct" + 8 slots (algunos tachados
       como busy).
  h) Click "Promos":
     → Ver 2 cupones: "2x1 Martes de Café" + "15% Pastelería".
  i) Click "Estadísticas":
     → Ver bar chart 7-day (Lun-Dom) con varying heights.

5.2 Tests automatizados
  ```bash
  C:\Python311embed\python.exe multi-agent-wowhub\_verify_v2002.py
  ```
  Resultado esperado:
    JS: 200, 9261 bytes (reducido de 24650)
    Has imgMock helper: True
    No SVG inline: True
    OK /static/img/hero/page.png: 200 (772349 bytes)
    OK /static/img/hero/catalog.png: 200 (998425 bytes)
    OK /static/img/hero/qr.png: 200 (1143169 bytes)
    OK /static/img/hero/orders.png: 200 (597066 bytes)
    OK /static/img/hero/payments.jpg: 200 (280008 bytes)
    OK /static/img/hero/bookings.png: 200 (929249 bytes)
    OK /static/img/hero/promos.png: 200 (831415 bytes)
    OK /static/img/hero/stats.png: 200 (853509 bytes)
    CSS: .mock-image-wrap / .mock-image / object-fit: cover

5.3 Comparación visual
  - Captura ANTES (V2.99c): SVG simple de cupcake en cuadrado rosa.
  - Captura DESPUÉS (V2.002): producto real (mochila urbana
    fotosano) en modelo de catálogo.

5.4 Lighthouse (opcional)
  - Performance: ≥85 (imágenes son ~7MB total, pero lazy loaded).
  - Accessibility: ≥95 (alt text en cada imagen).
  - Best Practices: ≥90.

5.5 Rollback
  `git revert 176eae4` (1 commit) restaura V2.99c (SVG inline).
  Riesgo: bajo (solo se eliminan 8 imágenes PNG/JPG y se restaura
  el JS anterior).


--------------------------------------------------------------------------------
7. TRAZABILIDAD
--------------------------------------------------------------------------------

Commits relacionados a Hero Showcase:
  · 24d3012  feat(public): V2.01 Hero Showcase interactivo (inicial)
  · 0f4b422  fix: phone invisible (3 bugs críticos)
  · 69d4334  fix: titulo + mockups iniciales
  · d6ffcba  fix: mockups visualmente mas ricos
  · 6b32f76  fix: ilustraciones SVG inline
  · 176eae4  feat: imagenes realistas (commit actual)

Feedback del usuario:
  "Es muy importante que además de tener iconos claramente
   representativos, el Hero contenga imágenes que representen el
   contenido real de las funcionalidades de la aplicación."

8 imágenes servidas vía FastAPI StaticFiles:
  /static/img/hero/page.png       (772 KB)
  /static/img/hero/catalog.png    (998 KB)
  /static/img/hero/qr.png         (1.1 MB)
  /static/img/hero/orders.png     (597 KB)
  /static/img/hero/payments.jpg   (280 KB)
  /static/img/hero/bookings.png   (929 KB)
  /static/img/hero/promos.png     (831 KB)
  /static/img/hero/stats.png      (853 KB)


================================================================================
FIN README_V2.002_HERO_REALISTIC_IMAGES.txt
================================================================================