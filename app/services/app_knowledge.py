"""Fuente de verdad (estructurada) sobre WowHub para el asistente IA.

Este módulo es la contraparte Python del documento canónico
`docs/CANONICAL_WOWHUB.md`. Se carga en runtime y se sirve a través de
la tool `get_app_help`. Cualquier módulo nuevo que se agregue al
producto DEBE reflejarse aquí y en el documento.

Regla de oro: ningún módulo de WowHub requiere activación.
"""
from __future__ import annotations

from typing import Any


# ── 1. Módulos del dashboard ──────────────────────────────────────
MODULES: list[dict[str, Any]] = [
    {
        "key": "resumen",
        "label": "Resumen",
        "path": "/dashboard",
        "description": "KPIs, ventas, productos top, agenda de hoy.",
        "requires_activation": False,
        "ai_tools": ["get_stats_overview"],
    },
    {
        "key": "productos",
        "label": "Productos",
        "path": "/dashboard/products",
        "description": "Catálogo, stock, precios, categorías, imágenes.",
        "requires_activation": False,
        "ai_tools": ["list_products", "analyze_inventory"],
    },
    {
        "key": "promociones",
        "label": "Promociones",
        "path": "/dashboard/promotions",
        "description": "Motor de descuentos, combos, campañas activas.",
        "requires_activation": False,
        "ai_tools": ["list_promotions", "create_promotion"],
    },
    {
        "key": "clientes",
        "label": "Clientes",
        "path": "/dashboard/customers",
        "description": "Base de clientes, tags, puntos de fidelización.",
        "requires_activation": False,
        "ai_tools": ["list_customers", "get_customer_segments"],
    },
    {
        "key": "pedidos",
        "label": "Pedidos / Ventas",
        "path": "/dashboard/orders",
        "description": "Órdenes, estados, ticket promedio.",
        "requires_activation": False,
        "ai_tools": [],
    },
    {
        "key": "reservas",
        "label": "Reservas",
        "path": "/dashboard/bookings",
        "description": "Agenda, KPIs, filtros, modal nueva reserva. Disponible para todos los tenants sin activación.",
        "requires_activation": False,
        "ai_tools": ["list_bookings", "check_availability", "create_booking"],
    },
    {
        "key": "campanas",
        "label": "Campañas",
        "path": "/dashboard/campaigns",
        "description": "Segmentos y envíos de email masivo.",
        "requires_activation": False,
        "ai_tools": ["send_campaign", "get_customer_segments"],
    },
    {
        "key": "sucursales",
        "label": "Sucursales",
        "path": "/dashboard/branches",
        "description": "Sedes, horarios (hours JSON), ubicación.",
        "requires_activation": False,
        "ai_tools": ["get_tenant_info"],
    },
    {
        "key": "fidelizacion",
        "label": "Fidelización",
        "path": "/dashboard/loyalty",
        "description": "Programas de puntos y sellos.",
        "requires_activation": False,
        "ai_tools": [],
    },
    {
        "key": "qr",
        "label": "QR",
        "path": "/dashboard/qr",
        "description": "Códigos QR para tienda física.",
        "requires_activation": False,
        "ai_tools": [],
    },
    {
        "key": "configuracion",
        "label": "Configuración",
        "path": "/dashboard/settings",
        "description": "Datos del tenant, branding, integraciones, Mi cuenta.",
        "requires_activation": False,
        "ai_tools": ["get_tenant_info"],
    },
    {
        "key": "admin_ia",
        "label": "Admin IA",
        "path": "/admin/ai",
        "description": "Métricas, logs, trazas, circuit breaker. Solo OWNER/ADMIN (guard server-side).",
        "requires_activation": False,
        "ai_tools": [],
    },
    {
        "key": "superadmin",
        "label": "SUPERADMIN",
        "path": "/admin/superadmin",
        "description": "Panel de plataforma: KPIs globales, gestión de tiendas, usuarios, auditoría. Solo para usuarios con `is_superuser=True` (a nivel de USUARIO, no de membresía). Guard server-side.",
        "requires_activation": False,
        "ai_tools": [],
    },
]


# ── 2. URLs públicas (sin auth) ───────────────────────────────────
PUBLIC_URLS: list[dict[str, str]] = [
    {
        "key": "landing",
        "pattern": "/u/{slug}",
        "description": "Landing pública del negocio. {slug} = identificador del tenant.",
    },
    {
        "key": "catalogo",
        "pattern": "/u/{slug}/catalogo",
        "description": "Catálogo público de productos sin login.",
    },
    {
        "key": "reservar",
        "pattern": "/u/{slug}/reservar",
        "description": "Flujo público de reservas: branch → fecha/hora → datos.",
    },
    {
        "key": "reservar_alias",
        "pattern": "/u/{slug}/book",
        "description": "Alias en inglés de /reservar.",
    },
]


# ── 3. Auth y cuenta ──────────────────────────────────────────────
AUTH_INFO: list[dict[str, str]] = [
    {"action": "Iniciar sesión", "how": "POST /api/v1/auth/login"},
    {"action": "Registrarme", "how": "POST /api/v1/auth/register"},
    {"action": "Cambiar contraseña", "how": "Dashboard → Configuración → Mi cuenta, o POST /api/v1/auth/password"},
    {"action": "Recuperar contraseña", "how": "POST /api/v1/auth/password/reset (envía email con token)"},
    {"action": "Refrescar token", "how": "POST /api/v1/auth/refresh"},
    {"action": "Cerrar sesión", "how": "POST /api/v1/auth/logout"},
    {"action": "Crear otro tenant", "how": "No se hace desde el chat. Ir a la landing o usar link de referido."},
]


# ── 4. FAQ rápidas (overrides literales) ──────────────────────────
FAQ: dict[str, str] = {
    "cómo activo Reservas": (
        "Reservas no requiere activación. Está disponible para todos los tenants. "
        "Ve directo a /dashboard/bookings desde el menú lateral."
    ),
    "cómo activo reservaciones": (
        "Reservas no requiere activación. Está disponible para todos los tenants. "
        "Ve directo a /dashboard/bookings desde el menú lateral."
    ),
    "cómo activo reservas": (
        "Reservas no requiere activación. Está disponible para todos los tenants. "
        "Ve directo a /dashboard/bookings desde el menú lateral."
    ),
    "qué módulos hay": (
        "WowHub tiene 13 módulos en el panel: Resumen, Productos, Promociones, "
        "Clientes, Pedidos, Reservas, Campañas, Sucursales, Fidelización, QR, "
        "Configuración, Admin IA y SUPERADMIN. Los 12 primeros están disponibles sin activación. "
        "SUPERADMIN es exclusivo para usuarios con `is_superuser=True` y no se muestra en el sidebar "
        "de los demás usuarios."
    ),
    # ── Automation Manager (Cap. 19.3) — FAQ ──
    "qué es el automation manager": (
        "El Automation Manager es el módulo que EJECUTA las recomendaciones "
        "que devuelve el Growth Coach. Cierra el ciclo análisis→acción. "
        "3 acciones MVP: create_promotion, create_booking, send_campaign. "
        "SIEMPRE requiere preview antes de ejecutar, escribe audit log y "
        "tiene rate limit propio (50/día/usuario)."
    ),
    "cómo ejecuto una acción del growth coach": (
        "Flujo: 1) El Growth Coach devuelve un insight con `recommended_action`. "
        "2) El frontend llama POST /api/v1/automation/preview con la action y los params. "
        "3) Muestras el preview al usuario en un modal. "
        "4) Si confirma, llamas POST /api/v1/automation/execute con `dry_run=false`, "
        "`confirmed=true` y el `preview_id` que devolvió el preview. "
        "El backend valida, ejecuta y devuelve el `resource_id` creado."
    ),
    "qué acciones puedo automatizar": (
        "Hoy 3 acciones en MVP: `create_promotion` (admin+), "
        "`create_booking` (staff+), `send_campaign` (admin+, email a un segmento). "
        "Próximamente: `send_whatsapp_template` (roadmap)."
    ),
    "cuál es el límite de automation": (
        "El límite es configurable vía `ai_daily_automation_limit` "
        "(default 50/día/usuario). Cuenta SOLO ejecuciones confirmadas, "
        "NO previews. Si te pasás, el backend devuelve 429 con código `rate_limited`."
    ),
    "puedo ver el historial de automatizaciones": (
        "Sí. GET /api/v1/automation/history devuelve el historial paginado "
        "del tenant. Filtros: `action_type`, `status`. El listado NO expone "
        "`params` (privacidad); el superadmin puede verlos en /admin/superadmin."
    ),
    # ── Dashboard URLs (v1.9.1) — UX fix: links clickeables ──
    "cómo abro el panel de productos": (
        "Llama primero a la tool `get_tenant_dashboard_urls`. Te devuelve "
        "los links YA CON la URL absoluta armada (ej. "
        "https://wowhub.app/dashboard/products) listos para mostrar con "
        "markdown `[Abrir Productos](url)` y que el usuario haga 1 click. "
        "NUNCA respondas con `/dashboard/products` desnudo — fuera del SPA "
        "no es clickeable. Si la tool falla, sugiere Configuración → Branding."
    ),
    "cómo abro el panel de": (
        "Llama primero a `get_tenant_dashboard_urls`. Te devuelve todos "
        "los links del panel con la URL absoluta (no el path relativo) "
        "para que sean clickeables. NUNCA respondas con paths desnudos."
    ),
    "dónde veo el admin ia": (
        "Llama a `get_tenant_dashboard_urls` y devuelve el link de Admin IA "
        "armado como markdown. Solo OWNER/ADMIN pueden acceder. Si el "
        "usuario es STAFF/VIEWER, dile que necesita permisos de admin."
    ),
    "pásame el link de": (
        "Llama a `get_tenant_dashboard_urls` y devuelve el link armado como "
        "markdown `[texto](https://wowhub.app/dashboard/...)` para que sea "
        "clickeable. NUNCA respondas con el path desnudo tipo "
        "`/dashboard/products`."
    ),
    "mándame el link por": (
        "Llama a `get_tenant_dashboard_urls` y devuelve el link ABSOLUTO. "
        "Como es una URL completa (no path relativo), el usuario puede "
        "compartirla por WhatsApp, email, SMS, etc."
    ),
    "dónde cambio mi contraseña": (
        "Ve a Configuración → Mi cuenta, o usa el botón Cambiar contraseña "
        "en tu perfil."
    ),
    "dónde veo mis ventas": (
        "En el menú lateral, Resumen, o directo en /dashboard."
    ),
    "cómo creo una promoción": (
        "Puedo crearla por ti. Dime: nombre, descuento (% o monto), fechas. "
        "Te muestro el preview antes de guardar."
    ),
    "cómo creo una reserva": (
        "Puedo agendarla. Necesito: cliente, sucursal, fecha, hora, duración. "
        "Te muestro el preview antes de guardar."
    ),
    "url pública": (
        "SIEMPRE llama primero a la tool `get_tenant_public_urls`. Te "
        "devuelve los links YA con el slug real sustituido (ej. "
        "https://wowhub.app/u/cafeluna/reservar) listos para mostrar y "
        "compartir. NUNCA respondas con el patrón de placeholder, NUNCA "
        "pidas al usuario que reemplace el slug a mano, NUNCA inventes "
        "el slug. Si la tool falla, di que ahora no puedes obtener el "
        "link y sugiere Configuración → Branding. Patrones que usa esa "
        "tool internamente: el de reservas y el de book, con /u/ y el "
        "slug del tenant — pero esos son para la tool, no para tu "
        "respuesta."
    ),
    "no me deja entrar": (
        "Verifica que tu sesión esté iniciada y que el chip de usuario del topbar "
        "muestre el tenant correcto. Si persiste, contáctanos."
    ),
    "cómo cambio el idioma": (
        "Por ahora WowHub está en español. La función multi-idioma está en roadmap."
    ),
    "cómo cambio el logo": (
        "En Configuración → Branding (subir imagen, máximo 2 MB)."
    ),
    "cuánto cuesta": (
        "Depende del plan. Revisa la sección de Planes en la landing o pregúntale "
        "al equipo de ventas."
    ),
    "eliminar mi cuenta": (
        "Por seguridad, la eliminación de cuenta se hace escribiendo a "
        "soporte@wowhub.app."
    ),
    "cómo conecto whatsapp": (
        "En Configuración → Integraciones (cuando esté disponible). Hoy puedes "
        "compartir el link público por WhatsApp manualmente."
    ),
    "marketing studio": (
        "El Marketing Studio es el endpoint POST /api/v1/ai/marketing/generate "
        "del AI Core. Genera copy de marketing contextual al tenant (negocio + "
        "producto + ciudad + tono + audiencia) con N variantes y hashtags. Si "
        "el LLM no está disponible, devuelve un template con fallback=true. "
        "NO genera imágenes ni persiste el copy — solo devuelve texto listo "
        "para usar. Comparte rate limit con /chat."
    ),
    "copy de marketing": (
        "Usa el Marketing Studio: POST /api/v1/ai/marketing/generate. Indica "
        "intent (instagram_post, whatsapp_broadcast, email_subject, etc.), "
        "topic (el tema), tone y audience. Te devuelve variantes listas. "
        "NO se guarda el copy en la base — solo se devuelve."
    ),
    "copy para instagram": (
        "El Marketing Studio puede generarlo: POST /api/v1/ai/marketing/generate "
        "con intent=instagram_post. Devuelve N variantes con hashtags. Si quieres "
        "story corto, usa intent=instagram_story. Para Reel, intent=instagram_reel."
    ),
    "asunto de email": (
        "El Marketing Studio puede redactarlo: POST /api/v1/ai/marketing/generate "
        "con intent=email_subject (asunto corto) o intent=email_body (cuerpo). "
        "Indica tone (ej. professional, friendly) y audience."
    ),
    "copy para whatsapp": (
        "El Marketing Studio puede generarlo: POST /api/v1/ai/marketing/generate "
        "con intent=whatsapp_broadcast (difusión) o intent=whatsapp_status "
        "(estado de 24h). Para SMS, intent=sms (≤160 chars)."
    ),
    "imagen con ia": (
        "Hoy el Marketing Studio solo genera texto. La generación de imágenes "
        "y videos está en roadmap. NO prometas esa función."
    ),
    "cuántas variantes": (
        "De 1 a 5 variantes, con variants=N (default 3). Cada variante es una "
        "versión distinta del mismo copy con el mismo intent/tone/audience."
    ),
    "límite diario marketing": (
        "El Marketing Studio NO tiene límite propio: comparte el contador "
        "diario con /api/v1/ai/chat. Si ya usaste todos tus mensajes del día, "
        "devuelve 429 antes de llamar al LLM."
    ),
}


# ── 5. Cosas que NO existen (anti-alucinación) ─────────────────────
NO_EXISTE: list[str] = [
    "No existe Configuración → Módulos ni Activación de funciones.",
    "No existe un toggle Activar/Desactivar Reservas o Promociones.",
    "No hay que contactar a soporte para habilitar algo.",
    "No hay espera 24-48 horas para la activación.",
    "No hay un Asistente Premium o Modo Pro para la IA.",
    "No hay un Marketplace de integraciones todavía (WhatsApp, Stripe, etc. están en roadmap).",
    "No hay Exportar a Excel nativo por ahora (solo CSV desde el panel).",
    "No hay Cambiar de plan desde el chat.",
    "No hay Multi-idioma todavía.",
    "No hay Borrar tenant desde el chat.",
    "No hay creación de tenant desde el chat.",
    "SUPERADMIN no es un módulo 'premium' ni requiere plan especial: es un rol a nivel de usuario (is_superuser=True), separado de los roles de membresía (OWNER/ADMIN/STAFF/VIEWER).",
    "Solo los usuarios con is_superuser=True ven el link 'SUPERADMIN' en el sidebar y pueden acceder a /admin/superadmin.",
    "El Marketing Studio NO genera imágenes ni videos — solo texto. La generación de assets visuales está en roadmap.",
    "El Marketing Studio NO persiste el copy generado — solo lo devuelve en la response. La persistencia es responsabilidad del frontend o de futuras features.",
    "El Marketing Studio NO tiene límite diario propio: comparte el contador con /api/v1/ai/chat (mismo recurso LLM).",
    "El Marketing Studio NO permite programar publicaciones — solo genera el copy. Programar/enviar es otra feature (roadmap).",
    "El Marketing Studio NO detecta el idioma automáticamente — el idioma se pide en el request (default 'es').",
    # ── Automation Manager (Cap. 19.3) — anti-alucinación ──
    "El Automation Manager NO ejecuta acciones sin `confirmed=true` Y `dry_run=false` simultáneos. Sin esto → 400 confirmation_required.",
    "El Automation Manager NO acepta acciones fuera del ActionRegistry (ActionType es Literal cerrado; valores no listados → 422 por Pydantic).",
    "El Automation Manager NO usa el tenant_id del body — siempre del JWT (cierre cross-tenant).",
    "El Automation Manager NO cuenta previews contra el rate limit — solo ejecuciones.",
    "El Automation Manager NO permite re-ejecutar un preview_id ya consumido (one-shot, anti-doble-click).",
    "El Automation Manager NO permite ejecutar con params distintos al preview (anti-drift).",
    "El Automation Manager NO tiene WhatsApp todavía — solo email vía send_campaign. send_whatsapp_template está en roadmap.",
    "El Automation Manager NO es un orquestador de jobs recurrentes — no cron, no scheduler. Es on-demand.",
    "El Automation Manager NO tiene un panel de historial dedicado en el sidebar — se consulta vía GET /automation/history.",
    "El Automation Manager NO incluye acciones destructivas (no hay cancel_booking, delete_promotion en MVP).",
    "El Automation Manager NO hace rollback del audit log en ejecuciones fallidas — queremos ver el intento (sí hace rollback del resource).",
    "El preview del Automation Manager NO toca la DB — es un dry_run puro que devuelve un texto legible y un preview_id con TTL 10 min.",
    # ── Dashboard URLs (v1.9.1) — anti-alucinación ──
    "Las rutas del panel (ej. /dashboard/products) NO son URLs absolutas. Para que sean clickeables fuera del SPA, SIEMPRE llama primero a la tool `get_tenant_dashboard_urls` que las arma con `settings.public_base_url` como prefijo.",
    "El AI NO debe inventar la URL base del panel. SIEMPRE usa la que devuelve `get_tenant_dashboard_urls` (que lee `settings.public_base_url`). No hardcodees `wowhub.app` ni `localhost`.",
    "El AI NO debe responder con paths desnudos como `/dashboard/products` cuando el usuario pide un link. Eso no es clickeable en WhatsApp/email/SMS. USA SIEMPRE la tool y devuelve el link completo.",
    "Las URLs del panel son las MISMAS para todos los tenants (ej. https://wowhub.app/dashboard/products) — el contexto multi-tenant lo da la sesión/JWT, no el subdominio. NO incluyas el slug del tenant en el path.",
    "El AI NO debe incluir `/u/{slug}/` en los links del panel — eso es para URLs PÚBLICAS. Para el panel, el prefijo es solo `https://wowhub.app/dashboard/...`.",
    "El AI NO debe confundir `get_tenant_public_urls` (URLs públicas, requieren slug) con `get_tenant_dashboard_urls` (URLs del panel autenticadas, misma URL para todos los tenants).",
    # ── Anti-placeholder (v1.9.1-r2) — placeholders literales prohibidos ──
    "NUNCA uses placeholders literales como 'tu-negocio', 'tu-tienda', 'tu-empresa', "
    "'tu-sucursal', 'tu-restaurante', 'my-business', 'my-shop', 'my-store', "
    "'mi-negocio', 'mi-tienda', 'mi-empresa', 'mi-sucursal', "
    "'<slug>', '{slug}', '[slug]', '[tu-slug]', '<tu-slug>', "
    "'ejemplo', 'example', 'test-slug', 'sample' ni variantes en una URL pública. "
    "El slug del tenant sale SOLO de la tool `get_tenant_public_urls`. "
    "Una URL pública con placeholder es directamente una URL FALSA — "
    "el usuario no puede hacer click.",
    "NUNCA respondas con un path desnudo del panel (ej. /dashboard/products) "
    "sabiendo que no es clickeable fuera del SPA. SIEMPRE llama primero a "
    "`get_tenant_dashboard_urls` y muestra el resultado como markdown "
    "`[Texto](https://...)`. Si la tool falla, di que ahora no puedes "
    "obtener el link y sugiere revisar la sesión.",
    "NUNCA hardcodees el dominio en una URL de respuesta al usuario. Está "
    "prohibido escribir 'wowhub.app', 'wowhub-api-production.up.railway.app', "
    "'localhost', 'localhost:3000', 'localhost:8000', '127.0.0.1' ni "
    "cualquier otro dominio a mano. El dominio SIEMPRE sale de "
    "`settings.public_base_url` vía la tool correspondiente. Si dudas, "
    "NO escribas la URL — di que la tool la devolverá.",
    "NUNCA confundas las dos tools de URLs: `get_tenant_dashboard_urls` "
    "(panel autenticado, MISMA URL para todos los tenants, prefijo "
    "settings.public_base_url, sin slug) vs `get_tenant_public_urls` "
    "(URL pública del tenant, slug real sustituido, prefijo "
    "settings.public_base_url + /u/{slug_real}/). Cada una resuelve un "
    "caso distinto. Usar la tool equivocada produce URLs falsas.",
]


# ── 6. Tools que requieren confirmación explícita ─────────────────
WRITE_TOOLS_REQUIRE_CONFIRMATION: list[str] = [
    "create_promotion",
    "create_booking",
    "send_email_to_customer",
    "send_campaign",
]


# ── 7. Marketing Studio (WowHub AI Core™ — Cap. 19.1) ──────────────
# Endpoint del AI Core que genera copy de marketing contextual al tenant.
# Es ATÓMICO (1 request → 1 response con N variantes), a diferencia de
# /api/v1/ai/chat que es conversacional. Rate limit compartido con /chat.
MARKETING_STUDIO: dict[str, Any] = {
    "endpoint": "POST /api/v1/ai/marketing/generate",
    "auth": "JWT (mismo que /chat)",
    "rate_limit": "Compartido con /api/v1/ai/chat (mismo contador diario).",
    "intents": [
        "instagram_post", "instagram_story", "instagram_reel",
        "facebook_post", "whatsapp_broadcast", "whatsapp_status",
        "email_subject", "email_body", "sms",
        "product_description", "promotion_headline", "promotion_body",
        "general",
    ],
    "tones": [
        "friendly", "professional", "urgent", "playful",
        "luxury", "casual", "inspirational",
    ],
    "audiences": [
        "all", "existing", "prospects", "vip", "inactive", "new", "local",
    ],
    "variants_range": "1-5 (default 3)",
    "languages": "ISO 639-1, default 'es'",
    "fallback": (
        "Si el LLM no está disponible (circuit abierto, timeout, JSON "
        "inválido), devuelve templates pre-armados por intent×tone con "
        "fallback=true. El usuario SIEMPRE recibe copy utilizable."
    ),
    "persistence": "NONE — el endpoint es stateless. No guarda el copy.",
    "scope": "Solo texto. NO genera imágenes ni videos.",
    "rules": [
        "NO inventes URLs públicas. Usa solo el public_url del context resuelto.",
        "NO incluyas bloques ```json ni ``` en el contenido (solo el copy final).",
        "NO prometas 'imagen generada' o 'video generado' — eso está en roadmap.",
        "Cada request consume 1 unidad del rate limit diario compartido con /chat.",
    ],
}


# ── 8. Intenciones conversacionales que disparan Marketing Studio ──
# Cuando el sub-agente (marketing/growth/automation) detecte una de
# estas intenciones, debe preparar el MarketingRequest (intent + topic +
# tone + audience + context) y sugerir al frontend llamar al endpoint.
MARKETING_STUDIO_TRIGGERS: list[str] = [
    "escríbeme un post para instagram",
    "necesito copy para whatsapp",
    "redacta un asunto de email",
    "genera variantes de copy",
    "quiero un sms corto para mis clientes",
    "ayuda con copy de marketing",
    "copy para facebook",
    "caption para instagram",
    "tweet / x post",
    "descripcion de producto",
    "headline para mi promo",
]


# ── 9. Automation Manager (WowHub AI Core™ — Cap. 19.3) ────────────
# Orquestador de las recommended_actions que devuelve el Growth Coach.
# Cierra el ciclo análisis→acción: el coach recomienda, el usuario
# confirma, el manager ejecuta. Es ATÓMICO (1 request → 1 response) y
# SIEMPRE requiere preview antes de ejecutar (anti-CSRF, anti-doble-click).
AUTOMATION_MANAGER: dict[str, Any] = {
    "endpoints": {
        "actions_list": "GET /api/v1/automation/actions",
        "action_detail": "GET /api/v1/automation/actions/{action_type}",
        "preview": "POST /api/v1/automation/preview",
        "execute": "POST /api/v1/automation/execute",
        "history": "GET /api/v1/automation/history",
    },
    "auth": "JWT (mismo que /chat) — el tenant_id SIEMPRE sale del JWT, nunca del body.",
    "actions": [
        {
            "key": "create_promotion",
            "required_role": "admin",
            "description": "Crea una promoción en el tenant.",
            "params_schema": "PromotionCreate (name, percent_off | amount_off, starts_at, ends_at, branch_ids[], ...).",
        },
        {
            "key": "create_booking",
            "required_role": "staff",
            "description": "Agenda una reserva en nombre de un cliente.",
            "params_schema": "BookingIn (customer_name, customer_phone, branch_id, starts_at, ends_at, party_size, ...).",
        },
        {
            "key": "send_campaign",
            "required_role": "admin",
            "description": "Envía una campaña de email a un segmento de clientes.",
            "params_schema": "CampaignCreate (segment_key, subject, body, from_name, ...).",
        },
    ],
    "flow": (
        "1) GET /automation/actions → lista de acciones disponibles para el rol del usuario. "
        "2) POST /preview {action_type, params, dry_run=true} → resuelve, valida, devuelve "
        "preview legible y `preview_id` con TTL 10 min. NO toca la DB. "
        "3) El frontend muestra el preview al usuario en un modal. "
        "4) POST /execute {action_type, params, dry_run=false, confirmed=true, preview_id} → "
        "valida el preview_id (anti-CSRF + anti-drift), ejecuta el handler, escribe audit log, "
        "devuelve `resource_id` + `resource_url`."
    ),
    "rate_limit": (
        "Configurable vía `ai_daily_automation_limit` (default 50/día/usuario). "
        "Cuenta SOLO ejecuciones confirmadas, NO previews. Si te pasás, el backend "
        "devuelve 429 con código `rate_limited`."
    ),
    "preview_ttl_seconds": 600,
    "preview_one_shot": True,
    "audit_log": (
        "Tabla `automation_executions` con todos los intentos (succeeded + failed). "
        "El audit log persiste aunque el resource haga rollback — queremos ver el "
        "intento. `params` se guarda encriptado; `GET /history` no los expone por defecto."
    ),
    "rollback_policy": (
        "Si el handler falla a mitad de camino, el resource creado se hace rollback. "
        "El audit log SIEMPRE persiste (status=failed + error). Si la validación de "
        "params falla, NO se escribe audit log (es error de input, no de ejecución)."
    ),
    "rules": [
        "NUNCA llames /execute sin haber mostrado el preview antes (o sin entender sus implicancias).",
        "NUNCA inventes `preview_id` — lo devuelve SIEMPRE /preview.",
        "NUNCA omitas `confirmed=true` en /execute. El backend rechaza con 400 confirmation_required.",
        "NUNCA uses `tenant_id` del body — el backend lo lee del JWT. Si lo pasás, se ignora silenciosamente.",
        "El prefijo de la insight del Growth Coach (recommended_action.action_type + recommended_action.params) se mapea 1:1 a una acción del registry.",
        "send_whatsapp_template NO está implementado todavía — si el coach lo sugiere, indicale al usuario que esa acción está en roadmap.",
    ],
}


# ── 10. Intenciones conversacionales que disparan Automation Manager ──
# Cuando el sub-agente (growth/automation) detecte una de estas
# intenciones + devuelva un insight con `recommended_action`, el
# frontend debe preparar un `AutomationRequest` y llamar al endpoint
# /preview primero, mostrar el modal, y luego /execute.
AUTOMATION_MANAGER_TRIGGERS: list[str] = [
    "ejecuta la promo que me recomendó el growth coach",
    "manda la campaña a los clientes inactivos",
    "agenda la reserva que me sugirió el coach",
    "aplica la recomendación del coach",
    "ejecuta la acción recomendada",
    "crea la promo del insight",
    "lanza la campaña del insight",
]


# ── 11. Dashboard URLs clickeables (WowHub AI Core™ — v1.9.1) ──────
# Catálogo que la tool `get_tenant_dashboard_urls` usa para armar los
# links ABSOLUTOS del panel (no paths relativos). Las rutas son las
# MISMAS para todos los tenants — el contexto multi-tenant lo da la
# sesión/JWT, no el subdominio.
#
# Esta constante existe para que cualquier agente (marketing, growth,
# automation, help) sepa qué módulos existen y pueda pedirle al LLM que
# use la tool en vez de inventar paths.
DASHBOARD_URLS: dict[str, Any] = {
    "endpoint": "tool get_tenant_dashboard_urls (no es HTTP, lee de app_knowledge)",
    "base_url_source": "settings.public_base_url",
    "url_format": "{base_url}{path} → https://wowhub.app/dashboard/products (ejemplo)",
    "modules": [
        # Se genera dinámicamente desde MODULES para no duplicar.
        # Esta lista es solo DOCUMENTATIVA (qué módulos están disponibles).
        "resumen", "productos", "promociones", "clientes", "pedidos",
        "reservas", "campanas", "sucursales", "fidelizacion", "qr",
        "configuracion", "admin_ia", "superadmin",
    ],
    "rules": [
        "SIEMPRE llama a `get_tenant_dashboard_urls` cuando el usuario pida un link al panel.",
        "Muestra los links como markdown `[texto](url)` para que sean clickeables.",
        "NUNCA respondas con paths desnudos tipo `/dashboard/products` — no son clickeables fuera del SPA.",
        "Las URLs son las MISMAS para todos los tenants. NO incluyas el slug en el path.",
        "Si la tool falla (settings.public_base_url no configurado), avísale al usuario y sugiere Configuración → Branding.",
    ],
}


# ── API pública del módulo ────────────────────────────────────────
def list_modules() -> list[dict[str, Any]]:
    return MODULES


def get_module(key: str) -> dict[str, Any] | None:
    key_norm = (key or "").strip().lower()
    for m in MODULES:
        if m["key"] == key_norm or m["label"].lower() == key_norm:
            return m
    return None


def list_public_urls() -> list[dict[str, str]]:
    return PUBLIC_URLS


def get_public_url(key: str) -> dict[str, str] | None:
    key_norm = (key or "").strip().lower()
    for u in PUBLIC_URLS:
        if u["key"] == key_norm:
            return u
    return None


def list_auth_info() -> list[dict[str, str]]:
    return AUTH_INFO


def faq_lookup(question: str) -> str | None:
    """Búsqueda tolerante: minúsculas, sin acentos, contiene."""
    if not question:
        return None
    q = question.lower().strip()
    # Match exacto primero
    if q in FAQ:
        return FAQ[q]
    # Match por substring en claves
    for k, v in FAQ.items():
        if k in q or q in k:
            return v
    return None


def list_no_existe() -> list[str]:
    return NO_EXISTE


def requires_confirmation(tool_name: str) -> bool:
    return tool_name in WRITE_TOOLS_REQUIRE_CONFIRMATION


def render_short_summary() -> str:
    """Resumen compacto que se inyecta en los system prompts."""
    lines = [
        "═══ DATOS VERÍDICOS DE WOWHUB (no inventes) ═══",
        "• NINGÚN módulo requiere activación. Todos están disponibles para todos los tenants.",
        "• NO existe 'Configuración → Módulos' ni interruptores para encender/apagar funciones.",
        "• NO hay que 'contactar a soporte' para habilitar nada.",
        "",
        "Módulos y rutas del panel:",
    ]
    for m in MODULES:
        lines.append(f"  - {m['label']}: {m['path']}")
    lines.append("")
    lines.append("URLs públicas:")
    for u in PUBLIC_URLS:
        lines.append(f"  - {u['pattern']} → {u['description']}")
    lines.append("")
    lines.append("AI Core (endpoints de IA):")
    lines.append(f"  - POST {MARKETING_STUDIO['endpoint']} → genera copy de marketing contextual al tenant (variants + hashtags + fallback).")
    lines.append("  - POST /api/v1/ai/chat → chat conversacional multi-agente.")
    lines.append("  - GET  /api/v1/ai/agents → lista sub-agentes (marketing, growth, automation, marketplace, help).")
    lines.append("  - GET  /api/v1/ai/status → estado del LLM (circuit, rate, enabled).")
    lines.append("  - POST /api/v1/automation/preview → preview (dry_run) de una recommended_action del Growth Coach. Devuelve preview_id con TTL 10 min.")
    lines.append("  - POST /api/v1/automation/execute → ejecuta la acción SOLO si confirmed=true y dry_run=false. Valida el preview_id (anti-CSRF). Escribe audit log.")
    lines.append("  - GET  /api/v1/automation/actions → catálogo de acciones disponibles para el rol del usuario.")
    lines.append("  - GET  /api/v1/automation/history → historial paginado de ejecuciones del tenant (no expone params).")
    lines.append("")
    lines.append("Reglas críticas:")
    lines.append("  - Si te preguntan algo de WowHub que NO sabes con certeza, di 'No estoy seguro, pero X está en /dashboard/x' o sugiere abrir un ticket.")
    lines.append("  - NUNCA inventes nombres de secciones, toggles o flujos que no estén listados aquí.")
    lines.append("  - Para acciones de escritura (create_*, send_*), SIEMPRE muestra preview y pide confirmación explícita antes de ejecutar.")
    lines.append("  - El Marketing Studio SOLO genera texto. NO inventes que genera imágenes o videos.")
    lines.append("  - Si el usuario pide 'escríbeme un post para X', prepara un MarketingRequest y sugiere al frontend llamar al endpoint (no redactes el copy directamente en el chat).")
    lines.append("  - Cuando el Growth Coach devuelva un insight con `recommended_action`, el frontend DEBE llamar /preview antes que /execute. NUNCA ejecutes una acción de escritura sin el paso de preview + confirmación del usuario.")
    lines.append("  - El Automation Manager tiene 3 acciones MVP: create_promotion, create_booking, send_campaign. send_whatsapp_template está en roadmap.")
    lines.append("  - LINKS DEL PANEL: SIEMPRE llama a la tool `get_tenant_dashboard_urls` para devolver links ABSOLUTOS clickeables. NUNCA respondas con paths desnudos como `/dashboard/products` — fuera del SPA no son clickeables. Muestra los links como markdown `[texto](url)`.")
    lines.append("  - Las URLs del panel son las MISMAS para todos los tenants (ej. https://wowhub.app/dashboard/products). NO incluyas el slug del tenant en el path del panel — eso es solo para URLs públicas (usa `get_tenant_public_urls`).")
    lines.append("  - ANTI-PLACEHOLDER: NUNCA escribas 'tu-negocio', 'tu-tienda', 'mi-negocio', '{slug}', '<slug>', 'my-business' ni ningún placeholder literal en una URL. El slug real del tenant sale SOLO de `get_tenant_public_urls`. Una URL con placeholder es una URL FALSA — el usuario no puede hacer click y queda con la impresión de que WowHub no funciona.")
    lines.append("  - ANTI-DOMINIO: NUNCA hardcodees el dominio en una URL de respuesta. Está prohibido escribir 'wowhub.app', 'wowhub-api-production.up.railway.app', 'localhost' a mano. El dominio SIEMPRE sale de `settings.public_base_url` vía la tool. El default de `settings.public_base_url` es `https://wowhub.app`.")
    lines.append("  - FORMATO DE RESPUESTA: si el usuario pide un link, tu respuesta SIEMPRE debe incluir el markdown `[Texto](https://...)` con la URL completa. Un link desnudo o un path sin prefijo es un link ROTO.")
    return "\n".join(lines)
