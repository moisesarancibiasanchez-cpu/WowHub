# Documento Canónico de WowHub — Fuente de Verdad para el Asistente IA

> **Propósito:** Este documento es la **única fuente de verdad** que el asistente IA de WowHub debe usar para responder preguntas sobre la plataforma (módulos, rutas, activación, URLs, FAQ). Cualquier nueva sección de WowHub que se agregue al producto debe reflejarse aquí.
>
> **Mantenedor:** Equipo WowHub.
> **Última actualización:** 20 de agosto de 2026.
> **Versión:** v1.9.1-r4 (micro-release correctiva sobre v1.9.1-r3: el OpenAPI de PRODUCCIÓN — `https://wowhub-api-production.up.railway.app/openapi.json` — es ahora la única fuente de verdad canónica, NO `app/main.py` (código de desarrollo) ni `wowhub.app` (dominio que no responde en DNS). Sincroniza §2, §3, §22.1 y §22.4 con la realidad desplegada. Cambia solo documentación + sistema anti-alucinación de la IA — sin cambios de schema ni de endpoints).
> v1.9.1-r2 (nueva regla "URL absolutas, paths desnudos prohibidos" + system-prompt reinforcement + post-procesador `_scrub_slug_placeholders` que reemplaza `{slug}` por el slug real del tenant).
> v1.9.1 (micro-release sobre v1.9: nueva tool `get_tenant_dashboard_urls` que devuelve los links del panel con URL absoluta clickeable. Cambia solo UX — sin cambios de schema ni de endpoints).
> v1.9 (nuevo módulo **Automation Manager** `POST /api/v1/automation/preview` y `POST /api/v1/automation/execute`: orquesta las `recommended_actions` que devuelve el Growth Coach — `create_promotion`, `create_booking`, `send_campaign` — con preview obligatorio, audit log persistente y rate limit propio).

---

## 1. Regla de oro

**Ningún módulo de WowHub requiere activación por parte del usuario.** Todos están disponibles para cualquier tenant creado y activo. No existe un panel de "Configuración → Módulos" con interruptores. Si un cliente afirma haber visto algo así, es un error o una alucinación de la IA — corregir de inmediato.

---

## 2. Features del producto (lo que WowHub ofrece HOY en producción)

> **v1.9.1-r4 — IMPORTANTE:** El OpenAPI de PRODUCCIÓN (`https://wowhub-api-production.up.railway.app/openapi.json`) describe **4 features del MVP** visibles al cliente final: **Página, Catálogo, QR y Promociones**. Las otras secciones del OpenAPI (`auth`, `tenants`, `members`, `branches`, `categories`, `products`, `customers`, `promotions`, `qrs`, `landing-config`) son **endpoints ADMIN / CRM autenticados con JWT**, NO features que el cliente final usa.
>
> En producción **NO existe un panel HTML público** con rutas `/dashboard/*` o `/admin/*` como vistas HTML. Esas rutas están en `app/main.py` (código de desarrollo) pero **NO están desplegadas** en Railway. Por eso:
>
> 1. La IA NO debe entregar links `/dashboard/...` como URLs públicas. Esos links NO existen para clientes externos.
> 2. La tool `get_tenant_dashboard_urls` está DEPRECADA en v1.9.1-r4.
> 3. La única tool de URLs vigente es `get_tenant_public_urls` (ver §3).
> 4. Si el usuario pide "el link de su panel", la IA debe explicarle que WowHub es una API y que la gestión la hace él desde su sesión autenticada.

### 2.1 Features visibles al cliente final (lo que ven los consumidores)

| Feature | Path público | Descripción corta | ¿Requiere activación? | Tool IA |
|---|---|---|---|---|
| **Página del negocio** | `{base}/api/v1/public/t/{slug}/profile` | Datos del tenant: nombre, descripción, dirección, logo, redes. Read-only (GET). | No | `get_tenant_info` |
| **Catálogo** | `{base}/api/v1/public/t/{slug}/catalog` | Lista de productos visibles al público (nombre, precio, imagen, descripción, disponibilidad). | No | `list_products` |
| **Ficha de producto** | `{base}/api/v1/public/t/{slug}/products/{product_slug}` | Detalle de UN producto: precio, galería, variantes, stock visible. | No | (vía `list_products`) |
| **Promociones** | `{base}/api/v1/public/t/{slug}/promotions` | Promociones activas: descuento, vigencia, condiciones. | No | `list_promotions` |
| **Categorías** | `{base}/api/v1/public/t/{slug}/categories` | Categorías del catálogo. | No | (vía catálogo) |
| **Sucursales** | `{base}/api/v1/public/t/{slug}/branches` | Sucursales del tenant: dirección, horarios, teléfono, coordenadas. | No | (vía `get_tenant_info`) |
| **Landing** | `{base}/api/v1/public/t/{slug}/landing` | Config de la landing pública: colores, copy, links a redes, claims. | No | (no expuesta aún) |
| **QR redirect** | `{base}/r/{short_code}` | URL CORTA de un QR. Server responde 302 al destino configurado. | No | (no expuesta aún) |

> `{base}` = `settings.public_base_url` (default `https://wowhub-api-production.up.railway.app`).

### 2.2 Gestión interna (autenticada con JWT — NO se entrega como link público)

El dueño accede a la gestión vía API autenticada. Los endpoints viven bajo `/api/v1/tenants/{tid}/...`, `/api/v1/auth/...`, `/api/v1/admin/...`, etc. y requieren JWT. NO hay vista HTML pública para ninguno de estos flujos. Algunos ejemplos:

- **Productos:** `GET/POST/PATCH/DELETE /api/v1/tenants/{tid}/products`
- **Sucursales:** `GET/POST/PATCH/DELETE /api/v1/tenants/{tid}/branches`
- **Categorías:** `GET/POST/PATCH/DELETE /api/v1/tenants/{tid}/categories`
- **Clientes:** `GET /api/v1/tenants/{tid}/customers`
- **Stats:** `GET /api/v1/tenants/{tid}/stats/overview`
- **Branding:** `PATCH /api/v1/tenants/{tid}` (campo `logo_url`) o `POST /api/v1/uploads`
- **Password:** `POST /api/v1/auth/password`
- **QRs:** `GET/POST/DELETE /api/v1/tenants/{tid}/qrs`
- **Admin IA:** `GET /api/v1/admin/ai/...` (solo OWNER/ADMIN, JWT + rol)
- **Superadmin:** `GET /api/v1/superadmin/...` (solo `is_superuser=True`)

> **Admin IA — guard de rol:** los endpoints `/api/v1/admin/ai/*` están protegidos con guard server-side. Si el usuario no tiene rol `OWNER` o `ADMIN` → 403. La página HTML `/admin/ai` está en `app/main.py` (código de desarrollo) pero **NO está desplegada en producción**; los superadmins/owners usan directamente la API autenticada o un panel interno (cuando se despliegue).
>
> **Superadmin — guard de plataforma:** los endpoints `/api/v1/superadmin/*` requieren `is_superuser=True` a nivel de **USUARIO** (no de membresía). Si el flag es False → 403. **Diferencia clave:** los roles de membresía (OWNER/ADMIN/STAFF/VIEWER) son **por tenant**; `is_superuser` es **por usuario** y aplica a TODA la plataforma.

---

## 3. URLs públicas (sin autenticación)

Estas son las URLs que el dueño comparte con sus clientes. La IA SIEMPRE debe llamar a la tool `get_tenant_public_urls` para devolverlas con el slug REAL sustituido.

| Función | Patrón | Notas |
|---|---|---|
| Perfil del negocio | `https://{base}/api/v1/public/t/{slug}/profile` | Datos del tenant: nombre, descripción, dirección, logo, redes. |
| Catálogo público | `https://{base}/api/v1/public/t/{slug}/catalog` | Productos visibles sin login. |
| Ficha de producto | `https://{base}/api/v1/public/t/{slug}/products/{product_slug}` | Detalle de UN producto puntual. |
| Promociones | `https://{base}/api/v1/public/t/{slug}/promotions` | Promos activas del tenant. |
| Categorías | `https://{base}/api/v1/public/t/{slug}/categories` | Categorías del catálogo. |
| Sucursales | `https://{base}/api/v1/public/t/{slug}/branches` | Sucursales: dirección, horarios, teléfono, coordenadas. |
| Landing | `https://{base}/api/v1/public/t/{slug}/landing` | Config de la landing pública: colores, copy, links. |
| QR redirect | `https://{base}/r/{short_code}` | URL CORTA de un QR. Server responde 302 al destino configurado. |

> `{base}` = `settings.public_base_url` (default `https://wowhub-api-production.up.railway.app`).
> `{slug}` = identificador del tenant (ej. `cafeluna`). Sale SIEMPRE de la tool `get_tenant_public_urls`, NUNCA inventado por la IA.
> `{product_slug}` = slug del producto puntual (sale de `list_products` o de la URL del producto en el catálogo).
> `{short_code}` = código alfanumérico corto del QR.

> **v1.9.1-r4 — Errores comunes a corregir:**
> 1. **Formato viejo `/u/{slug}/...` está MUERTO.** El prefijo `/u/{slug}/catalogo`, `/u/{slug}/perfil`, `/u/{slug}/reservar`, `/u/{slug}/menu`, `/u/{slug}/pedido`, `/u/{slug}/book` **NO existe en el OpenAPI de producción y da 404**. La forma REAL es `/api/v1/public/t/{slug}/...`.
> 2. **`wowhub.app` no responde (NXDOMAIN).** NUNCA entregues links con prefijo `https://wowhub.app/...`. La única URL que puedes garantizar como "existe y responde hoy" es `https://wowhub-api-production.up.railway.app/...`.
> 3. **`/loyalty/{slug}` NO está desplegado.** El feature de fidelización no existe en producción (solo en roadmap). NO lo ofrezcas como link.
> 4. **Reservas (`/u/{slug}/reservar` o `/api/v1/.../bookings`) NO están en el MVP actual.** El feature de reservas está en roadmap. La IA NO debe entregar URLs de reservas.
> 5. **La IA NO debe hardcodear el dominio ni el slug.** Ambos salen SIEMPRE de `settings.public_base_url` y de `get_tenant_public_urls`. Una URL con placeholder o dominio inventado es una URL FALSA.

---

## 4. Auth y cuenta del usuario

| Acción | Ruta / Endpoint |
|---|---|
| Login | `POST /api/v1/auth/login` |
| Registro | `POST /api/v1/auth/register` |
| Refrescar token | `POST /api/v1/auth/refresh` |
| Cambiar contraseña | `POST /api/v1/auth/password` (desde Mi cuenta) |
| Mi cuenta | `/dashboard/site` → sección "Mi cuenta" |
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
| `get_tenant_public_urls` | (nuevo, combina `get_tenant_info` + `app_knowledge.PUBLIC_URLS`) | Devuelve los links públicos del tenant **ya con el slug real sustituido** (ej. `https://wowhub.app/u/cafeluna/reservar`). Usar SIEMPRE que el usuario pregunte por su link para compartir, URL pública, link de reservas, link de catálogo o cómo compartir su tienda. Si el tenant aún no tiene slug, devuelve los patrones + hint. Disponible solo en el sub-agente `help`. |

### 5.2 Tools de escritura (ejecutan acciones)

| Tool | Endpoint interno | Requiere confirmación |
|---|---|---|
| `create_promotion` | `POST /tenants/{id}/promotions` | **Sí** — preview antes de guardar. |
| `create_booking` | `POST /tenants/{id}/bookings` | **Sí** — confirmar cliente, fecha, hora, sucursal. |
| `send_email_to_customer` | `POST /customers/{id}/email` | **Sí** — mostrar asunto + cuerpo antes de enviar. |
| `send_campaign` | `POST /tenants/{id}/campaigns` | **Sí** — preview de audiencia + cantidad + muestra. |

> **Regla de seguridad innegociable:** ninguna tool de escritura se invoca sin que la IA muestre el **preview** y el usuario responda "sí" (o equivalente) de forma explícita. Esto ya está implementado en el system prompt de `AUTOMATION` y debe replicarse en cualquier agente que herede estas tools (incluido el nuevo `HELP`).

### 5.3 Tool de plataforma: `get_tenant_public_urls` (v1.6)

Disponible **solo** en el sub-agente `help` (no la heredan marketing/growth/automation/marketplace porque no es de negocio).

**Qué hace:** combina `get_tenant_info` (para leer el `slug` real del tenant) con `app_knowledge.PUBLIC_URLS` (los patrones `/u/{slug}/...`) y devuelve las URLs **ya con el slug sustituido**, listas para mostrar y compartir.

**Cuándo usarla:** SIEMPRE que el usuario pregunte por:
- "Cuál es mi URL pública" / "link para compartir"
- "El link para que mis clientes agenden"
- "Cómo comparto mi tienda / mi landing"
- "Link del catálogo público"
- "Dónde pongo el QR"

**Contrato de salida:**

```json
{
  "source": "app_knowledge",
  "topic": "tenant_public_urls",
  "tenant": {"name": "Café Luna", "slug": "cafeluna"},
  "has_slug": true,
  "base_url": "https://wowhub.app",
  "urls": [
    {"key": "landing",        "url": "https://wowhub.app/u/cafeluna",                "description": "Landing pública del negocio..."},
    {"key": "catalogo",       "url": "https://wowhub.app/u/cafeluna/catalogo",       "description": "Catálogo público de productos sin login."},
    {"key": "reservar",       "url": "https://wowhub.app/u/cafeluna/reservar",       "description": "Flujo público de reservas: branch → fecha/hora → datos."},
    {"key": "reservar_alias", "url": "https://wowhub.app/u/cafeluna/book",           "description": "Alias en inglés de /reservar."}
  ]
}
```

Si el tenant **aún no tiene `slug`** configurado, devuelve los patrones + un `hint` para que el LLM le indique al usuario dónde configurarlo (`Configuración → Branding`).

**Anti-alucinación:** la IA **NUNCA** debe responder con `/u/{slug}/reservar` literal. Si la tool falla, debe decir "ahora no puedo obtener tu link; ve a Configuración para ver tu URL" en vez de inventar el slug.

### 5.4 Endpoints AI Core (atómicos)

A diferencia de las tools de lectura/escritura (que se invocan dentro del flujo de chat), estos endpoints son **atómicos**: 1 request → 1 response estructurada. Son los "productos" del WowHub AI Core™.

| Endpoint | Cap. | Auth | Rate limit | Qué hace |
|---|---|---|---|---|
| `POST /api/v1/ai/chat` | 18 | JWT + `X-Tenant-Id` | `ai_daily_message_limit` (compartido) | Chat conversacional multi-agente (streaming opcional). |
| `POST /api/v1/ai/marketing/generate` | 19.1 | JWT + `X-Tenant-Id` | Compartido con `/chat` | Genera N variantes de copy de marketing contextual al tenant. |
| `POST /api/v1/ai/growth/analyze` | 19.2 | JWT + `X-Tenant-Id` | Compartido con `/chat` | Analiza la Memoria de Negocio del tenant y devuelve insights accionables. |
| `GET  /api/v1/ai/agents` | 18 | JWT | — | Lista los sub-agentes disponibles (marketing, growth, automation, marketplace, help). |
| `GET  /api/v1/ai/status` | 18 | JWT | — | Estado del LLM (circuit breaker, rate usado, enabled). |
| `GET  /api/v1/ai/usage` | 18 | JWT | — | Mensajes consumidos hoy vs. el límite diario. |

> **Regla unificada de rate limit:** el contador diario (`ai_daily_message_limit`) es el mismo para `/chat`, `/marketing/generate` y `/growth/analyze`. Esto es coherente: el LLM es el mismo recurso limitado. El Growth Coach y el Marketing Studio NO tienen cuota propia.

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
| "¿URL pública para que mis clientes agenden?" | "`https://{tu-dominio}/u/{tu-slug}/reservar` — compártela en Instagram, WhatsApp o tu bio. (El asistente IA resuelve el `{tu-slug}` llamando a la tool `get_tenant_public_urls`, así que la respuesta SIEMPRE incluye el slug real, no el placeholder.)" |
| "No me deja entrar a X módulo" | "Verifica que tu sesión esté iniciada y que el chip de usuario del topbar muestre el tenant correcto. Si persiste, contáctanos." |
| "¿Cómo cambio el idioma?" | "Por ahora WowHub está en español. La función multi-idioma está en roadmap." |
| "¿Cómo cambio el logo de mi tienda?" | "**Configuración → Branding** (subir imagen, máximo 2 MB)." |
| "¿Cuánto cuesta WowHub?" | "Depende del plan. Revisa la sección de **Planes** en la landing o pregúntale al equipo de ventas." |
| "Quiero eliminar mi cuenta" | "Por seguridad, la eliminación de cuenta se hace escribiendo a **soporte@wowhub.app**." |
| "¿Cómo conecto WhatsApp?" | "En **Configuración → Integraciones** (cuando esté disponible). Hoy puedes compartir el link público por WhatsApp manualmente." |
| "¿Me ayudas a escribir un post para Instagram / un copy de marketing / un asunto de email?" | "Sí. Usa el **Marketing Studio**: `POST /api/v1/ai/marketing/generate` con `intent` según el canal (instagram_post, whatsapp_broadcast, email_subject, etc.), `topic` el tema, `tone` y `audience` según tu público. Te devuelve N variantes listas para usar. Si el LLM está caído, devuelve un template (`fallback: true`). El copy NO se guarda en la base — solo se devuelve." |
| "¿La IA puede generar imágenes para mi promo?" | "Hoy el Marketing Studio solo genera **texto**. La generación de imágenes y videos está en roadmap (ver §18.2)." |
| "¿Cuántas variantes de copy puedo pedir?" | "De 1 a 5, con `variants: N` (default 3). Cada variante es una versión distinta del mismo copy con el mismo `intent`/`tone`/`audience`." |
| "¿El Marketing Studio tiene su propio límite diario?" | "No. Comparte el contador con `/api/v1/ai/chat`. Si ya usaste todos tus mensajes del día, devuelve 429 antes de llamar al LLM." |
| "¿Cómo analizo mi negocio / qué me recomiendas / cómo sé si voy bien?" | "Usa el **Growth Coach**: `POST /api/v1/ai/growth/analyze`. Indica `focus` (overview, sales, inventory, customers, promotions, bookings o mixed), `lookback_days` (7-180, default 30) e `idioma`. Te devuelve un resumen ejecutivo + lista de insights priorizados (urgent → low) con acciones recomendadas. Si el LLM está caído, devuelve análisis determinístico (`fallback: true`) — igual obtienes insights útiles. NO ejecuta acciones: solo analiza y sugiere." |
| "¿Dónde veo los insights / recomendaciones del Growth Coach?" | "Hoy se exponen vía el endpoint `POST /api/v1/ai/growth/analyze` y los resultados se renderizan en el Resumen o dentro del chat. NO hay un módulo separado en el sidebar." |
| "¿El Growth Coach ejecuta las acciones que recomienda?" | "No. El Growth Coach solo ANALIZA y SUGIERE (devuelve `recommended_actions` y `linked_module`). La ejecución la hace el usuario desde el módulo correspondiente (ej. `linked_module: promotions` → ir a `/dashboard/promotions`). El Automation Manager (futuro) sería quien ejecute automáticamente." |
| "¿Cada cuánto corre el Growth Coach?" | "Es un endpoint **on-demand**: corre cuando tú lo llamas. NO se ejecuta periódicamente ni genera notificaciones automáticas. Si quieres un análisis fresco, llámalo a `/api/v1/ai/growth/analyze`." |
| "¿El Growth Coach tiene un límite diario propio?" | "No. Comparte el contador con `/api/v1/ai/chat` y `/marketing/generate`. Si ya consumiste el día, devuelve 429." |
| "¿Qué hace diferente al Growth Coach del Marketing Studio?" | "El **Marketing Studio** GENERA copy de marketing (textos listos para publicar). El **Growth Coach** ANALIZA tu negocio y devuelve insights accionables (qué tienes que hacer). Son complementarios: usa Studio para escribir, Coach para decidir." |
| "¿Qué diferencia hay entre OWNER, ADMIN, STAFF y VIEWER?" | "Son los 4 roles por membresía en un tenant. **OWNER**: administración completa del tenant (todo). **ADMIN**: administración operativa con casi los mismos poderes que OWNER — puede gestionar productos, reservas, clientes, campañas, miembros y configuración, pero no puede eliminar el tenant ni modificar el OWNER. **STAFF**: operación diaria con acceso limitado (ej. crear reservas, registrar ventas, ver clientes, pero no modificar configuración ni productos). **VIEWER**: solo consulta (lee KPIs, listas, agenda) sin poder ejecutar acciones de escritura. Los roles son **por tenant** — un mismo usuario puede ser OWNER en un tenant y VIEWER en otro. El **SUPERUSER** es otra cosa: es un flag **por usuario** (no por tenant) y aplica a TODA la plataforma; ver §11." |
| "¿El superadmin puede entrar a mi tienda y ver mis conversaciones del asistente?" | "Un **SUPERUSER** puede iniciar una sesión temporal de **impersonación** desde `/admin/superadmin`, siempre que el usuario objetivo no sea otro superuser y esté activo. Durante esa sesión puede acceder a las **funciones y datos permitidos para el usuario impersonado** dentro del tenant seleccionado. Esto **puede incluir** las conversaciones del asistente si están disponibles para esa cuenta. La sesión muestra un banner visible de impersonación, dura **como máximo 60 minutos** y todas las acciones quedan registradas (superuser, usuario objetivo, tenant, hora, acción). **Las contraseñas y secretos nunca se muestran.**" |
| "¿Qué ocurre si un superadmin entra a mi tienda?" | "La sesión normal del dueño **no se reemplaza ni se cierra**. La impersonación se ejecuta en una sesión temporal separada del superuser. El acceso queda registrado en la **auditoría del tenant** y puede ser revisado por usuarios autorizados según la política de WowHub. El superuser debe salir mediante el botón **'🚪 Salir'** del banner o esperar la expiración automática de la sesión." |

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
- ❌ No hay un "Asistente Premium" definido en planes — la IA es la misma para todos.
- ❌ No hay una URL pública de reservas distinta de `/u/{slug}/reservar` (no existe alias `/u/{slug}/book`).
- ❌ **No** existe un botón "Login As" o "Entrar como admin" visible para usuarios normales; la función de impersonación es exclusiva del superuser y solo se muestra dentro de `/admin/superadmin`.
- ❌ El **Growth Coach NO ejecuta acciones** sobre el negocio: solo ANALIZA datos y devuelve insights con `recommended_actions` y `linked_module`. La ejecución de las acciones (ej. "Crear promo 2x1", "Enviar WhatsApp a inactivos") la hace el usuario o el Automation Manager (roadmap).
- ❌ El **Growth Coach NO se agenda automáticamente** ni se ejecuta periódicamente. Es un endpoint on-demand: el usuario lo llama desde el panel o lo pide al chat.
- ❌ El **Growth Coach NO tiene un dashboard dedicado** en el sidebar. Sus resultados se muestran dentro del Resumen o del chat (no es un módulo nuevo del panel).
- ❌ El **Growth Coach NO persiste** los análisis ni los insights en la base. Cada llamada es stateless — la UI puede guardar la última response en localStorage si quiere.
- ❌ El **Growth Coach NO tiene límite diario propio**: comparte el contador con `/chat` y `/marketing/generate`. Si ya se consumió el día, devuelve 429.
- ❌ El **Growth Coach NO genera imágenes, gráficos ni videos** — solo devuelve texto estructurado (summary + insights). Visualizaciones son responsabilidad del frontend.
- ❌ El **Growth Coach NO reemplaza al Marketing Studio**: uno analiza (insights), el otro genera (copy). Son productos complementarios.

**Acciones prohibidas para la IA** (nunca debe intentar):

- ❌ Iniciar una sesión de impersonación.
- ❌ Crear, eliminar o promover a SUPERUSER.
- ❌ Cambiar contraseñas de ningún usuario.
- ❌ Borrar tenants.
- ❌ Enviar campañas sin preview y confirmación explícita.
- ❌ Enviar campañas a clientes que no cumplen las reglas de consentimiento de marketing.
- ❌ Revelar tokens, secretos, contraseñas ni JWT internos.
- ❌ Mostrar datos de otros tenants al usuario actual.
- ❌ Afirmar que una operación se realizó si la tool no devolvió éxito.

**Acciones que SIEMPRE requieren confirmación explícita** (la IA debe mostrar preview con datos exactos y esperar "sí"):

- ⚠️ Crear promociones.
- ⚠️ Crear reservas.
- ⚠️ Enviar emails individuales.
- ⚠️ Enviar campañas masivas.
- ⚠️ Eliminar o desactivar productos.
- ⚠️ Modificar precios.
- ⚠️ Cambiar horarios de sucursal.
- ⚠️ Cancelar reservas.
- ⚠️ Exportar datos personales.
- ⚠️ Cambiar configuración de privacidad.

> La confirmación debe estar vinculada a los **datos exactos** de la acción. Un "sí" antiguo o ambiguo no es válido.

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
- **v1.5 (16-ago-2026)**: **FAQ ampliada por categoría + protocolo de incertidumbre + matriz de capacidades como roadmap**. Cambios:
  - §6 FAQ: 2 entradas reescritas sobre impersonación con redacción más transparente (no promete "ver conversaciones" en términos absolutos, no dice "no notás nada").
  - §7: ampliada con 3 sub-listas explícitas (cosas que no existen, acciones prohibidas para la IA, acciones que requieren confirmación). 11 ❌ originales + 6 ❌ nuevos + 10 ⚠️ nuevos.
  - §14 NUEVA: FAQ ampliada organizada por categoría (Acceso y navegación, Módulos, Configuración, Promociones/Campañas, Reservas, Datos/Exportación) con respuestas dinámicas por rol/tenant.
  - §15 NUEVA: **Protocolo de incertidumbre** — 5 reglas explícitas sobre cuándo la IA debe decir "no tengo esa información" y frase literal canónica.
  - §16 NUEVA: **Matriz de capacidades** (estado actual + roadmap) + diseño objetivo de la tool `get_user_capabilities` para Fase 2.
  - §10 añade roadmap de tests recomendados (variantes, permisos, seguridad, consistencia, regresión negativa).
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

---

## 14. FAQ ampliada por categoría (respuestas dinámicas por contexto)

Esta sección complementa §6 con preguntas adicionales organizadas por categoría. La diferencia clave: muchas respuestas aquí son **dinámicas** — la IA debe considerar el rol, el tenant y el estado actual antes de responder. Ver §16 para la tool `get_user_capabilities` que automatiza esto en Fase 2.

### 14.1 Acceso y navegación

**¿Cómo entro a WowHub?**
- Ve a la pantalla de login de WowHub, ingresa tu correo y contraseña y, después de autenticarte, accederás al dashboard del tenant seleccionado.
- Si tienes más de un tenant, verifica el tenant activo en el selector del topbar.

**¿Qué hago si no veo un módulo?**
- Primero verifica que estés autenticado y que el **tenant activo** sea el correcto.
- La visibilidad de algunas secciones depende de tu **rol**: OWNER y ADMIN tienen más permisos que STAFF o VIEWER (ver §13).
- Si tienes permisos suficientes y la sección no aparece, puede tratarse de un problema de sesión o disponibilidad temporal.

### 14.2 Módulos y activación

**¿Tengo que activar un módulo?**
- No. Los módulos disponibles para un tenant activo no requieren activación manual.
- Si una sección no aparece, verifica el estado del tenant, tu rol y el tenant seleccionado (no es un toggle).

**¿Por qué no puedo usar Reservas?**
La IA debe comprobar (en este orden):
1. Usuario autenticado.
2. Tenant correcto.
3. Rol suficiente.
4. Tenant activo (no suspendido).
5. Existencia de al menos una sucursal.
6. Horarios de la sucursal configurados.
7. Disponibilidad del servicio (no en mantenimiento).

Respuesta dinámica:
- Caso normal: "Reservas no requiere activación. Para utilizarla, verifica que estés en el tenant correcto, que tengas permisos suficientes y que exista al menos una sucursal con horarios configurados. Puedes acceder desde `/dashboard/bookings`."
- Tenant suspendido: "El tenant está suspendido actualmente, por lo que algunas operaciones están bloqueadas. Consulta a un administrador autorizado de la plataforma."
- Sin sucursales: "Reservas está disponible, pero primero debes crear una sucursal y configurar sus horarios desde Sucursales."

### 14.3 Configuración

**¿Cómo cambio el logo?**
- Ve a **Configuración → Branding**.
- El límite y los formatos permitidos dependen del tipo de archivo y de la configuración vigente del tenant. Actualmente, el logo acepta imágenes JPG o PNG de hasta **{max_upload_mb} MB** (valor provisto por `app_knowledge.py` o por la config del backend — **no hardcodear** en la respuesta).

**¿Cómo cambio el nombre o slug de la tienda?**
- Ve a **Configuración → Datos del negocio**.
- El nombre visible y el slug pueden tener reglas diferentes. El slug debe ser **único** y puede cambiar la URL pública del negocio.
- ⚠️ **Advertencia:** si cambias el slug, las URLs públicas anteriores pueden dejar de funcionar, salvo que WowHub implemente redirecciones (no implementadas hoy).

**¿Cómo cambio mis horarios?**
- Ve a **Sucursales**, selecciona la sucursal y edita sus horarios.
- Los horarios de la sucursal se utilizan para calcular la disponibilidad de reservas.

### 14.4 Promociones, campañas y acciones de IA

**¿Cuál es la diferencia entre una promoción y una campaña?**
- Una **promoción** define un beneficio comercial, como un descuento, combo o precio especial.
- Una **campaña** es una comunicación dirigida a un segmento de clientes, normalmente por email.
- Una campaña puede **comunicar** una promoción, pero son objetos diferentes.

**¿La IA puede crear promociones?**
- Sí. La IA puede preparar una promoción, pero debe mostrar un **preview** con nombre, descuento, fechas, productos afectados y condiciones.
- **No guardará la promoción hasta que confirmes explícitamente.**

**¿La IA puede enviar campañas?**
- Sí, si tu rol tiene permiso y se cumplen las reglas de seguridad.
- Antes del envío debe mostrar el **segmento, cantidad de destinatarios, filtros aplicados, muestra del mensaje y canal**.
- Solo se deben incluir clientes con **consentimiento de marketing** cuando corresponda.

**¿Puedo cancelar una campaña?**
- Depende del estado:
  - **Borrador** → puede modificarse o eliminarse.
  - **Ya enviada** → no puede deshacerse; en ese caso se debe registrar un incidente y evaluar una comunicación correctiva.
- La IA **no debe prometer** una función de cancelación de campañas enviadas si todavía no está implementada.

### 14.5 Reservas

**¿Cómo creo una reserva?**
- "Puedo ayudarte a crearla. Necesito: cliente, sucursal, fecha, hora y duración. **Primero comprobaré la disponibilidad**; después te mostraré un preview y solo crearé la reserva si confirmas explícitamente."

**¿Cómo cancelo una reserva?**
- Usa el enlace seguro incluido en el correo de confirmación. No existe una URL fija para cancelar reservas; cada reserva genera su propio enlace con token (ver §3).

**¿Puedo modificar una reserva?**
- La modificación de reservas depende de las funciones disponibles para tu tenant. **Si la edición no está implementada**, puedo ayudarte a revisar la reserva existente y orientarte sobre la cancelación y creación de una nueva.
- La IA **debe evitar inventar un endpoint o botón de edición** que no exista.

### 14.6 Datos, exportación y eliminación

**¿Puedo exportar mis datos?**
- WowHub permite exportación en **CSV** desde las funciones habilitadas del panel.
- La exportación a Excel nativo **no está disponible** actualmente.
- Tipos de exportación que pueden existir (verificar disponibilidad real antes de prometer):
  - Exportación de clientes.
  - Exportación de pedidos.
  - Exportación de auditoría.
  - Exportación de conversaciones IA.
  - Exportación de datos para migración.

**¿Puedo borrar un producto?**
- Puedes eliminar productos si tu rol tiene permiso.
- ⚠️ **Advertencia:** antes de eliminarlos, verifica si están asociados a pedidos, promociones, stock o reportes históricos. Cuando sea necesario, es preferible **desactivarlos o archivarlos** en lugar de eliminarlos físicamente.

**¿Puedo borrar mi tenant?**
- La eliminación del tenant **no se realiza desde el chat de la IA**.
- Debes solicitarla al equipo autorizado de WowHub (soporte@wowhub.app o SUPERADMIN).
- La eliminación puede estar sujeta a validación de identidad, retención legal de registros y política de respaldo.
- Esto es mejor que decir simplemente "no existe borrar tenant", porque la capacidad puede existir por soporte o SUPERADMIN.

### 14.7 Preguntas frecuentes de transparencia sobre impersonación

Estas preguntas son **críticas para la confianza** del usuario. Todas las respuestas deben ser **transparentes y conservadoras** (no prometer más de lo que el sistema garantiza).

| Pregunta | Respuesta canónica |
|---|---|
| ¿Quién puede impersonar mi cuenta? | Solo un **SUPERUSER activo**, desde el panel `/admin/superadmin`. Los usuarios normales (OWNER, ADMIN, STAFF, VIEWER) **no pueden iniciar** una impersonación. |
| ¿El superuser puede ver mis conversaciones? | Puede acceder a las funciones y datos permitidos para tu rol dentro del tenant seleccionado. **Esto puede incluir las conversaciones del asistente si están disponibles para tu cuenta.** El superuser nunca ve contraseñas en claro. |
| ¿El superuser puede cambiar mis datos? | Durante la impersonación, el superuser puede realizar las acciones que tu rol permite en ese tenant. Cambios importantes (contraseña, email, rol) están protegidos por separado. |
| ¿El superuser puede ver mi contraseña? | **No.** Las contraseñas nunca se muestran en texto claro, ni forman parte de la sesión de impersonación. |
| ¿Cómo sé si alguien entró a mi cuenta? | La sesión de impersonación queda registrada en la **auditoría del tenant**. Puedes pedir a soporte un reporte filtrado por tu `tenant_id`. (Notificación automática al owner: roadmap.) |
| ¿La impersonación cambia mi contraseña? | **No.** La impersonación no cambia tus credenciales ni reemplaza tu sesión normal. |
| ¿Se cierra mi sesión cuando me impersonan? | **No.** Tu sesión normal del dueño no se reemplaza ni se cierra; la impersonación es una sesión temporal y separada del superuser. |
| ¿Cuánto dura la impersonación? | **Como máximo 60 minutos** o hasta que el superuser seleccione el botón "🚪 Salir" del banner. |
| ¿Qué pasa cuando expira? | El JWT pierde validez; el banner desaparece; el superuser debe volver a iniciar impersonación si necesita continuar. |
| ¿Puedo impedir la impersonación? | No por el momento. La auditoría garantiza trazabilidad. Bloqueo per-tenant de impersonación está en roadmap. |

---

## 15. Protocolo de incertidumbre (regla de oro anti-alucinación)

Esta sección es **la más importante después de §1**. Se aplica a CUALQUIER respuesta de la IA cuando la información no es 100% confirmada por la documentación vigente.

### 15.1 Las 5 reglas

1. **No inventar nombres de botones, rutas, endpoints ni límites.** Si no está en este documento o en `app_knowledge.py`, no se afirma.
2. **No convertir una función futura (roadmap) en una función disponible.** Si algo está en §11.5, §16 o en el changelog como "pendiente", la IA debe decir "está planificado pero aún no disponible".
3. **No afirmar que una acción se ejecutó sin confirmación del backend.** Si una tool no devolvió éxito, la respuesta debe ser "no pude completar la acción" + motivo, nunca "listo, ya lo hice".
4. **No divulgar información sensible.** Tokens, secretos, contraseñas, JWT internos, IDs internos de base de datos, SQL, paths de archivos del servidor: **NUNCA**.
5. **Indicar claramente el estado de la información** al responder. Usar uno de estos 5 estados:
   - ✅ **Disponible** — verificado en este documento y/o en el código.
   - 🔒 **Condicionada por permisos** — disponible si el rol/tenant lo permite.
   - 🛣️ **Roadmap** — planificado pero no implementado.
   - ⏳ **Temporalmente indisponible** — servicio en mantenimiento o caído.
   - ❓ **No documentada** — no figura en la documentación vigente.

### 15.2 Frase literal canónica

Cuando la IA no pueda confirmar algo, debe usar **exactamente** una de estas frases (en este orden de preferencia):

1. **"No tengo esa información confirmada en la documentación vigente de WowHub."**
2. "Esa función todavía no está disponible. Está planificada en el roadmap."
3. "No puedo confirmar el límite exacto; consulta con tu OWNER o con soporte@wowhub.app."
4. "Esa acción requiere permisos que tu rol actual no tiene."

### 15.3 Lo que la IA NUNCA debe responder

- ❌ "Debería poder hacer X..." (especulación).
- ❌ "Probablemente esté en Y..." (adivinanza).
- ❌ "Sí, seguro" sin verificación (riesgo de daño).
- ❌ "Ya lo hice" sin respuesta exitosa del backend.
- ❌ "Tengo acceso a la base de datos" (la IA no tiene acceso directo a la DB).
- ❌ Cualquier ruta, endpoint, parámetro o constante que no esté en este documento o en el código fuente verificable.

### 15.4 Cuando la información es ambigua

Si la pregunta del usuario es ambigua o falta contexto, la IA debe:
- Pedir **una aclaración concreta** (no divagar).
- Orientar al usuario hacia una **ruta existente** del dashboard cuando sea posible.
- Sugerir el canal de soporte (soporte@wowhub.app) cuando el tema excede el alcance del producto.

---

## 16. Matriz de capacidades (estado actual + roadmap)

### 16.1 Estado actual de las capacidades

| Capacidad | Estado | Quién puede usarla | Ruta principal | Respuesta canónica de la IA |
|---|---|---|---|---|
| Activar módulos | **No requerido** | Todos los usuarios autorizados | — | "No requiere activación." |
| Reservas | ✅ Disponible | Según rol/tenant | `/dashboard/bookings` | "Reservas no requiere activación..." |
| Promociones | ✅ Disponible | OWNER/ADMIN | `/dashboard/promotions` | "Puedo crearla por ti..." |
| Campañas email | ✅ Disponible | OWNER/ADMIN | (no tiene vista — usa la tool `send_campaign`) | "Sí, con preview antes de enviar." |
| WhatsApp Business | 🛣️ Roadmap | Nadie actualmente | — | "Está planificado, pero aún no disponible." |
| Exportar CSV | ✅ Disponible | Según permisos | Panel (varios módulos) | "Puedes exportar CSV desde..." |
| Exportar Excel nativo | ❌ No disponible | Nadie | — | "No está disponible actualmente." |
| Impersonación | ✅ Disponible | Solo SUPERUSER | `/admin/superadmin` | "Solo superusers pueden usar esta función." |
| Crear tenant desde chat | ❌ Bloqueado | Nadie vía IA | — | "La IA no crea tenants." |
| Borrar tenant desde chat | ❌ Bloqueado | Nadie vía IA | — | "No se realiza desde el chat; contacta a soporte." |
| Auto-promover a SUPERUSER | ❌ Bloqueado | Nadie | — | "No existe esa función." |
| Notificación al owner por impersonación | 🛣️ Roadmap | — | — | "Cuando esté habilitado, el sistema podrá enviar una notificación." |
| Ver conversaciones durante impersonación | 🔒 Condicionado | SUPERUSER | Según vista | Respuesta basada en política real (ver §12.3). |
| Multi-idioma UI | 🛣️ Roadmap | — | — | "Está en roadmap." |
| Marketplace de integraciones | 🛣️ Roadmap | — | — | "Está planificado." |
| Tool `get_user_capabilities` | 🛣️ Roadmap (Fase 2) | — | `/api/v1/auth/me/capabilities` | "Todavía no está disponible; ver §16.2." |

### 16.2 Diseño objetivo de la tool `get_user_capabilities` (Fase 2)

Esta herramienta es **clave** para que la IA pueda responder las preguntas dinámicas de §14 sin improvisar. **No está implementada aún** — está documentada como roadmap.

**Endpoint:** `GET /api/v1/auth/me/capabilities`

**Respuesta esperada:**

```json
{
  "user_id": "uuid",
  "tenant_id": "uuid",
  "role": "OWNER",
  "tenant_status": "active",
  "permissions": {
    "bookings.read": true,
    "bookings.create": true,
    "bookings.update": true,
    "bookings.delete": false,
    "campaigns.send": true,
    "products.delete": false,
    "products.update": true,
    "members.invite": true,
    "members.change_role": true,
    "tenant.delete": false
  },
  "requirements": {
    "branches_configured": true,
    "booking_hours_configured": true,
    "marketing_consent_required": true
  },
  "modules": {
    "bookings": { "available": true, "blocking_reason": null },
    "campaigns": { "available": true, "blocking_reason": null },
    "whatsapp": { "available": false, "blocking_reason": "not_implemented" }
  }
}
```

**Uso por la IA:** antes de responder cualquier pregunta de §14, llamar a `get_user_capabilities` y adaptar la respuesta al estado real. Si la respuesta no es concluyente, aplicar §15 (Protocolo de incertidumbre).

### 16.3 Tests recomendados para FAQ, anti-alucinación y capabilities

Esta lista se incorpora al roadmap de `tests/ai/`. Los nombres siguen la convención de `test_help_routes.py` existente.

**Tests de variantes de preguntas**
- `test_bookings_activation_variants`
- `test_public_booking_url_variants`
- `test_password_change_variants`
- `test_language_roadmap_response`
- `test_whatsapp_roadmap_response`

**Tests de permisos**
- `test_staff_cannot_be_told_they_can_manage_settings`
- `test_non_superuser_cannot_impersonate`
- `test_superuser_can_see_superadmin_route`
- `test_impersonation_requires_active_target`

**Tests de seguridad**
- `test_ai_never_reveals_jwt`
- `test_ai_never_reveals_password`
- `test_ai_does_not_claim_campaign_sent_without_success`
- `test_ai_requires_confirmation_before_write`
- `test_ai_does_not_cross_tenant_boundary`

**Tests de consistencia documental**
- `test_all_faq_routes_exist`
- `test_all_documented_modules_have_status`
- `test_no_faq_references_removed_route`
- `test_upload_limits_match_runtime_config`
- `test_no_conflicting_faq_entries`

**Tests de regresión negativa (anti-alucinación)**
- `test_no_activation_toggle_claim`
- `test_no_marketplace_claim`
- `test_no_excel_export_claim`
- `test_no_self_promote_superuser_claim`
- `test_no_absolute_impersonation_privacy_claim` (nuevo — verifica que la IA no afirme que el superuser "siempre ve" o "nunca ve" las conversaciones).

### 16.4 Estados de ejecución de tools (para acciones de la IA)

Cuando la IA ejecuta una tool, debe manejar explícitamente los siguientes estados. **Nunca** debe decir "listo, lo hice" sin que la tool haya devuelto `succeeded`.

| Estado | Significado | Qué dice la IA |
|---|---|---|
| `draft` | Tool iniciada, datos no completos. | "Necesito estos datos para continuar..." |
| `preview_ready` | Datos completos, falta confirmación. | "Te muestro el preview. ¿Confirmas?" |
| `awaiting_confirmation` | Esperando "sí" explícito. | (no dice nada, espera) |
| `executing` | Tool llamada al backend. | "Procesando..." |
| `succeeded` | Backend confirmó éxito. | "Listo, la promoción se creó con ID X." |
| `failed` | Backend devolvió error. | "No pude completar la acción. Motivo: [error]." |
| `partially_succeeded` | Algunos ítems ok, otros no. | "Se crearon 3 de 5 reservas. Las 2 que fallaron fueron: [detalle]." |
| `cancelled` | Usuario canceló antes de confirmar. | "Entendido, no se ejecutó la acción." |
| `expired` | La ventana de confirmación pasó. | "La confirmación expiró. ¿Querés que lo intente de nuevo?" |

Esto es especialmente crítico para **campañas y acciones que afectan datos personales**.

---

## 17. Marketing Studio (WowHub AI Core™ — Cap. 19.1)

### 17.1 Qué es

El **Marketing Studio** es un endpoint del AI Core que genera **copy de marketing contextual al tenant** (negocio + producto + ciudad + tono + audiencia) usando el LLM. A diferencia de `/api/v1/ai/chat` (que es conversacional), el Marketing Studio es **atómico**: 1 request → 1 response estructurada con N variantes de copy + hashtags + metadata.

Es el primer caso de uso del motor de IA como producto (recomendación #1 del análisis estratégico del proyecto: "Comenzar con un caso de uso único y de alto impacto (Marketing Studio)").

### 17.2 Endpoint

| Método | Ruta | Auth | Rate limit |
|---|---|---|---|
| `POST` | `/api/v1/ai/marketing/generate` | JWT (mismo que `/chat`) | Comparte el contador diario con `/chat` (mismo recurso LLM). |

**Headers:** `Authorization: Bearer <jwt>`, opcional `X-Tenant-Id` (si no, se toma la primera membresía activa del usuario).

### 17.3 Request body (resumen)

```json
{
  "intent": "instagram_post",          // canal/formato (enum, ver §17.4)
  "topic": "Promoción 2x1 en café",    // tema central (3-400 chars)
  "tone": "friendly",                  // tono (enum, ver §17.5)
  "audience": "all",                   // segmento (enum, ver §17.6)
  "keywords": ["café", "promo"],       // opcional, max 12
  "include_emojis": true,              // default true
  "include_hashtags": true,            // default false
  "hashtag_count": 5,                  // 0-20
  "language": "es",                    // ISO 639-1, default "es"
  "max_length": null,                  // opcional, 20-4000
  "variants": 3,                       // 1-5, default 3
  "context": {                         // contexto del negocio (opcional)
    "business_name": "Café Luna",      // si se omite, se intenta resolver del tenant
    "business_type": "cafetería",
    "city": "Palermo",
    "product_name": "Cappuccino",
    "product_features": ["orgánico", "de especialidad"],
    "price": "$3.500",
    "promotion_details": "2x1 los martes",
    "cta": "Reservá tu mesa",
    "public_url": "https://wowhub.app/u/cafeluna",
    "extra_notes": "..."
  }
}
```

### 17.4 `intent` — canal/formato (13 valores)

| Valor | Uso | Largo típico |
|---|---|---|
| `instagram_post` | Caption de Instagram | 100-500 chars |
| `instagram_story` | Texto corto para story | ≤80 chars |
| `instagram_reel` | Guion de Reel (gancho + desarrollo + CTA) | 200-400 chars |
| `facebook_post` | Post de Facebook | 100-500 chars |
| `whatsapp_broadcast` | Difusión por WhatsApp Business | 200-600 chars |
| `whatsapp_status` | Estado de WhatsApp (24h) | ≤140 chars |
| `email_subject` | Asunto de email (1-2 líneas) | ≤80 chars |
| `email_body` | Cuerpo de email promocional | 200-1000 chars |
| `sms` | SMS promocional | ≤160 chars |
| `product_description` | Descripción de producto del catálogo | 100-400 chars |
| `promotion_headline` | Titular corto de promoción | ≤60 chars |
| `promotion_body` | Cuerpo descriptivo de promoción | 100-400 chars |
| `general` | Texto libre (default) | variable |

### 17.5 `tone` — tono (7 valores)

`friendly` (default), `professional`, `urgent`, `playful`, `luxury`, `casual`, `inspirational`.

### 17.6 `audience` — segmento (7 valores)

`all` (default), `existing`, `prospects`, `vip`, `inactive`, `new`, `local`.

### 17.7 Response

```json
{
  "id": "uuid",
  "intent": "instagram_post",
  "topic": "Promoción 2x1 en café",
  "tone": "friendly",
  "audience": "all",
  "primary": {
    "index": 1,
    "content": "Tu próximo café te sale gratis. ☕ Válido los martes...",
    "hashtags": ["#CafeLuna", "#Palermo"],
    "character_count": 187
  },
  "variants": [ /* 3 MarketingVariant */ ],
  "hashtags": ["#CafeLuna", "#Palermo", "#Promo"],
  "fallback": false,         // true si se usó template (LLM caído)
  "model": "gpt-4o-mini",   // null si fallback
  "tokens_in": 412,
  "tokens_out": 187,
  "latency_ms": 1842,
  "resolved_context": {     // mezcla de request + tenant
    "business_name": "Café Luna",
    "public_url": "https://wowhub.app/u/cafeluna",
    "..."
  }
}
```

### 17.8 Fallback (cuando el LLM no está disponible)

Si el LLM falla (circuit abierto, timeout, JSON inválido, rate limit del provider), el endpoint **NO devuelve error** — usa **templates pre-armados** indexados por `intent × tone` y devuelve `fallback: true`. El `model` queda en `null` y `tokens_*` en `null`. Esto garantiza que la UI nunca rompa: el usuario siempre recibe copy utilizable.

Templates incluidos (no exhaustivo):
- `instagram_post` × `friendly` → "¡{topic}! Ven a disfrutar en {business_name}…"
- `whatsapp_broadcast` × `urgent` → "¡{topic}! Oferta por tiempo limitado en {business_name}…"
- `email_subject` × `professional` → "{topic} — {business_name}"
- `sms` × `friendly` → "¡{topic}! {cta or 'Más info'}: {public_url or ''}" (≤160 chars)

### 17.9 Reglas de uso (anti-alucinación)

- ❌ La IA **NO** debe inventar URLs públicas. Solo usa el `public_url` del `context` resuelto (o el del tenant si tiene slug). Si no hay URL disponible, omite la URL del copy.
- ❌ La IA **NO** debe incluir bloques ` ```json ` ni ` ``` ` en el contenido (solo el copy final).
- ❌ La IA **NO** debe prometer "imagen generada" o "video generado" — el Marketing Studio **solo genera texto**. La generación de assets visuales está en roadmap.
- ✅ Cada request consume 1 unidad del rate limit diario compartido con `/chat`. Si el usuario ya usó sus N mensajes del día, recibe 429 antes de llamar al LLM.
- ✅ El endpoint es **stateless**: no persiste nada. La persistencia del copy (guardar en borradores, programar envío) es responsabilidad del frontend o de futuras features.

### 17.10 Cuándo la IA conversacional debe sugerir el Marketing Studio

Los sub-agentes `marketing`, `growth` y `automation` deben reconocer estas intenciones y remitir al frontend a llamar al endpoint:
- "¿Me ayudás a escribir un post para Instagram?"
- "Necesito copy para una campaña de WhatsApp"
- "Redactame un asunto de email para mi promo"
- "Generame 3 variantes de copy para Facebook"
- "Quiero un SMS corto para mis clientes VIP"

La IA conversacional puede **preparar el preview** del `MarketingRequest` (intent + topic + tone + audience + context) y pedir confirmación, pero la **ejecución** la hace el frontend llamando al endpoint.

### 17.11 Anti-alucinación específica del Marketing Studio

- ❌ No existe "Generar imagen con IA" desde este endpoint (solo texto).
- ❌ No existe "Programar publicación" desde este endpoint (el copy se devuelve; programar es otra feature).
- ❌ No existe "Multi-idioma automático" — el idioma se pide en el request y el LLM responde en ese idioma.
- ❌ No existe un "límite diario" separado del de `/chat` — es el mismo contador.
- ❌ El endpoint **NO** persiste el copy en la base de datos. Solo lo devuelve.

---

## 18. Cambios recientes y roadmap del AI Core

### 18.1 Cambios recientes

- **v1.9.1 (19-ago-2026)**: micro-release UX — **Dashboard URLs clickeables** (§21). Nueva tool `get_tenant_dashboard_urls` (no es HTTP, lee de `app_knowledge`) que devuelve los links del panel YA CON URL ABSOLUTA clickeable (ej. `https://wowhub.app/dashboard/products`) usando `settings.public_base_url` como prefijo. La IA ahora puede responder con `[Abrir Productos](url)` que es clickeable en cualquier chat UI, email, WhatsApp, SMS. Disponible para los 5 sub-agentes (marketing, growth, automation, marketplace, help). Sin cambios de schema ni de endpoints — solo UX. Constante `DASHBOARD_URLS` en `app/services/app_knowledge.py`, 5 FAQ entries nuevas, 6 entradas en `NO_EXISTE` (anti-alucinación sobre "no respondas con paths desnudos"), `render_short_summary()` con 2 reglas críticas adicionales. Inspirado en feedback directo del usuario: "el link debería ser la ruta completa, para que el usuario pueda entrar fácilmente".
- **v1.9 (19-ago-2026)**: agregado **Automation Manager** (§20 — Cap. 19.3). Cierra el ciclo Growth Coach → Acción. Endpoints `POST /api/v1/automation/preview` (dry-run, genera preview_id) y `POST /api/v1/automation/execute` (requiere `dry_run=false` + `confirmed=true`). 3 acciones MVP en `ActionRegistry`: `create_promotion` (admin+), `create_booking` (staff+), `send_campaign` (admin+). Audit log persistente en nueva tabla `automation_executions` (tenant_id, user_id, action_type, status, resource_id, params JSON). Rate limit propio `ai_daily_automation_limit` (default 50/día/usuario, solo cuenta ejecuciones, NO previews). Preview cache con TTL 10 min + one-shot (anti-CSRF / anti-doble-click). 48 tests passing. Servicio en `app/services/automation_manager.py`, schemas en `app/schemas/automation.py`, modelo en `app/models/automation.py`, endpoint en `app/api/v1/automation.py`. **Inspirado en la recomendación #3 del análisis estratégico del proyecto.**
- **v1.8 (19-ago-2026)**: agregado **Growth Coach** (§19 — Cap. 19.2). Endpoint `POST /api/v1/ai/growth/analyze`. Análisis proactivo de la "Memoria de Negocio" (ventas, inventario, clientes, promociones, reservas). Devuelve `summary` + `insights` priorizados (urgent → low) con `recommended_actions` y `linked_module`. Soporta 7 `focus` (overview, sales, inventory, customers, promotions, bookings, mixed) y `lookback_days` (7-180, default 30). 64 tests passing. Servicio en `app/services/growth_coach.py`, schemas en `app/schemas/ai.py`, endpoint en `app/api/v1/ai.py`. **Inspirado en la recomendación #2 del análisis estratégico del proyecto.** Rate limit compartido con `/chat` y `/marketing/generate`. Fallback determinístico que SIEMPRE produce insights útiles.
- **v1.7 (18-ago-2026)**: agregado **Marketing Studio** (§17). Endpoint `POST /api/v1/ai/marketing/generate`. 13 `intent`, 7 `tone`, 7 `audience`. 47 tests passing. Servicio en `app/services/marketing_studio.py`, schemas en `app/schemas/ai.py`, endpoint en `app/api/v1/ai.py`. **Inspirado en la recomendación #1 del análisis estratégico del proyecto.**
- **v1.6 (17-ago-2026)**: tool `get_tenant_public_urls` (sustituye `{slug}` literal por el slug real del tenant).
- **v1.5 (17-ago-2026)**: FAQ ampliada por categoría + protocolo de incertidumbre + matriz de capacidades.

### 18.2 Roadmap inmediato del AI Core (próximas iteraciones)

Las siguientes features están **planificadas pero NO implementadas**. La IA NO debe prometerlas como disponibles.

| Feature | Estado | Notas |
|---|---|---|
| Streaming SSE real del Marketing Studio | 🛣️ Roadmap | Hoy devuelve JSON único. |
| Persistencia de borradores de copy | 🛣️ Roadmap | Hoy el copy se devuelve pero no se guarda. |
| Programación de publicación | 🛣️ Roadmap | Requiere integración con canales (Instagram, WhatsApp, email). |
| Generación de imágenes con IA | 🛣️ Roadmap | Hoy el Marketing Studio solo genera texto. |
| `send_whatsapp_template` en Automation Manager | 🛣️ Roadmap | Hoy solo email. Roadmap: WhatsApp Cloud API. |
| Acciones con efectos secundarios (p.ej. cancelar reserva) | 🛣️ Roadmap | Hoy MVP solo tiene 3 acciones de creación. |
| Smart Marketplace™ (Cap. 19.4) | 🛣️ Roadmap | Sugerencia de módulos premium según perfil del negocio. |
| Multi-idioma del LLM | 🛣️ Roadmap | Hoy el idioma se pide en el request; en el futuro se detectará del tenant. |
| Métricas de uso del Marketing Studio | 🛣️ Roadmap | Hoy no se persiste qué copy se generó para qué tenant. |
| Dashboard dedicado del Growth Coach | 🛣️ Roadmap | Hoy se renderiza en Resumen / chat. Pendiente panel con histórico. |
| Growth Coach programado / alertas | 🛣️ Roadmap | Hoy es on-demand. Futuras versiones: jobs recurrentes + notificaciones. |

---

## 19. Growth Coach (WowHub AI Core™ — Cap. 19.2)

### 19.1 Qué es

El **Growth Coach** es el módulo de WowHub AI Core™ que **analiza la "Memoria de Negocio"** del tenant (ventas, inventario, clientes, promociones, reservas) y devuelve **insights accionables** priorizados. A diferencia del Marketing Studio (que GENERA copy), el Growth Coach ANALIZA y SUGIERE — la ejecución de las acciones la hace el usuario desde el módulo correspondiente.

**Características clave:**
- Endpoint **atómico**: 1 request → 1 response estructurada (summary + insights + snapshot).
- **Memoria de Negocio** como input: el servicio agrega datos de `StatsService`, `AnalyticsService` y queries directas a `Promotion` / `Booking`.
- **Transparencia anti-alucinación**: la response incluye el `business_memory` (snapshot de los datos que se usaron) para que la UI y el debug vean exactamente qué se miró.
- **LLM + fallback determinístico**: si el LLM está disponible, devuelve insights enriquecidos. Si no, devuelve análisis basado en reglas (10+ escenarios cubiertos) — la UI **nunca rompe**.

### 19.2 Endpoint

```
POST /api/v1/ai/growth/analyze
```

**Auth:** JWT (mismo que `/chat`) + header `X-Tenant-Id`.
**Rate limit:** compartido con `/chat` y `/marketing/generate` (`ai_daily_message_limit`). Si el día ya se consumió, devuelve 429.

### 19.3 Request body

| Campo | Tipo | Default | Descripción |
|---|---|---|---|
| `focus` | enum | `"overview"` | `overview` \| `sales` \| `inventory` \| `customers` \| `promotions` \| `bookings` \| `mixed`. `mixed` = 1-2 insights por categoría. |
| `lookback_days` | int (7-180) | `30` | Ventana de análisis en días. |
| `language` | str (ISO 639-1) | `"es"` | Idioma del summary y de las recomendaciones. |
| `max_insights` | int (3-20) | `8` | Cantidad máxima de insights a devolver. |

**Ejemplo:**

```json
{
  "focus": "overview",
  "lookback_days": 30,
  "language": "es",
  "max_insights": 8
}
```

### 19.4 Response

```json
{
  "id": "uuid",
  "focus": "overview",
  "lookback_days": 30,
  "language": "es",
  "summary": "Tu negocio creció 12% en ventas vs. el mes pasado, pero tienes 3 productos top sin stock.",
  "insights": [
    {
      "id": "uuid",
      "type": "warning",
      "priority": "urgent",
      "category": "inventory",
      "title": "3 productos sin stock",
      "description": "Tres productos top están sin stock hace 5 días.",
      "evidence": ["Café latte: stock=0", "Brownie: stock=0", "Tostado: stock=0"],
      "recommended_actions": [
        "Ir a Productos y reponer los más vendidos primero",
        "Contactar proveedores para reposición urgente"
      ],
      "linked_module": "products",
      "metric_impact_estimate": "Recuperar ventas perdidas por falta de stock"
    }
  ],
  "business_memory": {
    "tenant_id": "...",
    "tenant_name": "Café Luna",
    "tenant_slug": "cafeluna",
    "lookback_days": 30,
    "sales": { "total_orders": 124, "total_revenue_cents": 1500000, ... },
    "inventory": { "low_stock": [...], "out_of_stock": [...], ... },
    "customers": { "total_customers": 80, "segments": {...} },
    "promotions": { "total": 3, "active": 1 },
    "bookings": { "total": 45, "cancellation_rate": 0.08 },
    "data_completeness": { "sales": true, "inventory": true, ... }
  },
  "generated_at": "2026-08-19T01:00:00Z",
  "fallback": false,
  "fallback_reason": null,
  "model": "claude-3-5-sonnet",
  "tokens_in": 1200,
  "tokens_out": 600,
  "latency_ms": 1800
}
```

### 19.5 Categorías de insights (6)

`"sales"` · `"inventory"` · `"customers"` · `"promotions"` · `"bookings"` · `"operations"` (cualquier insight cae en una de estas).

### 19.6 Tipos de insights (5)

`"opportunity"` (oportunidad de crecer) · `"warning"` (alerta que requiere atención) · `"anomaly"` (fuera de patrón) · `"recommendation"` (acción concreta) · `"insight"` (observación informativa).

### 19.7 Prioridades (4)

`"urgent"` (4) > `"high"` (3) > `"medium"` (2) > `"low"` (1). El endpoint SIEMPRE ordena los insights por prioridad descendente.

### 19.8 Fallback determinístico (cuando el LLM no está disponible)

Si el circuit breaker está abierto, no hay API key, el LLM devuelve JSON inválido o cualquier otra falla, se activa un **análisis basado en reglas** que SIEMPRE produce insights útiles:

| Disparador | Prioridad | Categoría | Módulo vinculado |
|---|---|---|---|
| 3+ productos sin stock | `urgent` | `inventory` | `products` |
| 1-2 productos sin stock | `high` | `inventory` | `products` |
| Stock bajo (cualquier cantidad) | `medium` | `inventory` | `products` |
| 3+ productos sin ventas 60+ días (dead stock) | `medium` | `inventory` | `promotions` |
| 3+ clientes inactivos | `high` | `customers` | `marketing_studio` |
| 3+ clientes VIP | `low` | `customers` | `campaigns` |
| 0 promociones creadas (nunca) | `high` | `promotions` | `promotions` |
| Promos creadas pero 0 activas | `medium` | `promotions` | `promotions` |
| Tasa de cancelación de reservas > 20% (con 5+ reservas) | `high` | `bookings` | `bookings` |
| Tenant sin datos en ninguna sección | `high` | `operations` | `products` |

### 19.9 Reglas de uso (anti-alucinación)

- ✅ El LLM SOLO puede usar cifras del snapshot. NO inventa.
- ✅ Las acciones recomendadas son 1-5 por insight, concretas y ejecutables.
- ✅ El endpoint SIEMPRE devuelve 200 — si el LLM falla, devuelve `fallback: true` con un reason (`circuit_open`, `invalid_json`, `unexpected:TypeError`, etc.).
- ❌ NO inventa módulos, rutas ni endpoints. Solo menciona módulos que EXISTEN.
- ❌ NO incluye URLs, links ni "consultar con soporte" salvo para problemas críticos.
- ❌ NO promete cifras exactas en `metric_impact_estimate` (siempre aproximado).
- ❌ NO ejecuta acciones. Sugiere. La ejecución es responsabilidad del usuario o del Automation Manager (futuro).

### 19.10 Cuándo la IA conversacional debe sugerir el Growth Coach

Cuando el sub-agente (especialmente `growth` o `help`) detecte una de estas intenciones, debe **preparar un `GrowthAnalysisRequest`** y sugerir al frontend llamar al endpoint:

- "Analizá mi negocio" / "qué me recomendás" / "cómo viene mi tienda"
- "Por qué bajaron las ventas" / "qué productos están sin stock"
- "Tengo clientes que no compran hace rato" / "qué hago con los inactivos"
- "Necesito ideas para crecer" / "qué oportunidades tengo"
- "Resumen del último mes" / "reporte de actividad"

### 19.11 Anti-alucinación específica del Growth Coach

- ❌ NO ejecuta acciones — solo ANALIZA y SUGIERE.
- ❌ NO se agenda automáticamente — es on-demand.
- ❌ NO tiene un dashboard dedicado en el sidebar.
- ❌ NO persiste análisis ni insights en la base (stateless).
- ❌ NO tiene límite diario propio (compartido con `/chat`).
- ❌ NO genera imágenes, gráficos ni videos — solo texto estructurado.
- ❌ NO reemplaza al Marketing Studio: uno analiza, el otro genera copy.

Ver lista ampliada en §7 ("Cosas que NO existen").

---

## 20. Automation Manager (WowHub AI Core™ — Cap. 19.3)

### 20.1 Qué es

El **Automation Manager** es el módulo que **ejecuta** las `recommended_actions` que devuelve el **Growth Coach** (Cap. 19.2). Es el "puente" entre análisis (Growth Coach) y acción real (crear la promo, agendar la reserva, mandar la campaña).

**Características clave:**
- **3 acciones MVP** en `ActionRegistry` (todas verificadas con Pydantic server-side):
  - `create_promotion` — crea una Promotion. Rol requerido: **admin+** (OWNER, ADMIN).
  - `create_booking` — agenda una reserva vía `BookingService`. Rol requerido: **staff+** (OWNER, ADMIN, STAFF).
  - `send_campaign` — envía campaña de email a un segmento. Rol requerido: **admin+** (OWNER, ADMIN).
- **Vista** (VIEWER) puede **previewear** acciones pero **NO ejecutar**.
- **Preview obligatorio**: el flujo es siempre `POST /preview` (dry-run, devuelve `preview_id`) → `POST /execute` (con `dry_run=false`, `confirmed=true` y el `preview_id` recibido).
- **Audit log persistente**: cada ejecución (exitosa o fallida) escribe una fila en `automation_executions` (tenant_id, user_id, action_type, status, resource_id, resource_url, params JSON, error). Accesible vía `GET /history`.
- **Rate limit propio**: `ai_daily_automation_limit` (default **50/día/usuario**, configurable). Cuenta **solo ejecuciones**, NO previews.
- **Anti-CSRF / anti-doble-click**: el `preview_id` se valida contra un cache server-side con TTL 10 min, es **one-shot** (se consume al ejecutar) y rechaza drift de params (si los params cambiaron entre preview y execute, falla con `preview_drift`).
- **Tenant isolation**: el `tenant_id` SIEMPRE se toma del JWT (vía `TenantMembership`), NUNCA del body. Esto cierra el vector cross-tenant write.

### 20.2 Endpoints

| Método | Path | Descripción |
|---|---|---|
| `GET` | `/api/v1/automation/actions` | Lista de acciones disponibles (catálogo). |
| `GET` | `/api/v1/automation/actions/{action_type}` | Detalle de una acción (label, descripción, schema, ejemplo). |
| `POST` | `/api/v1/automation/preview` | Genera un preview (dry-run, NO toca DB). Devuelve `preview_id`. |
| `POST` | `/api/v1/automation/execute` | Ejecuta (requiere `dry_run=false` + `confirmed=true`). |
| `GET` | `/api/v1/automation/history` | Historial paginado del tenant (filtros: `action_type`, `status`). |

### 20.3 Flujo recomendado (UX)

```
1. Usuario ve un insight del Growth Coach con recommended_action:
   "Crear una promo 2x1 en Cafés del 20 al 27 de agosto"
2. Frontend llama:
   POST /api/v1/automation/preview {
     "action_type": "create_promotion",
     "params": { "name": "2x1 Cafés", "discount_type": "percent",
                 "discount_value": 50, "category_ids": [...], ... }
   }
3. Backend devuelve:
   { "preview_id": "abc123", "result": {
       "preview": "Vas a crear la promoción 2x1 Cafés:\n  • ...",
       "status": "preview_ready"
     }
   }
4. UI muestra un modal con el preview + botones [Cancelar] [Ejecutar]
5. Usuario hace clic en [Ejecutar]:
   POST /api/v1/automation/execute {
     "action_type": "create_promotion",
     "params": { ... mismo params ... },
     "dry_run": false,
     "confirmed": true,
     "preview_id": "abc123"
   }
6. Backend:
   - Valida JWT + tenant
   - Valida permisos (rol)
   - Verifica rate limit
   - Valida preview_id (one-shot, TTL, no-drift)
   - Ejecuta el handler
   - Escribe audit log en `automation_executions`
   - Devuelve { "result": { "resource_id": "promo-uuid", "resource_url": "/dashboard/promotions/promo-uuid" } }
```

### 20.4 Anti-alucinación específica del Automation Manager

- ❌ NO ejecuta acciones sin `confirmed=true` Y `dry_run=false` simultáneos. Sin esto → 400 `confirmation_required`.
- ❌ NO acepta acciones fuera del `ActionRegistry` (el `ActionType` es `Literal` cerrado; valores no listados → 422 por Pydantic).
- ❌ NO usa el `tenant_id` del body — siempre del JWT (cierre cross-tenant).
- ❌ NO cuenta previews contra el rate limit (solo ejecuciones).
- ❌ NO permite re-ejecutar un `preview_id` ya consumido (one-shot).
- ❌ NO permite ejecutar con params distintos al preview (anti-drift).
- ❌ NO persiste `params` en el listado de historial expuesto al cliente (privacidad). Solo el superadmin puede verlos.
- ❌ NO hace rollback del audit log en ejecuciones fallidas (queremos ver el intento).
- ❌ NO tiene WhatsApp todavía (solo email vía `send_campaign`).
- ❌ NO es un orquestador de jobs recurrentes (no cron, no scheduler — es on-demand).
- ❌ NO tiene un panel de "historial" dedicado en el sidebar — se consulta vía `GET /history` desde el módulo de cada recurso o desde el chat.
- ❌ NO incluye acciones destructivas (no hay `cancel_booking`, `delete_promotion` en MVP).

Ver lista ampliada en §7 ("Cosas que NO existen").

---

## 21. Dashboard URLs clickeables (WowHub AI Core™ — v1.9.1)

### 21.1 Qué es

**Micro-release UX** sobre v1.9. La IA ahora devuelve los links del panel como **URLs absolutas clickeables** (ej. `https://wowhub.app/dashboard/products`) en vez de paths relativos desnudos (ej. `/dashboard/products`). Esto permite que el usuario haga **1 click** desde el chat, email, WhatsApp, SMS o cualquier otro canal — sin tener que abrir primero el dashboard y navegar manualmente.

**Cambia solo UX.** No hay nuevos endpoints, no hay nuevos schemas, no hay cambios en la DB. Es una **tool nueva** (`get_tenant_dashboard_urls`) más un cambio de comportamiento en el system prompt.

### 21.2 La nueva tool

```
get_tenant_dashboard_urls(ctx: AIToolContext) → dict
```

- **No es HTTP.** Lee de `app_knowledge` + `settings.public_base_url`.
- **Devuelve** un dict con:
  - `base_url` — el `public_base_url` configurado (ej. `https://wowhub.app`).
  - `dashboard_urls` — lista de los 13 módulos del panel con `key`, `label`, `url` (absoluta), `description`, `requires_role`.
  - `hint` — recordatorio de que el LLM debe mostrarlos como markdown `[texto](url)`.

**Disponible para los 5 sub-agentes:** `marketing`, `growth`, `automation`, `marketplace`, `help`.

### 21.3 Diferencia con `get_tenant_public_urls`

| Aspecto | `get_tenant_public_urls` | `get_tenant_dashboard_urls` |
|---|---|---|
| URLs | Públicas (landing, /reservar, /catalogo) | Panel autenticado (/dashboard/*) |
| **Prefijo** | `https://wowhub.app/u/{slug}` (**path-based**, no subdominio) | `https://wowhub.app/dashboard/*` (mismo para todos) |
| Requiere slug | Sí (sustituye `{slug}` en el path) | No (mismas rutas para todos) |
| Contexto | Multi-tenant (cada tienda la suya) | Single-tenant (sesión resuelve) |
| Uso típico | "Pásame mi link para compartir" | "Cómo abro el panel de productos" |

> **v1.9.1-r3 — corrección crítica:** WowHub **NO usa subdominios** por tenant (no existe `{slug}.wowhub.app`). El formato correcto es **path-based**: `https://wowhub.app/u/{slug}/...`. Esto aplica a TODAS las URLs públicas (landing, catálogo, reservar, loyalty). La tabla de arriba ya refleja el formato correcto. Si el AI Core o cualquier documento muestra `https://barberia-juan.wowhub.app/...` es un error — corregir de inmediato.

### 21.4 Reglas críticas (anti-alucinación)

- ❌ **NO respondas con paths desnudos** tipo `/dashboard/products`. Fuera del SPA no es clickeable. SIEMPRE llama a la tool y devuelve la URL absoluta.
- ❌ **NO inventes la URL base** del panel. SIEMPRE usa la que devuelve `get_tenant_dashboard_urls` (que lee `settings.public_base_url`). No hardcodees `wowhub.app` ni `localhost` ni `railway.app`.
- ❌ **NO incluyas el slug del tenant** en el path del panel. Las URLs del panel son las MISMAS para todos los tenants (ej. `https://wowhub.app/dashboard/products`) — el contexto multi-tenant lo da la sesión/JWT, no el subdominio.
- ❌ **NO confundas** `get_tenant_public_urls` (URLs públicas, requieren slug) con `get_tenant_dashboard_urls` (URLs del panel autenticadas, misma URL para todos los tenants).
- ✅ **Muestra los links como markdown** `[Abrir Productos](https://wowhub.app/dashboard/products)` para que sean clickeables.
- ✅ **Si la tool falla** (raro, `settings.public_base_url` no configurado), avísale al usuario y sugiere Configuración → Branding.

### 21.5 Ejemplo de respuesta correcta

**Antes (v1.9):**
> Tu cuenta está vacía. Carga productos en `/dashboard/products` para empezar.

**Después (v1.9.1):**
> Tu cuenta está vacía. Carga productos en **[Abrir Productos](https://wowhub.app/dashboard/products)** para empezar.

### 21.6 Implementación

- `app/services/ai_tools.py` — `tool_get_tenant_dashboard_urls()` + schema + dispatch + agregado a los 5 agentes.
- `app/services/app_knowledge.py` — constante `DASHBOARD_URLS` (documentativa), 5 FAQ entries, 6 entradas en `NO_EXISTE`, `render_short_summary()` con 2 reglas críticas.
- `docs/CANONICAL_WOWHUB.md` §21 (esta sección).
- **Tests:** `tests/test_tenant_dashboard_urls.py` — cobertura de tool + render + anti-alucinación.
- **Sin migración de DB** — solo código Python + docs.

### 21.7 Roadmap

- 🛣️ Cachear el resultado en el contexto del chat (hoy se llama cada vez; es barato pero podría evitarse).
- 🛣️ Versionar `public_base_url` por tenant (hoy es global; futuro: cada tienda puede tener su propio dominio custom).
- 🛣️ Deep links con query params (ej. `?utm_source=ai&action=create_promotion` para analytics).

---

## 22. Anti-alucinación de URLs (WowHub AI Core™ — v1.9.1-r2)

**Problema detectado en producción:** el AI Core devolvía al usuario URLs con placeholders literales (ej. `wowhub.app/u/tu-negocio/reservar`) o paths desnudos del panel (ej. `/dashboard/products`) que NO son clickeables fuera del SPA. El usuario copiaba el link, lo pegaba en WhatsApp, y llegaba a una página inexistente. Eso deteriora la confianza en el producto.

Esta sección es la fuente de verdad de qué es y qué NO es una URL válida en una respuesta del AI, y cómo debe resolverse cada caso.

### 22.1 Tipos de URL en WowHub (v1.9.1-r4)

> **v1.9.1-r4 — Cambio de modelo:** En producción **NO hay panel HTML público**. Las rutas `/dashboard/*` y `/admin/*` están en `app/main.py` (código de desarrollo) pero NO están desplegadas. Por eso:
>
> 1. La IA **NO debe entregar links `/dashboard/...` como URLs públicas**. Esos links NO existen para clientes externos.
> 2. La tool `get_tenant_dashboard_urls` está **DEPRECADA**.
> 3. La única tool de URLs vigente es `get_tenant_public_urls`.

| Tipo | Tool a invocar | Ejemplo real | Notas |
|---|---|---|---|
| **URL pública del tenant** (perfil, catálogo, producto, promociones, categorías, sucursales, landing, QR) | `get_tenant_public_urls` | `https://wowhub-api-production.up.railway.app/api/v1/public/t/cafeluna/catalog` | El slug sale del backend, NUNCA se escribe a mano. Formato `/api/v1/public/t/{slug}/...` (NO `/u/{slug}/...`). |
| **URL corta de QR** | `get_tenant_public_urls` (key=`qr_redirect`) | `https://wowhub-api-production.up.railway.app/r/abc123` | 302 al destino configurado. |
| **Panel autenticado** (gestión interna) | **(DEPRECADA en v1.9.1-r4)** | n/a | La gestión interna se hace vía API autenticada con JWT. NO hay link público para compartir con clientes. |

### 22.2 Formato de respuesta obligatorio

**SIEMPRE** que el AI devuelva un link, el formato debe ser:

```markdown
[Texto del feature](https://wowhub-api-production.up.railway.app/api/v1/public/t/cafeluna/catalog)
```

- `[Texto]` describe la acción o el destino.
- `(https://...)` es la URL ABSOLUTA con el prefijo real.
- El prefijo sale SIEMPRE de `settings.public_base_url` (default: `https://wowhub-api-production.up.railway.app`).
- El slug y el subpath salen SIEMPRE de `get_tenant_public_urls`.

### 22.3 Lo que NUNCA debe aparecer en una respuesta del AI

| Prohibido | Por qué | Qué hacer en su lugar |
|---|---|---|
| `wowhub.app/u/tu-negocio/reservar` | El placeholder `tu-negocio` no existe como dominio. Link FALSO. | Llamar `get_tenant_public_urls`. |
| `wowhub.app/u/{slug}/reservar` | El `{slug}` literal no se sustituye en el frontend. | Llamar `get_tenant_public_urls`. |
| `/u/{slug}/reservar` (cualquier variante: book, menu, pedido, catalogo, perfil) | **El prefijo `/u/{slug}/...` está MUERTO**. Da 404 en producción. | Usar el formato `/api/v1/public/t/{slug}/...`. |
| `/dashboard/products` (path desnudo) | No existe como link público en producción. | Decir "no hay panel HTML público; la gestión se hace vía API autenticada". |
| `https://wowhub.app/dashboard/products` | El dominio `wowhub.app` no responde (NXDOMAIN). | Usar `settings.public_base_url` (default `https://wowhub-api-production.up.railway.app`). |
| `https://wowhub.app/u/...` | El dominio no responde y el formato está muerto. | Idem. |
| `localhost:3000/dashboard/products` | Solo dev. NUNCA en producción. | Idem. |
| "Reemplaza `{slug}` por el nombre de tu negocio" | Obliga al usuario a hacer trabajo del AI. | Llamar la tool y devolver el link YA armado. |

### 22.4 Reglas duras (Regla 10 en `_GLOBAL_RULES`) — v1.9.1-r4

Cuando el usuario pida un link, una URL, un paso a paso con navegación, o quiera compartir por WhatsApp/email/SMS, el AI debe:

1. **Identificar QUÉ feature pide el usuario** (público: perfil/catálogo/producto/promo/QR — vs interno: gestión del tenant). Consultar §2.1 y §3.
2. **Si es público** → llamar `get_tenant_public_urls`. **NUNCA** llamar `get_tenant_dashboard_urls` (está DEPRECADA).
3. **Si es interno** → explicarle al usuario que WowHub es una API y que la gestión la hace él desde su sesión autenticada (vía `GET/POST/PATCH/DELETE /api/v1/tenants/{tid}/...` con JWT). NO entregar un link público porque NO existe.
4. **Mostrar el resultado como markdown** `[Texto](https://...)`.
5. **Si la tool falla o el tenant no tiene slug**, decir: "Ahora no puedo obtener tu link público. Primero andá a la configuración de tu tenant y definí tu slug". **NO inventar** el slug ni el dominio.

### 22.5 Ejemplo de respuesta correcta vs incorrecta

**❌ Incorrecto (v1.9.1):**
> Anda a `/dashboard/products` para cargar productos. Tu link público es `wowhub.app/u/tu-negocio/catalogo`.

**✅ Correcto (v1.9.1-r2):**
> Abre [Productos](https://wowhub.app/dashboard/products) desde el menú lateral. Para compartir tu tienda, usa tu link público: [Ver catálogo](https://wowhub.app/u/cafeluna/catalogo).

### 22.6 Anti-placeholder — lista taxativa de palabras prohibidas en URLs

NUNCA debe aparecer ninguna de estas como parte de una URL en una respuesta del AI:

- `tu-negocio`, `tu-tienda`, `tu-empresa`, `tu-sucursal`, `tu-restaurante`
- `mi-negocio`, `mi-tienda`, `mi-empresa`, `mi-sucursal`
- `my-business`, `my-shop`, `my-store`
- `<slug>`, `{slug}`, `[slug]`, `[tu-slug]`, `<tu-slug>`
- `ejemplo`, `example`, `test-slug`, `sample`

El slug real del tenant sale SOLO de `get_tenant_public_urls`. Una URL con placeholder es directamente una URL FALSA.

### 22.7 Anti-dominio — dominios prohibidos hardcodeados

NUNCA debe aparecer ninguno de estos como prefijo de una URL en una respuesta del AI:

- `wowhub-api-production.up.railway.app` (backend de Railway, no público)
- `localhost`, `127.0.0.1` (solo dev)
- `wowhub.app` (puede aparecer como parte de la URL, pero SOLO si vino de la tool, no si fue escrito a mano)

El prefijo sale SIEMPRE de `settings.public_base_url` (default: `https://wowhub.app`).

### 22.8 Implementación

- `app/services/ai_agents.py` — Regla 10 en `_GLOBAL_RULES` (concatenada a los 5 sub-agents).
- `app/services/ai_agents.py` — `fallback` de los 5 sub-agents con ejemplos de links clickeables.
- `app/services/app_knowledge.py` — 4 entradas nuevas en `NO_EXISTE` (anti-placeholder, anti-path, anti-dominio, anti-confusion).
- `app/services/app_knowledge.py` — 3 líneas nuevas en `render_short_summary()` (anti-placeholder, anti-dominio, formato markdown).
- `app/services/ai_tools.py` — `description` reforzado de `get_tenant_public_urls` y `get_tenant_dashboard_urls` (mencionan explícitamente placeholders prohibidos y dominio no hardcodeado).
- `app/services/ai_tools.py` — `hint` de la tool reformulado (sin ejemplo literal de path que pueda confundir al LLM).
- `app/config.py` — default de `public_base_url` cambiado a `https://wowhub.app`.
- `.env` — `PUBLIC_BASE_URL` actualizado a `https://wowhub.app`.
- **Tests:** `tests/test_tenant_dashboard_urls.py` — clase `TestAbsoluteURLsRegression` con 8 tests nuevos.

### 22.9 Roadmap

- 🛣️ Validar al runtime que toda URL devuelta por el AI (cuando se renderiza en el chat) matchee el patrón `^https://wowhub\.app/...` antes de enviarla al frontend. Si no matchea, sanitizar.
- 🛣️ Penalizar en el feedback loop cuando el usuario edita la URL que el AI le dio.
- 🛣️ Soportar dominio custom por tenant (ej. `tienda.com` en vez de `wowhub.app/u/cafeluna`).
