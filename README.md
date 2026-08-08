# WowHub — Prototipo Python

Plataforma SaaS modular para PyMEs en LATAM. **MVP**: Página, Catálogo, QR y Promociones

Construido con **FastAPI + SQLAlchemy 2.0 + Pydantic v2 + Jinja2 + HTMX**.

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

## 🧪 Tests

```bash
pytest                  # todos
pytest -k test_auth     # solo auth
pytest --cov=app        # con cobertura
```

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
| UI | Jinja2 + HTMX + tokens.css | Panel + landing pública |
| QR | qrcode + Pillow | Generación PNG |
| Tests | pytest + TestClient | Cobertura 80%+ |

### Multi-tenant

- Cada entidad de negocio lleva `tenant_id` (UUID).
- Las queries de servicios filtran siempre por tenant.
- Aislamiento reforzado con `Membership.user_id + tenant_id` único.
- En producción: agregar **PostgreSQL Row-Level Security** (ver spec sección 6).

### Modelo de datos (MVP)

```
User ─< Membership >─ Tenant ─< Branch
                          │
                          ├──< Category ─< Product
                          │
                          ├──< Customer
                          ├──< Promotion
                          ├──< QrCode
                          ├──< LandingConfig (1:1)
                          └──< Order ─< OrderItem
```

13 entidades (la spec completa define 19; el MVP cubre 11 + Order/OrderItem).

### Endpoints principales

```
POST   /api/v1/auth/register       # crear user (+ tenant opcional)
POST   /api/v1/auth/login          # JWT
POST   /api/v1/auth/refresh
GET    /api/v1/auth/me

GET    /api/v1/tenants             # propios
POST   /api/v1/tenants
GET    /api/v1/tenants/{id}
PATCH  /api/v1/tenants/{id}

# Recurso: Products (scoped por tenant_id)
GET    /api/v1/tenants/{tid}/products?page=1&page_size=20&search=...
POST   /api/v1/tenants/{tid}/products
GET    /api/v1/tenants/{tid}/products/{id}
PATCH  /api/v1/tenants/{tid}/products/{id}
DELETE /api/v1/tenants/{tid}/products/{id}

# (idem para categories, customers, promotions, qrs, landing, branches)

# PÚBLICOS — sin auth
GET    /api/v1/public/t/{slug}/profile
GET    /api/v1/public/t/{slug}/catalog
GET    /api/v1/public/t/{slug}/products/{product_slug}
GET    /api/v1/public/t/{slug}/categories
GET    /api/v1/public/t/{slug}/promotions
GET    /api/v1/public/t/{slug}/branches
GET    /api/v1/public/t/{slug}/landing

# QR — redirect
GET    /r/{short_code}             # → /u/{slug}/catalogo, etc.
```

## 📂 Estructura

```
wowhub-app/
├── app/
│   ├── api/v1/             # Routers REST
│   │   ├── auth.py
│   │   ├── tenants.py
│   │   ├── products.py
│   │   ├── categories.py
│   │   ├── customers.py
│   │   ├── promotions.py
│   │   ├── qrs.py
│   │   ├── landing.py
│   │   └── public.py
│   ├── core/               # tenant_context, errors, pagination
│   ├── models/             # 13 modelos SQLAlchemy
│   ├── schemas/            # 13+ schemas Pydantic
│   ├── services/           # Lógica de negocio
│   ├── templates/          # Jinja2
│   │   ├── auth/
│   │   ├── dashboard/
│   │   ├── public/
│   │   └── base.html, home.html
│   ├── static/             # CSS + JS
│   ├── config.py           # Settings (Pydantic)
│   ├── database.py         # Engine, session, Base
│   ├── deps.py             # FastAPI dependencies
│   ├── security.py         # JWT + bcrypt
│   ├── seed.py             # Datos demo
│   └── main.py             # App factory + UI routes
├── tests/                  # pytest (auth, tenants, products, qr, public, promotions)
├── pyproject.toml
├── .env.example
├── Dockerfile
└── docker-compose.yml
```

## 🔐 Seguridad

- **Passwords**: bcrypt con salt automático (passlib).
- **JWT**: HS256, access 60min + refresh 14 días.
- **Multi-tenant**: filtro explícito por `tenant_id` en cada query de servicio.
- **Validación**: Pydantic v2 con validadores custom (slug format, password strength, compare_at >= price).
- **CORS**: configurable vía `CORS_ORIGINS`.

## 🧭 Próximos pasos (post-MVP)

- [ ] Migrar a Alembic (ya hay carpeta `alembic/`)
- [ ] PostgreSQL + Row-Level Security policies
- [ ] 2FA TOTP para owners
- [ ] Storage S3/R2 para imágenes
- [ ] Cola de eventos (BullMQ → en Python: Celery + Redis)
- [ ] Webhooks + integraciones (WhatsApp Business, Mercado Pago)
- [ ] i18n (ya soporta `country`, `locale`, `currency` por tenant)

## 📜 Licencia

Propietaria — WowHub Team · 2026
