================================================================================
README_V2.99_HERO_SHOWCASE_VISUAL.txt
WowHub · Release Notes Atómicos · V2.99
================================================================================

FECHA          : 2026-10-22
BUILD          : post 69d4334 (Refinamiento previo)
ALCANCE        : Hero Showcase · Refinamiento visual de 4 mock variants
ATOMICIDAD       : 1 commit único (d6ffcba)
RIESGO         : Muy bajo · Solo CSS (sin tocar JS ni HTML).
                Cache busting `?v=v2.01-landing` aplica en próximo deploy.
REVERTIBLE     : Sí · `git revert d6ffcba`.


--------------------------------------------------------------------------------
1. BASE (contexto)
--------------------------------------------------------------------------------

Tras el refinamiento V2.99 (commit 69d4334) que agrandó el título
y mejoró mock-orders, el usuario reportó (capturas del 23:58) que
los mockups restantes (Reservas, Catálogo, Pedidos) seguían
visualmente "todo blanco sin las imágenes respectivas". Además
pidió agrandar aún más el título del hero.

Inspección de las capturas:
  · mock-bookings: 8 slots visibles pero muy pálidos (font 10px,
    background --landing-success-soft sin distinción). Fecha
    "Miércoles 22 Oct" no se veía prominente.
  · mock-catalog: 3 productos con imágenes emoji 38x38 (muy
    pequeñas) y precios en texto plano sin badge.
  · mock-orders: mejorados pero aún #orden en 13px (vs título 16px).
  · hero__title: aún pequeño a 44-72px (vs Linear/Vercel 80-100px).


--------------------------------------------------------------------------------
2. CAMBIO ÚNICO
--------------------------------------------------------------------------------

ARCHIVO: app/static/css/templates/landing.css

2.A) hero__title más grande:
   ANTES:
     font-size: clamp(44px, 6vw, 72px);
     line-height: 1.05;
     font-weight: 800;
     letter-spacing: -0.025em;
     margin: 0 0 20px;
   AHORA:
     font-size: clamp(52px, 7vw, 84px);  // +18% min, +17% max
     line-height: 1.02;
     font-weight: 900;
     letter-spacing: -0.03em;
     margin: 0 0 24px;
   EFECTO: título "Tu negocio online, en minutos." ahora entre
   52-84px según viewport (líderes del sector usan 64-96px).

2.B) mock-page enriquecido:
   · avatar 36px → 52px (gradiente accent→accent-hover + shadow
     0 4px 12px rgba(108,92,231,0.30) + font 22px/800)
   · nombre 14px → 16px/700; sub 10px → 12px (margin-top 2px)
   · mock-line height 8px → 10px (más visibles)
   · hero border-bottom separator (1px solid landing-border)

2.C) mock-catalog enriquecido (3 productos):
   · producto img 38x38 → 52x52, font emoji 18 → 28px
   · imagen con inset shadow (profundidad)
   · producto strong 12 → 14px/700 (+ margin-bottom 2px)
   · precio span → badge con bg --landing-accent-soft + padding
     2/6 + radius 4 + align-self flex-start

2.D) mock-orders enriquecido:
   · padding 10/12 → 12/14, gap 10 → 12
   · #orden 13 → 16px/800 + letter-spacing -0.01em
   · "Hace X min" 10 → 11px/500 + margin-top 2px
   · amt 12 → 13px (mantiene accent-soft badge)
   · dot 10 → 12px + pseudo ::after con halo (rgba(0,184,148,0.18)
     para ok, rgba(253,203,110,0.22) para proc)

2.E) mock-bookings enriquecido (8 slots):
   · fecha header 12 → 14px/700 + emoji 📅 antes + border-bottom
   · slot font 10 → 12px/700 + letter-spacing 0.01em + padding 8/4
     + border 1.5px (transparent → ok: rgba(0,184,148,0.3);
     busy: var(--landing-border) + opacity 0.7)
   · busy ahora con border-color explícito + opacity 0.7 (no solo
     text-decoration)
   · ok color verde más oscuro #00a07a (mejor contraste que --landing-success)
   · hint 10 → 11px + padding-top 6px + border-top dashed +
     margin-top 6px (separador visual del date y los slots)

Total de cambios: 99 líneas +, 47 líneas -.


--------------------------------------------------------------------------------
3. QUÉ NO SE MODIFICÓ
--------------------------------------------------------------------------------

· app/templates/home.html: 0 cambios.
· app/static/js/hero_showcase.js: 0 cambios (autoplay, ARIA, swipe
  intactos).
· app/static/js/landing.js: 0 cambios.
· app/main.py: 0 cambios.
· Backend, schemas, routers, DB: 0.
· Multi-agent tests: 0 cambios.
· mock-qr, mock-payment, mock-promos, mock-stats: NO modificados
  en este commit. Los 4 que se refinaron son los que el usuario
  reportó explícitamente en sus capturas (Reservas, Catálogo,
  Pedidos + Página como mejora base).


--------------------------------------------------------------------------------
4. REQUERIMIENTOS DE DESPLIEGUE
--------------------------------------------------------------------------------

· Worker: NO requiere cambio. Solo CSS estático.
· Cache busting: el link CSS en home.html usa `?v=v2.01-landing`.
  Sugerido bumpar a `?v=v2.99b-landing` en próximo deploy para
  forzar reload inmediato.
· Browser support: sin cambios. CSS ::after pseudo-elements,
  pseudo-class :hover y clamp() son compatibles con todos los
  browsers modernos (Chrome 90+, Firefox 88+, Safari 14+, Edge 90+).
· No requiere migraciones Alembic.
· No requiere cambio en variables de entorno.
· No requiere rebuild Docker.

Verificación post-deploy:
  1. Hard refresh / (Ctrl+Shift+R).
  2. Verificar que el título es ahora 52-84px (notablemente mayor).
  4. Click en "Reservas" → 8 slots visibles con border verde/gris
     + fecha con emoji 📅 + "Reservas vía WhatsApp" con separator.
  5. Click en "Catálogo" → 3 productos con imágenes 52x52
     (☕, 🧁, 🥗) + precios en badge púrpura.
  6. Click en "Pedidos" → 4 cards con #orden 16px/800 + precio
     en badge + dot con halo (verde para ok, naranja para proc).
  7. Tab "Página" (default) → avatar 52px con gradiente púrpura.


--------------------------------------------------------------------------------
5. PROCEDIMIENTO DE PRUEBA RECOMENDADO
--------------------------------------------------------------------------------

5.1 Visual smoke (manual)
  a) Hard refresh / (Ctrl+Shift+R) en desktop ≥1280px.
     - Título: 52-84px (notablemente más grande).
     - Hover sobre showcase pausa autoplay (igual que antes).
  b) Click secuencial en los 8 tabs:
     1. Página: avatar grande con gradiente, 3 líneas, CTA.
     2. Catálogo: 3 productos con imágenes grandes.
     3. QR: hotspot dominante (no modificado).
     5. Pagos: tarjeta SVG grande (no modificado).
     6. Reservas: fecha con emoji, 8 slots con borders.
     7. Promos: 2 cards con badges -60/30 -50/15 (no modificado).
     8. Estadísticas: bar chart 7-day (no modificado).
  c) Mobile responsive 375px: tabs scroll horizontal, mockups
     mantienen tamaño relativo (todo está en %, em, clamp).
  d) Verificar "Beta · v2.01" en hero, sin "MVP" ni "API Docs".

5.2 Tests automatizados
  ```bash
  C:\Python311embed\python.exe multi-agent-wowhub\_verify_css.py
  C:\Python311embed\python.exe multi-agent-wowhub\_audit_public.py
  ```
  Resultado esperado: todos OK.

5.3 Lighthouse (opcional)
  - Performance: ≥90 (CSS < 28KB).
  - Accessibility: ≥95 (ARIA tabs intactos).
  - Best Practices: ≥90 (sin cambios en deps).

5.4 Rollback
  `git revert d6ffcba` (1 commit) restaura CSS al estado 1d7fcc1.
  Sin riesgo: solo son estilos.


--------------------------------------------------------------------------------
6. TRAZABILIDAD
--------------------------------------------------------------------------------

Commits relacionados a Hero Showcase:
  · 24d3012  feat(public): V2.01 Hero Showcase interactivo inicial
  · 0f4b422  fix: phone invisible (3 bugs críticos)
  · 69d4334  fix: titulo + mockups iniciales
  · d6ffcba  fix: mockups visualmente mas ricos (commit actual)

Feedback del usuario (3 capturas del 2026-10-18 23:58):
  - "Está bastante mejor, dado que ahora se ve si todo blanco sin
    las imagenes respectivas aun (corrige esto ultimo).
    Agranda un poco mas el tamaño de la fuente del texto:
    Tu negocio online, en minutos."

Mock variants mejorados:
  ✓ mock-page     (avatar 52px gradiente)
  ✓ mock-catalog  (img 52x52, badge precio)
  ✓ mock-orders   (#orden 16px, dot 12px con halo)
  ✓ mock-bookings (slot 12px con border, fecha con 📅)
  · mock-qr       (sin cambios — ya tenía buen contraste)
  · mock-payment  (sin cambios — SVG prominente)
  · mock-promos   (sin cambios — badges grandes)
  · mock-stats    (sin cambios — bars visibles)


================================================================================
FIN README_V2.99_HERO_SHOWCASE_VISUAL.txt
================================================================================