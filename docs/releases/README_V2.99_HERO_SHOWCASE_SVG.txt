================================================================================
README_V2.99_HERO_SHOWCASE_SVG.txt
WowHub · Release Notes Atómicos · V2.99
================================================================================

FECHA          : 2026-10-22
BUILD          : post d6ffcba (V2.99b mockups enriquecidos)
ALCANCE        : Hero Showcase · Ilustraciones SVG reales (Catálogo + QR)
ATOMICIDAD     : 1 commit único (6b32f76)
RIESGO         : muy bajo · solo JS (visual factories) + CSS
                (degradados y animación de scan).
REVERTIBLE     : Sí · `git revert 6b32f76`.


--------------------------------------------------------------------------------
1. BASE (contexto)
--------------------------------------------------------------------------------

Tras V2.99b (commit d6ffcba) que enriqueció los mockups con
backgrounds, badges de precio y dots con halo, el usuario reportó
(00:10):

  "Se continúa presentando mismo error donde las imágenes relativas
   a los productos NO se visualizan (Ver imágenes anteriores)."

Diagnóstico:
  · Los 3 productos del mock-catalog usaban emojis (☕, 🧁, 🥗) sobre
    cuadrados de color 52x52 con font 28px. Aunque técnicamente se
    renderizaban, NO se percibían como "imágenes de producto"
    (parecían caracteres tipográficos).
  · El mock-qr mostraba solo 9 cuadritos (3x3) sin los 3 "finder
    patterns" característicos de un QR real. Parecía un patrón
    abstracto, no un código QR reconocible.

Decisión: reemplazar los emojis por **ilustraciones SVG inline
detalladas** que representen visualmente cada producto, y rehacer
el QR como SVG 25x25 con sus 3 esquinas + módulos de datos.


--------------------------------------------------------------------------------
2. CAMBIO ÚNICO
--------------------------------------------------------------------------------

2.A) ARCHIVO: app/static/js/hero_showcase.js (13,889 → 24,650 bytes)

   A.1) Mock-catalog — 3 productos con SVG inline:

   LATTE — taza humeante:
       <svg viewBox="0 0 48 48" width="40" height="40">
         <defs><linearGradient id="cupGrad" x1="0%" y1="0%" x2="0%" y2="100%">
           <stop offset="0%" stop-color="#f4f1ec"/>
           <stop offset="100%" stop-color="#d4c5b3"/>
         </linearGradient></defs>
         <!-- 3 paths de vapor animado -->
         <!-- Taza con asa lateral -->
         <!-- Café líquido (elipse #3e2723) -->
         <!-- Plato (elipse 50% opacity) -->
       </svg>
     · Vapor: 3 paths Q-curves con stroke blanco y opacity variable.
     · Taza: path rectangular con bordes redondeados.
     · Asa: curva en forma de asa lateral.
     · Café líquido: elipse oscura encima de la taza.
     · Plato: elipse inferior con opacity 0.5.

   TORTA — cupcake con frosting rosa + cherry:
       Wrapper: path trapezoidal marrón (#d4a574) con 5 líneas
                verticales (efecto papel cupcake).
       Frosting: path con 3 curvas Q (efecto swirl) en rosa (#f472b6).
       Highlights: 2 elipses blancas con opacity 0.6 (brillos).
       Cherry: círculo rojo (#dc2626) con tallo verde (#16a34a).

   ENSALADA — bowl con hojas verdes + tomates cherry:
       Bowl: path azul claro (#74b9ff) con borde (#0984e3).
       3 hojas: elipses verdes en gradiente (#16a34a, #22c55e)
               con rotate(-20/+5/+25) — direcciones distintas.
       2 tomates cherry: círculos rojos (#ef4444).
       Highlight: línea blanca con opacity 0.4.

   A.2) Mock-qr — SVG 25x25 con QR realista:

   El SVG incluye:
   · 3 FINDER PATTERNS (esquinas características del QR):
     - Top-left: rect 0,0 7x7 + #1-#1 5x5 blanco + #2-#2 3x3 negro
     - Top-right: rect 18,0 7x7 + idem
     - Bottom-left: rect 0,18 7x7 + idem
   · Módulos de datos (~70 cuadrados 1x1) distribuidos en
     patrón pseudo-aleatorio para simular datos QR reales.
   · Etiqueta "Mesa 1" con emoji 🪑 + background accent-soft.
   · Container .mock-qr__svg-wrap 144x144 con border 2px.

   Antes: <div class="mock-qr__pattern"> con 9 divs qr-cell.
   Ahora: <svg viewBox="0 0 25 25"> con ~75 rects posicionados.

2.B) ARCHIVO: app/static/css/templates/landing.css

   B.1) .mock-product__img — agrandado a 60x60:
     ANTES: 52x52, font-size 28px (emoji).
     AHORA: 60x60, overflow:hidden, position:relative.
            SVG dentro tiene z-index:1 (sobre el highlight).
            ::before con radial-gradient (luz desde una esquina)
            específico por producto.

   B.2) Selectores específicos por producto:
     .mock-product__img--latte:
       linear-gradient(135deg, #fde68a, #fb923c 50%, #f87171)
       (cálido: amarillo → naranja → rojo)
     .mock-product__img--cake:
       linear-gradient(135deg, #c084fc, #ec4899 50%, #db2777)
       (magenta: púrpura → rosa → rojo oscuro)
     .mock-product__img--salad:
       linear-gradient(135deg, #6ee7b7, #34d399 50%, #74b9ff)
       (turquesa-verde: menta → verde → celeste)

   B.3) .mock-qr reescrito:
     ANTES: .mock-qr__pattern con grid 3x3 + 9 .qr-cell.
     AHORA: .mock-qr__svg-wrap 144x144 + border 2px + shadow +
            .mock-qr__svg 100% + .mock-qr__scan animado.

   B.4) .mock-qr__scan nuevo:
     position:absolute, gradient horizontal (transparent → accent →
     transparent), animation qrScan 2s.

   B.5) @keyframes qrScan actualizado:
     ANTES: translateY(80px) (size 96px).
     AHORA: translateY(116px) (size 144px - nuevo container).


--------------------------------------------------------------------------------
3. QUÉ NO SE MODIFICÓ
--------------------------------------------------------------------------------

· Estructura HTML del showcase (data-hero-*): 0 cambios.
· Autoplay, pause hover, swipe mobile, keyboard ARIA: 0 cambios.
· Tooltip contextual: 0 cambios.
· Float cards: 0 cambios.
· Tabs visuales: 0 cambios.
· .mock-page, .mock-bookings, .mock-orders, .mock-payment,
  .mock-promos, .mock-stats: NO modificados (los productos y QR
  eran los que el usuario mencionó explícitamente).
· Backend, schemas, routers, DB: 0.
· Multi-agent tests: 0 cambios.


--------------------------------------------------------------------------------
4. REQUERIMIENTOS DE DESPLIEGUE
--------------------------------------------------------------------------------

· Worker: NO requiere cambio.
· Cache busting: el link CSS usa `?v=v2.01-landing`. Sugerido
  bumpar a `?v=v2.99c-landing` en próximo deploy.
· Browser support: sin cambios. SVG inline funciona en
  Chrome/Firefox/Safari/Edge modernos.
· No requiere migraciones Alembic.
· No requiere cambio en variables de entorno.
· No requiere rebuild Docker.

Verificación post-deploy:
  1. Hard refresh / (Ctrl+Shift+R).
  2. Click en "Catálogo" → ver 3 ilustraciones SVG:
     - Latte: taza con vapor, café oscuro, plato
     - Torta: cupcake con frosting rosa + cherry
     - Ensalada: bowl azul con hojas verdes + tomates
  3. Click en "QR" → ver código QR realista con 3 esquinas
     características + módulos de datos + label "🪑 Mesa 1".
  4. Verificar que el scan line animado cruza verticalmente
     sobre el QR (translateY 0 → 116px cada 2s).
  5. Las 3 imágenes de producto NO son emojis sino ilustraciones
     SVG con detalles (vapor, frosting, hojas).


--------------------------------------------------------------------------------
5. PROCEDIMIENTO DE PRUEBA RECOMENDADO
--------------------------------------------------------------------------------

5.1 Visual smoke (manual)
  a) Hard refresh / (Ctrl+Shift+R).
  b) Click "Catálogo":
     - Latte: taza con 3 trazos de vapor + café + plato
     - Torta: cupcake con líneas verticales en wrapper + frosting
       rosa + cherry rojo con tallo
     - Ensalada: bowl azul + 3 hojas verdes + 2 tomates rojos
  c) Click "QR":
     - 3 esquinas grandes (7x7) con cuadrados blancos dentro
     - Módulos negros 1x1 distribuidos (~70)
     - Border 2px alrededor
     - Scan line púrpura cruzando verticalmente
     - Label "🪑 Mesa 1" con fondo púrpura claro
  d) Click "Pedidos", "Reservas", "Pagos", "Promos", "Estadísticas",
     "Página": comportamiento sin cambios (no modificados).

5.2 Tests automatizados
  ```bash
  C:\Python311embed\python.exe multi-agent-wowhub\_verify_v299c.py
  ```
  Resultado esperado:
    Latte SVG (cupGrad): True
    Cake SVG (f472b6 pink): True
    Salad SVG (Bowl): True
    QR SVG (Mesa 1 label): True
    Has 3 finder patterns: True
    mock-product__img--latte/cake/salad: True

5.3 Comparación visual
  - Captura ANTES: emojis pequeños (28px) sobre cuadrados.
  - Captura DESPUÉS: ilustraciones SVG detalladas (40×40) sobre
    cuadrados con gradientes diferenciados por producto.

5.4 Rollback
  `git revert 6b32f76` (1 commit) restaura a estado c4fbf8c.
  Riesgo: cero (solo son assets estáticos).


--------------------------------------------------------------------------------
6. TRAZABILIDAD
--------------------------------------------------------------------------------

Commits relacionados a Hero Showcase:
  · 24d3012  feat(public): V2.01 Hero Showcase interactivo (inicial)
  · 0f4b422  fix: phone invisible (3 bugs críticos)
  · 69d4334  fix: titulo + mockups iniciales
  · d6ffcba  fix: mockups visualmente mas ricos (4 variants)
  · 6b32f76  fix: ilustraciones SVG reales para Catalogo y QR (commit actual)

Feedback del usuario:
  "Se continúa presentando mismo error donde las imágenes relativas
   a los productos NO se visualizan."

Mock variants mejorados en este commit:
  ✓ mock-catalog (3 ilustraciones SVG inline detalladas)
  ✓ mock-qr (SVG 25x25 con 3 finder patterns + datos)

Mock variants sin cambios (intencionales):
  · mock-page (avatar gradiente, sin contenido grafico necesario)
  · mock-bookings (slots numericos, sin necesidad de imagen)
  · mock-orders (ordenes de texto, sin necesidad de imagen)
  · mock-payment (tarjeta SVG ya estaba presente)
  · mock-promos (badges + emojis ya eran claros)
  · mock-stats (bar chart ya era visual)


================================================================================
FIN README_V2.99_HERO_SHOWCASE_SVG.txt
================================================================================