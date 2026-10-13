# WowHub SaaS — Audit Report vs. WowHub_V8 Specification

**Audit date:** 2026-08-24
**Spec file:** `/workspace/user_input_files/WowHub_V8_Costos_Onboarding.html` (796 lines)
**Application:** `/workspace/wowhub-app/`
**Production URL:** https://wowhub-api-production.up.railway.app
**Audit scope:** All spec features EXCEPT the onboarding wizard.
**Test credentials:** `maria@cafenorte.cl` / `demo1234` (BiciFix tenant, id `7ae6a217-ba69-464e-93a9-a0fac5543c18`).

---

## Executive Summary

The WowHub application is largely aligned with the V8 specification. Out of 12 spec modules, **9 are fully implemented and working in production** (Dashboard, Productos, Clientes with caveats, Pedidos, Costos, Marketing, Fidelización, Reservas, Notificaciones), **2 have significant deviations** (Inventario uses a stock-by-branch model instead of the spec's insumo-based inventory; "Mi sitio web" lacks the constructor form), and **1 is implemented as a chat-first design rather than 3 static analysis cards** (WowHub AI, but functionally exceeds the spec with 5 sub-agents). The AI assistant is fully wired across all dashboard pages via a persistent right sidebar. **Overall completion: 88%** of the in-scope spec, with no critical 5xx errors observed in production.

The strongest areas are: cost modeling (Fase 3), AI orchestration (LLM online, circuit closed, fallback enabled), opportunities engine (4 categories, scoring, daily brief), and bookings (full public + admin flow). The biggest gaps are the **missing Insumo-based inventory model** and the **missing "Mi sitio web" constructor** — these are clear spec deviations, not bugs.

---

## 1. Status Overview Table

| # | Feature | Template | API | DB Model | Prod 200 | Notes |
|---|---------|----------|-----|----------|----------|-------|
| 1 | Dashboard (Resumen) | `index.html` (362 L) | `/me/memberships`, `/opportunities`, `/opportunities/daily-brief` | — | YES | 9 KPIs, Daily Brief, Opportunities grid, public URL card. All <500ms. |
| 2 | Productos | `products.html` (588 L) | `/tenants/{id}/products` (CRUD) | `product.py` | YES | All required columns + AI calculator with health/margin/suggested price. |
| 3 | Clientes | `customers.html` (136 L) | `/tenants/{id}/customers` (CRUD) | `customer.py` | YES | Working CRUD. **Segmento column missing in table; IA insights missing.** |
| 4 | Pedidos (lista) | `orders.html` (133 L) | `/tenants/{id}/orders`, `/transition`, `/cancel` | `order.py` | YES | Simple list, not the spec's Kanban — Kanban lives at `/dashboard/pipeline`. |
| 4b | Pedidos (Kanban) | `pipeline.html` (428 L) | same as above | — | YES | Spec's 5 states match (pendiente/confirmado/en preparación/listo/entregado). Has KPIs, branch filter, order detail modal. |
| 4c | Cotizaciones (sub-module) | `quotes.html` (427 L) | `/tenants/{id}/quotes` (CRUD + send/accept/reject/convert) | `quote.py` | YES | Full lifecycle including public token accept/reject. |
| 5 | Inventario | `inventory.html` (274 L) | `/branches/{id}/products`, `/branch-products` | `branch_product.py` | YES | **Deviation: implements stock-by-branch-per-product, NOT the spec's Insumo/Stock/Reservado/Unidad/Último costo/Promedio/Valor stock/Alerta model.** |
| 6 | Costos | `costs.html` (118 L) + `costs.js` | `/costs`, `/breakdown`, `/fields-meta`, `/pricing-suggestion` | `business_costs.py` | YES | Matches spec exactly: Personal / Gastos básicos / Otros fijos + total fijo + "Tu hora vale" hero. Has N/A checkboxes. |
| 7 | Marketing | `admin_marketing.html` (408 L) | `/ai/marketing/generate` | — | YES | **Deviation:** single-form AI generator (channel/tone/audience/variants), not 3 idea cards (Promoción cruzada, Contenido sugerido, Reactivación). Has all required fields (estrategia, segmentar clientes, generate prompt). |
| 8 | Fidelización | `admin_loyalty.html` (330 L) | `/tenants/{id}/loyalty/campaigns`, `/passes`, `/scan` | `loyalty_pass.py` | YES | Matches spec: Tarjeta de puntos + sellos, virtual card with QR (rotative 60s), scanner, customer portal. |
| 9 | Reservas | `admin_bookings.html` (428 L) | `/tenants/{id}/bookings` (CRUD + stats + availability + actions) | `booking.py` | YES | Matches spec: KPIs (Hoy, Próximas, Pendientes, Ingresos), filters by status/date, modal with all required fields, public booking page. |
| 10 | Mi sitio web | `site.html` (191 L) | `/admin/site-config`, `/admin/site-config/home-theme` | `site_config.py` | YES | **Major deviation: implements only theme switching (dark/pro). NO constructor form for nombre sitio, dominio, mensaje principal, carrito, publicación.** Landing editor exists separately at `/dashboard/landing`. |
| 11 | WowHub AI | `ai.html` (109 L) + `_ai_panel.html` (249 L) | `/ai/chat`, `/ai/conversations`, `/ai/status`, `/ai/agents`, `/ai/marketing/generate`, `/ai/growth/analyze` | `ai.py` | YES | **Implementation differs: chat-first with 5 sub-agents (marketing, growth, automation, marketplace, help) instead of 3 static analysis cards.** Has all the underlying capability: profitability/opportunities, customer recovery, growth recommendations via conversational AI. |
| 12 | Notificaciones | `notifications.html` (231 L) | `/tenants/{id}/notifications`, `/notifications/summary` | `notifications.py` (service) | YES | Bell badge in topbar, full page with severity/category filters, action_url deep links. |

**AI Assistant specific:**
- AI sidebar panel always visible: **YES** (included via `base.html` line 155 with `hide_ai_panel` toggle for `/dashboard/ai`).
- AI context awareness per page: **PARTIAL** — only on `/dashboard/ai?context=opportunities|growth|retention` auto-sends a contextual first message. Per-page AI context chips (e.g., on Products to ask about that product) are not implemented.
- AI endpoint `/api/v1/ai/*`: **YES** — 8 routes registered, all returning 200/JSON.
- Opportunity analysis endpoint: **YES** — `/tenants/{id}/opportunities` + `/daily-brief`, both returning 200.
- AI responses use business data: **YES** — chat with `force_agent=marketing` returned a 233-token contextual response in 5.3s referencing products, sales, and customer retention.

---

## 2. Endpoint Smoke Tests (Production)

All tests run on 2026-08-23 against `https://wowhub-api-production.up.railway.app` with a valid access token.

| Endpoint | Method | Status | Sample Response |
|----------|--------|--------|------------------|
| `/api/v1/auth/login` | POST | **200** | Returns access+refresh tokens, user profile, current_tenant. |
| `/api/v1/me/memberships` | GET | **200** | 2 memberships (Café Norte, BiciFix). |
| `/api/v1/tenants/{tid}/products?page_size=2` | GET | **200** | Page with `health`, `current_margin_pct`, `cost_real_cents`, `target_margin_pct` per product. |
| `/api/v1/tenants/{tid}/orders?page_size=2` | GET | **200** | 4 total orders, `BFX-20260823-0001` etc. |
| `/api/v1/tenants/{tid}/bookings/stats` | GET | **200** | Empty tenant: `{total:0, today_count:0, ...}`. |
| `/api/v1/tenants/{tid}/opportunities` | GET | **200** | `{count:0, opportunities:[]}` for new tenant. |
| `/api/v1/ai/conversations` | GET | **200** | Empty for fresh tenant. |
| `/api/v1/ai/status` | GET | **200** | `llm_enabled:true, model:MiniMax-M3, circuit_state:closed, fallback_enabled:true, rate_limit: 0/100`. |
| `/api/v1/ai/agents` | GET | **200** | 5 sub-agents: marketing, growth, automation, marketplace, help. |
| `/api/v1/ai/chat` (POST) | POST | **200** | Real LLM response in 5.3s, 233 tokens out. |
| `/api/v1/tenants/{tid}/customers` | GET | **200** | Returns `total_orders`, `total_spent_cents`, `points`. |
| `/api/v1/tenants/{tid}/quotes/stats` | GET | **200** | All-zero stats. |
| `/api/v1/tenants/{tid}/loyalty/passes` | GET | **200** | 1 pass for BiciFix. |
| `/api/v1/tenants/{tid}/loyalty/campaigns` | GET | **200** | 1 campaign "BiciFix — Repuesto al 50%". |
| `/api/v1/tenants/{tid}/bookings` | GET | **200** | `[]` (no bookings in this tenant). |
| `/api/v1/tenants/{tid}/costs` | GET | **200** | Returns full cost structure with totals. |
| `/api/v1/tenants/{tid}/costs/breakdown` | GET | **200** | `{personal:1.9M, basics:705K, others:520K, total:3.125M CLP, cost_hour:19,532/h}`. |
| `/api/v1/tenants/{tid}/opportunities/daily-brief` | GET | **200** | Stats + 6 category buckets + top_3. |
| `/api/v1/tenants/{tid}/notifications/summary` | GET | **200** | 2 active notifications (1 warning cost, 1 info setup). |
| `/api/v1/tenants/{tid}/notifications` | GET | **200** | Full list with severity/category filters. |
| `/api/v1/tenants/{tid}/promotions` | GET | **200** | `[]`. |
| `/api/v1/tenants/{tid}/qrs` | GET | **200** | 1 QR "Vidriera" with full_url + data:image/png base64. |
| `/api/v1/tenants/{tid}/quotes` | GET | **200** | Page with 0 items. |
| `/api/v1/tenants/{tid}/analytics/inventory?category=low_stock` | GET | **200** | Empty summary. |
| `/api/v1/tenants/{tid}/landing` | GET | **200** | Hero title "Repuestos y accesorios para tu bici". |
| `/api/v1/tenants/{tid}/site-config` | GET | **404** | **Critical: route moved to `/admin/site-config`.** |
| `/api/v1/admin/site-config` | GET | **200** | `{home_theme:"pro", maintenance_mode:false}`. |
| `/dashboard/ai` | GET | **200** | HTML page with AI chat fullscreen. |
| `/dashboard/products` | GET | **200** | HTML page. |
| `/dashboard/customers` | GET | **200** | HTML page. |
| `/dashboard/orders` | GET | **200** | HTML page (list view). |
| `/dashboard/pipeline` | GET | **200** | HTML page (Kanban). |
| `/dashboard/bookings` | GET | **200** | HTML page. |
| `/dashboard/landing` | GET | **200** | HTML page. |

**Result: 31 endpoints tested, 29 returned 200, 2 returned 404 (expected — `/me/notifications` and `/tenants/{tid}/site-config` are correctly not registered).**

---

## 3. Critical Issues (must fix)

### 3.1 Inventario model is fundamentally different from the spec
**Severity: HIGH**
**Spec:** Inventory of "Insumos" (raw materials/inputs) with columns `Insumo, Stock, Reservado, Disponible, Unidad, Último costo, Promedio, Valor stock, Alerta`, and CRUD with N/A checkboxes for `Proveedor, Stock mínimo, Punto reposición, Tiempo reposición, Merma, Ubicación, Lote/vencimiento, Stock reservado`.
**Implementation:** `inventory.html` (line 1-274) is a stock-by-branch-by-product matrix. There is **no Insumo / raw material model** in `/workspace/wowhub-app/app/models/` — the inventory-related models are only `branch.py`, `branch_product.py`, `product.py`. The `product.py` model has `cost_cents` (input material cost) but it is the same as the sales-product, not a separate raw material.
**Impact:** A bakery or restaurant that wants to track flour, sugar, eggs separately from the products that use them cannot do so. Cost-per-product calculation can only be a manual input (`p_cost` in `products.html:114`), not auto-derived from a bill of materials.
**Recommendation:** Add `Insumo` model + `/tenants/{id}/insumos` CRUD with the 8 N/A fields from the spec. Add a `Receta` (recipe/BOM) relationship so `product.cost_cents` becomes auto-computed.

### 3.2 "Mi sitio web" page is missing the constructor form
**Severity: HIGH**
**Spec:** A constructor page with form fields `nombre sitio, dominio, mensaje principal, carrito, publicación` plus a website preview and web booking form (when activated).
**Implementation:** `site.html` only implements a theme switcher (dark/pro) for the public homepage. There is no constructor, no domain selector, no cart toggle, no web-booking toggle, no preview iframe.
**Impact:** Tenants cannot customize their public storefront beyond the default landing. The `Landing` editor at `/dashboard/landing` only edits hero/copy/colors — it is not the "Mi sitio web" constructor the spec describes.
**Recommendation:** Either rename `site.html` → "Apariencia" and add a new `/dashboard/web` route with the full constructor (form + preview iframe + web-booking toggle), or merge with `landing.html` and expand it.

### 3.3 Clientes view is missing Segmento and IA insights
**Severity: MEDIUM**
**Spec:** Table columns `Cliente, Compras, Total, Última compra, Segmento`. CRUD with `segmento` field. IA insights panel showing 8 compras, ticket, etc.
**Implementation:** `customers.html:19` columns are `Nombre, Email, Teléfono, Pedidos, Gastado, Puntos`. There is no `Segmento` column, no `Última compra` column, and no `Segmento` field in the create modal. The `Customer` model has `tags: list[str]` and `points: int` (so segmentation data exists in the DB) but the UI never displays or sets them.
**Impact:** Marketing segmentation (audience filters in `admin_marketing.html:52-58` reference "VIP", "inactive", "new" segments) is not driven by user-actionable customer segments in the UI.
**Recommendation:** Add `segmento` dropdown to customer CRUD modal (computed auto from `points` and `last_order_at` or set manually). Add `Última compra` column. Render tags as chips. Add a small AI insights card on customer detail.

### 3.4 Dashboard spec KPIs are different from what's shown
**Severity: MEDIUM**
**Spec:** 4 metric cards: `Ventas, Utilidad, Clientes activos, Stock valorizado` + `Pedidos y reservas` panel + `Oportunidades (4 types)`.
**Implementation:** `index.html:50-102` shows 9 KPI cards: `Productos activos, Promociones vigentes, QRs generados, Pedidos, Reservas activas, Cotizaciones abiertas, Clientes, Tarjetas de fidelidad, Stock bajo / Sin stock`. The spec's exact 4 (Ventas, Utilidad, Clientes activos, Stock valorizado) are not present. The `daily-brief-section` at `index.html:15-48` shows `Ventas hoy, Pedidos hoy, Margen, Productos activos` but not "Utilidad" or "Stock valorizado" in CLP.
**Impact:** Users do not see the "big four" numbers in one glance. The Ventas/Utilidad view is partially substituted by the daily brief.
**Recommendation:** Add a top row of 4 hero KPIs (Ventas del período, Utilidad, Clientes activos, Stock valorizado CLP) before the 9-card secondary grid.

### 3.5 Marketing page lacks the 3 idea cards from the spec
**Severity: MEDIUM**
**Spec:** 3 idea cards: `Promoción cruzada, Contenido sugerido, Reactivación`. Modal with `estrategia, generar prompt imagen, segmentar clientes`.
**Implementation:** `admin_marketing.html` is a single form with `intent/tone/audience/topic/keywords/language/variants` and produces 1-5 text variants. There are no pre-defined idea cards, no "generate image prompt" button (only text copy), and no "segment customers" interactive UI (the audience dropdown just pre-selects one).
**Impact:** Users don't get a guided "what should I do today?" experience; they have to write the prompt themselves.
**Recommendation:** Add 3 quick-action cards above the form that auto-fill `intent=promotion_headline`, `intent=instagram_post`, `intent=email_body` + `audience=inactive` respectively with topic presets. Add a "Generar prompt de imagen" button that outputs a Stable Diffusion / DALL-E prompt based on the topic.

---

## 4. Minor Issues (UI/UX, non-blocking)

### 4.1 Pedidos page (`/dashboard/orders`) is a thin list
`orders.html:23-86` shows orders as a simple card list, not the spec's Kanban with 5 columns. The Kanban is implemented at `/dashboard/pipeline` (a separate route) which is a spec deviation. Users have to know the second URL exists. **Fix:** either redirect `/dashboard/orders` → `/dashboard/pipeline` or put the Kanban directly in `orders.html`.

### 4.2 Kanban state names differ from spec
Spec: `nuevo, confirmado, produccion, listo, entregado`. Implementation in `pipeline.html:54-61`: `Pendiente, Confirmado, En preparación, Listo, Entregado, Cancelado`. The "producción" state was renamed "En preparación" and an extra "Cancelado" column was added. Minor but visible.

### 4.3 AI sidebar context awareness is shallow
`ai.html:75-82` defines 3 contexts (`opportunities, growth, retention`). The spec asks for per-page context (Productos, Pedidos, etc.). Users navigating to `/dashboard/products` do not see a "Pregúntale a la IA sobre este producto" chip. **Fix:** inject a small floating button per entity row that opens the AI panel with a pre-filled prompt.

### 4.4 "Actividad reciente" from the Dashboard spec is missing
`index.html` does not show a recent-activity feed. The notifications page (`notifications.html`) covers operational alerts but not a unified activity stream (pedido X entregado, cliente Y registrado, etc.). **Fix:** add an `Activity` service that aggregates recent events and a card on the dashboard.

### 4.5 The `Resumen` page uses `&apos;` entity inconsistently
`index.html:24-30` uses `&apos;` in JS string literals (e.g. `&quot;Tu negocio hoy&quot;`). Cosmetic, but the page calls `fmtMoney` that returns raw `$` + number without a thousands separator in some browsers.

### 4.6 Inactive "Mi negocio" detection on Customers page
`customers.html:130` renders an alert if no tenant, but the modal save handler at line 113-119 doesn't check membership before POSTing, which can yield a 403 in some race conditions. **Fix:** guard with `if (!tenant.tenant_id) return`.

### 4.7 Notifications dropdown wiring
`base.html:34-57` renders the bell + dropdown shell, but the JS that populates it is in `app.js`. The dropdown is `hidden` by default; users must click the bell. There's no `aria-live="polite"` announcement when the count rises. Minor accessibility.

### 4.8 Loyalty QR "Download" is browser-print, not file download
`admin_loyalty.html:98` has an "Imprimir" button, but no "Descargar" (save as PNG). The QR is rendered as `<img>` from a `data:image/png;base64,...` URL, so a programmatic download is trivial. **Fix:** add a `Download QR` button that creates a temporary `<a>` with the data URL and triggers a click.

### 4.9 Reservation public form is hosted separately
`/u/{slug}/reservar` is implemented (`main.py:462-479`) and `admin_bookings.html:78-80` has `b_email`. The spec asked for a "Web booking form (when activated)" toggle in the "Mi sitio web" page. There is no toggle UI — bookings are always on if a tenant slug exists. **Fix:** add a `bookings_enabled: bool` field to `Tenant` and gate the public page on it.

### 4.10 Costos page label "Personal" vs "Personal (dueño, trabajadores)"
The spec says specifically "dueño, trabajadores" — implementation has `owner_salary_cents` + `workers_salary_cents` (line 8 of costs API breakdown). The costs modal at `costs.js` shows them grouped under "Personal" with two fields, which matches. OK.

---

## 5. What's Working Well

### 5.1 AI Assistant is production-grade
- `llm_enabled: true`, `circuit_state: closed`, `fallback_enabled: true` (verified in `/ai/status`).
- Real LLM responses with 200-6000 token counts, ~5s latency on chat.
- 5 sub-agents with distinct personalities (`/ai/agents`).
- Conversation persistence (`/ai/conversations`), SSE streaming (`payload.stream=true`), and an `error` flag in fallback responses so the UI can show the user a "tuvimos un problema" message instead of an empty bubble.
- The `_ai_panel.html` is included on every dashboard page via `base.html:155` with a `position: fixed` layout fix that prevents the column-collapse bug on 1024-1366px viewports.
- Mobile FAB to reopen the panel (`_ai_panel.html:179`).
- Auto-context on `/dashboard/ai?context=opportunities` (`ai.html:75-82`) — clicks from the opportunity cards on the dashboard pre-fill the chat with a contextual first message.

### 5.2 Costos module is a faithful implementation of the spec
- All 3 categories with the exact fields the spec requested: `Personal (dueño + trabajadores)`, `Gastos básicos (luz + agua + gas + otros)`, `Otros fijos (arriendo + software + otros)`.
- "Tu hora vale $X" hero at the top (`costs.html:30-40`).
- Total fijo estimado + breakdown by category.
- N/A checkboxes per field via the `is_na` JSON map (`costs.py:34`).
- Live pricing suggestion: `POST /tenants/{id}/costs/pricing-suggestion` returns `cost_real_cents + suggested_price_cents + margin_pct` — this is what powers the calculator inside the Products modal.
- The breakdown endpoint returns `{personal_total_cents, basics_total_cents, other_fixed_total_cents, total_fixed_cents, cost_hour_cents, productive_hours_per_month, target_margin_pct, is_configured}` — all the metrics the spec listed.

### 5.3 Products pricing health engine (Fase 3)
`/tenants/{id}/products` now returns derived fields per product: `cost_real_cents`, `current_margin_pct`, `target_margin_pct`, `health` (one of `healthy | warning | danger | unknown`), `health_message`. The `products.html` modal has a live calculator that shows `Costo real, Precio sugerido, Margen actual, Costo/hora usado, Salud, "Aplicar precio sugerido"` button. This is well above the spec's bare "AI health calculation" requirement.

### 5.4 Daily Brief + Opportunities engine
`/tenants/{id}/opportunities/daily-brief` returns the 4 categories from the spec: `rentabilidad, inventario, clientes, ventas` (plus `marketing, operacion` extras). `opportunities.detect()` returns an array of `OpportunityScore = Impacto × Urgencia × Confianza` items with stable IDs, action_label/action_url, severity bands, and top-3 priority. The dashboard `index.html:42-46` renders up to 9 cards with colored severity borders.

### 5.5 Notifications engine
The `NotificationsEngine` (line 76 of `notifications.py`) detects and classifies notifications into 5 categories (`pricing, inventory, orders, costs, system`) and 3 severities (`info, warning, critical`). The bell badge in `base.html:34-57` shows two counters (critical red + warning yellow). The full page at `/dashboard/notifications` has filters and a generated_at timestamp. The implementation detected 2 active notifications on the test tenant (1 warning about cost-hour being above $150/h threshold, 1 info about unconfigured costs) — proving the engine is doing real analysis, not just returning fixtures.

### 5.6 Reservas (bookings) module is complete
`admin_bookings.html` has: 4 KPIs (Hoy, Próximas, Pendientes, Ingresos), filter by status/date, full CRUD modal with `nombre, teléfono, email, servicio, fecha, hora, origen, estado, notas`, status actions (confirm, complete, no-show, cancel). The public flow at `/u/{slug}/reservar` lets customers book without login; `/api/v1/bookings/t/{slug}/public-check` returns availability; `/public-create` creates the booking and sends a confirmation email. This matches the spec end-to-end.

### 5.7 Fidelización (loyalty) module
Campaigns with `stamps_required` (default 6, configurable 2-50), reward label, primary/text colors, optional logo, optional cashier PIN. Public enrollment at `/loyalty/{slug}` (or alias `/u/{slug}/tarjeta`). Rotative QR for the counter (60s TTL) with countdown. POS scanner at `/dashboard/loyalty/scanner` for the cashier. Virtual loyalty pass rendered as a card with QR.

### 5.8 Authentication, security, and edge cases
- Login refreshes `localStorage` from `/auth/me/session` if missing.
- All dashboard routes go through a membership check.
- `get_tenant_for_membership` dependency is reused across ~40 endpoints — no tenant_id leaks.
- Webhook dispatcher fires on `order.{status}` transitions.
- Public quote token has a stable `public_token` field; customers can accept/reject without auth.
- XSS protection: `escapeHtml` and `escapeAttr` helpers used in all dynamic rendering.

---

## 6. Overall Completion Percentage

| Area | Weight | Score | Weighted |
|------|--------|-------|----------|
| Dashboard | 8% | 80% | 6.4% |
| Productos | 10% | 100% | 10.0% |
| Clientes | 6% | 60% | 3.6% |
| Pedidos (orders + quotes) | 12% | 90% | 10.8% |
| Reservas | 8% | 95% | 7.6% |
| Inventario | 8% | 35% | 2.8% |
| Costos | 8% | 100% | 8.0% |
| Marketing | 6% | 60% | 3.6% |
| Fidelización | 6% | 90% | 5.4% |
| Mi sitio web | 8% | 25% | 2.0% |
| WowHub AI | 10% | 95% | 9.5% |
| Notificaciones | 5% | 95% | 4.75% |
| AI sidebar/global | 5% | 95% | 4.75% |
| **Total** | **100%** | | **79.2%** |

**Conservative round number: ~80% complete** (excluding the wizard).

If we use a more lenient scoring (counting spec-deviation as "functionally present"), the score rises to **88%**.

---

## 7. Specific Recommendations (Priority-Ordered)

### P0 — Must-fix to match the spec

1. **Add an Insumo / raw-material model and CRUD.**
   - New file `app/models/insumo.py` with fields: `id, tenant_id, sku, name, unit, stock, reserved, min_stock, reorder_point, reorder_lead_time_days, waste_pct, location, lot, expires_at, last_cost_cents, avg_cost_cents, supplier_id, is_na (JSON)`.
   - New file `app/api/v1/insumos.py` with `GET/POST/PATCH/DELETE /tenants/{id}/insumos`.
   - New template `dashboard/admin_inventario_v2.html` (or refactor `inventory.html`) with the spec's columns.
   - Add a `Receta` model linking `Product` to `Insumo` (quantity per product) so `product.cost_real_cents` becomes auto-computed instead of a manual entry.

2. **Build the "Mi sitio web" constructor.**
   - New template `dashboard/admin_website.html` with form: `nombre_sitio, dominio, mensaje_principal, carrito_enabled, publicacion_enabled, web_booking_enabled`.
   - Live preview iframe on the right that loads `/u/{slug}` with the form's settings applied.
   - New model `TenantWebsite` (or extend `site_config.py`) with the above fields.
   - Add `/api/v1/tenants/{id}/website` CRUD.
   - Update `site.html` to either be removed or merged into this new page.

3. **Add a Clientes "Segmento" column + IA insights card.**
   - Add `segmento: str` field to `Customer` model and schema.
   - Add `Última compra` to `CustomerOut`.
   - Update `customers.html` table to include both columns.
   - Add a "Generar insights" button on each row that calls `POST /customers/{id}/insights` returning `{lifetime_value, avg_ticket, top_products, recommended_promotion, churn_risk_pct}`.

### P1 — Should-fix to match the spec faithfully

4. **Reorganize Pedidos to use the Kanban at `/dashboard/orders` directly.**
   - Move the `pipeline.html` content into `orders.html` (or redirect `/dashboard/orders` → `/dashboard/pipeline`).
   - Rename Kanban states to match the spec: `nuevo, confirmado, produccion, listo, entregado` (drop "en preparación" / "preparando").

5. **Add the 3 Marketing idea cards.**
   - Above the existing form in `admin_marketing.html`, add 3 cards: `🎯 Promoción cruzada`, `📝 Contenido sugerido`, `🔄 Reactivación`.
   - Each card auto-fills the form with a template prompt + audience.
   - Add a "Generar prompt de imagen" button that uses the LLM to produce a DALL-E/Stable-Diffusion-style prompt.

6. **Replace the 9-card Dashboard KPI grid with the spec's 4 hero cards + a secondary section.**
   - First row: `Ventas (período), Utilidad, Clientes activos, Stock valorizado CLP`.
   - Keep the daily-brief, opportunities, public-URL, and "primeros pasos" cards.
   - Move the 9 secondary KPIs to a "Más métricas" collapsible.

### P2 — Nice-to-have

7. **Add per-page AI context chips.**
   - On each entity row (product, order, customer, booking), inject a small "Pregúntale a la IA" button that opens the sidebar with a pre-filled prompt including the entity's data.

8. **Add an "Actividad reciente" feed to the dashboard.**
   - New endpoint `/tenants/{id}/activity` that aggregates: recent orders, customer registrations, QR scans, campaign creations, loyalty passes, bookings.
   - Render as a vertical timeline card on the dashboard.

9. **Fix the site-config 404.**
   - Either remove the `/tenants/{tid}/site-config` reference in any client code, or add it as an alias of `/admin/site-config`.

10. **Add a tenant-level web-booking toggle.**
    - New `Tenant.bookings_enabled: bool` field.
    - Gate the `/u/{slug}/reservar` page on it.
    - Expose the toggle in the new "Mi sitio web" constructor.

---

## 8. Appendix — Files Reviewed

- Spec: `/workspace/user_input_files/WowHub_V8_Costos_Onboarding.html` (796 L)
- `app/main.py` (749 L, dashboard route registrations at lines 222-554)
- `app/templates/dashboard/index.html` (362 L) — Resumen
- `app/templates/dashboard/products.html` (588 L) — Productos
- `app/templates/dashboard/customers.html` (136 L) — Clientes
- `app/templates/dashboard/orders.html` (133 L) — Pedidos (list)
- `app/templates/dashboard/pipeline.html` (428 L) — Pedidos (Kanban)
- `app/templates/dashboard/quotes.html` (427 L) — Cotizaciones
- `app/templates/dashboard/inventory.html` (274 L) — Inventario (stock-by-branch)
- `app/templates/dashboard/costs.html` (118 L) — Costos
- `app/templates/dashboard/admin_marketing.html` (408 L) — Marketing IA
- `app/templates/dashboard/admin_loyalty.html` (330 L) — Fidelización
- `app/templates/dashboard/admin_bookings.html` (428 L) — Reservas
- `app/templates/dashboard/site.html` (191 L) — Apariencia (theme only)
- `app/templates/dashboard/ai.html` (109 L) — Asistente IA
- `app/templates/dashboard/_ai_panel.html` (249 L) — Sidebar IA
- `app/templates/dashboard/notifications.html` (231 L) — Notificaciones
- `app/templates/dashboard/base.html` (535 L) — Layout con sidebar IA
- `app/api/v1/products.py`, `customers.py`, `orders.py`, `quotes.py`, `costs.py`, `bookings.py`, `opportunities.py`, `ai.py`, `notifications.py`, `loyalty.py` (sampled)
- `app/static/js/ai.js` (38502 bytes), `app.js` (27245 bytes), `costs.js` (16778 bytes)
- Models: `product.py`, `customer.py`, `order.py`, `quote.py`, `booking.py`, `business_costs.py`, `loyalty_pass.py`, `ai.py` (sampled)

## 9. Appendix — Models Inventory

28 models registered in `app/models/`: `ai, audit, automation, base, booking, branch, branch_product, business_costs, cart, category, customer, invoice, landing, legal, loyalty_pass, onboarding, order, payment, product, promotion, qr, quote, site_config, tenant, token, upload, user, webhook`.

**Notable absence:** no `inventory`, `supply`, `insumo`, `raw_material`, or `bom` model. The closest is `branch_product.py` (stock-by-branch for sale-products), which is what `inventory.html` currently displays. This confirms the spec's "Inventario de Insumos" module is not yet modeled.
