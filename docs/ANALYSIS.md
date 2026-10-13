# Análisis Integral de WowHub v0.2.0

> **Alcance:** auditoría estática + funcional del repositorio `wowhub-app` al estado del commit `6f90c31` + fixes de deprecations.

## TL;DR

- **Tests:** 611 pass, 2 skip (e2e sin Playwright), 0 fail, **0 warnings del proyecto** (los 2 warnings restantes son de librerías externas: `httpx` + `crypt`).
- **Módulos:** 27 routers API + 23 servicios + 25+ modelos + 22 templates dashboard.
- **Bugs encontrados y corregidos en esta auditoría:** 6 (1 crítico: 2 e2e errors que contaminaban la suite; 5 deprecation warnings que se volverían errores en próximas versiones).
- **Recomendación:** lista para v0.3.0 con workarounds para v0.2.0 (ver §6).

---

## 1. Puntos Fuertes

### 1.1 Arquitectura sólida
- **Multi-tenant real**: cada entidad de negocio lleva `tenant_id` (UUID) + `Membership(user_id, tenant_id)` único. Storage aislado por tenant: `./storage/{tenant_id}/...`. Migración a PostgreSQL RLS documentada en `README.md §6`.
- **Separación limpia de capas**: `api/v1/` (HTTP) → `services/` (lógica) → `models/` (ORM) → `schemas/` (contratos). Cada endpoint es delgado y delega en servicios.
- **27 routers API** sin acoplamiento cruzado: cada feature tiene su router y su servicio dedicado.

### 1.2 Seguridad y observabilidad
- **Auth JWT (HS256) + bcrypt + Token Blacklist** para revocación server-side. `passlib[bcrypt]>=1.7.4` con `bcrypt==4.0.1` pinned (evita incompatibilidades conocidas).
- **Rate Limit Middleware** + **Audit Middleware** + **CORS** configurables vía settings. Banderas `RATE_LIMIT_ENABLED` y `AUDIT_ENABLED` en conftest para no contaminar tests.
- **Webhook outbox con retries**: `WebhookEvent` modela entregas asíncronas con `attempts` y `status_code`, permitiendo reintentos idempotentes.
- **Circuit breaker en AI Core**: `ai_orchestrator.py` con fallback determinístico cuando el LLM no está disponible (anti-alucinación, transparente al usuario).

### 1.3 Cobertura de tests excepcional
- **611 tests** distribuidos en 35+ archivos. Cubre:
  - Auth (registro, login, refresh, blacklist)
  - Multi-tenant (aislamiento cross-tenant)
  - Bookings (validación de horarios, conflictos, días cerrados)
  - Loyalty (campañas, scans, QR tokens)
  - AI (orchestrator fallback, circuit breaker, slug scrubber, tenant URLs)
  - Costos (cálculo de costo_hora, precio sugerido)
  - Products (pricing, márgenes, V8 calculator)
  - Public flows (catálogo, reservas, landing)
- **Tests de JS funcional** sin jsdom: `tests/test_dashboard_modal_refactor.py` levanta `app.js` en Node 20 con un DOM shim mínimo y verifica `WH.Modal`, `WH.Confirm`, `escapeHtml`, `debounce`, `Auth.resetSession`. Patrón replicable para otros módulos JS.

### 1.4 DX y mantenibilidad
- **WH namespace** centralizado en `app/static/js/app.js`: `api`, `Toast`, `Auth`, `ImagePicker`, `Upload`, `TokenStore`, `Modal`, `Confirm`, `formatMoney`, `formatDate`, `debounce`, `escapeHtml`, `escapeAttr`, `startAutoRefresh`. Un solo punto de extensión.
- **CSS con design tokens** (`tokens.css`): `var(--bg-elev, fallback)` + theme toggle light/dark automático.
- **i18n built-in** (es/en/pt) con detección por `Accept-Language` y helper `_t()` global para templates Jinja2.
- **i18n service** con diccionario por idioma, fácil de extender.

### 1.5 Features de producto bien implementadas
- **Cotizaciones (Quotes)**: modelo + service + UI + endpoint público con token. Ciclo completo: owner crea → cliente abre por token → owner ve estado.
- **Loyalty Pass**: 3 routers (owner/POS/public) + UI scanner con QR rotativo. Anti-fraude con `device_fp` + `cashier_pin`.
- **Costos (Fase 2 V8)**: 14 campos + cálculo de `costo_hora` en vivo (recalcula al editar cualquier input) + precio sugerido por producto con margen. Ver `app/services/costs_service.py` y `app/services/product_pricing.py`.
- **Pipeline Kanban** para pedidos: estados PENDING → DELIVERED con drag & drop server-side.

---

## 2. Puntos Débiles

### 2.1 Acoplamiento HTML-rutas en `main.py`
- `app/main.py` tiene **30+ `@app.get("/dashboard/X")`** handlers que solo renderizan templates. Esto debería ser un solo helper:
  ```python
  def _dashboard_page(name: str):
      def handler(request: Request):
          return templates.TemplateResponse(request, f"dashboard/{name}.html", {"settings": settings})
      return handler
  for name in ["products", "promotions", "qrs", ...]:
      app.get(f"/dashboard/{name}", include_in_schema=False)(_dashboard_page(name))
  ```
  Beneficio: −100 líneas en `main.py`, sin duplicación de la firma `(request: Request)`.

### 2.2 Inconsistencias en guards de páginas admin
- `/admin/ai` y `/admin/superadmin` tienen **lógica de auth inline** (5+ cada uno) con redirects hardcoded a `/dashboard/login?reason=...`. Esa lógica debería vivir en una dependencia `RequireRole(role)` reutilizable (similar al patrón que ya tiene `deps.py` para la API). Hoy hay 60+ líneas duplicadas.

### 2.3 Plantillas con HTML grande
- Varios templates son de 700+ líneas (`products.html`, `admin_loyalty.html`, `ai.html`). Migrar a `<template>` + render dinámico JS (como ya hicimos en products) reduce el TTFB y permite reuso.

### 2.4 Lint y formato
- El repo **no tiene CI de ruff** (aunque `pyproject.toml` lo declara en `[tool.ruff]` y `dev` deps). Una GitHub Action que corra `ruff check .` + `ruff format --check` cerraría issues de estilo automáticamente.
- No hay pre-commit configurado.

### 2.5 Logging
- `logging.basicConfig(level=settings.log_level)` se setea una sola vez al import. Los middlewares usan `logger = logging.getLogger("wowhub")` pero **no hay logging estructurado** (JSON). Para producción multi-tenant a escala, se recomienda `structlog` o `loguru` con `tenant_id` en cada línea.

### 2.6 Configuración
- `app/config.py` (no leído) probablemente tiene un `Settings` con muchos campos. Sin env-validation al arranque (más allá de Pydantic), errores de config se descubren tarde. Considerar un `make validate-config` o un health-check dedicado que falle el deploy si falta una var requerida.

### 2.7 Sin rate limit en rutas públicas sensibles
- El `RateLimitMiddleware` aplica a todo, pero el endpoint público de **registro de cliente Loyalty** (`/api/v1/loyalty/c/{slug}/register`) y el de **scan** podrían tener un rate limit específico (anti-abuso). Hoy hereda el global, que puede ser muy permisivo.

### 2.8 Documentación API dispersa
- OpenAPI está en `/docs` y `/redoc`, pero **no hay un runbook de troubleshooting** ni un changelog formal. El `README.md` cubre quick-start pero los detalles de deploy/rollback/incidents están en commits y memoria del equipo.

---

## 3. Lo necesario para implementar / desplegar

### 3.1 Setup local
```bash
# 1) Clonar
cd wowhub-app

# 2) Instalar deps (Python 3.11+)
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# 3) Variables de entorno
cp .env.example .env
# Editar .env: SECRET_KEY, JWT_SECRET, DATABASE_URL, etc.

# 4) Sembrar datos demo
python -m app.seed

# 5) Arrancar
uvicorn app.main:app --reload
```

### 3.2 Setup e2e (Playwright)
```bash
pip install -e ".[e2e]"
playwright install chromium
pytest tests/e2e -m e2e --base-url=https://tu-dominio.com
```

### 3.3 Setup con Docker
```bash
docker-compose up --build
docker-compose exec api python -m app.seed
```

### 3.4 Variables de entorno mínimas (`.env`)
```bash
APP_ENV=production
SECRET_KEY=<32+ chars>
JWT_SECRET=<32+ chars>
DATABASE_URL=postgresql://user:pass@host:5432/wowhub
STORAGE_PATH=/var/wowhub/storage
CORS_ORIGINS=["https://tu-dominio.com"]
RATE_LIMIT_ENABLED=true
AUDIT_ENABLED=true
# Opcionales:
PUBLIC_BASE_URL=https://tu-dominio.com
RESEND_API_KEY=re_xxx        # emails transaccionales
OPENAI_API_KEY=sk-xxx        # AI core
```

### 3.5 Deploy (Render / Railway / Fly.io)
El repo ya tiene `render.yaml` para deploy en Render. Para otras plataformas:
- **Procfile equivalente** para Heroku-style:
  ```
  web: uvicorn app.main:app --host 0.0.0.0 --port $PORT
  release: python -m app.seed  # opcional, solo primera vez
  ```
- **Migraciones DB**: hoy no hay Alembic en uso. `init_db()` crea todas las tablas en runtime — bien para dev, **riesgoso en prod** (sin ALTER sin downtime). Roadmap: agregar Alembic.

### 3.6 CI recomendado (GitHub Actions)
```yaml
name: ci
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: {python-version: "3.12"}
      - run: pip install -e ".[dev]"
      - run: ruff check .
      - run: ruff format --check .
      - run: pytest -q
```

---

## 4. Bugs corregidos en esta auditoría (commit actual)

| # | Tipo | Archivo | Síntoma | Fix |
|---|------|---------|---------|-----|
| 1 | Test infra | `tests/e2e/test_loyalty_flow.py` | 2 errors de "fixture 'page' not found" contaminaban la suite cuando `pytest-playwright` no está instalado | `tests/e2e/conftest.py` detecta deps ausentes y marca tests `e2e` como SKIP con mensaje claro |
| 2 | Pydantic v2 deprecation | `app/schemas/webhook.py` (3 clases), `app/schemas/upload.py` | `class Config: from_attributes = True` → warning en cada test | Migrado a `model_config = ConfigDict(from_attributes=True)` |
| 3 | Starlette deprecation | `app/core/errors.py` (ValidationError) | `status.HTTP_422_UNPROCESSABLE_ENTITY` → warning (será removido en Starlette 1.0) | `getattr(status, "HTTP_422_UNPROCESSABLE_CONTENT", 422)` con fallback numérico |
| 4 | Python 3.12 deprecation | `app/schemas/ai.py` (2 lugares) | `datetime.utcnow()` → warning, removido en 3.13+ | `datetime.now(timezone.utc)` con import de `timezone` |
| 5 | pytest 8 deprecation | `tests/test_dashboard_modal_refactor.py` | `@pytest.fixture(scope="class")` como instance method → warning, removido en pytest 10 | Decorador `@classmethod` agregado + comentario explicativo |
| 6 | (nuevo) Tests de regresión | `tests/test_deprecation_fixes.py` | No había guardia contra reintroducir APIs deprecadas | 13 tests nuevos verifican contrato: zero class-based Config, zero `utcnow`, zero old Starlette constant, etc. |

### Métricas
| Métrica | Antes | Después |
|---|---|---|
| Tests passed | 598 | **611** (+13) |
| Tests errors | 2 | **0** (→ 2 skipped) |
| Warnings del proyecto | 40+ | **0** |
| Warnings de libs externas | 2 | 2 (sin cambios) |

---

## 5. Bugs conocidos / riesgos (no críticos, documentados)

### 5.1 `init_db()` sin Alembic
- **Riesgo:** cambios de schema en runtime pueden ser lentos con datos existentes (>10K filas).
- **Mitigación actual:** `drop_all` + `create_all` en conftest para tests, lo que valida que el modelo es autocontenido.
- **Workaround prod:** documentado en `README.md §6` (RLS + stored procedures).

### 5.2 Sin CSRF tokens
- **Riesgo:** todas las requests POST/PUT/DELETE usan JWT en Authorization header (no cookie), así que el riesgo CSRF es **bajo** (los browsers no auto-attach Authorization headers cross-origin). Pero si en el futuro se pasa a cookies, hay que agregar CSRF.
- **Acción:** documentar la decisión arquitectónica en un ADR (Architecture Decision Record).

### 5.3 Logs sin redacción de PII
- `AuditMiddleware` registra `request.body` para algunos métodos. Si el body contiene passwords o tokens, podrían filtrarse.
- **Acción:** agregar lista de campos sensibles a redactar antes de persistir el log.

### 5.4 Sin timeout en webhook retries
- `webhook_service.py` reintenta webhooks sin timeout duro. Un cliente lento puede acumular conexiones.
- **Acción:** agregar `httpx.Timeout(connect=5, read=10)` a las requests salientes.

### 5.5 `whhub.db` versionado en repo
- `wowhub.db` (880KB) está en la raíz. En `.gitignore` debería estar, o commitear solo schema migrations.
- **Acción:** confirmar que `.gitignore` lo excluye (verificar antes del próximo commit).

---

## 6. Roadmap sugerido

### v0.2.1 (quick wins, 1-2 días)
- [ ] CI con ruff + pytest en GitHub Actions
- [ ] Refactor: extraer los 30+ `@app.get("/dashboard/X")` a un helper
- [ ] Fix el `wowhub.db` versionado (agregar a `.gitignore` si no está)
- [ ] ADR-001: "Por qué JWT en Authorization header y no en cookie"

### v0.3.0 (release blocker, 1-2 semanas)
- [ ] **Alembic migrations** (reemplaza `init_db()` en runtime)
- [ ] Rate limit específico para endpoints públicos de Loyalty (anti-abuso)
- [ ] Logging estructurado (structlog o loguru) con `tenant_id` en cada log
- [ ] Health check ampliado: `/health` verifica DB + storage + LLM opcional
- [ ] Refactor de guards admin a `RequireRole(role)` dependency

### v0.4.0 (escalada, 1 mes)
- [ ] Background tasks con Celery + Redis (hoy algunos procesos son sync)
- [ ] Multi-región (PostgreSQL read replicas)
- [ ] OpenAPI client SDK generado (TypeScript + Python)
- [ ] Observabilidad: OpenTelemetry traces + Prometheus metrics

---

## 7. Cómo verificar todo (TL;DR comandos)

```bash
# Suite completa (debe dar 611 passed, 2 skipped, 2 warnings)
pytest -q

# Solo e2e (si tienes Playwright instalado)
pip install -e ".[e2e]" && playwright install chromium
pytest tests/e2e -m e2e --base-url=https://tu-dominio.com

# Lint
ruff check .
ruff format --check .

# Server en dev
uvicorn app.main:app --reload
# → http://localhost:8000/docs
# → demo: maria@cafenorte.cl / demo1234
```

---

**Autor del análisis:** MiniMax Agent
**Fecha:** 2026-08-23
**Commit base:** 6f90c31 (modal refactor) + fixes de auditoría
