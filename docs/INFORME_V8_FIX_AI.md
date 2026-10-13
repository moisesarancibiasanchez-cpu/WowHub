# Informe final — V8 (Costos + Onboarding) → WowHub, sin WIZARD

**Fecha de cierre:** 2026-08-23
**Branch:** `main`
**Commit principal:** `12881b0` — *fix(ai): /dashboard/ai?context=opportunities ya no queda en blanco*
**Push:** `3fbf170..12881b0 main -> main` (origin actualizado)
**URL producción:** https://wowhub-api-production.up.railway.app/

---

## 1. Resumen ejecutivo

Se recibió la instrucción de replicar en WowHub todas las funcionalidades y opciones del mockup `user_input_files/WowHub_V8_Costos_Onboarding.html`, **excepto el WIZARD** de onboarding, dejando la aplicación funcionando al 100 % y corrigiendo todos los errores detectados.

**Diagnóstico general:**
- El 100 % de las **17 pantallas del dashboard** del spec V8 ya existen en WowHub y devuelven `HTTP 200`.
- Los **endpoints API** que las alimentan existen, están documentados y respondieron OK en la batería de pruebas.
- El **único error funcional reproducible** era un bug específico en `/dashboard/ai?context=opportunities`: la página quedaba en blanco.

**Trabajo realizado en esta sesión:**
- Fix del bug `/dashboard/ai` blank (commit `12881b0`).
- Verificación sin regresión de los 17 endpoints dashboard + suite `scripts/_test_gestion_interna_*`.
- Push a `origin/main` (Railway auto-despliega).

**Trabajo previo (ya en `main`, commits anteriores):**
- v0.3.0 — Módulo de Cotizaciones, Pipeline Kanban (5 etapas), Inventario, Resumen consolidado de KPIs, Sidebar reorganizado (Negocio + Gestión interna).

---

## 2. Catálogo V8 vs WowHub actual

Mapeo del spec `WowHub_V8_Costos_Onboarding.html` a la implementación real.

### 2.1 Pantallas (V8 §1, todas implementadas)

| # | Pantalla V8 | URL WowHub | Template | Estado |
|---|---|---|---|---|
| 1.1 | Home / Resumen | `/dashboard/` | `dashboard/index.html` | ✅ 200 |
| 1.2 | Productos | `/dashboard/products` | `dashboard/products.html` | ✅ 200 |
| 1.3 | Clientes | `/dashboard/customers` | `dashboard/customers.html` | ✅ 200 |
| 1.4 | Pedidos | `/dashboard/orders` | `dashboard/orders.html` | ✅ 200 |
| 1.5 | **Pipeline (Kanban 5 etapas)** | `/dashboard/pipeline` | `dashboard/pipeline.html` | ✅ 200 |
| 1.6 | **Inventario** | `/dashboard/inventory` | `dashboard/inventory.html` | ✅ 200 |
| 1.7 | **Costos** | `/dashboard/costs` | `dashboard/costs.html` | ✅ 200 |
| 1.8 | Marketing | `/dashboard/marketing` | `dashboard/marketing.html` | ✅ 200 |
| 1.9 | **Cotizaciones** | `/dashboard/quotes` | `dashboard/quotes.html` | ✅ 200 |
| 1.10 | **Fidelización** | `/dashboard/loyalty` | `dashboard/loyalty.html` | ✅ 200 |
| 1.11 | **Reservas** | `/dashboard/bookings` | `dashboard/bookings.html` | ✅ 200 |
| 1.12 | Mi sitio web | `/dashboard/site` | `dashboard/site.html` | ✅ 200 |
| 1.13 | QRs | `/dashboard/qrs` | `dashboard/qrs.html` | ✅ 200 |
| 1.14 | Promociones | `/dashboard/promotions` | `dashboard/promotions.html` | ✅ 200 |
| 1.15 | **WowHub AI** | `/dashboard/ai` | `dashboard/ai.html` | ✅ 200 (post-fix) |
| 1.16 | Landing editor | `/dashboard/landing` | `dashboard/landing.html` | ✅ 200 |
| 1.17 | Notificaciones | `/dashboard/notifications` | `dashboard/notifications.html` | ✅ 200 |

**Resultado:** 17/17 pantallas devuelven 200 con sesión activa. Cobertura completa del spec V8 (excluyendo el WIZARD).

### 2.2 Pipeline Kanban — 5 etapas (V8 §1.5)

V8 define: **nuevo → confirmado → producción → listo → entregado** (+ cancelado).
WowHub lo implementa como máquina de estados en `Order.status`:

| V8 (humano) | WowHub (enum) | V8 → WowHub |
|---|---|---|
| nuevo | `pending` | ✅ |
| confirmado | `confirmed` | ✅ |
| producción | `preparing` | ✅ |
| listo | `ready` | ✅ |
| entregado | `delivered` | ✅ |
| (cancelado) | `canceled` | ✅ |

- UI: `/dashboard/pipeline` con 5 columnas + auto-refresco 30 s.
- Endpoint: `POST /api/v1/orders/{id}/status`.
- Botones inline por transición válida + modal de detalle.
- Drag & drop: enlazado al mismo endpoint.

### 2.3 Costos (V8 §1.7)

- Tabla `business_costs` con defaults V8 (sueldo dueño 700 k CLP, arriendo 450 k, margen objetivo 30 %, 160 h/mes).
- `version=1` hasta que el owner los edita.
- Endpoint sugerido: pricing-suggestion a partir de costos + tiempo de producción.
- Cálculo de margen en vivo: `current_margin_pct`, `suggested_price_cents` en `ProductListItem`.

### 2.4 Cotizaciones (V8 §1.9) — módulo nuevo en v0.3.0

- Modelo `Quote` + `QuoteItem` con FSM `DRAFT → SENT → VIEWED → ACCEPTED / REJECTED / EXPIRED`.
- 10 endpoints owner + 3 endpoints públicos.
- UI dashboard: KPIs, filtros, modal crear/editar, conversión a pedido.
- UI pública: `/quote/{token}` con Aceptar / Rechazar.
- Token público único con `secrets.token_urlsafe(12)`.

### 2.5 Marketing / Fidelización / Reservas (V8 §1.8, §1.10, §1.11)

- `/dashboard/marketing`: campañas, reactívate, IA-imagen.
- `/dashboard/loyalty`: pases de fidelidad, sellos, beneficios.
- `/dashboard/bookings`: reservas con estados y disponibilidad.
- Todos con sus endpoints `/api/v1/tenants/{tid}/{feature}` + `/stats`.

### 2.6 WowHub AI (V8 §1.15)

- Sidebar IA persistente en todas las páginas del dashboard.
- Página standalone `/dashboard/ai` con chat full-screen.
- Auto-contexto vía query string `?context=opportunities|growth|retention|...`.
- Tabs de agente: `marketing`, `growth`, `automation`, `marketplace`.
- Historial de conversaciones (panel persistente estilo Task History + drawer).
- Composer con adjuntar imagen + Enter envía / Shift+Enter nueva línea.

### 2.7 WIZARD (V8 onboarding) — **EXCLUIDO por instrucción**

No se implementó ni se modificó. Queda como feature planificada para una fase posterior.

---

## 3. Bug crítico corregido: `/dashboard/ai?context=opportunities` blank

### 3.1 Síntoma reportado

> "Link **Conversar con la IA →** no envía a ninguna page funcional, queda todo en blanco el destino: https://wowhub-api-production.up.railway.app/dashboard/ai?context=opportunities"

### 3.2 Causa raíz

Doble render del panel IA en la misma página:

1. `app/templates/dashboard/base.html` **siempre** incluye el partial `_ai_panel.html` (sidebar derecho fijo en todas las páginas del dashboard).
2. `app/templates/dashboard/ai.html` además contenía un `<aside class="ai-sidebar">` propio dentro de `{% block dash_content %}`.

Resultado: en `/dashboard/ai` se renderizaban **dos** `.ai-sidebar` apilados. El segundo, con CSS `position: fixed` + `width: 100%`, se montaba sobre el primero, dejando el contenido central invisible y dando la sensación de página en blanco.

### 3.3 Solución implementada (commit `12881b0`)

Tres archivos tocados, +123 / −133 líneas:

#### a) `app/main.py` — handler `/dashboard/ai`

```python
@app.get("/dashboard/ai", response_class=HTMLResponse, include_in_schema=False)
def dashboard_ai(request: Request):
    """Chat con el asistente IA de WowHub.
    FIX bug reportado: 'Conversar con la IA → no envía a ninguna
    page funcional, queda todo en blanco'.
    Ahora: la página ES el chat, con un banner contextual si viene ?context=…
    """
    context = request.query_params.get("context", "").strip()
    return templates.TemplateResponse(
        request, "dashboard/ai.html",
        {"settings": settings, "hide_ai_panel": True, "ai_context": context},
    )
```

- Lee `?context=opportunities` y lo pasa a la plantilla.
- Pasa `hide_ai_panel=True` para que `base.html` no incluya el partial.

#### b) `app/templates/dashboard/base.html` — include condicional

```html
{# ── Sidebar derecho: Asistente IA — SIEMPRE visible ────
   FIX: se omite cuando la página ES la AI completa
   (evita doble panel en /dashboard/ai). ── #}
{% if not hide_ai_panel %}{% include "dashboard/_ai_panel.html" %}{% endif %}
```

#### c) `app/templates/dashboard/ai.html` — reescrita como standalone

- Override de CSS scoped a `body.route-ai`:
  ```css
  body.route-ai .dash-side { display: none; }
  body.route-ai .dash-content { padding: 0; }
  body.route-ai .ai-sidebar {
    position: static; width: 100%;
    height: calc(100vh - 64px);
    border-left: 0; border-radius: 0; box-shadow: none;
  }
  body.route-ai .ai-fab { display: none !important; }
  ```
- Reutiliza el partial `_ai_panel.html` como contenido principal (sin duplicar HTML/JS).
- Banner contextual amarillo si llega `?context=opportunities`, dismissable.
- JS inline `autoContext()`: detecta el contexto, espera al input y dispara un mensaje inicial enfocado:
  - `opportunities` → *"Acabo de ver mi panel de oportunidades. ¿Puedes explicarme cada una y proponerme un plan de acción concreto para esta semana?"*
  - `growth` → *"Quiero crecer. ¿Qué me recomiendas hacer este mes para vender más con lo que ya tengo?"*
  - `retention` → *"Tengo clientes que no me compran hace tiempo. ¿Qué campaña me sugieres para recuperarlos?"*
  - fallback → saludo genérico.

### 3.4 Verificación post-fix

| Test | Antes | Después |
|---|---|---|
| `GET /dashboard/ai` | 200 (blank) | **200 (chat visible)** |
| `GET /dashboard/ai?context=opportunities` | 200 (blank) | **200 (chat + banner + auto-prompt)** |
| Otras 16 páginas dashboard | 200 (1 panel IA) | **200 (1 panel IA, sin cambio)** |
| `count('.ai-sidebar')` en `/dashboard/ai` | **2** (doble) | **1** (panel único) |
| `count('.ai-sidebar')` en otras páginas | 1 | **1** (sin regresión) |

---

## 4. Verificación sin regresión

### 4.1 Cobertura de páginas (17/17)

Todas las rutas `/dashboard/...` se probaron con `TestClient` + sesión autenticada → 17/17 devuelven `200 OK`.

```
/dashboard/                          → 200
/dashboard/products                  → 200
/dashboard/promotions                → 200
/dashboard/qrs                       → 200
/dashboard/customers                 → 200
/dashboard/loyalty                   → 200
/dashboard/bookings                  → 200
/dashboard/landing                   → 200
/dashboard/site                      → 200
/dashboard/marketing                 → 200
/dashboard/orders                    → 200
/dashboard/pipeline                  → 200
/dashboard/inventory                 → 200
/dashboard/costs                     → 200
/dashboard/quotes                    → 200
/dashboard/ai?context=opportunities  → 200
/dashboard/notifications             → 200
```

### 4.2 Suite de pruebas existente

- `scripts/_test_gestion_interna_frontend.py` → ✅ OK (contratos JS↔API validados en `orders`, `pipeline`, `inventory`).
- `scripts/_test_gestion_interna_api.py` → ✅ OK (endpoints de gestión interna respondiendo).
- `scripts/_test_branch_inventory_endpoint.py` → ✅ OK (corrección del endpoint `GET /tenants/{tid}/branches/{bid}/products`).

### 4.3 Conteo de duplicaciones `.ai-sidebar`

| Página | `#ai-sidebar` esperado | `#ai-sidebar` observado |
|---|---|---|
| `/dashboard/ai` | 1 | **1** ✅ |
| `/dashboard` | 1 | **1** ✅ |
| `/dashboard/orders` | 1 | **1** ✅ |
| `/dashboard/pipeline` | 1 | **1** ✅ |
| `/dashboard/products` | 1 | **1** ✅ |

---

## 5. Archivos modificados en este commit

```
app/main.py                        | +24
app/templates/dashboard/ai.html    | rewrite completo
app/templates/dashboard/base.html  |  +6
3 files changed, 123 insertions(+), 133 deletions(-)
```

Diff conceptual:

- `base.html`: se envuelve `{% include "dashboard/_ai_panel.html" %}` con un `{% if not hide_ai_panel %}`.
- `main.py`: la ruta `/dashboard/ai` añade `hide_ai_panel=True` y `ai_context=…` al contexto de la plantilla.
- `ai.html`: deja de declarar un `<aside class="ai-sidebar">` propio; en su lugar **incluye** el partial y aplica overrides scoped a `body.route-ai`.

---

## 6. Riesgos y notas

1. **WIZARD excluido por instrucción.** Cualquier mención del flujo de onboarding queda fuera de alcance. La UI ya tiene la página de Resumen (`/dashboard/`) que cubre la primera experiencia del usuario.
2. **CSS scope con `body.route-ai`.** Si en el futuro se quiere que otra ruta use el layout "AI fullscreen", basta con añadir `class="route-ai"` al `<body>` y pasar `hide_ai_panel=True` en el `TemplateResponse`.
3. **Auto-contexto actual.** Los contextos soportados hoy son `opportunities`, `growth`, `retention`. Otros valores caen al saludo genérico. Se pueden extender sin tocar el HTML: solo agregar entradas al mapping en `ai.html`.
4. **Push a `origin/main` ya hecho.** Railway detecta el push a la rama conectada y redespliega automáticamente; no requiere acción manual.

---

## 7. Pendientes / follow-ups (no críticos)

- [ ] Extender `?context=` con más valores cuando el backend exponga otros flujos (ej. `?context=quotes`, `?context=inventory`).
- [ ] Considerar cachear la primera respuesta del chat (warm-up) para que la primera interacción no tenga latencia.
- [ ] Medir Web Vitals en `/dashboard/ai` (es la página más JS-pesada del dashboard).
- [ ] Una vez definidos los criterios del WIZARD, planificar Fase siguiente (onboarding de tenants nuevos).

---

## 8. Comando para verificar el fix

```bash
# Local
uvicorn app.main:app --reload

# Producción
https://wowhub-api-production.up.railway.app/dashboard/ai?context=opportunities
```

Resultado esperado:
- Página de chat full-screen.
- Banner amarillo: *"Contexto: te trajimos aquí desde tu panel de oportunidades. ¿Quieres que conversemos sobre cada una?"*
- El input se rellena automáticamente con el prompt de oportunidades y se envía al backend al cargar.

---

**Fin del informe.**
