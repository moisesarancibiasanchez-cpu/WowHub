# Documento Canónico de WowHub — Fuente de Verdad para el Asistente IA

> **Propósito:** Este documento es la **única fuente de verdad** que el asistente IA de WowHub debe usar para responder preguntas sobre la plataforma (módulos, rutas, activación, URLs, FAQ). Cualquier nueva sección de WowHub que se agregue al producto debe reflejarse aquí.
>
> **Mantenedor:** Equipo WowHub.
> **Última actualización:** 16 de agosto de 2026.
> **Versión:** v1.4 (documentado modelo de roles y membresías).

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
| "¿Qué diferencia hay entre OWNER, ADMIN, STAFF y VIEWER?" | "Son los 4 roles por membresía en un tenant. **OWNER**: administración completa del tenant (todo). **ADMIN**: administración operativa con casi los mismos poderes que OWNER — puede gestionar productos, reservas, clientes, campañas, miembros y configuración, pero no puede eliminar el tenant ni modificar el OWNER. **STAFF**: operación diaria con acceso limitado (ej. crear reservas, registrar ventas, ver clientes, pero no modificar configuración ni productos). **VIEWER**: solo consulta (lee KPIs, listas, agenda) sin poder ejecutar acciones de escritura. Los roles son **por tenant** — un mismo usuario puede ser OWNER en un tenant y VIEWER en otro. El **SUPERUSER** es otra cosa: es un flag **por usuario** (no por tenant) y aplica a TODA la plataforma; ver §11." |
| "El superadmin entró a mi tienda, ¿puede ver mis conversaciones del asistente?" | "Sí. Cuando un superuser usa 'Entrar como admin', obtiene la sesión completa del dueño, incluyendo todas sus conversaciones del asistente virtual. Esto es una función administrativa, no es un acceso oculto. Toda entrada y salida queda registrada en la auditoría." |
| "¿Cómo salgo si el superadmin entró a mi tienda?" | "El superadmin siempre usa el botón '🚪 Salir' del banner de impersonación; vos como dueño no notás nada en tu sesión normal." |

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
- ❌ **No** existe un botón "Login As" o "Entrar como admin" visible para usuarios normales; la función de impersonación es exclusiva del superuser y solo se muestra dentro de `/admin/superadmin`.

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
- **v1.3 (16-ago-2026)**: habilitada **impersonación de superuser** ("Login As" / "Entrar como admin"). Nuevos endpoints `POST /api/v1/superadmin/users/{id}/impersonate`, `POST /api/v1/superadmin/users/{id}/impersonate-tenant/{slug}`, `POST /api/v1/superadmin/impersonate/stop` y `GET /api/v1/superadmin/tenants/{id}/owner`. Claim JWT `imp={uid, tid, exp}`. Banner persistente de impersonación en `base.html`. Bug fix: limpiado `user`/`current_tenant` stale del localStorage en `confirmImpersonate` y `doStop` para resolver el "Cargando..." infinito. **Actualizado §11 y §7**: ya NO es cierto que el superuser no pueda impersonar; ahora sí puede y la IA debe reconocerlo.
- **v1.4 (16-ago-2026)**: documentado **modelo de roles y membresías**. Nueva §13 con la jerarquía completa OWNER/ADMIN/STAFF/VIEWER/SUPERUSER, sus permisos actuales vs. aspiracionales, la diferencia entre roles-por-tenant y flag-por-usuario, y cómo la IA debe responder preguntas sobre permisos. Nueva entrada en §6 FAQ: "¿Qué diferencia hay entre OWNER, ADMIN, STAFF y VIEWER?".
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
| GET | `/api/v1/superadmin/tenants/{tenant_id}/owner` | Devuelve el owner (o miembro primario activo) del tenant. Usado por el botón "Entrar como admin" en la tab Tiendas. |
| PATCH | `/api/v1/superadmin/tenants/{tenant_id}` | Actualizar `plan`, `status`, `is_active`, `display_name`. |
| GET | `/api/v1/superadmin/users?q=&is_active=&is_superuser=&limit=&offset=` | Listar todos los usuarios. |
| GET | `/api/v1/superadmin/users/{user_id}` | Detalle de un usuario (incluye `tenants[]`). |
| PATCH | `/api/v1/superadmin/users/{user_id}` | Actualizar `is_active`, `full_name`, `default_role`. |
| POST | `/api/v1/superadmin/users/{user_id}/superuser` | Promover o revocar `is_superuser`. Regla: no se puede revocar al único superuser activo. |
| POST | `/api/v1/superadmin/users/{user_id}/impersonate` | Inicia sesión como el usuario objetivo (sin tenant). Devuelve access_token con claim `imp={uid, tid, exp}`. |
| POST | `/api/v1/superadmin/users/{user_id}/impersonate-tenant/{slug}` | Inicia sesión como el usuario objetivo dentro de un tenant específico. |
| POST | `/api/v1/superadmin/impersonate/stop` | Termina la impersonación y devuelve un nuevo access_token con la sesión del superuser original. |
| GET | `/api/v1/superadmin/audit?action_prefix=&actor_user_id=&page=&page_size=` | Logs de auditoría cross-tenant. |

### 11.3 UI: `/admin/superadmin`

Una sola página con 3 pestañas:
- **Tiendas**: tabla con búsqueda + filtros por `status` y `plan`. Acciones: **🛡️ Entrar como admin** (detecta automáticamente al owner vía `/tenants/{id}/owner` y abre el modal de impersonación directo), Editar (modal con plan/status/activo/display name) y Suspender/Activar.
- **Usuarios**: tabla con búsqueda + filtro activo/superuser. Acciones: **🛡️ Login As** (modal de impersonación con campo de tenant opcional), Promover/Revocar SUPER (con modal de confirmación) y Activar/Desactivar.
- **Auditoría**: tabla con filtro por prefijo de action. Read-only.

KPIs globales arriba: tenants totales, activos, trial, suspended, usuarios, superusers, nuevos 7d.

Durante una sesión de impersonación, la página muestra un **banner persistente** en la parte superior con: nombre del superuser, nombre del usuario impersonado, tenant activo, y botón "🚪 Salir" que llama a `/api/v1/superadmin/impersonate/stop`.

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
- ❌ Un usuario regular **no** puede iniciar una sesión de impersonación — solo un superuser activo y desde `/admin/superadmin`.
- ❌ La impersonación **no** persiste al refrescar el token; está atada al `access_token` actual con el claim `imp` y un `exp` corto. Al refrescar, el claim se descarta.
- ❌ Un superuser **no** puede impersonar a otro superuser (devuelve 403).

### 11.7 Mecánica técnica de la impersonación (Login As)

- **JWT con claim `imp`:** el access_token emitido por los endpoints de impersonación incluye un objeto `imp = { uid: <target_user_id>, tid: <target_tenant_id or null>, exp: <epoch_unix_max> }` además de los claims estándar (`sub` sigue siendo el superuser original).
- **Resolución server-side (`app/deps.py → _resolve_impersonation`):** después de validar el JWT, si existe `imp` y su `exp` no expiró, el `get_current_user` retorna el **usuario target** en lugar del sub del JWT. `get_current_membership` busca por `imp.tid` y `user.id` (target), no por el sub.
- **Manejo de cookies + localStorage:** la sesión de impersonación emite cookies httpOnly (`wh_session`) Y expone el token en el body para que el frontend lo guarde en `WH.TokenStore` bajo `wowhub.tokens`. El frontend limpia los campos stale `user` y `current_tenant` antes de redirigir a `/dashboard` para forzar rehidratación desde `/api/v1/auth/me/session`.
- **Banner persistente (`base.html`):** un fragmento JS detecta el claim `imp` en el JWT, pinta un banner con datos del superuser/target/tenant y expone el botón "🚪 Salir".
- **Salir (`doStop`):** `POST /api/v1/superadmin/impersonate/stop` retorna un nuevo access_token **sin** el claim `imp` y limpia cookies/TokenStore. El frontend borra `user`/`current_tenant` stale para que la siguiente página se rehidrate con la sesión del superuser.
- **Auditoría:** cada `impersonate` y `impersonate/stop` registra un evento en `AuditLog` con `actor_user_id` (superuser), `target_user_id` (impersonado) y `action` ∈ {`superadmin.impersonate.start`, `superadmin.impersonate.stop`}.
- **Restricciones de seguridad:**
  - El target **no** puede ser un superuser (devuelve 403).
  - El target debe estar `is_active=True` (devuelve 403 si no).
  - El superuser **debe** conservar al menos un refresh token válido para poder salir de la impersonación.
  - El claim `imp.exp` es ≤ 60 minutos; la sesión se autolimpia pasada esa ventana incluso si el superuser no hace "Salir".

---

## 12. Impersonación desde la perspectiva del dueño y del superuser

### 12.1 Qué es

La **impersonación** (también llamada "Login As" o "Entrar como admin") es una función exclusiva del superuser que le permite iniciar sesión **como si fuera el dueño o admin de cualquier tienda**, sin pedirle la contraseña. El objetivo es soporte, debugging y auditoría en nombre del cliente.

### 12.2 Flujo del superuser (en `/admin/superadmin`)

1. **Tab Tiendas** → click en **🛡️ Entrar como admin** en la fila de la tienda. El sistema llama automáticamente a `GET /api/v1/superadmin/tenants/{id}/owner` para detectar al owner. Se abre el modal de impersonación con los datos del owner ya cargados.
2. **Tab Usuarios** → click en **🛡️ Login As** sobre cualquier usuario no-superuser y no-inactivo. Se abre el modal de impersonación con un campo opcional para elegir tenant.
3. El modal muestra: nombre, email, rol y tenant (si aplica). El superuser confirma y es redirigido a `/dashboard` ya con la sesión del target.
4. Un **banner rojo persistente** en la parte superior indica: `🛡️ IMPERSONACIÓN ACTIVA — Entrando como {nombre_target} en {tenant}`.
5. El superuser navega libremente: ve el dashboard, productos, reservas, clientes, **y todas las conversaciones del asistente virtual** del usuario impersonado.
6. Cuando termina, click en **🚪 Salir** del banner → vuelve a su sesión de superuser.

### 12.3 Qué ve y qué puede hacer el superuser durante la impersonación

- **Ve:** toda la data del tenant (productos, pedidos, clientes, reservas, campañas, configuración, **conversaciones del asistente IA del usuario target**).
- **Puede hacer:** todo lo que el usuario target puede hacer según su rol de membresía en ese tenant (OWNER puede todo; ADMIN no puede borrar el tenant; STAFF/VIEWER están restringidos por su rol).
- **No ve:** otros tenants del target (la sesión está limitada al `imp.tid` actual).
- **No puede:** cambiar la contraseña del target, promoverlo a superuser, ni impersonar a otro superuser.

### 12.4 Restricciones y auditoría

- Toda sesión de impersonación queda registrada en `AuditLog` con `action ∈ {superadmin.impersonate.start, superadmin.impersonate.stop}`, incluyendo `actor_user_id` (superuser), `target_user_id` (impersonado), `tenant_id` y timestamp.
- El banner es **obligatorio** en todas las páginas renderizadas con `base.html`; no se puede ocultar con CSS porque el frontend renderiza el banner desde JS contra el claim `imp` del JWT.
- El dueño del tenant, al iniciar sesión normalmente, **no ve el banner** porque su JWT no contiene el claim `imp`. Su sesión no se ve afectada.
- Si el dueño del tenant quiere saber si fue impersonado, puede pedir a soporte el reporte de auditoría filtrado por su `tenant_id`.

### 12.5 Bug conocido y resolución (histórico)

- **v1.3-fix:** durante un breve período en v1.3, después de una impersonación exitosa el dashboard quedaba en "Cargando..." infinito. La causa fue que `Auth.ensureSession()` retornaba una sesión cacheada desde localStorage con `user` y `current_tenant` stale del superuser, sin rehidratar desde el backend. **Solución:** `confirmImpersonate()` y `doStop()` ahora limpian los campos stale (`user`, `current_tenant`) y resetean `_sessionPromise` antes de redirigir, forzando una rehidratación limpia desde `/api/v1/auth/me/session`.

---

## 13. Modelo de roles y membresías

### 13.1 Concepto clave: dos ejes de permisos

WowHub maneja permisos en **dos dimensiones independientes** que la IA debe entender para no confundirlas:

1. **Roles por membresía (per-tenant):** OWNER, ADMIN, STAFF, VIEWER. Definen qué puede hacer un usuario **dentro de un tenant específico**. Un usuario puede tener un rol distinto en cada tenant del que es miembro.
2. **Flag de plataforma (per-usuario):** `is_superuser`. Define si un usuario tiene autoridad **transversal sobre toda la plataforma**. Es único por usuario, no por tenant.

Un usuario puede ser `OWNER` en el tenant A y, al mismo tiempo, `VIEWER` en el tenant B, y **además** ser `is_superuser=True`. Esos tres conceptos son ortogonales.

### 13.2 Tabla canónica de roles

| Rol | Scope | Alcance general | Quién lo asigna | Notas |
|---|---|---|---|---|
| **OWNER** | Por membresía (1 por tenant como mínimo) | **Administración completa del tenant.** Puede todo: crear/editar/borrar productos, reservas, clientes, campañas, sucursales, miembros, configuración, branding, integraciones, y facturación del tenant. Es el único que puede transferir la propiedad del tenant. | Se asigna automáticamente al crear el tenant (el usuario que lo crea queda como OWNER). Otro OWNER puede asignar un nuevo OWNER. | Cada tenant tiene **al menos 1 OWNER**. No se puede dejar un tenant sin OWNER. |
| **ADMIN** | Por membresía (0..N por tenant) | **Administración operativa.** Puede gestionar productos, reservas, clientes, campañas, sucursales, miembros (excepto OWNER) y configuración. **Hoy** en el código tiene poderes casi idénticos a OWNER — la diferencia práctica es que no puede eliminar el tenant ni modificar al OWNER. La descripción "según permisos configurados" es **aspiracional** (planeamos permisos granulares por ADMIN en el roadmap). | OWNER o cualquier ADMIN existente. | La IA NO debe prometer permisos granulares finos al usuario — eso aún no está implementado. Si la pregunta es sobre algo específico que un ADMIN puede o no puede hacer, responder con la regla práctica actual. |
| **STAFF** | Por membresía (0..N por tenant) | **Operación diaria con acceso limitado.** Pensado para empleados operativos: recepcionistas, vendedores, barberos, etc. Hoy puede crear reservas, registrar ventas, ver/actualizar clientes, ver productos y agenda. No debería modificar configuración general ni borrar productos. | OWNER o ADMIN. | Los permisos finos exactos de STAFF están en evolución. Si la IA no está 100% segura de una acción específica, decir "consulta con tu OWNER" en lugar de inventar. |
| **VIEWER** | Por membresía (0..N por tenant) | **Consulta de información sin acciones críticas.** Solo lectura: KPIs del dashboard, listas (productos, clientes, reservas, campañas), reportes. No puede crear, editar ni borrar nada. | OWNER o ADMIN. | Útil para auditores, socios pasivos, contadores externos, o el dueño revisando desde otro dispositivo sin riesgo de modificar algo por error. |
| **SUPERUSER** | Flag por usuario (cross-tenant) | **Administración global de la plataforma.** Ve y modifica todos los tenants y todos los usuarios. Accede a `/admin/superadmin` y a los endpoints `/api/v1/superadmin/*`. Puede impersonar a cualquier usuario no-superuser. | Solo otro SUPERUSER desde la UI, o el script CLI `python -m scripts.promote_superuser --email ... --grant` para el bootstrap inicial. | **No es un rol de tenant.** Un SUPERUSER que no es miembro de un tenant no tiene membresía ahí — pero su autoridad cross-tenant le permite ver/actuar igual. Ver §11. |

### 13.3 Diferencia entre ADMIN y OWNER (lo que la IA debe decir)

Esta es una de las preguntas más frecuentes. La respuesta corta y correcta es:

- **OWNER** es el "dueño" del tenant. Hay uno por tenant (como mínimo) y no se puede eliminar el tenant sin su acción.
- **ADMIN** es un "gerente" con poderes operativos similares. Puede hacer casi todo lo que hace un OWNER en el día a día (gestionar productos, ver reportes, modificar miembros que no sean OWNER, etc.), pero la cuenta del tenant sigue siendo del OWNER.

En la práctica actual, **la diferencia es más legal/administrativa que técnica**: si todos los OWNERs abandonan el tenant, los ADMINs no pueden recuperar la propiedad automáticamente. Si se necesita una separación dura de permisos, lo correcto hoy es crear un tenant separado.

### 13.4 Jerarquía de visibilidad (qué ve cada rol en la UI)

- **OWNER** y **ADMIN** ven el menú lateral completo (12 módulos de §2), incluido "Admin IA".
- **STAFF** ve el menú con los módulos operativos (Resumen, Productos, Pedidos/Ventas, Reservas, Clientes, Campañas) y **no** ve Configuración, Admin IA ni SUPERADMIN.
- **VIEWER** ve un menú reducido de solo lectura: Resumen, Productos, Clientes, Reservas, Campañas, Sucursales, Fidelización. **No** ve Configuración, Admin IA ni SUPERADMIN.
- **SUPERUSER** (adicional a su rol de tenant) ve el link "SUPERADMIN" en el sidebar.

> **Guard server-side:** los endpoints sensibles (`/api/v1/admin/ai/*`, `/api/v1/superadmin/*`, y las acciones destructivas de tenant) están protegidos con `Depends(require_role("OWNER", "ADMIN"))` o `Depends(require_superuser)`. Si un STAFF/VIEWER intenta llamar al endpoint por URL directa, recibe 403. La UI oculta los links, pero el server siempre re-valida.

### 13.5 Quién puede agregar miembros

| Acción | OWNER | ADMIN | STAFF | VIEWER | SUPERUSER |
|---|---|---|---|---|---|
| Agregar miembro a su tenant | ✅ | ✅ | ❌ | ❌ | ✅ (vía panel superadmin) |
| Cambiar rol de un miembro | ✅ | ✅ (excepto OWNER) | ❌ | ❌ | ✅ |
| Eliminar miembro | ✅ | ✅ (excepto OWNER) | ❌ | ❌ | ✅ |
| Transferir propiedad (cambiar OWNER) | ✅ | ❌ | ❌ | ❌ | ✅ |
| Promover a SUPERUSER | ❌ | ❌ | ❌ | ❌ | ✅ (solo desde `/admin/superadmin` o CLI) |

### 13.6 Anti-alucinación específica del modelo de roles

- ❌ No existe un rol "MANAGER" o "EDITOR" o "ANALYST" — solo los 4 (OWNER/ADMIN/STAFF/VIEWER) por tenant + SUPERUSER por plataforma.
- ❌ No existe un "rol personalizado" configurable por el usuario. La personalización de permisos finos está en roadmap.
- ❌ No existe "rol de facturación" separado — la facturación del tenant la ve y gestiona el OWNER.
- ❌ Un usuario NO puede auto-asignarse un rol; lo hace el OWNER, un ADMIN, o un SUPERUSER.
- ❌ Un usuario NO puede tener un rol en un tenant del cual NO es miembro. Primero hay que agregarlo como miembro.
- ❌ El flag `is_superuser` NO se "gana" por uso, antigüedad, pago de plan ni referidos. Se otorga manualmente.
- ❌ Un SUPERUSER NO es automáticamente OWNER de todos los tenants. Puede actuar sobre ellos por autoridad transversal, pero no es miembro hasta que alguien lo agregue (lo cual no es necesario para sus funciones de plataforma).

### 13.7 Cómo debe responder la IA a preguntas sobre roles

Cuando un usuario pregunte "¿qué diferencia hay entre X e Y?" o "¿puedo hacer Z con mi rol?", la IA debe:

1. Identificar el rol del usuario actual desde el JWT (`payload.role` o `membership.role` en `/me/session`).
2. Responder con la tabla de §13.2 como base.
3. Si la pregunta es ambigua o sobre una acción específica no documentada, **decir "no tengo esa información exacta; consulta con tu OWNER o con soporte"** en lugar de inventar.
4. **Nunca** prometer permisos que la tabla no garantiza. Si el usuario dice "soy ADMIN y quiero borrar el tenant", la respuesta correcta es "los ADMIN no pueden eliminar el tenant; esa acción la realiza el OWNER o el equipo de WowHub".
5. Si el usuario pide ascender a SUPERUSER, remitir a §11.4 (bootstrap CLI o pedir a otro SUPERUSER).
