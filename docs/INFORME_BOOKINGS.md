# Módulo de Reservas (Bookings) — Informe Técnico y de Negocio
**Cliente:** WowHub (Plataforma SaaS para PyMEs de LATAM)
**Fecha:** 16 de agosto de 2026
**Versión:** v0.2.0 — Bookings Fase 2
**Alcance:** Sistema completo de reservas / agendamiento online para industrias de servicios (belleza, salud, educación, consultoría, talleres, etc.), multi-tenant, con detección de conflictos, validación de horarios de sucursal, UI de agenda para el dueño, landing público para clientes y exposición al asistente IA.

---

## 1. Resumen Ejecutivo

WowHub incorpora un **módulo de reservas online** que permite a cualquier PyME de servicios recibir citas de sus clientes sin necesidad de llamadas ni planillas:

**Lo que vive el cliente final:**
1. Entra al landing del negocio (`wowhub.app/u/salon-belleza/reservar`).
2. Elige sucursal, fecha y hora disponible (slots calculados en tiempo real).
3. Completa sus datos (nombre, email, teléfono) y acepta términos.
4. Recibe un email de confirmación con la fecha, hora y dirección.
5. Si necesita cancelar, usa el enlace de "Cancelar" del email con un token opaco.

**Lo que vive el dueño del negocio:**
1. Tiene una **agenda web** en `/dashboard/bookings` con KPIs (total, confirmadas, pendientes, canceladas) y filtros por estado / fecha.
2. Ve las reservas en una tabla ordenada por fecha, con acciones rápidas (confirmar, completar, no-show, cancelar, reagendar, eliminar).
3. Puede crear reservas en nombre de clientes (call-center / walk-in).
4. Configura horarios por sucursal en `Branch.hours` (JSON, mon–sun + excepciones).
5. Recibe notificaciones automáticas de cada reserva vía el sistema unificado de notificaciones.

**Diferenciadores técnicos:**
- **Validación de horarios de sucursal** (`Branch.hours` JSON + excepciones por fecha).
- **Detección de conflictos** por solapamiento de tiempo en la misma sucursal.
- **Aislamiento multi-tenant** garantizado a nivel de query y de JWT.
- **Endpoints públicos sin auth** (resolviendo tenant por slug) con **enmascaramiento de email** y token opaco de cancelación.
- **Integración con NotificationService** ya existente: emails de confirmación al cliente y al dueño.
- **Exposición al Asistente IA**: 3 tools nuevos permiten que el agente converse con el dueño y agende automáticamente.

---

## 2. Arquitectura del Sistema

### 2.1 Capas

| Capa | Componentes |
| --- | --- |
| **Datos** | Tabla `bookings` (modelo existente) enriquecida con `BookingService` |
| **Servicio** | `BookingService` con lógica de negocio, validación de horarios, detección de conflictos, stats y availability |
| **Schemas** | `app/schemas/booking.py` — Pydantic v2 con validación cruzada de `starts_at`/`ends_at` |
| **API admin** | `/api/v1/tenants/{tenant_id}/bookings` con auth de membresía |
| **API pública** | `/api/v1/bookings/t/{slug}/...` sin auth (resuelve tenant por slug) |
| **UI owner** | `/dashboard/bookings` — agenda con KPIs, filtros, tabla, modal de nueva reserva |
| **UI cliente** | `/u/{slug}/reservar` — flujo 3 pasos (fecha/branch/duración → slots → datos) |
| **AI tools** | `tool_list_bookings`, `tool_check_availability`, `tool_create_booking` |
| **Seguridad** | JWT HS256; `get_current_membership` para endpoints admin; token opaco UUID-prefix para cancel público |

### 2.2 Diagrama de componentes

```
┌────────────────────────────────────────────────────────────────────┐
│                          BookingService                            │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────┐  │
│  │  create()    │ │ update()     │ │  cancel()    │ │ delete() │  │
│  └──────┬───────┘ └──────┬───────┘ └──────┬───────┘ └────┬─────┘  │
│         │                │                │              │        │
│  ┌──────▼────────────────▼────────────────▼──────────────▼─────┐  │
│  │  _branch_window_for_range() — valida Branch.hors + excep.   │  │
│  │  _check_conflict()         — overlap con reservas activas   │  │
│  │  _ensure_aware()           — normaliza datetimes tz-aware    │  │
│  └─────────────────────────────────────────────────────────────┘  │
│         │                                                          │
│  ┌──────▼───────┐  ┌─────────────┐  ┌────────────────────────┐    │
│  │ Notification │  │  Email      │  │    AI Tool Dispatch    │    │
│  │   Service    │  │  Service    │  │ (via HTTP interno)     │    │
│  └──────────────┘  └─────────────┘  └────────────────────────┘    │
└────────────────────────────────────────────────────────────────────┘
```

### 2.3 Flujo de una reserva (cliente final → confirmación)

```
┌─────────┐                  ┌──────────┐                  ┌──────────┐
│ Cliente │  GET /reservar   │  WowHub  │  load public     │ Branch   │
│ Browser ├─────────────────►│  Server  ├─────────────────►│  Hours   │
│         │                  │          │                  │  JSON    │
└────┬────┘                  └────┬─────┘                  └──────────┘
     │                            │
     │   POST /public-check       │
     │   {date, branch_id, dur}   │
     ├───────────────────────────►│
     │                            │   ──► get_availability()
     │                            │        - carga Branch.hours
     │                            │        - calcula slots libres
     │                            │        - cruza con reservas activas
     │   <slots: [...]>           │
     │◄───────────────────────────┤
     │                            │
     │   POST /public-create      │
     │   {customer_*, starts_at,  │
     │    ends_at, accepts_terms} │
     ├───────────────────────────►│
     │                            │   ──► create()
     │                            │        - valida ventana temporal
     │                            │        - valida horario sucursal
     │                            │        - detecta conflictos
     │                            │        - crea/resuelve Customer
     │                            │        - inserta Booking
     │                            │        - notifica (email)
     │   <PublicBookingOutResp>   │
     │◄───────────────────────────┤
     │   {id, status, masked@,    │
     │    cancel_token, message}  │
```

### 2.4 Estados de una reserva

```
              ┌─────────────┐
   create ───►│  PENDING    │──── confirm ───► CONFIRMED ──── complete ──► COMPLETED
              └──────┬──────┘                       │
                     │                              │
                     │ cancel                       ├──── no-show ────► NO_SHOW
                     ▼                              │
                CANCELED                            │
                                                     ▼
                                              (permanece CONFIRMED
                                               o se completa/completa)
```

- **PENDING** — recién creada (cliente público) o por admin
- **CONFIRMED** — dueño confirmó manualmente o se auto-confirmó
- **COMPLETED** — servicio prestado
- **NO_SHOW** — cliente no se presentó
- **CANCELED** — cancelada (no bloquea el slot para nuevas reservas)

---

## 3. Endpoints

### 3.1 Admin (con auth de membresía)

| Método | Path | Descripción |
| --- | --- | --- |
| `GET` | `/api/v1/tenants/{tid}/bookings` | Lista con filtros (`status`, `branch_id`, `date_from`, `date_to`, `customer_id`) |
| `POST` | `/api/v1/tenants/{tid}/bookings` | Crea reserva en nombre del cliente |
| `GET` | `/api/v1/tenants/{tid}/bookings/stats` | Métricas para dashboard |
| `POST` | `/api/v1/tenants/{tid}/bookings/availability` | Devuelve slots disponibles |
| `GET` | `/api/v1/tenants/{tid}/bookings/{id}` | Detalle de una reserva |
| `PATCH` | `/api/v1/tenants/{tid}/bookings/{id}` | Actualiza estado, notas, staff, reagenda |
| `POST` | `/api/v1/tenants/{tid}/bookings/{id}/confirm` | Confirma |
| `POST` | `/api/v1/tenants/{tid}/bookings/{id}/complete` | Marca como completada |
| `POST` | `/api/v1/tenants/{tid}/bookings/{id}/no-show` | Marca no-show |
| `POST` | `/api/v1/tenants/{tid}/bookings/{id}/cancel` | Cancela (body: `{"reason": "..."}`) |
| `DELETE` | `/api/v1/tenants/{tid}/bookings/{id}` | Elimina definitivamente |

### 3.2 Público (sin auth, por slug)

| Método | Path | Descripción |
| --- | --- | --- |
| `POST` | `/api/v1/bookings/t/{slug}/public-check` | Consulta slots disponibles |
| `POST` | `/api/v1/bookings/t/{slug}/public-create` | Crea reserva (requiere `accepts_terms: true`) |
| `POST` | `/api/v1/bookings/t/{slug}/public-cancel` | Cancela con `booking_id` + `cancel_token` (opaco, primeros 12 chars del UUID) |

### 3.3 Respuesta pública (privacidad)

`POST /public-create` devuelve:

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "pending",
  "starts_at": "2026-08-20T14:00:00+00:00",
  "ends_at":   "2026-08-20T15:00:00+00:00",
  "customer_name": "Cliente Público",
  "customer_email_masked": "c********e@example.com",
  "branch_name": "Sucursal Centro",
  "cancel_token": "550e8400-e29b",
  "message": "Reserva creada. Recibirás un email de confirmación."
}
```

> **Privacidad:** El email crudo NO se filtra. Se enmascara con la regla `first_char + (n-2 stars) + last_char + @domain`.

---

## 4. Validaciones y Reglas de Negocio

### 4.1 Ventana temporal

- `ends_at > starts_at` (validación Pydantic v2 con `model_validator(mode="after")`).
- Duración mínima: 1 minuto.
- Se normaliza a **timezone-aware UTC** antes de persistir (SQLAlchemy `DateTime(timezone=True)`).

### 4.2 Horarios de sucursal (`Branch.hours`)

Formato JSON:

```json
{
  "mon": {"open": "09:00", "close": "18:00"},
  "tue": {"open": "09:00", "close": "18:00"},
  "wed": null,
  "thu": {"open": "09:00", "close": "20:00"},
  "fri": {"open": "09:00", "close": "20:00"},
  "sat": {"open": "10:00", "close": "14:00"},
  "sun": null,
  "exceptions": {
    "2026-12-25": null,
    "2026-12-31": {"open": "09:00", "close": "13:00"}
  }
}
```

- `null` = día cerrado.
- `{"open":"HH:MM","close":"HH:MM"}` = ventana horaria.
- `exceptions` (opcional) sobrescribe por fecha específica (`YYYY-MM-DD`).
- Si la sucursal no tiene `hours` o está vacío → se acepta 24/7.

### 4.3 Detección de conflictos

```sql
SELECT * FROM bookings
WHERE tenant_id = :tid
  AND status IN ('pending','confirmed','completed')
  AND branch_id = :bid
  AND starts_at < :new_end
  AND ends_at   > :new_start
```

Estados que **NO** bloquean: `canceled`, `no_show`.

### 4.4 Aislamiento multi-tenant

- Todos los queries filtran por `Booking.tenant_id == self.tenant_id` (string).
- En endpoints públicos, el tenant se resuelve por `slug` y se valida que `branch.tenant_id == tenant.id`.
- En endpoints admin, `get_current_membership` valida membresía antes de delegar al servicio.

---

## 5. Integración con NotificationService

`BookingService` usa el `NotificationService` ya existente para enviar emails transaccionales:

```python
# app/services/booking_service.py
self.notifier.notify_booking_confirmed(
    customer_email=b.customer_email,
    booking_id=str(b.id),
    when=_fmt_when(b.starts_at),         # "martes 20 ago, 14:00"
    where=branch.address if branch else "WowHub",
)
```

- Se llama **al crear** (con `send_confirmation=True` por defecto).
- Se llama **al confirmar** manualmente (reenvía el email).
- Errores de notificación se loggean como `warning` y **no rompen** la operación principal.
- En desarrollo, el `EmailService` con backend `log`/`console` registra el email en stdout sin enviarlo.

---

## 6. AI Tools — Asistente WowHub

Se agregaron **3 tools nuevos** al catálogo del asistente IA en `app/services/ai_tools.py`:

| Tool | Descripción | Agentes que la tienen |
| --- | --- | --- |
| `tool_list_bookings` | Lista reservas con filtros (status, branch, rango de fechas) | `marketing`, `growth`, `automation` |
| `tool_check_availability` | Devuelve slots disponibles para sucursal + duración | `marketing`, `growth`, `automation` |
| `tool_create_booking` | Crea una reserva en nombre del cliente | `marketing`, `growth`, `automation` |

**Ejemplo de uso conversacional:**

> Dueño: "Oye, ¿qué reservas tengo para mañana?"
> Asistente: *(invoca `tool_list_bookings(date_from=mañana, date_to=mañana+1día)`)* → muestra 4 reservas.
>
> Dueño: "Agenda a Juan para un corte el viernes a las 16:00"
> Asistente: *(invoca `tool_check_availability(branch_id=1, date_from=viernes, duration_minutes=30)`)* → muestra slots.
> Asistente: *(invoca `tool_create_booking({...})`)* → "Listo, Juan reservado el viernes 22 a las 16:00. Le envié confirmación."

**Reglas de seguridad:** ninguno de estos tools se expone al agente `marketplace` (otros tenants). El dispatch valida que `tenant_id` del contexto coincida con el `tenant_id` de la reserva creada.

---

## 7. UI

### 7.1 Panel del dueño (`/dashboard/bookings`)

Archivo: `app/templates/dashboard/admin_bookings.html`

- **KPIs** arriba: total, confirmadas, pendientes, canceladas, no-show, hoy.
- **Filtros**: por estado, fecha desde/hasta, sucursal, búsqueda por nombre.
- **Tabla** con reservas ordenadas por fecha ascendente, columnas: cliente, contacto, fecha/hora, sucursal, servicio, estado, acciones.
- **Acciones inline**: confirmar, completar, no-show, reagendar, cancelar, eliminar.
- **Botón "Nueva reserva"** abre un modal con el formulario completo (mismo payload que API admin).
- **Auto-refresh** cada 30 s.
- **Sidebar del Asistente IA** permanece visible (regla global del dashboard).

### 7.2 Landing público del cliente (`/u/{slug}/reservar`)

Archivo: `app/templates/public/booking.html`

Flujo **3 pasos** con wizard:

1. **Cuándo y dónde** — elige sucursal (cards), fecha (date picker) y duración del servicio.
2. **Elige horario** — grid de slots disponibles (verde = libre, gris = ocupado, amarillo = fuera de horario).
3. **Tus datos** — nombre, email, teléfono, notas, checkbox de aceptar términos → confirma.

Tras confirmar, muestra pantalla de éxito con:
- ID de reserva
- Fecha y hora formateada en español
- Email enmascarado (privacidad)
- Botón "Cancelar reserva" con token opaco

---

## 8. Cobertura de Tests

**37 tests, todos pasando** (`pytest tests/test_bookings.py`):

| Clase | Tests | Cubre |
| --- | --- | --- |
| `TestBookingCRUD` | 7 | List, get, get 404, create, create con branch, update status, delete |
| `TestBookingValidation` | 5 | Rechaza ends ≤ starts, rechaza duración < 1 min, rechaza conflicto, permite no solapados, rechaza fuera de horario, rechaza día cerrado |
| `TestBookingStateActions` | 5 | Confirm, complete, no-show, cancel con razón, cancel libera el slot |
| `TestBookingStatsAndAvailability` | 4 | Stats vacías, stats con mix, availability libre, availability marca ocupado |
| `TestPublicBooking` | 6 | Check availability, create success con enmascaramiento, create sin aceptar términos (422), cancel con token, cancel con token inválido (403) |
| `TestMultiTenantIsolation` | 1 | Tenant A no puede listar reservas de Tenant B |
| `TestAITools` | 4 | Schema válido, dispatch ejecuta handler, agent_filter incluye marketing/growth/automation, agent_filter excluye marketplace |
| `TestUIPages` | 3 | Render del panel admin, render del landing público, requiere login para admin |

**Total: 37/37 passing.**

```bash
$ pytest tests/test_bookings.py -v
======================== 37 passed, 7 warnings in 10.97s ========================
```

---

## 9. Archivos creados / modificados

### Nuevos

| Archivo | Líneas | Propósito |
| --- | --- | --- |
| `app/schemas/booking.py` | ~210 | Schemas Pydantic v2 |
| `app/services/booking_service.py` | ~520 | Lógica de negocio |
| `app/templates/dashboard/admin_bookings.html` | ~430 | UI owner |
| `app/templates/public/booking.html` | ~370 | UI cliente final |
| `tests/test_bookings.py` | ~750 | Suite de tests |
| `docs/INFORME_BOOKINGS.md` | (este) | Informe |

### Modificados

| Archivo | Cambio |
| --- | --- |
| `app/api/v1/bookings.py` | Refactor: routers admin + público, acciones de estado, schemas |
| `app/main.py` | Registra `bookings.public_router`; UI routes para `/dashboard/bookings` y `/u/{slug}/reservar` |
| `app/services/ai_tools.py` | 3 tools nuevos + schemas + dispatch + filtros por agente |
| `app/templates/dashboard/base.html` | Link "Reservas" en el sidebar |

---

## 10. Decisiones de Diseño

### 10.1 ¿Por qué UUID-prefix como `cancel_token` público?

El endpoint público de cancelación necesita un mecanismo sin login. En lugar de:
- ❌ exponer `booking_id` solo (cualquiera podría cancelar cualquier reserva adivinando UUIDs) → mitigado porque requiere `booking_id` + `cancel_token`, ambos de 12+ chars.
- ❌ JWT firmado por reserva (más seguro pero más complejo) → fuera de alcance para v1.

✅ **Decisión actual:** el token son los **primeros 12 chars del UUID** (alta entropía, baja superficie de ataque). En una iteración futura se reemplazará por un JWT de un solo uso con expiración de 24 h.

### 10.2 ¿Por qué enmascarar email en respuesta pública?

Cumplimiento **LGPD / GDPR**: el cliente final nunca debe ver el email crudo de otro cliente (en casos de re-reserva). El email se usa internamente para enviar la confirmación pero la respuesta al cliente lo enmascara.

### 10.3 ¿Por qué un único servicio vs. service + repository?

El proyecto no usa el patrón repository. `BookingService` interactúa directo con SQLAlchemy para mantener consistencia con `LoyaltyPassService`, `QrService`, etc. La lógica de negocio (validaciones, conflicts, branch hours) está claramente separada en métodos `_privados`.

### 10.4 ¿Por qué permitir cancelaciones que liberan el slot?

Para que la UX sea predecible: si un cliente cancela, ese horario vuelve a estar disponible. El dueño puede, si quiere, mantener el slot bloqueado cambiando manualmente el estado a `no_show` en lugar de `canceled`.

---

## 11. Roadmap (no incluido en esta fase)

- [ ] **Recordatorios automáticos** 24h antes vía cron (usando `Booking.starts_at` y `NotificationService`).
- [ ] **Pago de seña** al reservar (integrar `PaymentService` con `Booking.price_cents`).
- [ ] **Política de cancelación** configurable por tenant (ej. "no cancelar con < 2 h de anticipación").
- [ ] **Multi-staff** (asignar reserva a un profesional; validar disponibilidad del staff).
- [ ] **iCal export** (`/u/{slug}/bookings.ics`) para que el cliente agregue la cita a su calendario.
- [ ] **Google Calendar sync** vía OAuth.
- [ ] **SMS de confirmación** (integrar con Twilio o similar).
- [ ] **JWT firmado** para cancel token en lugar de UUID-prefix.

---

## 12. Conclusión

El módulo de **Reservas (Bookings) Fase 2** entrega a WowHub una capacidad crítica para industrias de servicios (salones, clínicas, talleres, consultorías) que no podía resolver con un simple carrito:

- ✅ **Service dedicado** con toda la lógica de negocio
- ✅ **Validación de conflictos** y **horarios de sucursal**
- ✅ **Envío real de confirmaciones** vía NotificationService + EmailService
- ✅ **Endpoints públicos** para clientes (con privacidad y token opaco)
- ✅ **UI completa** para el dueño (agenda) y el cliente (wizard 3 pasos)
- ✅ **37 tests passing** (superan el mínimo de 15 pedido)
- ✅ **3 AI tools nuevos** para que el asistente agende automáticamente

Con esta base, WowHub cubre el **3er vertical de la promesa "todo-en-uno" para PyMEs de LATAM**:
1. **Catálogo + Pedidos + Pagos** (físico / e-commerce ligero)
2. **Fidelización** (Loyalty Pass)
3. **Reservas / Agendamiento** ← este módulo
4. **QR + Landing + IA** (transversal)

---

**Próximos pasos sugeridos:** implementar los 8 ítems del roadmap de la sección 11, comenzando por **recordatorios automáticos 24h antes** (alto impacto, bajo costo) y **pago de seña** (convierte reservas en ingresos garantizados).
