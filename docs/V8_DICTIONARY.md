# Diccionario V8 — Pantalla × Entidad × Endpoint × Seed

> **Propósito:** este documento es la **fuente de verdad** del proyecto WowHub. Cada pantalla del dashboard está mapeada a la entidad ORM que persiste sus datos, al endpoint API que la alimenta, y al dato de seed que la puebla. Es lo único que evita perder contexto entre fases (Fase 4 → 5 → 6 → …).

## Convenciones

- **URL** — ruta de página servida por `app/main.py` (FastAPI `HTMLResponse`).
- **Template** — archivo Jinja2 en `app/templates/`.
- **Entidad** — modelo ORM en `app/models/` que persiste los datos.
- **Endpoints** — uno o más routers en `app/api/v1/`. Formato `METHOD /ruta`.
- **Seed** — bloque de `app/seed.py` que crea el dato demo. Si dice "—", no se siembra.
- **Servicio** — capa de lógica en `app/services/`.
- **Schema** — contrato request/response en `app/schemas/`.

## Datos demo del seed

- **Usuarios:**
  - `maria@cafenorte.cl` / `demo1234` (owner Café Norte)
- **Tenants:**
  - `cafe-norte` (slug) — Café Norte SpA — Industria GASTRO — Moneda CLP
  - `bicifix` (slug) — BiciFix Repuestos — Industria RETAIL — Moneda CLP
- **Productos:** 8 productos en Café Norte (cafés, tes, pastelería, sándwiches) y 6 en BiciFix.
- **Categorías:** `cafes`, `tes`, `pasteleria`, `sandwiches` (Café Norte); `repuestos`, `accesorios` (BiciFix).
- **Sucursales:** 1 por tenant.
- **Landing config:** 1 por tenant.
- **QR codes:** 3 por tenant (mesa, entrada, promo).
- **Promociones:** 2 por tenant (1 fija + 1 cupón).
- **Costos (BusinessCosts):** defaults V8 (sueldo dueño 700k, arriendo 450k, margen objetivo 30%, 160h/mes). `version=1` hasta que el owner los edite.

---

## 1. Pantallas del Dashboard Owner

### 1.1 Home / Inicio
- **URL:** `/dashboard/`
- **Template:** `app/templates/dashboard/index.html`
- **Entidades:** `Tenant`, `Order` (resumen), `Product` (conteos)
- **Endpoints:**
  - `GET /api/v1/tenants/me` — info del tenant activo
  - `GET /api/v1/stats/summary` — métricas rápidas (ventas hoy, productos, etc.)
- **Servicio:** `StatsService` (en `app/services/stats_service.py`)
- **Seed:** Tenants `cafe-norte` y `bicifix`.

### 1.2 Productos
- **URL:** `/dashboard/products`
- **Template:** `app/templates/dashboard/products.html`
- **Entidades:** `Product`, `Category`, `BranchProduct`
- **Endpoints:**
  - `GET /api/v1/products?branch_id=…` — listar productos del branch
  - `POST /api/v1/products` — crear
  - `PUT /api/v1/products/{id}` — actualizar (incluye `production_time_min`, `cost_cents`)
  - `DELETE /api/v1/products/{id}` — archivar
  - `GET /api/v1/categories` — para el selector
  - `POST /api/v1/products/{id}/pricing-suggestion` — preview de precio sugerido
- **Servicio:** `ProductService`, `product_pricing.compute_for_product()`
- **Schemas:** `ProductCreate`, `ProductUpdate`, `ProductOut`, `ProductListItem` (incluye `pricing_health`, `current_margin_pct`, `suggested_price_cents`)
- **Seed:** 8 productos en Café Norte, 6 en BiciFix.

### 1.3 Pedidos (Orders)
- **URL:** `/dashboard/orders`
- **Template:** `app/templates/dashboard/orders.html`
- **Entidades:** `Order`, `OrderItem`, `Customer`
- **Endpoints:**
  - `GET /api/v1/orders` — listar con filtros (status, branch, customer, fecha)
  - `GET /api/v1/orders/{id}` — detalle
  - `POST /api/v1/orders/{id}/status` — cambiar estado (PENDING → CONFIRMED → …)
  - `POST /api/v1/orders/{id}/cancel` — cancelar
- **Servicio:** `OrderService`
- **Seed:** 0 (se crean vía flujo público o se cargan en runtime).

### 1.4 Pipeline (Kanban de pedidos)
- **URL:** `/dashboard/pipeline`
- **Template:** `app/templates/dashboard/pipeline.html`
- **Entidades:** `Order`
- **Endpoints:**
  - `GET /api/v1/orders?status=pending,confirmed,preparing,ready,delivered` — todas las columnas
  - `POST /api/v1/orders/{id}/status` — drag & drop entre columnas
- **Servicio:** mismo `OrderService`
- **Seed:** — (visualización en vivo).

### 1.5 Clientes
- **URL:** `/dashboard/customers`
- **Template:** `app/templates/dashboard/customers.html`
- **Entidades:** `Customer`, `Order` (historial)
- **Endpoints:**
  - `GET /api/v1/customers?segment=inactive|top|new|no_orders` — segmentos
  - `GET /api/v1/customers/{id}` — detalle
  - `PUT /api/v1/customers/{id}` — editar
- **Servicio:** `CustomerService`
- **Seed:** 0 (se crean al registrarse vía landing o scanner).

### 1.6 Promociones
- **URL:** `/dashboard/promotions`
- **Template:** `app/templates/dashboard/promotions.html`
- **Entidades:** `Promotion`
- **Endpoints:**
  - `GET /api/v1/promotions?active=true|false`
  - `POST /api/v1/promotions` — crear
  - `PUT /api/v1/promotions/{id}` — actualizar
  - `DELETE /api/v1/promotions/{id}`
- **Servicio:** `PromotionService`
- **Seed:** 2 por tenant (1 descuento %, 1 cupón código).

### 1.7 QRs
- **URL:** `/dashboard/qrs`
- **Template:** `app/templates/dashboard/qrs.html`
- **Entidades:** `QrCode`
- **Endpoints:**
  - `GET /api/v1/qrs?target=menu|promo|landing|table`
  - `POST /api/v1/qrs` — crear
  - `GET /api/v1/qrs/{id}/download` — descargar PNG
  - `DELETE /api/v1/qrs/{id}`
- **Servicio:** `QrService`
- **Seed:** 3 por tenant (mesa, entrada, promo).

### 1.8 Inventario
- **URL:** `/dashboard/inventory`
- **Template:** `app/templates/dashboard/inventory.html`
- **Entidades:** `Product` (stock), `BranchProduct`
- **Endpoints:**
  - `GET /api/v1/products?track_inventory=true`
  - `PUT /api/v1/products/{id}` — actualizar `stock`, `low_stock_threshold`
  - `POST /api/v1/products/bulk-stock` — bulk update
- **Servicio:** `ProductService`
- **Seed:** — (los productos seeded tienen `stock=10` por default).

### 1.9 Pagos
- **URL:** `/dashboard/payments`
- **Template:** `app/templates/dashboard/payments.html`
- **Entidades:** `Order`, `PaymentIntent` (si existe)
- **Endpoints:**
  - `GET /api/v1/orders?status=paid`
  - `GET /api/v1/stats/sales?period=day|week|month`
- **Servicio:** `StatsService`
- **Seed:** — (depende de pagos reales en flujo público).

### 1.10 Stats / Analytics
- **URL:** `/dashboard/stats`
- **Template:** `app/templates/dashboard/stats.html`
- **Entidades:** `Order`, `Product` (top sellers)
- **Endpoints:**
  - `GET /api/v1/stats/summary`
  - `GET /api/v1/stats/sales?period=…`
  - `GET /api/v1/analytics/inventory?category=low_stock|out_of_stock|top_selling`
  - `GET /api/v1/analytics/customer-segments?segment=…`
  - `GET /api/v1/opportunities` — oportunidades detectadas
- **Servicio:** `AnalyticsService`, `OpportunityEngine`
- **Seed:** —

### 1.11 Cotizaciones (Quotes)
- **URL:** `/dashboard/quotes`
- **Template:** `app/templates/dashboard/quotes.html`
- **Entidades:** `Quote`, `QuoteItem`
- **Endpoints:**
  - `GET /api/v1/quotes`
  - `POST /api/v1/quotes` — crear
  - `PUT /api/v1/quotes/{id}/status`
  - `GET /api/v1/quotes/{id}/public-link` — token público
- **Servicio:** `QuoteService`
- **Seed:** —

### 1.12 Landing (editor visual)
- **URL:** `/dashboard/landing`
- **Template:** `app/templates/dashboard/landing.html`
- **Entidades:** `LandingConfig`
- **Endpoints:**
  - `GET /api/v1/landing/{slug}` — público
  - `PUT /api/v1/landing` — owner edita
  - `POST /api/v1/landing/upload-image`
- **Servicio:** `LandingService`
- **Seed:** 1 por tenant (defaults).

### 1.13 Sitio / Site config
- **URL:** `/dashboard/site`
- **Template:** `app/templates/dashboard/site.html`
- **Entidades:** `SiteConfig` (por tenant), `Tenant.settings`
- **Endpoints:**
  - `GET /api/v1/site-config`
  - `PUT /api/v1/site-config`
- **Servicio:** `SiteConfigService`
- **Seed:** 1 fila por tenant (defaults).

### 1.14 Webhooks
- **URL:** `/dashboard/webhooks`
- **Template:** `app/templates/dashboard/webhooks.html`
- **Entidades:** `Webhook`, `WebhookEvent`, `WebhookDelivery`
- **Endpoints:**
  - `GET /api/v1/webhooks`
  - `POST /api/v1/webhooks` — registrar
  - `GET /api/v1/webhooks/{id}/deliveries`
  - `POST /api/v1/webhooks/{id}/test` — envío de prueba
- **Servicio:** `WebhookService`
- **Seed:** — (solo si el owner los crea).

### 1.15 AI (Asistente conversacional)
- **URL:** `/dashboard/ai`
- **Template:** `app/templates/dashboard/ai.html`
- **Entidades:** `AiConversation`, `AiMetricsDaily`
- **Endpoints:**
  - `POST /api/v1/ai/chat` — enviar mensaje (con circuit breaker)
  - `GET /api/v1/ai/conversations` — historial
- **Servicio:** `AIOrchestrator` (con fallback determinístico)
- **Seed:** — (conversaciones se crean en runtime).

### 1.16 Bookings (Reservas)
- **URL:** `/dashboard/admin_bookings`
- **Template:** `app/templates/dashboard/admin_bookings.html`
- **Entidades:** `Booking`, `BookingSlot`, `BookingService`
- **Endpoints:**
  - `GET /api/v1/bookings?date=…`
  - `POST /api/v1/bookings/{id}/confirm`
  - `POST /api/v1/bookings/{id}/cancel`
  - `GET /api/v1/bookings/availability?service_id=…&date=…`
- **Servicio:** `BookingService`
- **Seed:** —

### 1.17 Notificaciones (Bell badge + Centro) — Fase 5/6
- **URL:** `/dashboard/notifications`
- **Template:** `app/templates/dashboard/notifications.html`
- **Componentes UI:**
  - **Bell badge** en `dashboard/base.html` (header): ícono SVG + 2 contadores (critical/warning) + dropdown con top 3
  - **Sidebar link** "Notificaciones" en `dashboard/base.html` con badge inline (total)
  - **Página** `/dashboard/notifications`: 4 KPI cards (total, critical, warning, info) + chips de filtro (severity/category) + lista con rail lateral de color
- **Endpoints (Fase 5):**
  - `GET /api/v1/tenants/{tid}/notifications/summary` → `{ total, by_severity, by_category, top_3, generated_at }` (para el bell)
  - `GET /api/v1/tenants/{tid}/notifications?severity=&category=&limit=` → `{ count, items, total_by_severity, total_by_category }` (para la página)
- **Entidades:** ninguna tabla nueva. Las notificaciones se **derivan** (compute-time) desde el estado actual de: `Product`, `BusinessCosts`, `Order`, `LandingConfig`, `Tenant.created_at`, `Booking`.
- **Servicio:** `NotificationsEngine` (Fase 4, `app/services/notifications.py`) — 9 reglas N1-N9:
  - N1 Pricing — producto con margen < 5% (`critical`)
  - N2 Pricing — producto con margen < 15% (`warning`)
  - N3 Inventory — producto con `stock <= low_stock_threshold` (`warning`)
  - N4 Inventory — producto con `stock == 0` (`critical`)
  - N5 Orders — pedido pendiente > 24h (`warning`)
  - N6 Orders — nuevo pedido en las últimas 2h (`info`)
  - N7 Costs — `BusinessCosts.version == 1` o sin configurar (`info`)
  - N8 Landing — `LandingConfig` sin `hero_image_url` (`info`)
  - N9 System — tenant recién creado (< 24h) (`info`, one-time)
- **Severidades:** `info | warning | critical`
- **Categorías:** `pricing | inventory | orders | costs | system`
- **Schemas:** `NotificationOut`, `NotificationListOut`, `NotificationSummaryOut` (en `app/schemas/notifications.py`)
- **JS Helper:** `WH.Notifications` en `app/static/js/app.js` (Fase 6):
  - `summary(tenantId?)` → fetch del summary
  - `list(tenantId?, params)` → fetch de la lista con filtros
  - `lastSummary()` → cache del último fetch del bell
- **Polling:** el bell hace `GET /summary` cada 60s (configurable).
- **Aislamiento:** todos los endpoints usan `get_tenant_for_membership` → 403 si el user no es miembro del tenant.
- **Seed:** — (las notificaciones se computan en runtime desde el estado actual del tenant).

---

## 2. Pantallas del Dashboard Admin

### 2.1 Costos (Fase 2 V8)
- **URL:** `/dashboard/costs`
- **Template:** `app/templates/dashboard/costs.html`
- **Entidades:** `BusinessCosts`
- **Endpoints:**
  - `GET /api/v1/tenants/{id}/costs` — leer config + breakdown
  - `PUT /api/v1/tenants/{id}/costs` — actualizar
  - `POST /api/v1/tenants/{id}/costs/pricing-suggestion` — preview
- **Servicio:** `CostsService` + `product_pricing.compute_for_product()`
- **Schemas:** `BusinessCostsUpdate`, `BusinessCostsBreakdown`, `PricingSuggestionRequest/Response`
- **Seed:** defaults V8 (`version=1`) — `app/services/costs_service.py:COST_FIELDS_META`.
- **Campos (14):** ver `docs/V8_COSTOS.md` o el listado en `costs_service.COST_FIELDS_META`.

### 2.2 Loyalty (Admin)
- **URL:** `/dashboard/admin_loyalty`
- **Template:** `app/templates/dashboard/admin_loyalty.html`
- **Entidades:** `LoyaltyCampaign`, `LoyaltyMember`, `LoyaltyStamp`
- **Endpoints:**
  - `GET /api/v1/loyalty/campaigns`
  - `POST /api/v1/loyalty/campaigns`
  - `GET /api/v1/loyalty/members`
  - `GET /api/v1/loyalty/stats`
- **Servicio:** `LoyaltyService`
- **Seed:** 1 campaña demo por tenant.

### 2.3 Scanner (Admin / POS)
- **URL:** `/dashboard/admin_scanner`
- **Template:** `app/templates/dashboard/admin_scanner.html`
- **Entidades:** `LoyaltyMember`, `LoyaltyStamp` (validación)
- **Endpoints:**
  - `POST /api/v1/loyalty/c/{slug}/scan` — validar QR + cashier_pin
  - `POST /api/v1/loyalty/c/{slug}/register` — alta de miembro
- **Servicio:** `LoyaltyService` con anti-fraude (`device_fp` + `cashier_pin`)

### 2.4 AI Admin
- **URL:** `/dashboard/admin_ai`
- **Template:** `app/templates/dashboard/admin_ai.html`
- **Entidades:** `AiMetricsDaily`, configuración LLM
- **Endpoints:**
  - `GET /api/v1/admin/ai/metrics`
  - `GET /api/v1/admin/ai/agents`
  - `POST /api/v1/admin/ai/agents/{id}/test`
- **Servicio:** `AIOrchestrator` (superusuario)
- **Auth:** requiere rol `OWNER` con permisos especiales.

### 2.5 Superadmin
- **URL:** `/dashboard/superadmin`
- **Template:** `app/templates/dashboard/superadmin.html`
- **Entidades:** todos los tenants
- **Endpoints:**
  - `GET /api/v1/superadmin/tenants`
  - `GET /api/v1/superadmin/metrics`
  - `POST /api/v1/superadmin/tenants/{id}/suspend`
- **Auth:** requiere rol `SUPERADMIN`.

---

## 3. Pantallas Públicas (sin auth)

### 3.1 Landing pública
- **URL:** `/c/{slug}`
- **Template:** `app/templates/public/landing.html`
- **Entidades:** `Tenant`, `LandingConfig`, `Product` (catálogo)
- **Endpoints:**
  - `GET /api/v1/public/landing/{slug}`
  - `GET /api/v1/public/landing/{slug}/products`
  - `POST /api/v1/public/landing/{slug}/contact`

### 3.2 Menú QR
- **URL:** `/menu/{slug}`
- **Template:** `app/templates/public/menu.html`
- **Entidades:** `Product`, `Category`
- **Endpoints:**
  - `GET /api/v1/public/menu/{slug}`

### 3.3 Reservas
- **URL:** `/book/{slug}`
- **Template:** `app/templates/public/booking.html`
- **Entidades:** `Booking`, `BookingSlot`
- **Endpoints:**
  - `GET /api/v1/public/booking/{slug}/availability`
  - `POST /api/v1/public/booking/{slug}/reserve`

### 3.4 Cotización pública
- **URL:** `/q/{token}`
- **Template:** `app/templates/public/quote.html`
- **Entidades:** `Quote`
- **Endpoints:**
  - `GET /api/v1/public/quote/{token}`

### 3.5 Registro Loyalty
- **URL:** `/loyalty/{slug}/register`
- **Template:** `app/templates/public/loyalty_register.html`
- **Entidades:** `LoyaltyMember`
- **Endpoints:**
  - `POST /api/v1/loyalty/c/{slug}/register`

---

## 4. Servicios de soporte (sin pantalla)

### 4.1 NotificationsEngine (Fase 4)
- **Módulo:** `app/services/notifications.py`
- **Endpoint (Fase 6):** `GET /api/v1/notifications?limit=20`
- **Sub-endpoint badge:** `GET /api/v1/notifications/summary`
- **Consumido por:** futura campanita en `app/templates/dashboard/base.html` (header)
- **Reglas:** N1-N9 (ver docstring del módulo)
- **Tests:** `tests/test_notifications.py` (27 tests)

### 4.2 OpportunityEngine
- **Módulo:** `app/services/opportunity_engine.py`
- **Endpoint:** `GET /api/v1/opportunities?limit=12`
- **Endpoint brief:** `GET /api/v1/opportunities/daily-brief`
- **Consumido por:** pantalla `/dashboard/stats` (sección "Oportunidades")
- **Reglas:** R1-R6 (stock bajo, sin rotación, sobre-stock, cliente inactivo, etc.)

---

## 5. Mapa de notificaciones (V8 → engine)

| Regla | Pantalla destino | Categoría | Severidad | Dispara en |
|-------|------------------|-----------|-----------|-----------|
| N1 critical margin | `/dashboard/products/{id}#pricing` | pricing | critical | health="danger" |
| N2 low margin | `/dashboard/products/{id}#pricing` | pricing | warning | health="warning" |
| N3 pricing below | `/dashboard/products/{id}#pricing` | pricing | warning | gap >= 10% |
| N4 out of stock | `/dashboard/products/{id}#inventory` | inventory | critical | stock==0 + track_inv |
| N5 low stock | `/dashboard/products/{id}#inventory` | inventory | warning | stock <= threshold |
| N6 pending order | `/dashboard/orders/{id}` | orders | warning | PENDING > 24h |
| N7 costs unconfigured | `/dashboard/costs` | costs | info | BusinessCosts.version == 1 |
| N8 high cost_hour | `/dashboard/costs` | costs | warning | cost_hour_cents > 15.000 |
| N9 welcome | `/dashboard/onboarding` | system | info | tenant < 24h de creado |

---

## 6. Fases de UI pendientes (consumen engines ya listos)

| Fase | Pantalla | Engine backend ya listo |
|------|----------|--------------------------|
| 6 | Bell badge + dropdown en header | `NotificationsEngine` |
| 6 | Página `/dashboard/notifications` (filtrable) | `NotificationsEngine` |
| 6 | Push browser (Web Push API) | `NotificationsEngine` (nueva regla) |
| 7 | `GrowthCoach` agent con notificaciones | `AIOrchestrator` |
| 7 | Auto-sugerir horario de promo | `OpportunityEngine` R5/R6 |

---

**Autor:** MiniMax Agent
**Fecha:** 2026-08-23
**Commit base:** v0.2.0 (post-eddeb9d)
