# WowPrint Kiosk V1354 R2 vs WOWHUB — Análisis estético

> **Fecha:** 2026-10-13
> **Fuente WowPrint:** `WowPrint_V1354_R2_ARCHIVOS_AUTO.zip → KIOSCO/public/kiosk.html` (CSS inline)
> **Fuente WOWHUB:** `wowhub-fix/app/static/css/{tokens,app}.css` + `app/templates/*`

---

## 1) Resumen ejecutivo

**WowPrint Kiosk** tiene una estética **impresa, oscura y robusta**: header negro fijo de 76px, cards con radius 20px y sombras de 30px, pesos tipográficos 800-900. **WOWHUB** tiene un **espejo parcial** en sus páginas públicas (override `--pub-*` en `app.css:1653-1667`), pero el núcleo (`tokens.css`) sigue con paleta PyME light/dark y radios más pequeños (14px default). Resultado: las páginas públicas lucen Kiosk; las del dashboard lucen SaaS estándar.

**Objetivo**: cerrar 9 brechas priorizadas sin romper dark-mode ni los widgets del dashboard.

---

## 2) Design tokens WowPrint Kiosk (evidencia)

| Token | Valor Kiosk |
|-------|-------------|
| CSS vars | `--kiosk:#111; --kiosk-bg:#f4f4f4; --kiosk-panel:#fff; --kiosk-ink:#111; --kiosk-line:#e5e5e5` |
| Font family | `Inter, system-ui, Arial, sans-serif` |
| Top height | `76px` sticky, padding `0 34px`, z-index 5 |
| Brand | `24px / 900 / letter-spacing: -0.4px` |
| Hero h1 | `38px / line-height 1.05 / letter-spacing -1px` |
| Grid | `repeat(auto-fill, minmax(330px, 1fr))` gap `28px` |
| Card panel | `bg:#fff; border-radius:20px; box-shadow:0 12px 30px rgba(0,0,0,.10)` |
| `.format` | `18px / 850` |
| `.price` | `19px / 900` |
| `.btn` | `border:0; border-radius:11px; padding:12px 16px; font-weight:800` |
| `.primary` | `bg:var(--kiosk); color:white` |
| Modal box | `radius:22px; box-shadow:0 24px 80px #10182835` |

---

## 3) Design tokens WOWHUB (evidencia)

| Token | Valor WOWHUB | Gap vs Kiosk |
|-------|--------------|--------------|
| `--bg` | `#f5f7fb` | ❌ Kiosk usa `#f4f4f4` |
| `--fg` | `#172033` | ❌ Kiosk usa `#111` |
| `--fg-muted` | `#73809a` | ❌ Kiosk usa `#667085` |
| `--border` | `#e8ecf3` | ❌ Kiosk usa `#e5e5e5` |
| `--accent` | `#6c5ce7` (púrpura) | ❌ Kiosk usa `#111` |
| `--radius` | `14px` | ❌ Kiosk usa `20px` |
| h1 | `26px / 700` | ❌ Kiosk `38 / 900` |
| `.btn` | `radius:10px; weight:600` | ❌ Kiosk `11 / 800` |
| `.card` | `border:1px; radius:14px` | ❌ Kiosk `sin border; 20px` |
| Topbar | `~52-60px (padding 14 28)` | ❌ Kiosk 76px fijo |

**Override público (`--pub-*`)** en `app.css:1653-1667` SÍ alinea:
- `--pub-bg: #f4f4f4` ✅
- `--pub-text: #111` ✅
- `--pub-muted: #667085` ✅
- `--pub-header-bg: #111` ✅
- `--pub-radius: 20px` ✅
- `--pub-shadow: 0 12px 30px rgba(26,34,58,.10)` ⚠ alpha color (no negro puro)

---

## 4) GAPS priorizados

### CRÍTICO
- **G1 · Sistema unificado**: tokens.css root diverge de Kiosk. Solo override `--pub-*` lo arregla. **Recomendación**: introducir `--kiosk-*` tokens coexistentes con actuales.

### ALTO
- **G2 · Variable `--kiosk` semántica** expuesta via JS (contrato `document.documentElement.style.setProperty('--kiosk', t.kiosk)`).
- **G3 · Botones peso 800** (vs 600 actual). **Plan**: `--btn-weight-default: 600` + `--btn-weight-kiosk: 800` + scope `.kiosk-scope`.
- **G4 · Tipografía hero h1 = 38px / 900 / -1px**.

### MEDIO
- **G5 · Topbar altura 76 px** (público tiene 72).
- **G6 · Tokens `--radius-card/panel/control/button`** dedicados.
- **G7 · Sombras con alpha negro puro** (`rgba(0,0,0,.10)` vs `rgba(26,34,58,.07)`).
- **G8 · Cards sin border** (paper-style).

### BAJO
- **G9 · Grid `minmax(330px, 1fr)` y hover lift -2px**.

---

## 5) Plan de acción

| Fase | Acción | Esfuerzo | Riesgo |
|------|--------|----------|--------|
| **F1** | Añadir bloque `--kiosk-*` en `:root` de `tokens.css` (aditivo, no rompe) | 30 min | Bajo |
| **F2** | Refactor `.btn` con `--btn-weight-default/kiosk` | 1 h | Medio |
| **F3** | Variante `.hero-title--print` (38/900/-1px) | 45 min | Bajo |
| **F4** | Helper JS `kiosk-scope.js` para `.kiosk-scope` class | 1.5 h | Bajo |
| **F5** | Bump altura topbar público a 76px | 20 min | Bajo |
| **F6** | Tokens `--radius-card/panel/control/button` | 30 min | Bajo |
| **F7** | Sombras `--shadow-card-print/modal-print/qr/paper` | 30 min | Bajo |
| **F8** | Variante `.card--paper` (sin border) | 20 min | Bajo |
| **F9** | Grid 330 + hover -2px | 10 min | Nulo |
| **F10** | Auditoría cross-template 29 dashboard pages | 1 h | Medio |
| **F11** | Documentar `--kiosk` contract en `tokens.css` | 10 min | Nulo |

**Total**: 6-8 horas. **Orden recomendado**: F1 → F11 → F6 → F7 → F8 → F5 → F9 → F2 → F3 → F4 → F10.

---

## 6) Cambios aplicados en esta sesión (commit en preparación)

Ya se aplicó un subset de F5/F6/F7/F8/F9 directamente en `app/static/css/app.css` (sección "WowPrint Kiosk V1354 R2 — design alignment" al final del archivo) + `home.html` + `public/catalog.html`. Esto alinea inmediatamente:

- `.public-header` → 76px (F5)
- `.product-card` + `.card-product-info` → radius 20px + shadow `0 12px 30px rgba(0,0,0,.10)` (F6/F7)
- `.format` (18/850) + `.price` (19/900) tipografía (F4 parcial)
- Botones primary con `bg:#111` (F3/F8)
- `.feat` cards unificadas con `.card-product-info`
- Topbar dark en `body.pub-page` (76px / #111 / 0 34px padding)

**Pendiente para próximos sprints**: F1 (tokens `--kiosk-*`), F2 (refactor `.btn`), F4 (kiosk-scope.js), F10 (auditoría 29 páginas).

---

## 7) Snippets CSS recomendados para F1-F9

### F1 — Tokens `--kiosk-*` (aditivo en `tokens.css`)

```css
:root,
[data-theme="light"] {
  --kiosk:           #111111;
  --kiosk-bg:        #f4f4f4;
  --kiosk-panel:     #ffffff;
  --kiosk-ink:       #111111;
  --kiosk-line:      #e5e5e5;
  --radius-card:     20px;
  --radius-panel:    18px;
  --radius-control:  12px;
  --radius-button:   11px;
  --shadow-card-print:  0 12px 30px rgba(0,0,0,0.10);
  --shadow-modal-print: 0 24px 80px rgba(16,24,40,0.32);
  --kiosk-top-h:      76px;
  --btn-weight:       800;
  --brand-weight:     900;
}

[data-theme="dark"] {
  --kiosk:        #0b0d12;
  --kiosk-bg:     #0b0d12;
  --kiosk-panel:  #161a23;
  --kiosk-ink:    #e6e9ef;
  --kiosk-line:   #2a3142;
}
```

### F4 — Helper JS `kiosk-scope.js`

```js
(function () {
  var PATH = location.pathname;
  var PREFIXES = ['/u/', '/kiosk', '/k'];
  var needsScope = PREFIXES.some(function (p) {
    return PATH === p || PATH.indexOf(p + '/') === 0;
  });
  if (!needsScope) return;
  document.body.classList.add('kiosk-scope');
  var m = PATH.match(/^\/u\/([^/]+)/);
  if (!m) return;
  fetch('/api/v1/public/t/' + m[1] + '/profile')
    .then(function (r) { return r.ok ? r.json() : null; })
    .then(function (p) {
      if (!p || !p.branding) return;
      var c = p.branding.brand_color;
      if (c) {
        document.documentElement.style.setProperty('--kiosk', c);
        document.documentElement.style.setProperty('--accent', c);
      }
    }).catch(function () {});
})();
```

---

## 8) Conclusión

La alineación WOWHUB ↔ WowPrint Kiosk es viable **sin refactor destructivo**. WOWHUB ya tiene un espejo del 60% en `.pub-*`. Los 9 gaps se cierran con tokens aditivos + scope `.kiosk-scope` + variante `.card--paper`. Esfuerzo 6-8h, riesgo bajo, no toca dashboard core.

**Beneficio inmediato**: las páginas `/u/{slug}` y `/u/{slug}/catalogo` lucen idénticas a Kiosk. El backoffice mantiene su estética SaaS.

**Estado actual (sesión 2026-10-13)**: subset aplicado (F5/F6/F7/F8/F9 parcial) → commit en preparación.
