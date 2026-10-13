# Changelog — WowHub

Todos los cambios relevantes del proyecto, organizados por fecha y categoría.
Este archivo sigue parcialmente el estándar [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/).

---

## [0.5.0] — 2026-09-07

### Added — F0 Baseline + F1 Hardening (paquete `app/f0_baseline/`)

F0 introdujo el paquete `app.f0_baseline/` (3 HU, 8 SP, 30 tests) y F1 lo endureció
para producción (3 HU más, 8 SP, 58 tests nuevos). Total: 16 SP, 88 tests.

#### F1.1 — Pydantic v2 estricto en `/f0/*` (HU_04, 3 SP)
- **12 schemas Pydantic v2** nuevos en `app/f0_baseline/schemas.py`:
  `PackageInfo`, `ReportLink`, `IndexResponse`, `HealthResponse` (con
  `Literal["ok"]`), `MetricsResponse` + `MetricsCounts` + `MetricsRatios` +
  `MetricsFlags` + `MetricsPackage` (con `Field(..., ge=0)` y `le=100.0` para
  validar ratios), `CatalogDiffResponse`, `Hu01Response` + `Hu01Result`,
  `Hu02Response` + `Hu02Result` + `Hu02MappingSampleItem`,
  `Hu03Query` + `Hu03Response` + `Hu03Result`, `Hu03TimeoutResponse`,
  `ErrorResponse`.
- **Router estricto** en `app/f0_baseline/router.py`: cada endpoint declara
  `response_model=...` y `responses={503: {"model": Hu03TimeoutResponse, ...}}`
  / `responses={404: {"model": ErrorResponse, ...}}`. La spec OpenAPI ahora
  expone los shapes exactos de cada endpoint, incluyendo los modelos 404/503.
- **18 tests nuevos** en `tests/f0_baseline/test_schemas.py` que verifican:
  OpenAPI spec (paths + 503/404 + `$ref`), cada response valida contra su
  schema, Pydantic v2 rechaza payloads malformados (incluyendo `ge=0` para
  `MetricsCounts` y `le=100.0` para `MetricsRatios`), el 503 del circuit
  breaker valida contra `Hu03TimeoutResponse` con `monkeypatch` + `sleep`.

#### F1.2 — AST-lite parser para `window.*` (HU_05, 3 SP)
- **`app/f0_baseline/js_parser.py`** (505 líneas): lexer JS (`JSLexer`) con
  `TokKind` enum (IDENT, KEYWORD, STRING, NUMBER, BLOCK_COMMENT, LINE_COMMENT,
  PUNCT, WHITESPACE, EOF) + parser (`parse_window_functions`) que tokeniza,
  skipea strings/comentarios, y cuenta braces con un stack.
- **Clasificación del RHS**: `function` (con JSDoc como `description`),
  `arrow` (`() => ...`), `method` (clase/objeto), `other`.
- **Refactor de `app/f0_baseline/inventory.py`**: eliminados los regex
  `RE_WINDOW_FN` y `RE_ANY_FN`; `WindowInventory.extract()` ahora delega en
  el parser. Dedupe por `(name, line)`.
- **23 tests nuevos** en `tests/f0_baseline/test_js_parser.py`: lexer (strings
  con escape, comentarios, line tracking, operadores de 2 chars), `_safe_source`
  (preserva newlines, reemplaza strings/comments por spaces), `_find_matching_brace`
  (simple, anidado, en strings, en comments), `parse_window_functions` end-to-end
  (detecta funciones con JSDoc, ignora `window.X` en strings y comentarios,
  soporta braces anidados, arrow functions, métodos de clase, dedupe).
- **Bugs eliminados del regex original**:
  - `"window.fake = function(){}"` ya no genera falsos positivos.
  - `/* window.fake = function(){} */` ya no genera falsos positivos.
  - `function() { if (x) { y(); } }` ya no trunca el cuerpo.
  - `window.X = () => {...}` ya se detecta (antes era falso negativo).

#### F1.3 — Alembic init + autogen desde `Base` (HU_06, 2 SP)
- **`alembic/`** inicializado con `alembic init alembic` y customizado:
  - `alembic/env.py` (133 líneas) reescrito: agrega `PROJECT_ROOT` a
    `sys.path`, resuelve `DATABASE_URL` de env var o `settings.database_url`
    (nunca hardcoded), importa `Base` y todos los módulos de `app.models`
    (user, tenant, branch, category, product, customer, promotion, qr,
    landing, order, site_config, loyalty_pass, automation, business_costs,
    insumo) para que se registren en `Base.metadata`.
  - `alembic.ini` con `file_template` cronológico
    (`%%(year)d_%%(month).2d_%%(day).2d_%%(hour).2d%%(minute).2d-%%(rev)s_%%(slug)s`)
    y la `sqlalchemy.url` documentada como placeholder.
- **Migración inicial autogenerada**:
  `alembic/versions/2026_09_07_1002-f2efb29e03b1_initial_schema.py` (1201
  líneas, captura los 30+ modelos del proyecto). Se agregó
  `import app.models.base  # noqa: F401` para que `GUID()` esté disponible
  en `upgrade()`.
- **Verificado end-to-end**: `alembic upgrade head` y `alembic downgrade
  base` funcionan contra SQLite temporal. La DB queda vacía tras el
  downgrade.
- **17 tests nuevos** en `tests/f0_baseline/test_alembic.py`: 15 estáticos
  (estructura de directorios, contenido de `env.py`, `alembic.ini`, imports
  de la migración) + 2 dinámicos marcados `@pytest.mark.slow` (upgrade head
  contra SQLite temporal, downgrade base tras upgrade).
- **Marker `slow`** agregado a `pyproject.toml` `[tool.pytest.ini_options]`
  para omitir los tests lentos en el flujo default de CI.

### Changed
- `app/f0_baseline/__init__.py` ahora declara `__version__ = "1.1.0"`,
  `__phase__ = "F1"`, `__story_points__ = 16`, y `__hu_covered__` extendido
  con HU_04, HU_05, HU_06. Lazy loader (`__getattr__`) ahora también exporta
  `parse_window_functions`.
- `app/f0_baseline/inventory.py` ya no contiene regex; usa el parser AST-lite.

### Tests
- **Suite F0+F1**: 88 tests pasando (30 F0 + 18 F1.1 + 23 F1.2 + 17 F1.3).
  Sin slow: 86 tests en ~0.6 s. Con slow: 88 tests en ~3.7 s.
- **Comando rápido** (CI): `pytest tests/f0_baseline -m "not slow"`.
- **Comando completo** (nightly): `pytest tests/f0_baseline`.

### Documentación
- Nuevo: [`docs/f1/F1_REPORT.md`](f1/F1_REPORT.md) — reporte completo de F1.1,
  F1.2, F1.3 con métricas, decisiones de diseño y limitaciones.
- Actualizado: `README.md` con la sección F0/F1 Baseline, endpoints `/f0/*`
  con sus schemas, comandos de Alembic, y roadmap v0.5.0/v0.6.0/v0.7.0/v0.8.0.

---

## [0.3.0] — 2026-08-22

### Added — Módulo de Cotizaciones, Pipeline Kanban, Inventario y Resumen consolidado

#### Cotizaciones (nuevo módulo completo)
- **Modelo**: `Quote` + `QuoteItem` con máquina de estados (`DRAFT → SENT → VIEWED → ACCEPTED / REJECTED / EXPIRED`).
- **Schemas Pydantic**: `QuoteCreate`, `QuoteUpdate`, `QuoteOut`, `QuoteListItem`, `QuoteStats`, `QuoteItemCreate`, `QuoteItemOut`.
- **Servicio** (`app/services/quote_service.py`): CRUD, list con búsqueda, stats por estado, transiciones, conversión a `Order`, generación de `public_token` único (`secrets.token_urlsafe(12)`).
- **API owner** (autenticada, scope por `tenant_id`):
  - `GET    /api/v1/tenants/{tid}/quotes` — listado paginado.
  - `GET    /api/v1/tenants/{tid}/quotes/stats` — KPIs (total, value, acceptance rate, draft value, accepted value).
  - `GET    /api/v1/tenants/{tid}/quotes/{id}` — detalle.
  - `POST   /api/v1/tenants/{tid}/quotes` — crear.
  - `PATCH  /api/v1/tenants/{tid}/quotes/{id}` — editar.
  - `DELETE /api/v1/tenants/{tid}/quotes/{id}` — eliminar.
  - `POST   /api/v1/tenants/{tid}/quotes/{id}/send` — marcar como enviada.
  - `POST   /api/v1/tenants/{tid}/quotes/{id}/accept` — aceptar.
  - `POST   /api/v1/tenants/{tid}/quotes/{id}/reject` — rechazar.
  - `POST   /api/v1/tenants/{tid}/quotes/{id}/convert` — convertir a pedido.
- **API pública** (sin auth, por token):
  - `GET    /api/v1/public/quotes/{token}` — abre la cotización.
  - `POST   /api/v1/public/quotes/{token}/accept` — cliente acepta.
  - `POST   /api/v1/public/quotes/{token}/reject` — cliente rechaza.
- **UI dashboard** `/dashboard/quotes` — KPIs, filtros, tabla, modal crear/editar, modal ver, acciones de estado, conversión a pedido.
- **UI pública** `/quote/{token}` — vista cliente con Aceptar / Rechazar.
- **Token público único**: `secrets.token_urlsafe(12)` con validación de unicidad.

#### Pipeline de Pedidos (Kanban)
- Nueva UI `/dashboard/pipeline` con columnas por estado: `pending → confirmed → preparing → ready → delivered` (más `canceled`).
- Auto-refresco cada 30 s.
- Botones inline para transiciones válidas.
- Modal de detalle del pedido.

#### Inventario
- Nueva UI `/dashboard/inventory` con:
  - KPIs (total SKUs, stock total, alertas de reposición, valor de inventario).
  - Tabla por producto-sucursal con `stock`, `reserved`, `available`, `low_stock_threshold`.
  - Alertas visuales (bajo / sin stock / OK).
  - Búsqueda y filtro por sucursal.
  - Modal para ajustar stock.

#### Resumen consolidado
- `/dashboard` ahora carga 9 KPIs en paralelo:
  Pedidos, Reservas activas, Cotizaciones abiertas, Clientes, Tarjetas de fidelidad, Stock bajo, Productos, Facturas, Visitas.

#### Sidebar
- Reorganizado en 2 secciones siguiendo el spec del usuario:
  - **Negocio** (Resumen, Funcionalidades, Clientes, Reservas, Productos, Promociones, QRs, Sitio público, Fidelidad)
  - **Gestión interna** (Pedidos, Pipeline, Inventario, Cotizaciones)

#### Documentación
- README actualizado a v0.3.0 con modelo de datos, endpoints de cotizaciones y notas de inventario.

### Fixed
- `Page` schema de cotizaciones ahora respeta el campo `total_pages` esperado (mismatch con `pages` del servicio original).

---

## [No publicado] — 2026-08-16

### Added — Integración del Asistente Virtual con todos los módulos

#### Endpoints nuevos (4)
- `GET /api/v1/tenants/{id}/analytics/inventory` — análisis de inventario con 6 categorías (`all`, `low_stock`, `out_of_stock`, `overstock`, `dead_stock`, `top_selling`).
- `GET /api/v1/tenants/{id}/analytics/customer-segments` — segmentación de clientes con 6 perfiles (`all`, `inactive`, `top`, `new`, `vip`, `no_orders`).
- `POST /api/v1/tenants/{id}/campaigns` — envío masivo de email por segmento (máx. 500 destinatarios, filtro opt-in).
- `POST /api/v1/tenants/{id}/campaigns/preview` — vista previa de campaña sin envío.

#### AI Tools nuevas (3)
- `analyze_inventory` — inventario categorizado.
- `get_customer_segments` — clientes por segmento.
- `send_campaign` — campaña masiva con confirmación.

#### Sub-agentes actualizados (4)
- **Marketing:** detecta stock bajo, dead stock y segmentos para combos.
- **Growth:** oportunidades de venta cruzada y subida de ticket.
- **Automation:** lanza campañas a inactivos / VIP / nuevos.
- **Marketplace:** detecta sin stock, sin rotación y mejora de catálogo.

#### Router heurístico
- +25 keywords nuevas para detectar intenciones de inventario, segmentos y campañas.
- Tests actualizados para reflejar la nueva taxonomía.

#### Servicios y schemas nuevos
- `app/services/analytics_service.py` (450 líneas, lógica de inventario + segmentos).
- `app/schemas/analytics.py` (modelos Pydantic).
- `app/api/v1/analytics.py` (routers de analytics).
- `app/api/v1/campaigns.py` (routers de campañas + email).

#### Tests
- 14 tests nuevos en `tests/test_analytics_campaigns.py` (100 % pasan).
- 1 test ajustado en `tests/test_ai_orchestrator_fallback.py` por nueva keyword `producto`.

#### Documentación
- Informe detallado en [`docs/INFORME_INTEGRACION_IA.md`](INFORME_INTEGRACION_IA.md).
- Informe del sistema de fidelización en [`docs/INFORME_FIDELIZACION.md`](INFORME_FIDELIZACION.md).

---

## Formato de las versiones

- **Added** — funcionalidades nuevas.
- **Changed** — cambios en funcionalidades existentes.
- **Deprecated** — funcionalidades que se eliminarán pronto.
- **Removed** — funcionalidades eliminadas.
- **Fixed** — corrección de bugs.
- **Security** — cambios de seguridad.

---

## [No publicado] — 2026-08-16 (Bookings Fase 2)
### Added — Módulo de Reservas / Bookings completo
#### Servicio de negocio (`app/services/booking_service.py`)
- `BookingService` con CRUD, validación de ventana temporal, validación de horarios de sucursal (`Branch.hours` + excepciones), detección de conflictos por solapamiento, stats, availability y notificaciones integradas.
- Helpers `_ensure_aware`, `_parse_hhmm`, `_fmt_when`, `_branch_window_for_range`, `_check_conflict`.
#### Schemas (`app/schemas/booking.py`)
- `BookingIn`, `PublicBookingIn`, `BookingUpdate`, `BookingOut`, `PublicBookingOut`.
- `AvailabilityQuery`, `AvailabilitySlot`, `AvailabilityResponse`.
- `BookingStats` con desglose por estado.
#### API Admin (con auth de membresía)
- 11 endpoints: list, create, stats, availability, get, update, confirm, complete, no-show, cancel, delete.
- Filtros por `status`, `branch_id`, `date_from`, `date_to`, `customer_id`.
#### API Pública (sin auth, por slug)
- 3 endpoints: `public-check`, `public-create`, `public-cancel`.
- Enmascaramiento de email en respuestas (`first_char + stars + last_char + @domain`).
- Token opaco de cancelación (primeros 12 chars del UUID).
#### UI
- **Panel del dueño** `/dashboard/bookings` — KPIs, filtros, tabla con acciones inline, modal de nueva reserva, auto-refresh cada 30 s.
- **Landing del cliente** `/u/{slug}/reservar` — wizard 3 pasos (fecha/branch/duración → slots → datos → confirmación).
- Link "Reservas" agregado al sidebar del dashboard.
#### AI Tools nuevas (3)
- `tool_list_bookings` — lista reservas con filtros.
- `tool_check_availability` — devuelve slots disponibles.
- `tool_create_booking` — crea reserva en nombre del cliente.
- Expuestas a los sub-agentes `marketing`, `growth`, `automation` (no a `marketplace`).
#### Integración con NotificationService
- `notify_booking_confirmed` se llama al crear (con `send_confirmation=True`) y al confirmar manualmente.
- Errores de notificación se loggean sin romper la operación.
#### Tests
- **37 tests pasando** en `tests/test_bookings.py` (cubren CRUD, validación, conflictos, horarios, estados, stats, availability, endpoint público, multi-tenant isolation, AI tools, UI).
- 8 clases: `TestBookingCRUD`, `TestBookingValidation`, `TestBookingStateActions`, `TestBookingStatsAndAvailability`, `TestPublicBooking`, `TestMultiTenantIsolation`, `TestAITools`, `TestUIPages`.
#### Documentación
- Nuevo `docs/INFORME_BOOKINGS.md` (~520 líneas) con arquitectura, endpoints, validaciones, AI tools, UI, tests, decisiones de diseño y roadmap.

---

## Cómo contribuir al changelog

Cuando añadas un cambio, agrégalo bajo `[No publicado]` con la fecha actual
y la categoría correspondiente. En cada release estable, mueve la sección
a una versión fechada (p. ej. `[0.2.0] — 2026-08-16`).
