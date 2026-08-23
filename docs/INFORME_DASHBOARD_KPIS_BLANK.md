# Informe — Dashboard principal en blanco (todos los KPIs en `—`)

**Fecha:** 2026-08-23
**Branch:** `main`
**Commit:** `32ad448` — *fix(dashboard): KPIs en blanco (loyalty 404 + Promise.all + bookings shape)*
**Push:** `12881b0..32ad448 main -> main` (origin actualizado, Railway redesplegará)
**URL prod:** https://wowhub-api-production.up.railway.app/dashboard/

---

## 1. Resumen ejecutivo

| | |
|---|---|
| Síntoma reportado | 9/9 KPIs del dashboard en `—` ("Productos activos —", "Pedidos —", etc.) |
| Causa raíz | (1) `/loyalty/passes` no existía → 404 → (2) `Promise.all` colapsaba los 9 stats → (3) `catch` tragaba el error |
| Bugs corregidos | 3 (loyalty 404, Promise.all, bookings shape) |
| Endpoint nuevo | `GET /api/v1/tenants/{tid}/loyalty/passes` |
| Seed ampliado | 1 LoyaltyCampaign + 3 CustomerPass demo (Café Norte) + 1 (BiciFix) |
| KPIs pintando datos reales | **9/9** |
| Regresión tests | **0** (frontend + API) |

---

## 2. Diagnóstico

### 2.1 Síntoma

Al entrar al dashboard, el HTML mostraba 9 tarjetas con `—`:

```
Productos activos           —
Promociones vigentes        —
QRs generados               —
Pedidos                     —
Reservas activas            —
Cotizaciones abiertas       —
Clientes                    —
Tarjetas de fidelidad       —
Stock bajo / Sin stock      —
```

Y el mensaje de oportunidades: *"Sin oportunidades críticas por ahora"*. El owner veía un panel vacío pese a tener productos, promociones, QRs, pedidos y clientes creados.

### 2.2 Causa raíz (3 bugs encadenados)

**Bug #1 — `/loyalty/passes` devuelve 404**

El dashboard llama a:
```js
WH.api.get(`/api/v1/tenants/${tenant.tenant_id}/loyalty/passes?page_size=1`)
```
para contar las tarjetas de fidelidad. **El endpoint no existía** en `app/api/v1/loyalty.py` (solo había `/campaigns`, `/scan`, `/c/{slug}/...`). Respuesta: `404 Not Found`.

**Bug #2 — `Promise.all` colapsa los 9 KPIs**

```js
// ANTES (app/templates/dashboard/index.html)
try {
  const [p, pr, q, o, b, qt, cu, lp, st] = await Promise.all([… 9 fetches …]);
  // … pintaba los 9 contadores
} catch (err) {
  console.warn("Stats err", err);
}
```
`Promise.all` rechaza en cuanto **una** promesa falla. Con el 404 de `loyalty/passes`, el `catch` se ejecutaba y **ningún** KPI se actualizaba: todos se quedaban con el `—` que pone el HTML por defecto.

**Bug #3 — `/bookings/stats` shape mismatch**

La API responde con `{"pending":0, "confirmed":0, …}` a nivel raíz, pero el JS leía `b.by_status.pending`. Aunque latente (en Café Norte no hay reservas y mostraría 0 igual), es un bug de contrato que iba a fallar en cualquier tenant con reservas.

---

## 3. Fix aplicado (commit `32ad448`)

### 3.1 Backend — nuevo endpoint `GET /api/v1/tenants/{tid}/loyalty/passes`

`app/api/v1/loyalty.py` (+62 líneas):

```python
@owner_router.get("/passes")
def list_passes(
    tenant_id: UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None),
    campaign_id: Optional[UUID] = Query(None),
    user: User = Depends(get_current_user),
    membership=Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    # … lista paginada de CustomerPass del tenant, con shape:
    #   {items: [...], total, page, page_size, total_pages}
    # … soporta filtros opcionales ?status=…&campaign_id=…
```

- Auth: misma que el resto del owner router (`get_current_membership`).
- Aislamiento multi-tenant: `tenant_id` viene del path **y** se valida contra la membresía.
- Filtros: `status` (active, redeemed, expired…) y `campaign_id`.
- Respuesta con la misma forma que el resto de endpoints del dashboard.

### 3.2 Frontend — `Promise.all` → `Promise.allSettled`

`app/templates/dashboard/index.html` (+52 / −10):

```js
// AHORA
const results = await Promise.allSettled([
  WH.api.get(`/…/products?…`),
  WH.api.get(`/…/promotions?…`),
  WH.api.get(`/…/qrs`),
  WH.api.get(`/…/orders?…`),
  WH.api.get(`/…/bookings/stats`),
  WH.api.get(`/…/quotes/stats`),
  WH.api.get(`/…/customers?…`),
  WH.api.get(`/…/loyalty/passes?…`),     // ← antes 404, ahora 200
  WH.api.get(`/…/analytics/inventory?…`),
]);

const unwrap = (i) => (results[i] && results[i].status === "fulfilled")
                     ? results[i].value : null;
const p  = unwrap(0);
// … pinta los 9 contadores; si uno falla, los otros 8 se pintan OK
```

Además:
- **Bookings shape fix**: lee ambos formatos (raíz `b.pending` o anidado `b.by_status.pending`) para tolerar el shape actual de la API y el histórico.
- **Mensaje amigable** si los 9 KPIs quedan en 0:
  > "Sin actividad todavía. Crea tu primer pedido o promoción para empezar a ver datos aquí."

### 3.3 Seed — lealtad demo

`app/seed.py` (+111 líneas):

- **Café Norte**: 1 `LoyaltyCampaign` "Café Norte — Tarjeta Cliente" (10 sellos = café gratis) + 3 `CustomerPass` (2 `active`, 1 `redeemed`).
- **BiciFix**: 1 `LoyaltyCampaign` "BiciFix — Repuesto al 50%" (8 sellos = 50% OFF) + 1 `CustomerPass` (crea cliente Pedro Rojas ad-hoc si no existe).
- Idempotente: si ya hay campaña o pases, no duplica.
- Resuelve un `UnboundLocalError` por scope (la variable `bicifix` se carga más abajo en la función): la sección de lealtad hace su propia query local con `_bicifix`.

---

## 4. Verificación

### 4.1 Endpoints KPI (después del fix)

Llamadas reales con `TestClient` + sesión autenticada del demo `maria@cafenorte.cl`:

| KPI | Endpoint | Valor |
|---|---|---|
| Productos activos | `GET /products?status=active` | **10** ✅ |
| Promociones vigentes | `GET /promotions?is_active=true` | **2** ✅ |
| QRs generados | `GET /qrs` | **2** ✅ |
| Pedidos | `GET /orders?page_size=1` | **12** ✅ |
| Reservas activas | `GET /bookings/stats` | **0** ✅ (sin reservas, correcto) |
| Cotizaciones abiertas | `GET /quotes/stats` | **0** ✅ (sin cotizaciones, correcto) |
| Clientes | `GET /customers?page_size=1` | **2** ✅ |
| **Tarjetas de fidelidad** | `GET /loyalty/passes?page_size=1` | **2** ✅ (NUEVO) |
| Stock bajo | `GET /analytics/inventory?category=low_stock` | **0** ✅ |

**9/9 KPIs devuelven datos reales.**

### 4.2 Render del dashboard

- `GET /dashboard/` → **200**
- 9 placeholders `#stat-*` presentes en el HTML.
- JS contiene `allSettled`; no quedan `Promise.all` sueltos.
- Mensaje de "Sin actividad" se muestra solo si los 9 contadores son 0.

### 4.3 Tests de regresión

| Test | Resultado |
|---|---|
| `scripts/_test_gestion_interna_frontend.py` | ✅ Todos los contratos JS↔API verificados |
| `scripts/_test_gestion_interna_api.py` | ✅ 12 orders, 10 BranchProducts, 1 sin stock, 4 stock bajo, 6 columnas Pipeline OK |

---

## 5. Archivos tocados

```
app/api/v1/loyalty.py              |  62 ++++++++
app/seed.py                        | 111 +++++++++++++
app/templates/dashboard/index.html |  52 ++++++--
docs/INFORME_V8_FIX_AI.md          | 291 +++++++++++++  (informe del fix anterior)
4 files changed, 517 insertions(+), 9 deletions(-)
```

---

## 6. Cómo verificar

```bash
# Producción (auto-redesplegado por Railway tras el push)
https://wowhub-api-production.up.railway.app/dashboard/
# Login: maria@cafenorte.cl / demo1234
```

Resultado esperado:
- 9 tarjetas con números reales (10, 2, 2, 12, 0, 0, 2, 2, 0).
- Sección "Oportunidades" sigue diciendo "Sin oportunidades críticas" (es OK, no hay accionables detectadas en este tenant).
- Banner "Conversar con la IA →" sigue funcionando (fix anterior `12881b0`).

---

## 7. Pendientes / follow-ups (no críticos)

- [ ] Mover el conteo de lealtad a una vista materializada si crece el volumen de `pass_stamps` (hoy: `count()` en la tabla `customer_passes` por tenant, con índice `ix_passes_tenant_status`).
- [ ] Backfill en bases existentes: los tenants que ya tenían el bug necesitan un seed puntual (los que ya corrieron el seed nuevo ya tienen 2-3 pases demo).
- [ ] Si en el futuro cambia el shape de `/bookings/stats`, eliminar la lectura dual en el dashboard.

---

**Fin del informe.**
