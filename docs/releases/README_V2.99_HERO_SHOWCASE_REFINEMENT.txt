================================================================================
README_V2.99_HERO_SHOWCASE_REFINEMENT.txt
WowHub · Release Notes Atómicos · V2.99
================================================================================

FECHA          : 2026-10-22
BUILD          : post 0f4b422 (Hero Showcase visibility fix)
ALCANCE        : Hero Showcase · Refinamiento visual (UX feedback)
ATOMICIDAD     : 1 commit único (69d4334)
RIESGO         : Muy bajo · Solo CSS (sin tocar JS ni HTML).
                Cache busting `?v=v2.01-landing` fuerza reload.
REVERTIBLE     : Sí · `git revert 69d4334`.


--------------------------------------------------------------------------------
1. BASE (contexto)
--------------------------------------------------------------------------------

Tras el fix de visibilidad (commit 0f4b422), el Hero Showcase mostraba
correctamente el contenido del phone screen (fondo blanco con mockups
cambiando). Sin embargo, el usuario reportó 2 mejoras pendientes:

  1. "El título 'Tu negocio online, en minutos.' se ve pequeño,
     agranda un poco más el tamaño de la fuente".
  2. "Todo se ve blanco sin los respectivos visuales / imágenes",
     especialmente los cards de Pedidos (#124, #123, #122, #121)
     aparecían como cajas casi vacías sin jerarquía visual.

Cambios aplicados SOLO en CSS (sin tocar JS ni HTML del showcase).


--------------------------------------------------------------------------------
2. CAMBIO ÚNICO
--------------------------------------------------------------------------------

2.A) ARCHIVO: app/static/css/templates/landing.css

   A.1) Título del hero agrandado:
   ANTES:
     .hero__title {
       font-size: clamp(36px, 5vw, 56px);
       line-height: 1.1;
       font-weight: 800;
       color: var(--landing-fg);
       margin: 0 0 20px;
       letter-spacing: -0.02em;
     }
   AHORA:
     .hero__title {
       font-size: clamp(44px, 6vw, 72px);  // +22% min, +29% max
       line-height: 1.05;
       font-weight: 800;
       letter-spacing: -0.025em;
       color: var(--landing-fg);
       margin: 0 0 20px;
     }
   EFECTO: el título "Tu negocio online, en minutos." tiene ahora
   mayor jerarquía visual y se alinea con propuestas tipo Linear,
   Vercel, Stripe (clamp 44-72px según viewport).

   A.2) Phone mockup agrandado:
   ANTES:
     .phone {
       width: 290px;
       height: 600px;
       background: #1a1d28;
       border-radius: 44px;
       padding: 8px;
       ...
     }
   AHORA:
     .phone {
       width: 320px;   // +10% ancho
       height: 640px;  // +7% alto
       background: linear-gradient(180deg, #1a1d28 0%, #232735 100%);
       border-radius: 48px;
       padding: 10px;
       ...
     }
   EFECTO: el teléfono es más prominente, el contenido del screen
   es más legible. El background gradiente da un toque premium.

   A.3) Phone screen con fondo blanco explícito + inset shadow:
   ANTES:
     .phone__screen {
       width: 100%;
       height: 100%;
       background: #fff;
       border-radius: 36px;
       ...
     }
   AHORA:
     .phone__screen {
       width: 100%;
       height: 100%;
       background: #ffffff;
       border-radius: 38px;
       box-shadow: inset 0 0 0 1px rgba(23,32,51,0.05);
       ...
     }
   EFECTO: defensa-en-profundidad para garantizar contraste del
   screen contra el frame del phone.

   A.4) Mock-orders enriquecido visualmente:
   ANTES:
     .mock-order {
       display: flex;
       align-items: center;
       gap: 8px;
       padding: 6px 8px;
       border-radius: var(--landing-radius-sm);
       background: var(--landing-bg);
       border: 1px solid var(--landing-border);
     }
     .mock-order strong { font-size: 12px; color: var(--landing-fg); }
     .mock-order small  { font-size: 10px; color: var(--landing-fg-muted); }
     .mock-order .amt    { font-size: 11px; font-weight: 700; color: var(--landing-accent); }
     .dot {
       width: 8px; height: 8px;
       border-radius: 50%;
     }
   AHORA:
     .mock-order {
       display: flex;
       align-items: center;
       gap: 10px;                  // +2px
       padding: 10px 12px;         // +4/4px
       border-radius: var(--landing-radius-sm);
       background: var(--landing-bg-elev-2);  // gris muy suave
       border: 1px solid var(--landing-border);
       box-shadow: 0 1px 3px rgba(23,32,51,0.04);
       transition: transform 150ms ease;
     }
     .mock-order > div { ...; min-width: 0; }  // evita overflow
     .mock-order strong { font-size: 13px; ...; font-weight: 700; }  // +1px
     .mock-order small  { ...; margin-top: 1px; }
     .mock-order .amt {
       font-size: 12px;           // +1px
       font-weight: 800;
       color: var(--landing-accent);
       background: var(--landing-accent-soft);  // badge con bg
       padding: 3px 7px;
       border-radius: 6px;
       white-space: nowrap;
     }
     .dot {
       width: 10px; height: 10px;  // +2px
       border-radius: 50%;
       flex-shrink: 0;
       box-shadow: 0 0 0 3px rgba(0,184,148,0.15);  // halo verde
     }
   EFECTO: los cards de Pedidos ahora tienen fondo distinguible,
   precio destacado en badge púrpura, status dot con halo verde
   → mucho más visualmente rico sin saturar.


--------------------------------------------------------------------------------
3. QUÉ NO SE MODIFICÓ
--------------------------------------------------------------------------------

· app/templates/home.html: 0 cambios.
· app/static/js/hero_showcase.js: 0 cambios.
· app/static/js/landing.js: 0 cambios.
· app/main.py: 0 cambios (no se tocó el fix de routing).
· Backend, schemas, routers, DB: 0.
· Multi-agent tests: 0 cambios.
· Otros componentes del showcase: mock-page, mock-qr, mock-payment,
  mock-bookings, mock-promos, mock-stats NO modificados en este commit.
  Solo mock-orders recibió enriquecimiento porque era el que mostraba
  el tab activo en la captura del usuario.

Decisión: aplicar refinamiento quirúrgico solo a lo reportado.
Mock-page/catalog/etc. ya tienen backgrounds explícitos del fix
anterior (commit 0f4b422) y se ven correctamente. Si el usuario
reporta más, se ajustarán en commits futuros.


--------------------------------------------------------------------------------
4. REQUERIMIENTOS DE DESPLIEGUE
--------------------------------------------------------------------------------

· Worker: NO requiere cambio. Solo CSS estático.
· Cache busting: el link CSS en home.html usa `?v=v2.01-landing`.
  Para forzar reload inmediato de los usuarios, considerar bump a
  `?v=v2.99-landing` en próximo deploy. Por ahora el browser
  re-renderizará al refrescar.
· Browser support: sin cambios. CSS clamp() y box-shadow
  inset son compatibles con todos los browsers modernos.
· No requiere migraciones Alembic.
· No requiere cambio en variables de entorno.
· No requiere rebuild Docker.

Verificación post-deploy:
  1. Hard refresh / (Ctrl+Shift+R).
  2. Verificar que el título "Tu negocio online, en minutos."
     ahora es notablemente más grande (~44-72px según viewport).
  3. Verificar que el phone mockup es más grande (320x640).
  4. Click en tab "Pedidos" → ver cards con fondo gris-suave y
     precio $3.500 en badge púrpura.
  5. Status dots de "proc" deben tener halo verde animado.


--------------------------------------------------------------------------------
5. PROCEDIMIENTO DE PRUEBA RECOMENDADO
--------------------------------------------------------------------------------

5.1 Visual smoke (manual)
  a) Hard refresh / (Ctrl+Shift+R) en desktop ≥1280px.
     - Título debe ocupar 2 líneas (no 3) y verse más prominente.
     - Phone debe ser visiblemente más grande.
     - Tab "Pedidos" activo → 4 cards #121-#124 con:
       * Fondo gris-suave distinguible
       * Dot verde/naranja con halo a la izquierda
       * Precio $X.XXX en badge púrpura a la derecha
  b) Click en "Catálogo" → 3 productos (Latte, Torta, Ensalada).
  c) Click en "Reservas" → 8 slots horarios.
  d) Click en "Estadísticas" → 7-day bar chart (no modificado).
  e) DevTools responsive 375px iPhone SE.
     - Título debe escalar a ~60px (clamp responde al viewport).
     - Phone mantiene proporción 320x640.

5.2 Tests automatizados
  ```bash
  C:\Python311embed\python.exe multi-agent-wowhub\_verify_css.py
  C:\Python311embed\python.exe multi-agent-wowhub\_audit_public.py
  ```
  Resultado esperado: todos los checks pasan.

5.3 Comparación visual (opcional)
  - Captura screenshot de / ANTES de este commit.
  - Hard refresh → Captura screenshot DESPUÉS.
  - Comparar tamaño de título y riqueza de mock-orders.

5.4 Rollback
  `git revert 69d4334` (1 commit) restaura CSS al estado 1abb402.
  Sin riesgo de regresión: solo son estilos.


--------------------------------------------------------------------------------
6. TRAZABILIDAD
--------------------------------------------------------------------------------

Commits relacionados:
  · 24d3012  feat(public): V2.01 Hero Showcase interactivo (versión
              inicial, 3 bugs de visibilidad detectados tras deploy)
  · 0f4b422  fix(public): V2.01 Hero Showcase - phone invisible
              (3 fixes críticos: JS + CSS)
  · 69d4334  fix(public): V2.99 Hero Showcase - titulo + mockups
              visuales (commit actual)

Feedback del usuario:
  Captura del 2026-10-18 23:49 → "Está bastante mejor, dado que
  ahora ya no se ve Negro, pero si todo blanco sin las imagenes
  respectivas. Agranda un poco mas el tamaño de la fuente del
  texto: Tu negocio online, en minutos."


================================================================================
FIN README_V2.99_HERO_SHOWCASE_REFINEMENT.txt
================================================================================