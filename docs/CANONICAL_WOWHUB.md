# Documento Canónico de WowHub — Fuente de Verdad para el Asistente IA

> **Propósito:** Este documento es la **única fuente de verdad** que el asistente IA de WowHub debe usar para responder preguntas sobre la plataforma (módulos, rutas, activación, URLs, FAQ). Cualquier nueva sección de WowHub que se agregue al producto debe reflejarse aquí.
>
> **Mantenedor:** Equipo WowHub.
> **Última actualización:** 16 de agosto de 2026.
> **Versión:** v1.0 (alineado con Bookings Fase 2).

---

## 1. Regla de oro

**Ningún módulo de WowHub requiere activación por parte del usuario.** Todos están disponibles para cualquier tenant creado y activo. No existe un panel de "Configuración → Módulos" con interruptores. Si un cliente afirma haber visto algo así, es un error o una alucinación de la IA — corregir de inmediato.

---

## 2. Módulos del dashboard (panel del dueño)

Todos los módulos se acceden desde el menú lateral del dashboard (`/dashboard`). El dueño llega con sesión iniciada y el tenant resuelto en el topbar.

| Módulo | Ruta interna | Descripción corta | ¿Requiere activación? | Tool IA |
|---|---|---|---|---|
| **Resumen** | `/dashboard` | KPIs, ventas, productos top, agenda de hoy. | No | `get_stats_overview` |
| **Productos** | `/dashboard/products` | Catálogo, stock, precios, categorías, imágenes. | No | `list_products` |
| **Promociones** | `/dashboard/promotions` | Motor de descuentos, combos, campañas activas. | No | `list_promotions`, `create_promotion` |
| **Clientes** | `/dashboard/customers` | Base de clientes, tags, puntos de fidelización. | No | `list_customers` |
| **Pedidos / Ventas** | `/dashboard/orders` | Órdenes, estados, ticket promedio. | No | (vía stats) |
| **Reservas** | `/dashboard/bookings` | Agenda, KPIs, filtros, modal nueva reserva. | No | `list_bookings`, `create_booking`, `check_availability` |
| **Campañas** | `/dashboard/campaigns` | Segmentos y envíos de email masivo. | No | `send_campaign`, `get_customer_segments` |
| **Sucursales** | `/dashboard/branches` | Sedes, horarios (`hours` JSON), ubicación. | No | (vía tenant info) |
| **Fidelización** | `/dashboard/loyalty` | Programas de puntos y sellos. | No | (no expuesta aún) |
| **QR** | `/dashboard/qr` | Códigos QR para tienda física. | No | (no expuesta aún) |
| **Configuración** | `/dashboard/settings` | Datos del tenant, branding, integraciones, Mi cuenta. | No | `get_tenant_info` |
| **Admin IA** | `/admin/ai` | Métricas, logs, trazas, circuit breaker. (Solo OWNER/ADMIN) | No | (n/a, es la IA misma) |
| **SUPERADMIN** | `/admin/superadmin` | Panel de plataforma: KPIs globales, gestión de tiendas, usuarios, auditoría. (Solo `is_superuser=True`) | No | (n/a, panel de plataforma) |

> **Admin IA — guard de rol:** la página `/admin/ai` y los endpoints `/api/v1/admin/ai/*` están protegidos con guard server-side. Si el usuario no tiene rol `OWNER` o `ADMIN`:
> - Si no hay sesión → redirige a `/dashboard/login?reason=admin_auth`.
> - Si hay sesión pero el rol no alcanza → redirige a `/dashboard?reason=admin_forbidden`.
> - En el sidebar, el link "Admin IA" se muestra **solo** a OWNER/ADMIN (`data-requires-role="owner,admin"` + JS de guard).

> **SUPERADMIN — guard de plataforma:** la página `/admin/superadmin` y los endpoints `/api/v1/superadmin/*` están protegidos con guard server-side que requiere `is_superuser=True` a nivel de **USUARIO** (no de membresía).
> - Si no hay sesión → redirige a `/dashboard/login?reason=superadmin_auth`.
> - Si hay sesión pero el flag es False → redirige a `/dashboard?reason=superadmin_forbidden`.
> - En el sidebar, el link "SUPERADMIN" se muestra **solo** si `payload.is_superuser === true` (decodificando el JWT en el cliente) o `user.is_superuser === true`.
> - El claim `is_superuser` se incluye en el access token y el refresh token desde `auth_service.py`.
> - **Diferencia clave:** los roles de membresía (OWNER/ADMIN/STAFF/VIEWER) son **por tenant**; `is_superuser` es **por usuario** y aplica a TODA la plataforma.

---

## 3. URLs públicas (sin autenticación)

Estas son las URLs que el dueño comparte con sus clientes:

| Función | Patrón | Notas |
|---|---|---|
| Landing del negocio | `https://{dominio}/u/{slug}` | Página pública del tenant. `{slug}` es el identificador (ej. `barberia-juan`). |
| Catálogo público | `https://{dominio}/u/{slug}/catalogo` | Productos visibles sin login. |
| Reservar (cliente) | `https://{dominio}/u/{slug}/reservar` | Flujo público de reservas: branch → fecha/hora → datos. |
| Reservar (alias inglés) | `https://{dominio}/u/{slug}/book` | Alias equivalente a `/reservar`. |
| Cancelar reserva | (enlace del email con token opaco) | No hay URL "fija"; cada reserva genera un link único con `cancel_token`. |

> **Error común a corregir:** si la IA dice "la URL pública es `/book/{slug}`" o similar, está mal. El patrón correcto es `/u/{slug}/book` o `/u/{slug}/reservar`.

---

## 4. Auth y cuenta del usuario

| Acción | Ruta / Endpoint |
|---|---|
| Login | `POST /api/v1/auth/login` |
| Registro | `POST /api/v1/auth/register` |
| Refrescar token | `POST /api/v1/auth/refresh` |
| Cambiar contraseña | `POST /api/v1/auth/password` (desde Mi cuenta) |
| Mi cuenta | `/dashboard/settings` → sección "Mi cuenta" |
| Cerrar sesión | `POST /api/v1/auth/logout` (limpia JWT) |
| Recuperar contraseña | `POST /api/v1/auth/password/reset` (envía email con token) |

> **El usuario no puede "crear otro tenant" desde el chat de la IA** — esa acción la hace desde la landing o con un link de referido. La IA NO debe ofrecer botones para eso.

---

## 5. Resumen de endpoints IA (cómo la IA conversa con la plataforma)

Todas las tools de la IA están definidas en `app/services/ai_tools.py` y se invocan vía HTTP a la API interna con el JWT del usuario + `X-Tenant-Id`.

### 5.1 Tools de lectura

| Tool | Endpoint interno | Uso |
|---|---|---|
| `get_tenant_info` | `GET /tenants/{id}` | Nombre, slug, plan, branding. |
| `list_products` | `GET /tenants/{id}/products` | Catálogo, búsqueda por nombre, filtros por estado. |
| `list_promotions` | `GET /tenants/{id}/promotions` | Promos activas o todas. |
| `list_customers` | `GET /tenants/{id}/customers` | Base de clientes, búsqueda. |
| `list_bookings` | `GET /tenants/{id}/bookings` | Agenda del tenant. |
| `check_availability` | `POST /tenants/{id}/bookings/availability` | Slots libres para una fecha/sucursal. |
| `get_stats_overview` | `GET /tenants/{id}/stats/overview` | KPIs, top productos, ventas por día. |
| `analyze_inventory` | `GET /tenants/{id}/analytics/inventory` | `low_stock`, `out_of_stock`, `dead_stock`, `top_selling`, `overstock`. |
| `get_customer_segments` | `GET /tenants/{id}/analytics/customer-segments` | `inactive`, `vip`, `new`, `top`, `no_orders`. |
| `get_app_help` | (nuevo, lee de `app/services/app_knowledge.py`) | Devuelve este documento canónico en formato resumido. |

### 5.2 Tools de escritura (ejecutan acciones)

| Tool | Endpoint interno | Requiere confirmación |
|---|---|---|
| `create_promotion` | `POST /tenants/{id}/promotions` | **Sí** — preview antes de guardar. |
| `create_booking` | `POST /tenants/{id}/bookings` | **Sí** — confirmar cliente, fecha, hora, sucursal. |
| `send_email_to_customer` | `POST /customers/{id}/email` | **Sí** — mostrar asunto + cuerpo antes de enviar. |
| `send_campaign` | `POST /tenants/{id}/campaigns` | **Sí** — preview de audiencia + cantidad + muestra. |

> **Regla de seguridad innegociable:** ninguna tool de escritura se invoca sin que la IA muestre el **preview** y el usuario responda "sí" (o equivalente) de forma explícita. Esto ya está implementado en el system prompt de `AUTOMATION` y debe replicarse en cualquier agente que herede estas tools (incluido el nuevo `HELP`).

---

## 6. FAQ rápidas (overrides literales)

Estas son respuestas literales que la IA debe dar si el usuario pregunta exactamente esto. La prioridad es la fuente (`app_knowledge.py`), pero este glosario sirve de referencia:

| Pregunta del usuario | Respuesta correcta |
|---|---|
| "¿Cómo activo Reservas?" | "Reservas no requiere activación. Está disponible para todos los tenants. Ve directo a `/dashboard/bookings` desde el menú lateral." |
| "¿Qué módulos hay?" | Lista de los 12 módulos de la sección 2. |
| "¿Dónde cambio mi contraseña?" | "Ve a **Configuración → Mi cuenta** o usa el botón 'Cambiar contraseña' en tu perfil." |
| "¿Dónde veo mis ventas?" | "En el menú lateral, **Resumen**, o directo en `/dashboard`." |
| "¿Cómo creo una promoción?" | "Puedo crearla por ti. Dime: nombre, descuento (% o monto), fechas. Te muestro el preview antes de guardar." |
| "¿Cómo creo una reserva?" | "Puedo agendarla. Necesito: cliente, sucursal, fecha, hora, duración. Te muestro el preview antes de guardar." |
| "¿URL pública para que mis clientes agenden?" | "`https://{tu-dominio}/u/{tu-slug}/reservar` — compártela en Instagram, WhatsApp o tu bio." |
| "No me deja entrar a X módulo" | "Verifica que tu sesión esté iniciada y que el chip de usuario del topbar muestre el tenant correcto. Si persiste, contáctanos." |
| "¿Cómo cambio el idioma?" | "Por ahora WowHub está en español. La función multi-idioma está en roadmap." |
| "¿Cómo cambio el logo de mi tienda?" | "**Configuración → Branding** (subir imagen, máximo 2 MB)." |
| "¿Cuánto cuesta WowHub?" | "Depende del plan. Revisa la sección de **Planes** en la landing o pregúntale al equipo de ventas." |
| "Quiero eliminar mi cuenta" | "Por seguridad, la eliminación de cuenta se hace escribiendo a **soporte@wowhub.app**." |
| "¿Cómo conecto WhatsApp?" | "En **Configuración → Integraciones** (cuando esté disponible). Hoy puedes compartir el link público por WhatsApp manualmente." |

---

## 7. Cosas que NO existen (anti-alucinación)

Si la IA no está segura, debe decir **"no tengo esa información"** antes que inventar. Esta es la lista negra explícita:

- ❌ No existe "Configuración → Módulos" ni "Activación de funciones".
- ❌ No existe un toggle "Activar/Desactivar Reservas" o "Activar/Desactivar Promociones".
- ❌ No hay que "contactar a soporte" para habilitar algo.
- ❌ No hay "espera 24-48 horas para la activación".
- ❌ No hay un "Asistente Premium" o "Modo Pro" para la IA (es la misma para todos).
- ❌ No hay un "Marketplace de integraciones" todavía (WhatsApp, Stripe, etc. están en roadmap).
- ❌ No hay "Exportar a Excel" nativo por ahora (solo CSV desde el panel).
- ❌ No hay "Cambiar de plan" desde el chat (se hace en la landing).
- ❌ No hay "Multi-idioma" todavía.
- ❌ No hay "Borrar tenant" desde el chat.

---

## 8. Cómo usar este documento en el sistema

1. **Carga en runtime:** `app/services/app_knowledge.py` contiene la versión **estructurada** de este documento (módulos, rutas, URLs, FAQ, no_existe) lista para que la tool `get_app_help` la lea.
2. **System prompt base:** la versión resumida (top 10 preguntas + lista negra) se inyecta en `_GLOBAL_RULES` para que TODOS los sub-agentes (marketing, growth, automation, marketplace, **help**) tengan los hechos verídicos en su prompt.
3. **Tests de regresión:** cada vez que se agregue un módulo, se agrega una entrada en §2, una URL en §3 si aplica, una pregunta en §6 y un test en `tests/ai/test_help_routes.py`.

---

## 9. Cambio de agente (handoff) entre módulos

Cuando el usuario hace una pregunta de **plataforma** (este documento) y luego pide **ejecutar una acción** (ej. "perfecto, entonces créame la reserva"), el flujo es:

1. El agente `HELP` detecta la intención de acción.
2. Prepara el **preview** (qué va a hacer, con qué datos, a quién afecta).
3. Pregunta: **"¿Confirmas que ejecute esto?"**
4. Si el usuario responde **"sí"**, el orquestador cambia a `AUTOMATION` (que ya tiene los prompts de seguridad, confirmación y envío).
5. `AUTOMATION` ejecuta la tool correspondiente y devuelve la confirmación final.

Este handoff queda implementado en `app/services/ai_orchestrator.py` con la regla: **HELP solo sugiere, AUTOMATION ejecuta**.

---

## 10. Versiones

- v1.0 (16-ago-2026): documento inicial alineado con Bookings Fase 2, 12 módulos en panel, 4 tools de lectura + 4 de escritura + 1 de ayuda.
- v1.1 (16-ago-2026): corregida ruta real de Admin IA (`/admin/ai`, antes erróneamente `/dashboard/admin/ai`). Agregada nota sobre guard de rol server-side.
- **v1.2 (16-ago-2026)**: agregado módulo **SUPERADMIN** (panel de plataforma). 13 módulos en panel. Nuevo guard `require_superuser`. Nuevo claim `is_superuser` en JWT. Nueva ruta `/admin/superadmin` y endpoints `/api/v1/superadmin/*`. Script CLI `python -m scripts.promote_superuser --email ... --grant`.
- Próxima: cuando se agregue el módulo de Fidelización a tools IA.

---

## 11. SUPERADMIN (panel de plataforma)

### 11.1 Concepto

`is_superuser` es un **flag a nivel de USUARIO** (no de membresía). Un superuser:
- Ve y modifica **todos los tenants** de la plataforma.
- Ve y modifica **todos los usuarios** (incluido promover/revocar otros superusers).
- Accede a la **auditoría global**.
- Tiene acceso a la página `/admin/superadmin` y a los endpoints `/api/v1/superadmin/*`.

A diferencia de los roles de membresía (OWNER/ADMIN/STAFF/VIEWER), un superuser **no necesita membresía** en un tenant para actuar sobre él. Su autoridad es transversal.

### 11.2 Endpoints MVP (Fase 1)

| Método | Endpoint | Función |
|---|---|---|
| GET | `/api/v1/superadmin/stats` | KPIs globales: tenants (total/activos/trial/suspended), usuarios, superusers, growth 7d/30d. |
| GET | `/api/v1/superadmin/tenants?q=&status=&plan=&limit=&offset=` | Listar todos los tenants con filtros. |
| GET | `/api/v1/superadmin/tenants/{tenant_id}` | Detalle de un tenant (incluye `members_count`). |
| PATCH | `/api/v1/superadmin/tenants/{tenant_id}` | Actualizar `plan`, `status`, `is_active`, `display_name`. |
| GET | `/api/v1/superadmin/users?q=&is_active=&is_superuser=&limit=&offset=` | Listar todos los usuarios. |
| GET | `/api/v1/superadmin/users/{user_id}` | Detalle de un usuario (incluye `tenants[]`). |
| PATCH | `/api/v1/superadmin/users/{user_id}` | Actualizar `is_active`, `full_name`, `default_role`. |
| POST | `/api/v1/superadmin/users/{user_id}/superuser` | Promover o revocar `is_superuser`. Regla: no se puede revocar al único superuser activo. |
| GET | `/api/v1/superadmin/audit?action_prefix=&actor_user_id=&page=&page_size=` | Logs de auditoría cross-tenant. |

### 11.3 UI: `/admin/superadmin`

Una sola página con 3 pestañas:
- **Tiendas**: tabla con búsqueda + filtros por `status` y `plan`. Acciones: Editar (modal con plan/status/activo/display name) y Suspender/Activar.
- **Usuarios**: tabla con búsqueda + filtro activo/superuser. Acciones: Promover/Revocar SUPER (con modal de confirmación) y Activar/Desactivar.
- **Auditoría**: tabla con filtro por prefijo de action. Read-only.

KPIs globales arriba: tenants totales, activos, trial, suspended, usuarios, superusers, nuevos 7d.

### 11.4 Bootstrap

Para promover al **primer superuser** (operación one-time, sin endpoint público por seguridad):

```bash
python -m scripts.promote_superuser --email admin@wowhub.app --grant
python -m scripts.promote_superuser --list
python -m scripts.promote_superuser --email admin@wowhub.app --revoke
```

Una vez que hay al menos un superuser, el resto se promueve desde la UI (pestaña Usuarios).

### 11.5 Funcionalidades futuras (Fase 2 — NO implementadas aún)

Listadas en `user_input_files/pasted-text-2026-08-16T02-29-33.txt` y priorizadas:

| Función | Estado | Notas |
|---|---|---|
| Planes y facturación (CRUD planes, asignar, cupones) | Pendiente | Requiere extender `TenantPlan` enum y agregar tabla `subscriptions` + `coupons`. |
| Configuración global (moneda, timezone, idioma default) | Pendiente | Requiere tabla `platform_settings`. |
| Branding global (logo, colores, T&C) | Pendiente | Requiere tabla `platform_brand`. |
| Notificaciones globales (plantillas email/SMS/push) | Pendiente | Requiere `notification_templates` + integración SendGrid. |
| Soporte y tickets | Pendiente | Requiere módulo de tickets. |
| API keys (rotar, revocar) | Pendiente | Requiere tabla `api_keys`. |
| Modo mantenimiento | Pendiente | Requiere flag global + middleware. |
| Gestión de dominios personalizados | Pendiente | Requiere módulo de dominios. |
| Incidencias | Pendiente | Requiere tabla `incidents`. |
| Exportar reportes (CSV/PDF) | Pendiente | Pendiente en general, no solo SUPERADMIN. |

### 11.6 Anti-alucinación específica de SUPERADMIN

- ❌ **No** existe un panel "Configuración → Mi cuenta → Rol" donde un usuario se auto-promueva a superuser.
- ❌ **No** hay un "Registro como superuser" — el flag solo se otorga manualmente (script CLI o desde la UI por otro superuser).
- ❌ El superuser **no** es un plan ni un add-on de pago.
- ❌ El superuser **no** puede ver contraseñas en claro de otros usuarios.
- ❌ El superuser **no** puede impersonar sesiones de otros usuarios (todavía).
