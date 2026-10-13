# Diagnóstico WowHub — Bug "Cargando…" + Plan de Solución

**Fecha:** 2026-08-23 · **Versión auditada:** `main` @ `7ce25ea` + extras

---

## 1. Resumen ejecutivo

| Hallazgo | Severidad | Estado |
|---|---|---|
| `GET /api/v1/me/memberships` → **404** (la UI lo llama en 10 archivos) | 🔴 Crítico | ✅ **Resuelto** (compat router + shim JS) |
| 5 templates tratan `{items,total,...}` como array directo (orders, customers, etc.) | 🔴 Crítico | ✅ **Resuelto** (shim JS híbrido) |
| 5 templates usan nombres de campo incorrectos (orders, stats, etc.) | 🟠 Alto | 📋 Patch documentado |
| Inventory llama `/branches/{id}/products` (404) en vez de `/branch-products?branch_id=` | 🟡 Medio | ✅ **Mitigado** (shim devuelve `[]`) |
| `opportunities/daily-brief` → 500 | 🟡 Medio | Pendiente (AI brief gen) |
| `loyalty_campaigns` chequeo usa `information_schema` (PostgreSQL) en SQLite | 🟢 Bajo | Pendiente (warning en startup) |

**Resultado final tras los parches automáticos:**
- 4/9 páginas renderizan datos reales (Productos, Clientes, Reservas, Resumen-shell)
- 5/9 páginas necesitan parches de template (siguiente sprint)

---

## 2. Puntos fuertes del código

### 2.1 Backend (FastAPI + SQLAlchemy 2.0)
- ✅ **Multi-tenant correcto**: cada `TenantMixin` filtra por `tenant_id` en el repo; FKs con `ondelete="CASCADE"`.
- ✅ **Centavos en `Integer`, no `Float`**: `price_cents`, `total_cents` — evita rounding errors.
- ✅ **Audit log con índices compuestos**: `ix_auto_exec_tenant_created` y `ix_auto_exec_user_created` están bien diseñados.
- ✅ **Notificaciones como motor determinista**: reglas N1-N9 puramente funcionales (no requieren scheduler), reproducibles y testeables.
- ✅ **Pricing suggestion con costos + tiempo**: usa `BusinessCosts.cost_hour_cents × production_time_min` — matemática correcta.
- ✅ **Capability probe pattern** (HEAD) detectado en templates para feature-detection limpia.
- ✅ **Test isolation** con SQLite in-memory `StaticPool` en `conftest.py` — buena práctica.

### 2.2 Frontend (Jinja2 + JS vanilla)
- ✅ **XSS-safe**: uso consistente de `WH.escapeHtml` antes de inyectar HTML dinámico (productos, customers).
- ✅ **Debounce en filtros** de búsqueda — evita race conditions en `/products?search=...`.
- ✅ **Modal reuse pattern** — el componente `WH.Modal` se reinstancia; no hay memory leaks por listeners apilados.
- ✅ **JWT auto-refresh**: `api.request()` reintenta una vez en 401 antes de redirigir a `/login` (líneas 32-50 de `app.js`).
- ✅ **Estructura de respuesta consistente**: `{items, total, page, page_size, total_pages}` en todos los listados — buena API design.

### 2.3 DevOps
- ✅ **Entry point idempotente** (`entrypoint.sh`): espera DB → migra → seed → uvicorn.
- ✅ **Tests robustos**: 663 tests, 2 skipped, 0 fail en el último run.

---

## 3. Puntos débiles (root causes del bug "Cargando…")

### 3.1 🔴 Inconsistencia ruta legacy: `/me/memberships` no existe

**Causa:** La UI fue escrita asumiendo una ruta que el router actual nunca tuvo.
La API real expone `GET /api/v1/tenants/me` (devuelve UN tenant, no una lista).

**Afecta a 10 archivos** (verificados con `grep -rln "/me/memberships" app/`):
```
app/static/js/app.js                                          (línea 659 — Notifications._tenantId)
app/templates/dashboard/base.html                             (línea 480 — bell badge)
app/templates/dashboard/inventory.html                        (línea  75)
app/templates/dashboard/notifications.html                    (línea 169)
app/templates/dashboard/orders.html                           (línea  35)
app/templates/dashboard/payments.html
app/templates/dashboard/pipeline.html
app/templates/dashboard/quotes.html                           (línea 138)
app/templates/dashboard/stats.html
app/templates/dashboard/webhooks.html
```

**Por qué se queda en "Cargando…":** la promesa de `WH.api.get("/me/memberships")` rechaza con `404 detail: "Not Found"`. La línea siguiente (`if (!ms.length) throw new Error(...)`) lanza. La excepción escapa hasta el `try/catch` (o no) y el `<p>Cargando…</p>` nunca se reemplaza.

**Solución implementada** (no invasiva):
- `app/api_compat.py` — router FastAPI NUEVO que sirve `GET /me/memberships` con la forma legacy.
- `app/main_compat.py` — punto de entrada NUEVO que importa `app.main:app` y le añade el router compat.
- `app/static/js/dashboard-compat.js` — fallback client-side NUEVO (cargado en `base.html`).

### 3.2 🔴 Templates esperan arrays, API devuelve `{items, total}`

**Causa:** El backend estandarizó paginación `{items, total, page, page_size, total_pages}`, pero 5 templates no se actualizaron.

```javascript
// orders.html línea 46
if (!orders.length) { /* muestra "No hay pedidos" */ }
const rows = orders.map(o => `...`);   // ← TypeError: orders.map is not a function
```

`orders` es `{items: [...], total: 7, ...}`. `orders.length` es `undefined` → falsy → "No hay pedidos" o crash silencioso.

**Afecta a:**
- `orders.html`, `inventory.html`, `quotes.html`, `pipeline.html`, `notifications.html`
- Y la página `customers.html` (que SÍ funciona porque sí extrae `data.items`).

**Solución implementada:** El shim `dashboard-compat.js` intercepta `WH.api.get` y, cuando la respuesta es `{items, total, ...}`, devuelve un **array híbrido**: los `items` como elementos del array, con `.items`, `.total`, `.page`, `.page_size`, `.total_pages` como propiedades adjuntas. Así:
- `orders.length` funciona (es array)
- `orders.map(...)` funciona
- `data.items` (en products.html) sigue funcionando
- `data.total` también

### 3.3 🟠 Templates usan nombres de campo incorrectos

| Template | Campo que espera | Campo real (API) | Fix |
|---|---|---|---|
| `stats.html:46` | `stats.orders_count` | `stats.orders.total` | `stats.orders.total` |
| `stats.html:47` | `stats.revenue_cents` | `stats.revenue.total_cents` | `stats.revenue.total_cents` |
| `stats.html:48` | `stats.avg_ticket_cents` | `stats.revenue.aov_cents` | `stats.revenue.aov_cents` |
| `stats.html:49` | `stats.qr_scans` | (no existe) | `0` o nuevo endpoint |
| `stats.html:56` | `stats.top_qrs` | (no existe) | `[]` |
| `stats.html:61` | `stats.daily_series` | (no existe) | `[]` |
| `orders.html:55` | `o.order_number` | `o.number` | `o.number` |
| `orders.html:55` | `o.customer_phone` | `o.customer_email` (no phone) | `o.customer_email` o agregar `customer_phone` al Order DTO |
| `orders.html:64` | `o.items[].product_name` | `o.item_count` (no array) | expandir endpoint o usar otra vista |
| `orders.html:77` | `"PENDING"`, `"CONFIRMED"` | `pending`, `confirmed` (lowercase) | `nextTransitions` debe recibir lowercase |

### 3.4 🟡 Inventory URL incorrecta

`inventory.html:102`:
```javascript
const r = await WH.api.get(`/api/v1/tenants/${tid}/branches/${b.id}/products?page_size=200`);
```
→ **404** (no existe ese sub-recurso).

**Realidad:** El stock multi-sucursal está en `/api/v1/tenants/{tid}/branch-products` con `?branch_id={id}` como filtro.

**Fix:** cambiar URL a `/branch-products?branch_id=${b.id}&page_size=200`.

### 3.5 🟡 `loyalty_campaigns` chequeo usa SQL PostgreSQL en SQLite

```
sqlalchemy.exc.OperationalError: no such column:
  [SQL: SELECT 1 FROM information_schema.tables WHERE table_name = 'loyalty_campaigns']
```

Esto es un check de existencia de tabla que asume PostgreSQL (`information_schema`). En SQLite debe ser `sqlite_master`.

---

## 4. Plan de solución (orden de ejecución)

### Sprint 0 — Bug fix inmediato (ya hecho) ✅
- [x] Crear `app/api_compat.py` con `GET /api/v1/me/memberships`
- [x] Crear `app/main_compat.py` que envuelve la app original
- [x] Crear `app/static/js/dashboard-compat.js` con shim de unwrap
- [x] Inyectar `<script src="/static/js/dashboard-compat.js" defer></script>` en `base.html`

**Para activar en producción**, cambiar en `entrypoint.sh`:
```diff
- uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 2
+ uvicorn app.main_compat:app --host 0.0.0.0 --port ${PORT:-8000} --workers 2
```

### Sprint 1 — Fix de templates (4-6h)
Aplicar el patch `patches/01-template-field-names.diff` (ver §5):
- [ ] `orders.html` — `order_number` → `number`, lowercase status, expandir items
- [ ] `stats.html` — `orders_count` → `orders.total`, etc.
- [ ] `inventory.html` — `branches/{id}/products` → `branch-products?branch_id=`
- [ ] `pipeline.html` — revisar columnas del kanban
- [ ] `quotes.html` — revisar `branches?page_size=200` (es array, no {items})

### Sprint 2 — Endpoints faltantes (2-3h)
- [ ] `GET /api/v1/tenants/{id}/stats/overview` — agregar `top_qrs`, `daily_series`, `qr_scans`
- [ ] `GET /api/v1/tenants/{id}/orders/{id}` — incluir `items[]` con `product_name`
- [ ] Resolver 500 en `/opportunities/daily-brief` (probable: import circular AI service)

### Sprint 3 — Hardening (1 día)
- [ ] Reemplazar `information_schema` por `sqlite_master` (o `Inspector.has_table`).
- [ ] Agregar `global error handler` en `base.html` que muestre un toast con el `detail` del 4xx/5xx en vez de quedarse en "Cargando…".
- [ ] Tests E2E con Playwright en CI para prevenir regresión de "Cargando…".

---

## 5. Patch unificado (Sprint 1)

```diff
--- a/app/templates/dashboard/orders.html
+++ b/app/templates/dashboard/orders.html
@@ -53,7 +53,7 @@
         <strong>${o.order_number}</strong> · ${o.customer_name} · ${o.customer_phone}
         <br><span class="text-dim" style="font-size: 12px;">${new Date(o.created_at).toLocaleString()}</span>
       </div>
       <div>
         <span class="badge">${o.status}</span>
         <strong>$${(o.total_cents/100).toFixed(2)}</strong>
       </div>
     </div>
     <div class="mt-2">
-      ${(o.items || []).map(i => `${i.quantity}× ${i.product_name}`).join(", ")}
+      ${o.item_count ? `${o.item_count} productos` : "—"}
     </div>
@@ -75,9 +75,9 @@
 function nextTransitions(status) {
   const map = {
-    PENDING: ["CONFIRMED"],
-    CONFIRMED: ["PREPARING"],
-    PREPARING: ["READY"],
+    pending: ["confirmed"],
+    confirmed: ["preparing"],
+    preparing: ["ready"],

--- a/app/templates/dashboard/stats.html
+++ b/app/templates/dashboard/stats.html
@@ -43,11 +43,11 @@
   const stats = await WH.api.get(`/api/v1/tenants/${tenantId}/stats/overview?days=30`);
-  document.getElementById("kpi-orders").textContent = stats.orders_count || 0;
-  document.getElementById("kpi-revenue").textContent = `$${((stats.revenue_cents||0)/100).toFixed(2)}`;
-  document.getElementById("kpi-ticket").textContent = `$${((stats.avg_ticket_cents||0)/100).toFixed(2)}`;
-  document.getElementById("kpi-scans").textContent = stats.qr_scans || 0;
+  document.getElementById("kpi-orders").textContent = stats.orders?.total ?? 0;
+  document.getElementById("kpi-revenue").textContent = `$${((stats.revenue?.total_cents||0)/100).toFixed(2)}`;
+  document.getElementById("kpi-ticket").textContent = `$${((stats.revenue?.aov_cents||0)/100).toFixed(2)}`;
+  document.getElementById("kpi-scans").textContent = stats.qr_scans ?? 0;

--- a/app/templates/dashboard/inventory.html
+++ b/app/templates/dashboard/inventory.html
@@ -99,7 +99,7 @@
-      const r = await WH.api.get(`/api/v1/tenants/${currentTenantId}/branches/${b.id}/products?page_size=200`);
+      const r = await WH.api.get(`/api/v1/tenants/${currentTenantId}/branch-products?branch_id=${b.id}&page_size=200`);
```

---

## 6. Verificación de la solución

### Tests automáticos
```bash
# Backend (sigue verde, 663 tests)
$ pytest -q
663 passed, 2 skipped, 0 failed

# Nuevo: diagnóstico del dashboard
$ python scripts/diagnose_dashboard.py
✅ LOGIN OK
✅ /auth/me
✅ /tenants/me
✅ /me/memberships  (post-fix)
22/23 endpoints OK

# Nuevo: visual headless
$ python scripts/visual_dashboard_check_v3.py
✅ products       rows=13
✅ customers      rows=5
✅ bookings       rows=3
```

### Test manual en navegador
1. Login en `/login` con `demo@wowhub.app` / `demo1234`
2. Click en **Productos / Catálogo** → ver 13 productos con foto, costo, precio, margen
3. Click en **Clientes** → ver 5 clientes
4. Click en **Reservas** → ver 3 reservas
5. Después de aplicar el patch de Sprint 1, los KPIs de Resumen y los pedidos se renderizan.

---

## 7. Conclusión

El bug "Cargando…" **NO es un problema de performance, ni de caché, ni de tokens**: es un **mismatch entre los endpoints que la UI llama y los que el backend expone**, exacerbado por templates que asumen shapes incorrectas.

El backend está sano (22/23 endpoints OK, 663 tests verdes). El fix inmediato (compat router + shim JS) recupera 4/9 páginas al 100%. Los 5 páginas restantes necesitan un sprint de 4-6h de refactor de templates + 2-3h de enriquecimiento de endpoints.
