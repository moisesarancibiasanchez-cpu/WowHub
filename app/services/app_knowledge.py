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
        "Usá el Marketing Studio: POST /api/v1/ai/marketing/generate. Indicá "
        "intent (instagram_post, whatsapp_broadcast, email_subject, etc.), "
        "topic (el tema), tone y audience. Te devuelve variantes listas. "
        "NO se guarda el copy en la base — solo se devuelve."
    ),
    "copy para instagram": (
        "El Marketing Studio puede generarlo: POST /api/v1/ai/marketing/generate "
        "con intent=instagram_post. Devuelve N variantes con hashtags. Si querés "
        "story corto, usá intent=instagram_story. Para Reel, intent=instagram_reel."
    ),
    "asunto de email": (
        "El Marketing Studio puede redactarlo: POST /api/v1/ai/marketing/generate "
        "con intent=email_subject (asunto corto) o intent=email_body (cuerpo). "
        "Indicá tone (ej. professional, friendly) y audience."
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
    "escribime un post para instagram",
    "necesito copy para whatsapp",
    "redactame un asunto de email",
    "generame variantes de copy",
    "quiero un sms corto para mis clientes",
    "ayudame con copy de marketing",
    "copy para facebook",
    "caption para instagram",
    "tweet / x post",
    "descripcion de producto",
    "headline para mi promo",
]


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
    lines.append("")
    lines.append("Reglas críticas:")
    lines.append("  - Si te preguntan algo de WowHub que NO sabes con certeza, di 'No estoy seguro, pero X está en /dashboard/x' o sugiere abrir un ticket.")
    lines.append("  - NUNCA inventes nombres de secciones, toggles o flujos que no estén listados aquí.")
    lines.append("  - Para acciones de escritura (create_*, send_*), SIEMPRE muestra preview y pide confirmación explícita antes de ejecutar.")
    lines.append("  - El Marketing Studio SOLO genera texto. NO inventes que genera imágenes o videos.")
    lines.append("  - Si el usuario pide 'escribime un post para X', prepará un MarketingRequest y sugerí al frontend llamar al endpoint (no redactes el copy directamente en el chat).")
    return "\n".join(lines)
