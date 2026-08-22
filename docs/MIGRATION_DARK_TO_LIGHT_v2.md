# Plan de Migración — WowHub UI v2 (light + dark sidebar)

> **Objetivo:** Pasar de la estética dark actual (`#0b0d12` + `--accent: #7c5cff`) a la estética del prototipo desplegado (`#f5f7fb` main + sidebar dark `#111827` + acento `#6c5ce7`), sin romper ninguna página existente, con cero downtime, en 7 fases incrementales testeables.

---

## 📐 Inventario actual (estado del repo)

| Archivo | Líneas | Rol |
|---|---|---|
| `app/static/css/tokens.css` | 198 | Design tokens (DARK) |
| `app/static/css/app.css` | 623 | Shell, topbar, formularios, tablas, modales |
| `app/static/css/ai.css` | 814 | Panel AI lateral derecho |
| `app/static/css/landing-pro.css` | 596 | Landing pública de marketing |
| `app/static/js/app.js` | 431 | Auth + API + token store |
| `app/static/js/ai.js` | 1 009 | Chat panel |
| `app/templates/base.html` | 37 | Shell público (topbar) |
| `app/templates/dashboard/base.html` | 382 | Shell admin (topbar + sidebars + impersonation banner) |
| Templates dashboard | 13 | Extienden `dashboard/base.html` |
| Templates public | 6 | `landing.html`, `catalog.html`, `booking.html`, `loyalty.html`, `404.html`, `error.html` |
| Templates auth | 4 | `login.html`, `register.html`, `forgot_password.html`, `reset_password.html` |
| Templates legal | 3 | `terms.html`, `privacy.html`, `cookies.html` |
| Templates payments | 1 | `mock_checkout.html` |
| Templates misc | 2 | `home.html`, `home_pro.html` |

**Estrategia clave:** la migración se hace por **tokens primero** (porque los nombres semánticos no cambian), luego por **componentes**, luego por **layouts**, y finalmente por **páginas**. Esto permite mergear cada fase sin tocar las páginas que aún no han migrado.

---

## 🗺️ Fases (orden estricto)

### **FASE 0 — Baseline y rama**  (30 min)

| Paso | Acción | Archivo |
|---|---|---|
| 0.1 | Crear rama `feat/ui-v2-light` | `git` |
| 0.2 | Tomar screenshots de las 30+ páginas actuales (Playwright/Chromium) | `docs/baseline/` |
| 0.3 | Ejecutar suite de tests actual y guardar baseline | `pytest` |
| 0.4 | Crear `docs/baseline/perf.json` (LCP, CLS, INP) | Lighthouse |

**Criterio de salida:** branch listo, baseline visual y de performance capturado.

---

### **FASE 1 — Tokens v2 (SKIN SWAP, 0 templates tocados)**  ⬅️ **aquí ya tienes el artefacto** (`tokens-v2.css`)

| Paso | Acción | Archivo |
|---|---|---|
| 1.1 | Crear `app/static/css/tokens-v2.css` con valores light + variables sidebar | ✅ HECHO |
| 1.2 | Hacer que `tokens.css` (existente) mantenga su contenido para no romper imports directos | — |
| 1.3 | En `base.html` y `dashboard/base.html`, añadir **debajo** del link a `app.css`: | `app/templates/base.html` y `app/templates/dashboard/base.html` |
|  | `<link rel="stylesheet" href="/static/css/tokens-v2.css?v=v2-tokens">` | |
| 1.4 | Verificar que la carga es: `tokens.css` (mantiene compat) + `tokens-v2.css` (override) + `app.css` |  |
| 1.5 | Probar **/login**, **/dashboard**, **/dashboard/products** → deben verse light con misma estructura |  |
| 1.6 | Si algo se ve mal (ej. un color hardcodeado en `app.css`): usar DevTools, identificar el selector, agregarlo a `tokens-v2.css` en la sección "v2 exclusivo" | `tokens-v2.css` |

**Truco importante:** `tokens-v2.css` debe cargarse **DESPUÉS** de `app.css` para que sus overrides ganen. El orden actual en `base.html` es:
```html
<link rel="stylesheet" href="/static/css/app.css?v=...">
```
queda:
```html
<link rel="stylesheet" href="/static/css/app.css?v=...">
<link rel="stylesheet" href="/static/css/tokens-v2.css?v=v2-tokens">
```

**Criterio de salida:** la app completa se ve light sin haber tocado un solo template. El sidebar de la izquierda todavía no existe (eso es Fase 4), pero el fondo y los textos son claros. Algunos acentos del dark pueden sobrevivir — anotarlos.

**Rollback:** borrar la línea que importa `tokens-v2.css`.

---

### **FASE 2 — Inventario de overrides necesarios**  (1–2 h)

| Paso | Acción |
|---|---|
| 2.1 | Abrir DevTools en cada página, buscar todos los colores que NO se ven bien (probablemente: `rgba(255,255,255,0.04)` en `.table tr:hover`, `var(--bg-elev-2)` cuando debería ser un color claro, etc.) |
| 2.2 | Crear `docs/migration/v2-overrides.md` con la lista de selectores a reescribir |
| 2.3 | Aplicar overrides en `app/static/css/v2-overrides.css` (nuevo archivo, solo lo que falte) |

**Patrones típicos a buscar:**

```css
/* En app.css — reemplazar manualmente */
.table tr:hover td { background: rgba(255,255,255,0.02); }   →  background: var(--bg-elev-2);
.alert-info { background: rgba(124,92,255,0.05); … }           →  background: var(--info-bg); color: #1a4a82;
.brand-mark { background: conic-gradient(from 200deg, ...); }   →  background: linear-gradient(135deg, var(--accent), var(--accent-2));
```

**Criterio de salida:** no quedan colores oscuros hardcodeados sin justificación (sólo en `tokens-v2.css` y selectores con nombre `*-dark`).

---

### **FASE 3 — Componentes nuevos (sidebar, AI bar, pills)**  (2–3 h)

Los estilos ya están en `tokens-v2.css` (sección "v2 exclusivo"). Ahora los usamos en los templates.

| Paso | Acción | Archivo |
|---|---|---|
| 3.1 | Añadir el bloque `<aside class="sidebar">` a `dashboard/base.html` **encima** del `<header class="topbar">` actual (o reemplazar el topbar, decisión de UX) | `dashboard/base.html` |
| 3.2 | Añadir `<button class="sidebar-toggle">☰</button>` y `<div class="sidebar-overlay">` | `dashboard/base.html` |
| 3.3 | Añadir la `<div class="app-shell"><main class="app-main">` envolviendo el `{% block content %}` | `dashboard/base.html` |
| 3.4 | Convertir el panel AI derecho en AI bar superior (decisión UX: bar arriba da más espacio) — mover `_ai_panel.html` al inicio del `app-main` y darle la clase `ai-bar` | `dashboard/base.html` + `_ai_panel.html` |
| 3.5 | Mover el brand "WowHub" del topbar al sidebar (workspace card) | `dashboard/base.html` |
| 3.6 | Añadir JS mínimo para abrir/cerrar drawer móvil (~10 líneas) | `app.js` (nueva función `WH.Sidebar.toggle()`) |
| 3.7 | Reemplazar los badges inline del sidebar por `<span class="badge">` o `<span class="badge soon">` | `dashboard/base.html` |
| 3.8 | Reemplazar los `<span class="status s-ready">` que ya usabas (si los hay) por el nuevo estándar | donde corresponda |

**HTML ya listo para copiar desde el prototipo** (líneas 500–545 de `wowhub-prototype/index.html`):
```html
<aside class="sidebar" id="sidebar">
  <div class="logo">Wow<span>Hub</span></div>
  <div class="workspace">…</div>
  <div class="nav-title">General</div>
  <nav class="nav">…</nav>
  <div class="sidebar-bottom"><div class="plan">…</div></div>
</aside>
```

**Criterio de salida:** el dashboard tiene sidebar dark a la izquierda + main light, todas las páginas existentes siguen funcionando.

**Rollback:** `git revert` de los cambios en `dashboard/base.html`.

---

### **FASE 4 — Migrar páginas del dashboard (13 templates)**  (3–4 h)

Patrón de migración para cada template (mismo para todos):

| Paso | Acción |
|---|---|
| 4.1 | Reemplazar `<div class="dash-layout">` por `<div class="app-shell">` si existe |
| 4.2 | Reemplazar `<aside class="dash-side">` viejo (que estaba DENTRO del layout) — ya no se renderiza (lo hace el `base.html`) |
| 4.3 | Reemplazar `<main class="dash-main">` → `<main class="app-main">` |
| 4.4 | Añadir AI bar al tope del `{% block dash_content %}` si quieres consistencia (opcional) |
| 4.5 | Reemplazar clases legacy: |
|       | `.btn-secondary` → `.btn-soft` |
|       | `.btn-ghost` en toolbar → `.btn-outline` |
|       | `.panel` → `.card .card-pad` |
|       | status colors hardcoded → `<span class="status s-ready/s-work/s-new">` |
| 4.6 | Tablas: si tienen `<div class="table-wrap">` queda; añadir clase `.table` light (ya está en tokens-v2) |
| 4.7 | Reemplazar iconos emoji sueltos por glifos consistentes o iconos SVG inline |

**Orden recomendado de migración (de menos a más riesgo):**

1. `dashboard/landing.html` (preview del sitio público) — pocas dependencias
2. `dashboard/qrs.html` (tabla simple)
3. `dashboard/payments.html` (KPI cards) — buen showcase de metric tiles
4. `dashboard/orders.html` (kanban)
5. `dashboard/customers.html` (tabla con acciones)
6. `dashboard/products.html` (cards + tabla)
7. `dashboard/promotions.html` (cards con status)
8. `dashboard/site.html` (form + preview)
9. `dashboard/loyalty.html` (preview tarjeta + form)
10. `dashboard/stats.html` (charts)
11. `dashboard/ai.html` (chat)
12. `dashboard/admin_ai.html` (panel de control)
13. `dashboard/superadmin.html` (el más complejo — al final)
14. `dashboard/admin_bookings.html` (calendario, complejo)
15. `dashboard/admin_scanner.html` (cámara, muy específico)
16. `dashboard/webhooks.html` (lista técnica)

**Criterio de salida por página:** la página carga sin warnings en consola, todos los colores son del sistema, no hay regresiones visuales vs baseline.

---

### **FASE 5 — Páginas públicas + auth**  (2 h)

| Paso | Acción | Archivo |
|---|---|---|
| 5.1 | `templates/public/landing.html` — reemplazar el dark hero por light con gradiente violeta suave | `public/landing.html` |
| 5.2 | `templates/public/catalog.html` — cards de productos en light | `public/catalog.html` |
| 5.3 | `templates/public/booking.html` — wizard de reservas con steps pill | `public/booking.html` |
| 5.4 | `templates/public/loyalty.html` — usar nueva clase `.loyalty-card` | `public/loyalty.html` |
| 5.5 | `templates/auth/login.html` + `register.html` — fondo light, card centrada, sombra suave | `templates/auth/*` |
| 5.6 | `templates/legal/*` — solo tipografía, ya estaban bien | `legal/*` |
| 5.7 | `templates/payments/mock_checkout.html` — wizard style | `payments/mock_checkout.html` |
| 5.8 | `templates/home.html` y `home_pro.html` — unificar el marketing landing con la estética nueva | `home*.html` |

**Criterio de salida:** un visitante anónimo puede navegar `landing → catálogo → booking → checkout` sin ver un solo color dark.

---

### **FASE 6 — Landing de marketing (`landing-pro.css`)**  (1 h)

| Paso | Acción |
|---|---|
| 6.1 | Reescribir `landing-pro.css` alineado con tokens v2 (mismo archivo, no nuevo) |
| 6.2 | Reemplazar el dark hero "Lanza tu SaaS" por light con gradient + product mockup |
| 6.3 | Sección pricing: 3 cards light con feature comparison |
| 6.4 | Footer con light bg + 4 columnas |

**Criterio de salida:** la landing pública de marketing (`/`) tiene la misma estética que el resto.

---

### **FASE 7 — Hardening, QA y deploy**  (1–2 h)

| Paso | Acción |
|---|---|
| 7.1 | Correr suite de tests: `pytest -x` |
| 7.2 | Correr Playwright visual diff contra baseline — debe dar 0 regresiones |
| 7.3 | Lighthouse: LCP < 2.5s, CLS < 0.1, INP < 200ms (en dashboard home y en landing pública) |
| 7.4 | Probar manualmente en 3 viewports: 1440, 768, 375 |
| 7.5 | Verificar que la consola no tiene errores (404 de CSS, JS roto, warnings de Vue/etc) |
| 7.6 | Build de assets de producción (no aplica — no usamos bundler, todo es estático con cache-bust `?v=…`) |
| 7.7 | Deploy a staging → probar con datos reales de un tenant |
| 7.8 | Si OK: merge a `main` + bump de versión a **v1.9.2** |
| 7.9 | Deploy a producción |
| 7.10 | Monitorear Sentry/logs por 24h |

**Criterio de salida:** la app en producción se ve 100% light + dark sidebar, sin errores, con mejor performance percibida.

---

## 🧪 Pruebas de aceptación por fase

Cada fase debe pasar este checklist antes de mergear:

```
[ ] Compila sin errores
[ ] Pasa pytest
[ ] Captura visual contra baseline: 0 regresiones
[ ] Probado en 3 viewports (1440 / 768 / 375)
[ ] Sin warnings en consola
[ ] Sin colores hardcodeados (grep -E '#[0-9a-fA-F]{3,6}' --exclude=tokens*.css)
[ ] Sin `!important` nuevos (mantener los del impersonation banner que son críticos)
[ ] Cache-bust `?v=…` actualizado en <link>
[ ] Documentado en CHANGELOG.md
```

---

## 🚨 Plan de rollback (si algo se rompe en producción)

| Severidad | Acción |
|---|---|
| Bug visual menor | Forward fix en hotfix |
| Página blanca / 500 | `git revert` del merge de la fase afectada + redeploy (5 min) |
| Performance regresión severa | Rollback completo a `v1.9.1-r8` + post-mortem |

---

## 📅 Resumen de esfuerzo

| Fase | Esfuerzo | Riesgo |
|---|---|---|
| 0 — Baseline | 30 min | — |
| 1 — Tokens v2 | 30 min | Muy bajo (skin swap) |
| 2 — Overrides | 1–2 h | Bajo |
| 3 — Sidebar + AI bar | 2–3 h | Medio (cambia el shell) |
| 4 — Páginas dashboard | 3–4 h | Bajo por página |
| 5 — Páginas públicas | 2 h | Bajo |
| 6 — Landing marketing | 1 h | Bajo |
| 7 — Hardening + deploy | 1–2 h | — |
| **Total** | **~10–14 h** | |

---

## 🎯 Resultado esperado

Una sola fase a la vez, en orden, y al final de la Fase 7 la app completa en producción se ve **idéntica al prototipo desplegado** en `https://mysup5rg02jx.space.mcode.io`, pero con los datos reales, multi-tenant, con Supabase, JWT, AI Core, Marketing Studio y Automation Manager funcionando.

¿Quieres que arranque por la **Fase 1** ya? Solo necesito que me digas "aplica Fase 1" y modifico `base.html` + `dashboard/base.html` para que `tokens-v2.css` se cargue. Es 5 minutos de cambio y puedes verlo en tu dev server.
