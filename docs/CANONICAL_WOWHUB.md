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
| **Admin IA** | `/dashboard/admin/ai` | Métricas, logs, trazas, circuit breaker. (Solo OWNER/ADMIN) | No | (n/a, es la IA misma) |

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
- Próxima: cuando se agregue el módulo de Fidelización a tools IA.
