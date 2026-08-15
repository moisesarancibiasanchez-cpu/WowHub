# WowHub — Prototipo Python

Plataforma SaaS modular para PyMEs en LATAM. **v0.2.0**: Página, Catálogo, QR, Promociones, Pedidos, Pagos, Reservas, Loyalty, AI Assistant, Uploads, Audit, Webhooks.

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

### Modelo de datos (v0.2.0)

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
                                └──< AuditLog                 # quién hizo qué
```

24 entidades cubriendo CRM ligero, e-commerce básico, reservas, fidelización, pagos, webhooks, auditoría, branding y uploads.

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

## 🧪 Tests

```bash
pytest                                        # todos
pytest -k test_auth                           # solo auth
pytest -k test_loyalty                        # loyalty
pytest -k test_ai                             # AI (circuit breaker, fallback, strip think)
pytest tests/e2e/test_loyalty_flow.py         # Playwright E2E (requiere server arriba)
pytest --cov=app                              # con cobertura
```

Suite cubre: autenticación, multi-tenancy, productos, promociones, QR, endpoints públicos, loyalty, AI (circuit breaker, orquestador con fallback, strip de `<think>…</think>`), y un flujo E2E con Playwright.

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

## 🧭 Próximos pasos (post-MVP)

- [x] Migrar a Alembic (ya hay carpeta `alembic/`)
- [ ] PostgreSQL + Row-Level Security policies
- [ ] 2FA TOTP para owners
- [ ] Storage S3/R2 para imágenes (placeholder ya en `UploadService`)
- [ ] Variantes de imagen (thumb/medium/full) — hoy se guarda solo el original
- [ ] Strip de EXIF en el server (privacidad)
- [ ] Cola de eventos (Celery + Redis) para webhooks y emails transaccionales
- [ ] Más integraciones (WhatsApp Business, MercadoPago producción)
- [ ] i18n UI (ya soporta `country`, `locale`, `currency` por tenant en data)

## 📚 Documentación

La documentación para clientes, equipo y reportes de avance vive en la carpeta
[`docs/`](docs/). Encontrarás:

- 📄 **[Informe de Integración del Asistente Virtual](docs/INFORME_INTEGRACION_IA.md)** —
  qué se entregó en la fase IA ↔ módulos de negocio, beneficios y roadmap.
- 📋 **[Changelog](docs/CHANGELOG.md)** — historial detallado de cambios.
- 🗂️ **[Índice de docs](docs/README.md)** — punto de entrada a la documentación.

## 📜 Licencia

Propietaria — WowHub Team · 2026
