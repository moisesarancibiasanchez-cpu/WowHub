# WowHub — Prototipo Python

Plataforma SaaS modular para PyMEs en LATAM. **v0.4.0**: Página, Catálogo, QR, Promociones, Pedidos, Pagos, Reservas, Loyalty, AI Assistant, Uploads, Audit, Webhooks, **Cotizaciones**, **Pipeline Kanban**, **Inventario**, **Costos V8 (Fase 2)**, **Notificaciones (Fase 4)**.

Construido con **FastAPI + SQLAlchemy 2.0 + Pydantic v2 + Jinja2 + JS vanilla**.

## ⚡ Quick start

```bash
# 1. Clonar e instalar
cd wowhub-app
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# 2. Variables de entorno
cp .env.example .env
# (editar .env si quieres)

# 3. Sembrar datos demo
python -m app.seed

# 4. Arrancar
uvicorn app.main:app --reload
```

Abre:

- **Demo landing**: http://localhost:8000/u/cafe-norte
- **Login**: http://localhost:8000/login (maria@cafenorte.cl / demo1234)
- **API docs**: http://localhost:8000/docs

## 🐳 Docker

```bash
docker-compose up --build
# luego en otro terminal:
docker-compose exec api python -m app.seed
```

## 🏗️ Arquitectura

### Stack

| Capa | Tecnología | Propósito |
|---|---|---|
| API | FastAPI 0.110 | HTTP + OpenAPI 3.1 |
| ORM | SQLAlchemy 2.0 | Modelado + multi-tenant |
| DB | SQLite (dev) / PostgreSQL 16 (prod) | Persistencia |
| Auth | JWT (HS256) + bcrypt | Sesiones stateless |
| Validación | Pydantic v2 | Schemas entrada/salida |
| UI | Jinja2 + JS vanilla (`app/static/js/`) + tokens.css | Panel + landing pública |
| QR | qrcode + Pillow | Generación PNG |
| Uploads | Pillow + StaticFiles | JPG/PNG ≤ 3 MB, scoped por tenant |
| AI | OpenAI-compatible LLM (MiniMax-M3) | Asistente por tenant con circuit breaker |
| Tests | pytest + TestClient + Playwright (E2E) | Cobertura de unidades, integración y flujos |

### Multi-tenant

- Cada entidad de negocio lleva `tenant_id` (UUID).
- Las queries de servicios filtran siempre por tenant.
- Aislamiento reforzado con `Membership.user_id + tenant_id` único.
- Storage aislado por tenant: `./storage/{tenant_id}/...` (imágenes subidas).
- En producción: agregar **PostgreSQL Row-Level Security** (ver spec sección 6).

### Modelo de datos (v0.3.0)

```
User ─< Membership >─ Tenant ─< Branch ─< BranchProduct >─ Product
                                │                │
                                │                └─ stock por sucursal
                                │
                                ├──< Category ─< Product
                                │
                                ├──< Customer ─< Order ─< OrderItem
                                │                  │
                                │                  └──< Payment (mock | mercadopago)
                                │
                                ├──< Promotion        ─< PromotionUsage
                                ├──< QrCode
                                ├──< LandingConfig (1:1)
                                ├──< SiteConfig (1:1)         # theme + branding
                                ├──< Upload                   # archivos subidos
                                ├──< Booking                  # reservas por servicio
                                ├──< LoyaltyPass ─< LoyaltyStamp
                                ├──< Cart                     # carrito anónimo + bound
                                ├──< Invoice                  # boleta/factura
                                ├──< TokenBlacklist           # JWT revocados
                                ├──< WebhookEvent             # outbox + retries
                                ├──< Quote ─< QuoteItem       # cotizaciones (v0.3.0)
                                └──< AuditLog                 # quién hizo qué
```

25 entidades cubriendo CRM ligero, e-commerce básico, reservas, fidelización, pagos, webhooks, auditoría, branding, uploads y cotizaciones.

### Endpoints principales (v0.2.0 — 23 routers)

```
# ── Auth & sesión ─────────────────────────────
POST   /api/v1/auth/register
POST   /api/v1/auth/login
POST   /api/v1/auth/refresh
GET    /api/v1/auth/me
GET    /api/v1/auth/me/session        # rehidrata current_tenant
POST   /api/v1/auth/password/forgot
POST   /api/v1/auth/password/reset
POST   /api/v1/auth/logout

# ── Tenants ───────────────────────────────────
GET    /api/v1/tenants                # propios
POST   /api/v1/tenants
GET    /api/v1/tenants/{id}
PATCH  /api/v1/tenants/{id}

# ── Recursos por tenant (CRUD + search) ─────
# Products, Categories, Customers, Branches, Promotions, QRs,
# Landing, SiteConfig, BranchProducts (stock por sucursal)
GET    /api/v1/tenants/{tid}/products?page=1&page_size=20&search=...
POST   /api/v1/tenants/{tid}/products
GET    /api/v1/tenants/{tid}/products/{id}
PATCH  /api/v1/tenants/{tid}/products/{id}
DELETE /api/v1/tenants/{tid}/products/{id}
# (mismo patrón para el resto)

# ── Uploads (imágenes) ───────────────────────
POST   /api/v1/tenants/{tid}/uploads                  # multipart: file + purpose
GET    /api/v1/tenants/{tid}/uploads?entity_type=...
DELETE /api/v1/tenants/{tid}/uploads/{upload_id}
# Servidas vía /storage/{tenant_id}/{filename} (StaticFiles)

# ── Pedidos, pagos, reservas, loyalty, carrito, facturas ─
GET    /api/v1/tenants/{tid}/orders
POST   /api/v1/tenants/{tid}/orders                   # crea + PaymentIntent
GET    /api/v1/tenants/{tid}/orders/{id}
POST   /api/v1/tenants/{tid}/payments                 # mock/mercadopago
POST   /api/v1/tenants/{tid}/bookings
GET    /api/v1/tenants/{tid}/loyalty/passes
POST   /api/v1/tenants/{tid}/loyalty/redeem
# (más rutas en cada router)

# ── Stats, CSV, búsqueda, auditoría, webhooks, i18n, legal, onboarding
GET    /api/v1/tenants/{tid}/stats/overview
POST   /api/v1/tenants/{tid}/csv/export
GET    /api/v1/tenants/{tid}/search?q=...
GET    /api/v1/tenants/{tid}/audit?actor=...
POST   /api/v1/tenants/{tid}/webhooks
GET    /api/v1/i18n/{locale}.json
GET    /api/v1/tenants/{tid}/onboarding/state

# ── AI (asistente por tenant) ────────────────
POST   /api/v1/tenants/{tid}/ai/chat                  # → LLM + tools
GET    /api/v1/tenants/{tid}/ai/history
# (admin) configurar modelo, system prompt, límites
POST   /api/v1/admin/ai/config

# ── PÚBLICOS — sin auth ───────────────────────
GET    /api/v1/public/t/{slug}/profile
GET    /api/v1/public/t/{slug}/catalog
GET    /api/v1/public/t/{slug}/products/{product_slug}
GET    /api/v1/public/t/{slug}/categories
GET    /api/v1/public/t/{slug}/promotions
GET    /api/v1/public/t/{slug}/branches
GET    /api/v1/public/t/{slug}/landing
GET    /api/v1/public/t/{slug}/site-config
POST   /api/v1/public/orders                          # checkout anónimo
POST   /api/v1/public/loyalty/lookup
GET    /api/v1/public/loyalty/{pass_id}

# ── QR — redirect ────────────────────────────
GET    /r/{short_code}                                # → /u/{slug}/catalogo, etc.
```

## 📂 Estructura

```
wowhub-app/
├── app/
│   ├── api/v1/             # 23 routers REST
│   │   ├── auth.py · tenants.py · products.py · categories.py
│   │   ├── customers.py · promotions.py · qrs.py · landing.py
│   │   ├── branches.py · branch_products.py · site_config.py
│   │   ├── orders.py · payments.py · bookings.py · loyalty.py
│   │   ├── carts.py · invoices.py · webhooks.py · audit.py
│   │   ├── stats.py · search.py · csv.py · i18n.py · legal.py
│   │   ├── onboarding.py · password.py · uploads.py
│   │   ├── ai.py · admin_ai.py · public.py
│   ├── core/               # tenant_context, errors, pagination, rate limit
│   ├── models/             # 24 modelos SQLAlchemy (ver diagrama arriba)
│   ├── schemas/            # Schemas Pydantic v2
│   ├── services/           # Lógica de negocio (auth, products, loyalty, llm_client, …)
│   │   └── upload_service.py   # JPG/PNG ≤ 3 MB + base_url dinámico
│   ├── templates/          # Jinja2
│   │   ├── auth/ · dashboard/ · public/ · legal/ · payments/
│   │   ├── base.html · home.html · home_pro.html
│   ├── static/             # CSS + JS
│   │   ├── css/  (tokens.css · app.css · landing-pro.css · ai.css)
│   │   └── js/   (app.js · ai.js)   # WH.Upload + WH.ImagePicker
│   ├── config.py           # Settings (Pydantic v2)
│   ├── database.py         # Engine, session, Base
│   ├── deps.py             # FastAPI dependencies (auth, tenant, rate limit)
│   ├── security.py         # JWT + bcrypt
│   ├── seed.py             # Datos demo
│   └── main.py             # App factory + UI routes + /storage mount
├── scripts/                # Utilidades one-off
│   ├── seed_demo.py
│   └── fix_upload_urls.py  # reescribe URLs existentes a PUBLIC_BASE_URL
├── storage/                # Archivos subidos (por tenant_id)
├── tests/                  # pytest + Playwright
│   ├── test_auth.py · test_tenants.py · test_products.py
│   ├── test_promotions.py · test_public.py · test_qr.py
│   ├── test_loyalty.py
│   ├── test_ai_circuit_breaker.py · test_ai_orchestrator_fallback.py
│   ├── test_ai_strip_think.py
│   └── e2e/                # Playwright (test_loyalty_flow.py)
├── pyproject.toml
├── .env.example
├── Dockerfile
└── docker-compose.yml
```

## 🤖 AI Assistant (v0.2.0)

Asistente conversacional por tenant, con herramientas (tools) que ejecutan acciones reales sobre el negocio (consultar productos, crear pedidos, etc.).

- **Proveedor LLM**: OpenAI-compatible (recomendado MiniMax). Configurable por env (`LLM_PROVIDER`, `LLM_BASE_URL`, `LLM_MODEL`).
- **Aislamiento por tenant**: cada tenant tiene su `system_prompt` y límites (`AI_DAILY_MESSAGE_LIMIT`).
- **Tool use**: el agente puede llamar tools que ejecutan servicios del backend (crear orden, buscar producto, etc.).
- **Resiliencia**:
  - **Circuit breaker**: si el LLM falla N veces seguidas (`LLM_CB_FAIL_THRESHOLD`), el circuito se abre por `LLM_CB_RESET_SECONDS` y el endpoint responde con un fallback pre-canned.
  - **Fallback**: cuando el circuito está abierto o el LLM no responde, `ai_orchestrator` devuelve respuestas razonables por sub-agente (`AI_FALLBACK_ENABLED`).
  - **Strip de `<think>…</think>`**: tags internos del LLM que no deben llegar al usuario final (`test_ai_strip_think.py`).
- **Historial**: últimas N interacciones por usuario (`AI_CONTEXT_MESSAGES`).
- **Admin**: el owner puede editar el system prompt y los límites por tenant desde `/dashboard/admin_ai`.

## 🖼️ Imágenes: subir archivos (v0.2.0)

Reemplaza los `<input type="url">` clásicos por un selector con drag & drop, preview y subida automática al server.

**Límites (cliente y server, autoridad en `app/services/upload_service.py`):**

| | |
|---|---|
| Formatos | `image/jpeg`, `image/png` |
| Tamaño máx. | 3 MB |
| Storage | Local: `./storage/{tenant_id}/{filename}`. S3: placeholder |
| Naming | `{secrets.token_hex(8)}-{slug_stem}.{ext}` (anti-colisiones y anti-enumeración) |
| Validación | `PIL.Image.verify()` rechaza archivos disfrazados de imagen |

**Endpoint:**

```http
POST /api/v1/tenants/{tid}/uploads
Content-Type: multipart/form-data
Authorization: Bearer <jwt>

file:        (binario, JPG/PNG ≤ 3 MB)
purpose:     "product_image" | "logo" | "hero" | ...   # opcional
entity_type: "product" | "landing" | ...                # opcional
entity_id:   <uuid>                                      # opcional
```

Respuesta `201 Created` → `{url, width, height, filename, ...}`. Las URLs se sirven vía `GET /storage/{tenant_id}/{filename}` (StaticFiles).

**JS helpers (expuestos en `window.WH`):**

```html
<!-- 1) Declarativo: reemplaza el <input type="url"> por un picker -->
<div data-image-picker
     data-target="p_image_url"
     data-purpose="product_image"
     data-max-size-mb="3"
     data-accept="image/jpeg,image/png"></div>
<input type="hidden" id="p_image_url" name="image_url">

<script>
  WH.ImagePicker.initAll();      // activa todos los [data-image-picker] de la página

  // Al editar, refresca el preview si el valor cambia programáticamente:
  WH.ImagePicker.setValue("p_image_url", product.image_url);
</script>
```

```js
// 2) Imperativo: subir un File desde cualquier handler
const out = await WH.Upload.image(file, { purpose: "logo" });
// → {url, width, height, ...}
// Lanza Error si el archivo no pasa validación cliente o server.
```

**Resolución dinámica de URL pública:** el backend usa `request.base_url` (el host desde el que el browser habla) en lugar de leer `BASE_URL`/`PUBLIC_BASE_URL` de env. Esto garantiza que la URL guardada en la DB sea siempre alcanzable, sea `http://localhost:8000` en dev o el dominio público en Railway.

**Migración de URLs existentes** (DBs creadas antes de este fix):

```bash
# Reescribe http://localhost:8000/storage/* → PUBLIC_BASE_URL/storage/*
python scripts/fix_upload_urls.py --dry-run
python scripts/fix_upload_urls.py
```

## 💰 Costos V8 (Fase 2) — pricing con margen objetivo

Módulo de estructura de costos fijos mensuales por tenant. Es la **fuente de verdad** para `costo_hora` y, en consecuencia, para el costo real de los productos y las sugerencias de precio.

**Fórmulas:**

```
total_fijo_mensual  = Σ campos monetarios (no NA)
costo_hora          = total_fijo_mensual / horas_productivas
costo_real          = costo_insumos + (tiempo_min / 60) * costo_hora
precio_sugerido     = costo_real / (1 - margen_objetivo/100)
margen              = (precio - costo_real) / precio * 100
```

**14 campos en 4 secciones:**

| Sección | Campos |
|---------|--------|
| **Personal** | `owner_salary_cents`, `workers_salary_cents` |
| **Operación** | `productive_hours_per_month`, `target_margin_pct` |
| **Básicos** | `rent_cents`, `electricity_cents`, `water_cents`, `gas_cents` |
| **Otros** | `software_cents`, `advertising_cents`, `payment_commission_cents`, `packaging_cents`, `maintenance_cents`, `depreciation_cents`, `waste_pct` |

**Endpoints:**

```http
GET   /api/v1/tenants/{tid}/costs                      # breakdown actual
PUT   /api/v1/tenants/{tid}/costs                      # actualizar (recalcula cost_hour)
POST  /api/v1/tenants/{tid}/costs/pricing-suggestion   # preview de precio
```

**Health checks por producto** (derivados de Costos V8):

| Health | Significado |
|--------|-------------|
| `healthy` | margen >= target |
| `warning` | margen >= 50% del target |
| `danger` | margen < 50% del target |
| `unknown` | sin Costos configurados |

**Producto expone** (`ProductListItem`): `pricing_health`, `current_margin_pct`, `suggested_price_cents`, `cost_real_cents`, `cost_hour_used_cents`. La celda "Salud" de la tabla de productos muestra uno de: `Saludable`, `Margen bajo`, `Subir precio`, `Margen crítico`, `—`.

**Pantalla:** `/dashboard/costs` (template `costs.html`, 3 secciones colapsables + botón "No aplica" por campo).

**Versionado:** `BusinessCosts.version == 1` indica defaults (nunca editado). Las reglas de notifications disparan la alerta N7 hasta que el owner edite la primera vez.

## 🔔 Notificaciones (Fase 4) — event-based generator

Motor de notificaciones accionables que el dashboard consumirá en Fase 6 (bell badge + dropdown + página filtrable). Hoy **el backend está 100% listo**: la UI solo debe consumir el endpoint y renderizar.

**Diferencia clave con `OpportunityEngine`:**

| | `OpportunityEngine` | `NotificationsEngine` |
|---|---|---|
| Concepto | Ideas / tendencias | Hechos / alertas |
| Severidades | `atencion`, `oport`, `inact` | `info`, `warning`, `critical` |
| Orden | por `score` (0-100) | por severidad (critical primero) |
| Cantidad | muchas (top-N) | pocas y curadas |
| Acción | recomendación | botón directo |

**Reglas MVP:**

| ID | Categoría | Severidad | Detecta |
|----|-----------|-----------|---------|
| N1 | pricing | critical | Margen crítico (health="danger") |
| N2 | pricing | warning | Margen bajo (health="warning") |
| N3 | pricing | warning | Precio actual < sugerido en ≥ 10% |
| N4 | inventory | critical | Sin stock (stock=0, track_inventory) |
| N5 | inventory | warning | Stock bajo (stock ≤ threshold) |
| N6 | orders | warning | Pedido PENDING > 24h |
| N7 | costs | info | Costos sin configurar (BusinessCosts.version=1) |
| N8 | costs | warning | Costo_hora > 15.000 CLP/h |
| N9 | system | info | Bienvenida (tenant < 24h) |

**Uso backend (Fase 6):**

```python
from app.services.notifications import NotificationsEngine

engine = NotificationsEngine(db, tenant_id)
summary = engine.summary()              # → para el badge del header
items = engine.detect_all(limit=20)     # → para el dropdown
```

**Output JSON (cada notificación):**

```json
{
  "id": "notif_a3f8b2c1d4e5f678",
  "severity": "critical",
  "category": "pricing",
  "title": "'Café Latte' tiene margen crítico",
  "body": "Estás ganando 12.0% (objetivo: 30%). ...",
  "action_label": "Subir precio",
  "action_url": "/dashboard/products/{id}#pricing",
  "entity_type": "product",
  "entity_id": "<uuid>",
  "detected_at": "2026-08-23T12:34:56+00:00",
  "metric": {"current_margin_pct": 12.0, "suggested_price_cents": 5500, ...}
}
```

**IDs estables:** SHA1 de `(regla, entity_id)`, prefijado `notif_`. Permite caching en el front y evita parpadeos al recargar.

**Thresholds configurables** (single source of truth en `THRESHOLDS`):
- `low_stock_default`: 5
- `high_cost_hour_cents`: 15.000 (CLP/h)
- `pending_order_hours`: 24
- `pricing_gap_pct`: 10

**Tests:** `tests/test_notifications.py` (27 tests cubriendo constantes, reglas individuales, orden por severidad, aislamiento entre tenants, JSON-serialización).

## 🧪 Tests

```bash
pytest                                        # todos
pytest -k test_auth                           # solo auth
pytest -k test_loyalty                        # loyalty
pytest -k test_ai                             # AI (circuit breaker, fallback, strip think)
pytest tests/e2e/test_loyalty_flow.py         # Playwright E2E (requiere server arriba)
pytest --cov=app                              # con cobertura
```

Suite cubre: autenticación, multi-tenancy, productos, promociones, QR, endpoints públicos, loyalty, AI (circuit breaker, orquestador con fallback, strip de `<think>…</think>`), **Costos V8 (pricing suggestion, health)**, **Notifications (9 reglas, summary, by_category/severity, aislamiento entre tenants)**, deprecation regressions y un flujo E2E con Playwright.

## 🔐 Seguridad

- **Passwords**: bcrypt con salt automático (passlib).
- **JWT**: HS256, access 60min + refresh 14 días + blacklist.
- **Multi-tenant**: filtro explícito por `tenant_id` en cada query de servicio.
- **Validación**: Pydantic v2 con validadores custom (slug format, password strength, compare_at >= price).
- **CORS**: configurable vía `CORS_ORIGINS`.
- **Uploads**:
  - Whitelist MIME (`image/jpeg`, `image/png`).
  - Límite de tamaño (3 MB) en cliente y server.
  - `PIL.Image.verify()` rechaza archivos disfrazados de imagen.
  - Nombres con `secrets.token_hex` (no se puede enumerar archivos por nombre).
  - Storage aislado por `tenant_id` en disco (un tenant nunca lee otro).
  - Las URLs se sirven vía `StaticFiles` con `check_dir=False` (no listable).

## 🧭 Roadmap

### ✅ v0.2.0 — MVP completo
- [x] 27 routers API, 25 modelos ORM, 23 servicios, dashboard + landing pública
- [x] Auth JWT + bcrypt + blacklist, multi-tenant, rate limit, audit, CORS
- [x] AI Assistant con circuit breaker + fallback determinístico
- [x] Uploads JPG/PNG ≤ 3MB con `PIL.Image.verify()` anti-fake
- [x] Loyalty Pass con QR rotativo + anti-fraude (`device_fp` + `cashier_pin`)
- [x] 611 tests + 13 tests de regresión de deprecations (0 warnings del proyecto)

### ✅ v0.3.0 — Costos V8 + refactors
- [x] **Fase 2 V8 — Costos**: 14 campos, `costo_hora`, `costo_real`, `precio_sugerido`, health (healthy/warning/danger/unknown)
- [x] **Fase 3 — Opportunities**: `OpportunityEngine` con 6 reglas (R1-R6)
- [x] Modal refactor (JS, `WH.Modal` + `WH.Confirm`)
- [x] Análisis integral + bug fixes de deprecations (Pydantic v2, Starlette ≥0.40, Python 3.12, pytest 8)

### ✅ v0.4.0 — Notifications (Fase 4) **← estamos acá**
- [x] **`NotificationsEngine`** (`app/services/notifications.py`) con 9 reglas (N1-N9)
- [x] `THRESHOLDS` configurables (single source of truth)
- [x] IDs estables (SHA1) para caching en front
- [x] 27 tests (`tests/test_notifications.py`)
- [x] Diccionario V8 (`docs/V8_DICTIONARY.md`) — mapa completo pantalla × entidad × endpoint × seed

### 🔜 v0.5.0 — Fase 6 UI (próximo)
- [ ] Bell badge en `base.html` (consume `NotificationsEngine.summary()`)
- [ ] Dropdown de notificaciones en el header (consume `detect_all(limit=20)`)
- [ ] Página `/dashboard/notifications` con filtros por categoría/severidad
- [ ] Marcar como leída / dismiss (nuevo modelo `NotificationDismiss` opcional)
- [ ] Web Push API para notificaciones críticas (browser-level)

### 🔜 v0.6.0 — Post-MVP
- [x] Migrar a Alembic (carpeta `alembic/` ya existe)
- [ ] PostgreSQL + Row-Level Security policies
- [ ] 2FA TOTP para owners
- [ ] Storage S3/R2 para imágenes (placeholder ya en `UploadService`)
- [ ] Variantes de imagen (thumb/medium/full) — hoy se guarda solo el original
- [ ] Strip de EXIF en el server (privacidad)
- [ ] Cola de eventos (Celery + Redis) para webhooks y emails transaccionales
- [ ] Más integraciones (WhatsApp Business, MercadoPago producción)
- [ ] i18n UI (ya soporta `country`, `locale`, `currency` por tenant en data)
- [ ] Growth Coach agent con notificaciones (Fase 7)

## 📚 Documentación

La documentación para clientes, equipo y reportes de avance vive en la carpeta
[`docs/`](docs/). Encontrarás:

- 🗂️ **[Diccionario V8](docs/V8_DICTIONARY.md)** — pantalla × entidad × endpoint × seed.
  Mapa de toda la app: para cada URL del dashboard, qué template, qué entidad ORM, qué
  endpoint API, qué regla de `NotificationsEngine` la alimenta, y qué dato de seed la puebla.
  **Es el documento de referencia entre fases** (Fase 4 → 5 → 6 → …).
- 📄 **[Análisis Integral](docs/ANALYSIS.md)** — auditoría estática + funcional del repo
  (puntos fuertes, débiles, bugs corregidos, roadmap v0.2.1/v0.3.0/v0.4.0).
- 📄 **[Informe de Integración del Asistente Virtual](docs/INFORME_INTEGRACION_IA.md)** —
  qué se entregó en la fase IA ↔ módulos de negocio, beneficios y roadmap.
- 📄 **[Informe del Sistema de Fidelización (Loyalty Pass)](docs/INFORME_FIDELIZACION.md)** —
  tarjetas digitales con sellos, QR rotativo anti-fraude, modos de aplicación.
- 📋 **[Changelog](docs/CHANGELOG.md)** — historial detallado de cambios.
- 🗂️ **[Índice de docs](docs/README.md)** — punto de entrada a la documentación.

## 📜 Licencia

Propietaria — WowHub Team · 2026
