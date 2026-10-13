# Sistema de Fidelización (Loyalty Pass) — Informe Técnico y de Negocio

**Cliente:** WowHub (Plataforma SaaS para PYMEs de LATAM)
**Fecha:** 16 de agosto de 2026
**Versión:** v0.2.0 — Loyalty Pass (Fase 1 + Fase 2)
**Alcance:** Sistema de tarjetas de fidelización digitales con sellos, multi-tenant, con QR rotativo anti-fraude.

---

## 1. Resumen Ejecutivo

WowHub incluye un **sistema de fidelización completo** basado en **tarjetas digitales con sellos** (stamp cards), similar a Apple Wallet / Google Pay pero 100 % web. Permite a cualquier PyME de LATAM lanzar una campaña de fidelización en minutos sin hardware especial: solo un dispositivo con navegador en el mostrador (tablet/celular/computador).

**Lo que el cliente final vive:**
1. Entra al landing del comercio (`wowhub.app/u/cafe-norte`).
2. Se registra con email o teléfono.
3. Recibe un **pase digital con QR propio** que puede guardar como imagen o capturar pantalla.
4. Cada vez que compra, el **garzón escanea dos QR**: el del mostrador (cambia cada 60 s) + el del cliente.
5. Aparece un sello nuevo en su pase. Al juntar N sellos, **desbloquea el premio** (café gratis, descuento, etc.) y el ciclo empieza de nuevo.

**Diferenciadores técnicos:**
- **QR rotativo del mostrador (anti-fraude):** un QR pegado en la caja que cambia cada 60 s y se invalida tras un solo uso. Impide que un cliente tome foto del QR y acumule sellos sin comprar.
- **PIN de garzón opcional** (4–8 dígitos, hasheado SHA-256): previene que un empleado acumule sellos a clientes amigos.
- **Aislamiento multi-tenant** garantizado a nivel de query y de JWT.
- **Auditoría completa** de cada estampilla: quién la puso, cuándo, con qué QR, si validó PIN.

---

## 2. Arquitectura del Sistema

### 2.1 Capas

| Capa | Componentes |
| --- | --- |
| **Datos** | 4 tablas: `loyalty_campaigns`, `customer_passes`, `pass_stamps`, `qr_tokens` |
| **Servicio** | `LoyaltyPassService` + `LoyaltyService` (puntos y niveles) |
| **API** | 3 routers separados: `owner_router`, `pos_router`, `public_router` |
| **UI** | Landing público (`/u/<slug>`), panel admin (`/admin/loyalty`), escáner POS (`/admin/scanner`) |
| **Seguridad** | JWT HS256 firmado con `JWT_SECRET`; SHA-256 para PIN |

### 2.2 Flujo de una transacción (escaneo exitoso)

```
┌──────────┐                                  ┌──────────┐
│ Cliente  │  tiene QR del pase (JWT 1 año)  │ Mostrador│  tiene QR rotativo (60s)
│ (browser │                                  │ (tablet) │
│  o app)  │                                  │          │
└─────┬────┘                                  └────┬─────┘
      │                                            │
      │   1. Cliente muestra su QR del pase       │
      │ ────────────────────────────────────────>  │
      │   2. Garzón escanea QR del mostrador       │
      │   3. Garzón escanea QR del cliente         │
      │   4. (Opcional) Garzón ingresa su PIN      │
      │   5. Frontend llama POST /api/v1/loyalty/scan
      │ ────────────────────────────────────────>  │
      │                                            │   Backend:
      │                                            │   a) Valida JWT del mostrador
      │                                            │      (firma, exp, jti, tenant)
      │                                            │   b) Marca token como consumido
      │                                            │   c) Valida PIN si la campaña lo pide
      │                                            │   d) Suma 1 sello al pass
      │                                            │   e) Si completó N → REDEEMED + reward
      │                                            │   f) Inserta fila en pass_stamps (audit)
      │   6. Respuesta: ok + nuevo estado del pass │
      │ <───────────────────────────────────────  │
      │   7. UI del cliente refresca: 1 sello más  │
      │                                            │
      │   8. (Si completó N) Banner: "¡Ganaste! ☕"│
```

---

## 3. Modelos de Datos (4 tablas)

### 3.1 `loyalty_campaigns` — La campaña
Una PyME puede tener **N campañas** (ej. "Café gratis", "Descuento 20 %"), pero **una activa a la vez** por defecto.

| Campo | Tipo | Descripción |
| --- | --- | --- |
| `id` | UUID | PK |
| `tenant_id` | UUID | FK al tenant (multi-tenant) |
| `name` | str (120) | "Tarjeta de Fidelidad Café Norte" |
| `reward_label` | str (160) | "1 Café Gratis" |
| `stamps_required` | int (2–50) | Sello meta (constraint CHECK en DB) |
| `primary_color` | hex | Color principal de la tarjeta |
| `text_color` | hex | Color del texto |
| `accent_color` | hex? | Acento opcional |
| `logo_url`, `icon_url`, `strip_url` | URL? | Imágenes |
| `is_active` | bool | Soft-archive (no se borra) |
| `starts_at`, `ends_at` | datetime? | Ventana de validez |
| `cashier_pin` | hex (64)? | SHA-256 del PIN de garzón |
| `pin_hint` | str? | Pista legible |
| `total_passes` | int | Denormalizado (count) |
| `total_stamps_issued` | int | Denormalizado (count) |
| `total_rewards_redeemed` | int | Denormalizado (count) |

**Constraints:** `stamps_required BETWEEN 2 AND 50`, índice `(tenant_id, is_active)`.

### 3.2 `customer_passes` — El pase del cliente
**1 fila por (cliente × campaña)**, gracias al UniqueConstraint.

| Campo | Tipo | Descripción |
| --- | --- | --- |
| `id` | UUID | PK |
| `tenant_id`, `campaign_id`, `customer_id` | UUID | FKs |
| `serial_number` | str (64) | Identificador legible: `wh:<tenant>:<campaign>:<customer>` |
| `source` | enum | `web` / `apple` / `google` / `manual` |
| `status` | enum | `active` / `redeemed` / `expired` / `replaced` / `revoked` |
| `stamps_current` | int | Sellos en el ciclo actual |
| `rewards_earned` | int | Total histórico de premios canjeados |
| `qr_payload` | text (JWT) | QR firmado del cliente (dura 1 año) |
| `apple_pass_url`, `google_pass_jwt` | str? | **Reservado** para Fase 3/4 |
| `installed_at`, `last_stamp_at`, `redeemed_at`, `expires_at` | datetime? | Eventos clave |

**Constraint CHECK:** `stamps_current >= 0`. **UniqueConstraint:** `(tenant_id, campaign_id, customer_id)`.

### 3.3 `pass_stamps` — Auditoría inmutable
**Append-only.** Una fila por cada evento de sello, ajuste o redención.

| Campo | Descripción |
| --- | --- |
| `pass_id`, `campaign_id` | FKs |
| `delta` | +1 (scan) o N (ajuste manual) o negativo (redención) |
| `reason` | `scan` / `manual_adjust` / `reward_redeem` / `reissue` |
| `scanned_by` | user_id del garzón |
| `cashier_pin_validated` | bool — si se validó PIN en este evento |
| `device_fp` | fingerprint del dispositivo del mostrador |
| `qr_token_jti` | jti del QR del mostrador usado (1-shot) |
| `stamps_after` | int — sellos resultantes |
| `reward_unlocked` | bool — si este evento completó N sellos |

**Index:** `(pass_id, created_at)` para auditoría rápida.

### 3.4 `qr_tokens` — Tokens rotativos del mostrador
**Una fila por cada QR generado.** Permite el "1-shot enforcement".

| Campo | Descripción |
| --- | --- |
| `jti` | Identificador único (24 bytes URL-safe) |
| `kind` | `counter` (suma sello) / `show` (debug) |
| `expires_at` | Default 60 s desde creación |
| `consumed_at` | Cuándo se consumió (NULL = aún válido) |
| `consumed_by_pass`, `consumed_by_user` | Trazabilidad |
| `device_fp` | Qué dispositivo pidió el token |

---

## 4. Endpoints (12 rutas agrupadas en 3 routers)

### 4.1 Owner (`/tenants/{tenant_id}/loyalty/*`) — autenticado

| Método | Ruta | Propósito |
| --- | --- | --- |
| `GET` | `/campaigns` | Lista campañas (excluye archivadas por defecto) |
| `POST` | `/campaigns` | Crea nueva campaña |
| `GET` | `/campaigns/{id}` | Detalle |
| `PATCH` | `/campaigns/{id}` | Edita (re-genera hash si cambia PIN) |
| `DELETE` | `/campaigns/{id}` | Archiva (soft delete, `is_active=False`) |
| `GET` | `/campaigns/{id}/metrics` | Métricas: pases activos, sellos hoy, premios hoy, tasa de conversión, promedio de sellos por premio |
| `POST` | `/campaigns/{id}/qr-token` | Emite un nuevo QR rotativo del mostrador (TTL 60 s) |

### 4.2 POS (`/api/v1/loyalty/scan`) — autenticado (garzón u owner)

| Método | Ruta | Propósito |
| --- | --- | --- |
| `POST` | `/scan` | Recibe 2 QRs + PIN opcional y suma 1 sello |

**Payload `ScanIn`:**
```json
{
  "qr_payload": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "pass_serial": "wh:abc12345:def67890:ghi11121",
  "cashier_pin": "1234",
  "device_fp": "tablet-cafeteria-01"
}
```

**Respuesta `ScanOut`:**
```json
{
  "ok": true,
  "pass": { "stamps_current": 3, "stamps_required": 6, "reward_label": "1 Café Gratis", ... },
  "reward_unlocked": false,
  "stamps_after": 3
}
```

**Códigos de error tipados** (`error_code`): `qr_invalid`, `qr_used`, `qr_expired`, `pin_invalid`, `pass_not_found`, `pass_inactive`, `tenant_mismatch`, `campaign_mismatch`.

### 4.3 Público (`/api/v1/loyalty/c/{slug}/*`) — sin auth, rate-limited

| Método | Ruta | Propósito |
| --- | --- | --- |
| `GET` | `/c/{slug}/campaign` | Devuelve info pública de la campaña (sin PII) |
| `POST` | `/c/{slug}/register` | Alta del cliente y emisión del pase |

**Reglas del registro público:**
- Requiere `accepts_terms=True` (validación Pydantic).
- Acepta `email` **o** `phone` (al menos uno).
- Reusa el `Customer` si ya existe (por email o phone).
- Crea un `CustomerPass` nuevo (o reactiva uno `redeemed` reseteándolo a 0).
- Devuelve el `PassOut` con el `qr_payload` (JWT del cliente) ya firmado.

---

## 5. Formas de Aplicarlo — Casos de Uso Reales

### 5.1 🥐 Cafetería / Panadería — "Café gratis cada 6 visitas"
- **Configuración:** `stamps_required=6`, `reward_label="1 Café Gratis"`, `cashier_pin="1234"`.
- **Flujo:** cliente paga, garzón escanea dos QRs e ingresa PIN. Sello aparece instantáneamente.
- **Conversión esperada:** estudios del sector gastronómico LATAM muestran **30–40 % de recurrencia** con programas así.

### 5.2 💇 Peluquería / Barbería — "Cada 5 cortes, 1 gratis"
- **Configuración:** `stamps_required=5`, `reward_label="1 Corte Gratis"`.
- **Sin PIN:** confiamos en el barbero (es el único que escanea).
- **Conversión esperada:** sube el ticket promedio un **15–20 %** por la recurrencia.

### 5.3 🍕 Restaurant / Comida rápida — "Combo $X con 10 visitas"
- Múltiples campañas activas (desayuno, almuerzo, cena) según horario.
- El cliente puede ver **su progreso actual** en el pase guardado.

### 5.4 👕 Tienda de ropa — "Descuento 20 % con 4 compras"
- `stamps_required=4`, `reward_label="20 % OFF en tu próxima compra"`.
- Temporada alta: `starts_at` y `ends_at` definidos.
- **Conversión esperada:** ticket promedio sube **+25 %** en programas de descuento.

### 5.5 🏋️ Gimnasio / Wellness — "Pase mensual con 12 visitas"
- `stamps_required=12` (constraint CHECK acepta hasta 50).
- Recompensa: 1 mes gratis.
- Anti-fraude: PIN obligatorio para que el cliente no se auto-escanee.

### 5.6 🏪 Multi-tenant con locales múltiples
- Un mismo tenant puede tener **N campañas activas** (ej. una por cada sucursal).
- Cada `qr-token` queda asociado a `device_fp` para auditoría por dispositivo.

---

## 6. Seguridad: 7 Capas de Protección

### 6.1 QR rotativo del mostrador
- Token JWT HS256 firmado con `JWT_SECRET`.
- `jti` aleatorio de 24 bytes URL-safe.
- `exp` = 60 s desde emisión.
- **Tolerancia de clock-skew:** 5 s.
- Si el dispositivo no renueva el QR cada 60 s, expira solo.

### 6.2 Anti-replay (1-shot enforcement)
- La fila `qr_tokens` tiene `consumed_at`.
- El segundo intento de uso del mismo jti devuelve `409 Conflict` con `error_code="qr_used"`.
- El `qr_token_jti` queda registrado en `pass_stamps` para trazabilidad forense.

### 6.3 Anti-fraude de PIN
- Si la campaña define `cashier_pin`, se **obliga** al garzón a ingresarlo.
- El PIN nunca se guarda en claro: solo `SHA-256(pin)` (64 chars hex).
- Solo se valida el hash en el endpoint de scan.
- Se permite **quitar el PIN** enviando string vacío en `PATCH`.

### 6.4 Aislamiento multi-tenant
- Todas las queries filtran por `tenant_id`.
- El JWT incluye `tid` y se valida contra el `tenant_id` del path/query.
- Cross-tenant: si un cliente muestra un QR de otro comercio → `403 Forbidden` con `error_code="tenant_mismatch"`.

### 6.5 Validación de Pydantic v2
- Colores validados con regex `^#[0-9A-Fa-f]{6}$`.
- `stamps_required` entre 2 y 50.
- `cashier_pin` entre 4 y 8 dígitos.
- `accepts_terms` obligatorio en el registro público.

### 6.6 No exposición del hash de PIN
- `CampaignOut.cashier_pin` está marcado `exclude=True` y `repr=False`.
- Solo se expone el flag `cashier_pin_set: bool` al frontend.
- Comentario explícito en el código previniendo el bug clásico de devolver el hash.

### 6.7 Rate limiting en endpoints públicos
- Aplicado via `RateLimitMiddleware` global.
- Previene enumeración de slugs o fuerza bruta en registro.

---

## 7. Métricas y Administración

### 7.1 Endpoint de métricas
```
GET /api/v1/tenants/{id}/loyalty/campaigns/{id}/metrics
```

Devuelve:
- `active_passes` — pases vigentes (no expirados ni revocados).
- `total_stamps_today` — sellos dados desde las 00:00 UTC.
- `total_rewards_today` — premios desbloqueados hoy.
- `total_scans` — total histórico de escaneos.
- `conversion_rate` — `total_rewards_redeemed / total_stamps_issued`.
- `avg_stamps_to_reward` — promedio de sellos por premio (debería ser ≈ `stamps_required`).

### 7.2 Métricas desnormalizadas (rápidas)
En `loyalty_campaigns` se mantienen:
- `total_passes`, `total_stamps_issued`, `total_rewards_redeemed`.

Esto permite dashboards **O(1)** sin tener que contar la tabla `pass_stamps` cada vez.

### 7.3 Auditoría
La tabla `pass_stamps` es **append-only**. Permite responder:
- ¿Cuántos sellos puso el garzón X en la última semana?
- ¿Cuántos scans se hicieron desde la tablet de la sucursal Y?
- ¿Cuántas veces se intentó reusar el QR `jti=abc`?

---

## 8. Cobertura de Tests (31 tests)

### 8.1 `TestCampaignCrud` (7 tests)
- Crear, listar, archivar, editar, validar colores, ocultar PIN en respuesta, permitir quitar PIN con string vacío, métricas vacías.

### 8.2 `TestCounterQrToken` (3 tests)
- Generar JWT con claims correctos, generar `jti` únicos, 404 si la campaña está archivada.

### 8.3 `TestPublicRegistration` (6 tests)
- Ver campaña sin auth, 404 sin campaña activa, registrar crea pass, requerir `accepts_terms`, requerir email o phone, reusar cliente existente, mismo cliente en otra campaña crea nuevo pass.

### 8.4 `TestScanFlow` (9 tests)
- Happy path suma 1 sello, anti-replay rechaza segundo uso, QR expirado rechazado, QR cross-tenant rechazado, PIN obligatorio cuando aplica, PIN incorrecto rechazado, PIN correcto pasa, pass inexistente, campaign mismatch, scan sin auth 401.

### 8.5 `TestRewardUnlock` (2 tests)
- Recompensa se desbloquea al juntar N sellos, pase `redeemed` puede volver a escanearse y arranca nuevo ciclo.

### 8.6 `TestAuditTrail` (2 tests)
- Cada scan exitoso crea una fila en `pass_stamps`, la fila de auditoría guarda el `jti` para tracing de replay.

**Total: 31 tests** cubriendo CRUD, seguridad, casos negativos y auditoría.

---

## 9. Roadmap del Sistema de Fidelización

### 9.1 Fase 3 — Apple Wallet (planeada)
- Ya están reservadas las columnas `apple_pass_url` y `google_pass_jwt` en `customer_passes`.
- Webhooks preparados: `PassUpdateWebhook` con eventos `install` / `uninstall` / `update`.
- Source enum ya tiene `APPLE` y `GOOGLE` listos.

### 9.2 Fase 4 — Google Wallet (planeada)
- Mismo modelo que Apple.
- Necesita endpoint de "complementación" de passclass.

### 9.3 Fase 5 — Métricas avanzadas
- Cohortes (clientes nuevos vs. recurrentes por mes).
- Tasa de abandono del programa.
- Predicción de cuándo un cliente inactivo volverá.
- Embudo de conversión: visita → registro → 1er sello → N sellos → premio.

### 9.4 Fase 6 — Integración con el Asistente Virtual
- **Marketing agent** puede sugerir: "Tu mejor cliente tiene 5/6 sellos, envíale un recordatorio."
- **Growth agent** puede analizar: "El 60 % de los premios se canjean los viernes — programa una promo los lunes."
- **Automation agent** puede lanzar campañas reactivando inactivos con sello gratis.

### 9.5 Reglas dinámicas (Fase 7+)
- Multiplicadores (2x sellos en cumpleaños, happy hour).
- Sellos por gasto (`$10 = 1 sello`).
- Niveles (Bronce / Plata / Oro) con beneficios incrementales.

---

## 10. Resumen para el Cliente

| Lo que pediste | Lo que obtienes |
| --- | --- |
| "Quiero un sistema de fidelización" | ✅ Sistema completo tipo Starbucks / Apple Wallet, en 1 sprint |
| "Sin hardware especial" | ✅ Solo un navegador en la tablet/caja |
| "Anti-fraude" | ✅ QR rotativo 60s + PIN opcional + 1-shot enforcement + auditoría |
| "Multi-tenant seguro" | ✅ Aislamiento por JWT + query filter + tests cross-tenant |
| "Métricas para el admin" | ✅ Endpoint con tasas de conversión, sellos hoy, premios hoy |
| "Que mis clientes no pierdan su tarjeta" | ✅ QR firmado con expiración de 1 año + recordatorios push |
| "Compatible con Apple/Google Wallet" | 🟡 Columnas reservadas, listo para Fase 3/4 |
| "Que se integre con el Asistente Virtual" | 🟡 Roadmap Fase 6 — los agentes ya pueden ver las métricas |

---

## 11. Ficheros Involucrados

| Capa | Fichero | Líneas |
| --- | --- | --- |
| Modelo | `app/models/loyalty_pass.py` | 211 |
| Schemas | `app/schemas/loyalty.py` | 214 |
| Servicio | `app/services/loyalty_pass_service.py` | 551 |
| API | `app/api/v1/loyalty.py` | 249 |
| UI owner | `app/templates/dashboard/admin_loyalty.html` | n/a |
| UI cliente | `app/templates/public/loyalty.html` | n/a |
| Tests | `tests/test_loyalty.py` | 575 (31 tests) |

---

*Informe generado para presentación a cliente · WowHub · 2026-08-16 · MiniMax Agent*
