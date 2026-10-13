# WowPrint V1354 R2 — CSS Inventory

> **Fecha:** 2026-10-13
> **Fuente:** `WowPrint_V1354_R2_ARCHIVOS_AUTO.zip`
> **Archivos auditados:** 4 HTML con CSS inline (no hay archivos `.css` separados)

---

## 1. File overview

| Archivo | Tamaño | Bloques `<style>` | CSS inline | Tipo |
|---|---|---|---|---|
| `KIOSCO/public/upload.html` | 2.7 KB | 1 | ~0.9 KB | Upload (captura fotos) |
| `KIOSCO/public/admin.html` | 11 KB | 1 | ~1.4 KB | Admin Control Center |
| `KIOSCO/public/kiosk.html` | 56 KB | 1 | ~5 KB | Kiosk storefront + editor |
| `WowPrint.html` | 588 KB | **10** (7 named + 3 anónimos) | ~27 KB | Admin/back-office SPA |

---

## 2. CSS Variables (`:root`)

### kiosk.html
```
--kiosk:#111111
--kiosk-bg:#f4f4f4
--kiosk-panel:#fff
--kiosk-ink:#111
--kiosk-line:#e5e5e5
```
Runtime-overridable via `document.documentElement.style.setProperty('--kiosk', ...)` desde `/api/branding`.

### WowPrint.html
- **Block 1**: `--bg:#f4f4f4; --panel:#fff; --ink:#111; --muted:#666; --line:#ddd; --brand:#111; --blue:#111; --green:#222; --orange:#333; --red:#111; --sidebar:#111; --kiosk:#111; --catalog:#111; --quote:#111; --voucher:#111`
- **Block 4 (V59)**: `--catalog-accent; --catalog-bg`

> **Observación**: casi todos los tokens de marca (`--brand`, `--blue`, `--green`, `--orange`, `--red`, `--kiosk`, etc.) resuelven al **mismo gris oscuro `#111/222/333`**. Sistema monocromático, sin diferenciación por módulo.

### admin.html / upload.html
**No tienen `:root`** — todos los colores hardcodeados.

---

## 3. Color palette consolidada

### Backgrounds
- `#fff` (panel universal)
- `#f4f4f4` (kiosk bg)
- `#f5f7fa` (admin bg)
- `#f4f6f8` (upload bg)
- `#f6f8fb` (wp-cat-public bg)
- `#fafbfc` (drop zone, picker-item)
- `#eef1f5` (stage, .light btn)

### Borders
- `#e5e5e5` (kiosk line)
- `#ddd` (WowPrint line)
- `#e4e7ec` (admin card border)
- `#e1e5eb` (picker-item, face-slot)
- `#d0d5dd` (inputs admin/upload)
- `#cbd2dc` (drop dashed)

### Texto
- `#111` (ink principal)
- `#172033` (upload body, face-tab active, .light btn)
- `#667085` (`.small`, variant meta)
- `#475467` (orientation-badge text)
- `#cbd5e1` (sidebar nav text)

### Brand / Accent (todos oscuros)
- `#111111` (kiosk top, brand principal)
- `#222222` (.machine chip)
- `#1f2937` (nav hover/active bg)
- `#1677ff` (sticker selected outline)
- `#2446a8` (template-badge text)

### Status colors
- `#15803d` (ok), `#c2410c` (warn), `#b42318` (danger)
- `#067647` (kiosk-service-online), `#b91c1c` (kiosk-service-offline)
- `#eab308` (priority-high), `#22c55e` (delivery-ok), `#ef4444` (delivery-late)
- `#fffbeb` (margin-yellow bg), `#ecfdf5` (margin-green bg), `#fef2f2` (margin-red bg)

---

## 4. Typography scale

### Font stacks
- `system-ui, Arial` (upload, admin)
- `Inter, system-ui, Arial, sans-serif` (kiosk)
- `Inter, Segoe UI, Arial, sans-serif` (WowPrint)

### Font sizes usados
- 9px → 48px
- Picos: 11.5px (`.size`), 18px (`.format`), 19px (`.price`), 24px (`.brand`), 27px (top h1 WowPrint), 38px (`.hero h1`)

### Font weights
- 400 (default), 500, 700, 750 (upload btn), 800, **850** (`.format`), **900** (`.price`, `.brand`)

### Letter-spacing
- `-.4px` (brand), `-1px` (hero h1), `-.2px` (format), `.06em` (kiosk-label)

---

## 5. Border-radius scale

| Radio | Uso |
|---|---|
| `8px` | nav buttons, .btn (WowPrint, admin) |
| `10px` | .machine, .face-tab, .linehead |
| **`11px`** | **kiosk .btn (objetivo WOWHUB)** |
| `12px` | .control, .picker-item, .sticker-handle |
| `14px` | .status (upload) |
| `16px` | .modalbox, .column, .wp-cat-public |
| `18px` | .stage, .picker-box, .qr |
| **`20px`** | **.card, .card-product-info, .card-product-photo (objetivo WOWHUB)** |
| `22px` | .box (kiosk modal) |
| `24px` | .box (upload) |
| `50% / 999px` | stickers, .pill, .marginbox |

---

## 6. Box-shadow patterns

| Shadow | Uso |
|---|---|
| **`0 12px 30px rgba(0,0,0,.10)`** | **.card, .card-product-info (objetivo WOWHUB)** |
| `0 14px 24px rgba(0,0,0,.16)` | card-product-photo img drop-shadow |
| `0 12px 40px #0001` | upload .box |
| `0 24px 80px #10182835` | kiosk .box modal |
| `0 5px 18px #10182808` | kiosk .qr |
| `0 12px 28px rgba(16,24,40,.12)` | .variantOption:hover |
| `0 4px 14px rgba(16,24,40,.06)` | .variantOption |

---

## 7. Grid patterns clave

- `repeat(auto-fill, minmax(330px, 1fr))` gap 28px — **kiosk catálogo**
- `repeat(auto-fill, minmax(74px, 1fr))` gap 9px — picker-grid
- `repeat(4, 1fr)` gap 14px — admin .grid
- `repeat(7, 1fr)` gap 6px — kiosk .frames
- `minmax(210px, 48%) minmax(0, 1fr)` gap 20px — kiosk .card

---

## 8. Responsive breakpoints

| Breakpoint | Archivos | Efecto |
|---|---|---|
| `700px` | kiosk | variantChooser collapse |
| `800px` | admin, kiosk | admin grid 2 col, kiosk hero 32px |
| `900px` | kiosk, WowPrint | editor 1 col, kanban 2 col |
| `1200px` | WowPrint | kanban 4 col |
| `max-height:760px` | kiosk | modal 96vh |

---

## 9. Animaciones / Keyframes

- `wowZoomIn` (kiosk.html) — modal entry: 0% scale(.82) → 70% scale(1.025) → 100% scale(1), `.24s cubic-bezier(.2,.8,.2,1)`
- `wowPrintModalZoom` (WowPrint.html V112) — **idéntico a wowZoomIn**, solo cambia el nombre
- **Candidato a consolidación** (mismo comportamiento, distinto nombre)

---

## 10. Observaciones audit-worthy

1. **Keyframes duplicados**: `wowZoomIn` y `wowPrintModalZoom` son funcionalmente idénticos
2. **Cards layouts duplicados**: `.card` (kiosk) y `.wp-cat-product` (V60) comparten misma estructura
3. **Breakpoints inconsistentes**: 7+ breakpoints distintos (520/600/700/720/750/760/800/900/1050/1200) sin sistema unificado
4. **Color tokens no diferenciados**: `--brand/--blue/--green/--orange/--red` = todos `#111/#222/#333`
5. **`!important` en cascada**: 5 bloques de compact-job (V56/V57/V58/V59/V61) sobreescriben con `!important`
6. **Sin CSS reset más allá de `*{box-sizing}`** — no hay focus styles globales
7. **Sin `prefers-reduced-motion`** para los keyframes de zoom
8. **Sin `@media print`** — kiosk vende servicios de impresión pero no tiene print stylesheets

---

## 11. Conclusión para WOWHUB

Los tokens más importantes a alinear con WowPrint Kiosk V1354 R2:

| Elemento | Valor Kiosk | Estado WOWHUB |
|----------|-------------|---------------|
| Top height | 76px | 14px 28px padding (no fijo) |
| Top bg | `#111111` sólido | `--topbar-bg` light/dark |
| Card radius | 20px | `--radius` 14px |
| Card shadow | `0 12px 30px rgba(0,0,0,.10)` | `--shadow` 0 10px 30px rgba(26,34,58,.07) |
| Format (.name) | 18px / 850 | 15px / 700 |
| Price | 19px / 900 | 18px / 800 |
| Button | 11px radius / 800 | 10px radius / 600 |
| Hero h1 | 38px / 900 | 26px / 700 |

**Subset aplicado en WOWHUB (commit `0cb2405`)**: topbar 76px dark, cards 20px + shadow 0,12,30 rgba(0,0,0,.10), format 18/850, price 19/900, button primary #111.

**Pendiente para F1-F11**: tokens `--kiosk-*` en `tokens.css` (aditivo), refactor `.btn` con scope `.kiosk-scope`, helper JS para auto-aplicar scope, auditoría 29 páginas dashboard.
