"""Fuente de verdad (estructurada) sobre WowHub para el asistente IA.

Este módulo es la contraparte Python del documento canónico
`docs/CANONICAL_WOWHUB.md`. Se carga en runtime y se sirve a través de
la tool `get_app_help`. Cualquier módulo nuevo que se agregue al
producto DEBE reflejarse aquí y en el documento.

Regla de oro: ningún módulo de WowHub requiere activación.
"""
from __future__ import annotations

from typing import Any


# ── 1. Features del producto (lo que WowHub ofrece HOY en producción) ──
#
# v1.9.1-r4: el OpenAPI en producción
# (https://wowhub-api-production.up.railway.app/openapi.json) describe
# explícitamente "4 features del MVP: Página, Catálogo, QR y Promociones".
# Las otras secciones (auth, tenants, members, branches, categories,
# products, customers, qrs, landing-config) son endpoints ADMIN / CRM
# autenticados con JWT, NO features visibles al cliente final.
#
# Por eso MODULES se reduce a 4 features visibles + 0 admin (los admin
# no son "features" sino "gestión interna"). La IA NO debe prometer
# features que no están en el OpenAPI de producción.
MODULES: list[dict[str, Any]] = [
    {
        "key": "pagina",
        "label": "Página de tu negocio",
        "path": "/api/v1/public/t/{slug}/profile",
        "description": (
            "Página pública del tenant: nombre, descripción, dirección, "
            "logo, datos del negocio. Read-only (GET). Equivale al "
            "perfil público del negocio."
        ),
        "requires_activation": False,
        "ai_tools": ["get_tenant_info"],
    },
    {
        "key": "catalogo",
        "label": "Catálogo de productos",
        "path": "/api/v1/public/t/{slug}/catalog",
        "description": (
            "Lista de productos visibles al público: nombre, precio, "
            "imagen, descripción, disponibilidad. Read-only (GET). "
            "Para ver UN producto puntual, el path es "
            "/api/v1/public/t/{slug}/products/{product_slug}."
        ),
        "requires_activation": False,
        "ai_tools": ["list_products"],
    },
    {
        "key": "qr",
        "label": "Códigos QR",
        "path": "/r/{short_code}",
        "description": (
            "Códigos QR de corta duración. Cuando el cliente escanea el "
            "QR, es redirigido (302) al destino configurado (perfil, "
            "catálogo, producto, promo, etc.). El path es la URL CORTA "
            "que el dueño pega en su QR físico."
        ),
        "requires_activation": False,
        "ai_tools": [],
    },
    {
        "key": "promociones",
        "label": "Promociones",
        "path": "/api/v1/public/t/{slug}/promotions",
        "description": (
            "Promociones activas del tenant: descuento, vigencia, "
            "condiciones. Read-only (GET) en el endpoint público. La "
            "gestión interna (crear/editar) se hace vía API autenticada "
            "POST /api/v1/tenants/{tid}/promotions."
        ),
        "requires_activation": False,
        "ai_tools": ["list_promotions", "create_promotion"],
    },
]


# ── 2. URLs públicas (sin auth) ───────────────────────────────────
#
# v1.9.1-r4: el OpenAPI en producción
# (https://wowhub-api-production.up.railway.app/openapi.json) expone
# EXACTAMENTE 7 paths públicos bajo `/api/v1/public/t/{slug}/`:
#   - /profile          → datos del negocio
#   - /catalog          → lista de productos
#   - /products/{slug}  → ficha de un producto
#   - /promotions       → promociones activas
#   - /categories       → categorías del catálogo
#   - /branches         → sucursales (dirección, horarios)
#   - /landing          → config de la landing pública
# Más el path `/r/{short_code}` (default) que es un 302 redirect para
# los QRs cortos.
#
# Esta es la ÚNICA lista válida. Los paths anteriores (`/u/{slug}/...`,
# `/u/{slug}/reservar`, `/loyalty/{slug}`) NO EXISTEN en el OpenAPI de
# producción y son RUTAS FANTASMA que la IA NO debe entregar.
PUBLIC_URLS: list[dict[str, str]] = [
    {
        "key": "perfil",
        "pattern": "/api/v1/public/t/{slug}/profile",
        "description": (
            "Datos públicos del tenant: nombre, descripción, dirección, "
            "logo, redes, datos del negocio. Read-only (GET). "
            "{slug} = identificador del tenant en la URL."
        ),
    },
    {
        "key": "catalogo",
        "pattern": "/api/v1/public/t/{slug}/catalog",
        "description": (
            "Catálogo público de productos: nombre, precio, imagen, "
            "descripción, disponibilidad. Read-only (GET)."
        ),
    },
    {
        "key": "producto",
        "pattern": "/api/v1/public/t/{slug}/products/{product_slug}",
        "description": (
            "Ficha de UN producto: detalle, precio, galería de imágenes, "
            "variantes, stock visible. {product_slug} = slug del producto. "
            "Read-only (GET)."
        ),
    },
    {
        "key": "promociones",
        "pattern": "/api/v1/public/t/{slug}/promotions",
        "description": (
            "Promociones activas del tenant: descuento, vigencia, "
            "condiciones. Read-only (GET)."
        ),
    },
    {
        "key": "categorias",
        "pattern": "/api/v1/public/t/{slug}/categories",
        "description": (
            "Categorías del catálogo. Útil para agrupar el catálogo. "
            "Read-only (GET)."
        ),
    },
    {
        "key": "sucursales",
        "pattern": "/api/v1/public/t/{slug}/branches",
        "description": (
            "Sucursales del tenant: dirección, horarios, teléfono, "
            "coordenadas. Read-only (GET)."
        ),
    },
    {
        "key": "landing",
        "pattern": "/api/v1/public/t/{slug}/landing",
        "description": (
            "Config de la landing pública del tenant: colores, copy, "
            "links a redes, claims. Read-only (GET). La edición se "
            "hace internamente vía API autenticada."
        ),
    },
    {
        "key": "qr_redirect",
        "pattern": "/r/{short_code}",
        "description": (
            "URL CORTA de un QR. Cuando el cliente escanea, el server "
            "responde 302 hacia el destino configurado (perfil, "
            "catálogo, producto, promo, etc.). {short_code} = código "
            "alfanumérico corto del QR."
        ),
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
        "v1.9.1-r4: el feature de Reservas NO está expuesto en el OpenAPI de producción. "
        "Si lo que el usuario quiere es gestionar reservas internamente, se hace vía "
        "API autenticada (con JWT). Si es para clientes finales (pedir una reserva), "
        "esa función tampoco está en el MVP actual — está en roadmap."
    ),
    "cómo activo reservaciones": (
        "v1.9.1-r4: el feature de Reservas NO está expuesto en el OpenAPI de producción "
        "(https://wowhub-api-production.up.railway.app/openapi.json). Está en roadmap."
    ),
    "cómo activo reservas": (
        "v1.9.1-r4: el feature de Reservas NO está expuesto en el OpenAPI de producción. "
        "Está en roadmap."
    ),
    "qué módulos hay": (
        "WowHub ofrece 4 features públicas (lo que ven tus clientes): "
        "Página, Catálogo, QR y Promociones. Estas son las 4 funciones del MVP "
        "desplegado en producción. El dueño también tiene acceso a la gestión interna "
        "vía API autenticada (productos, sucursales, clientes, etc.) pero esas NO son "
        "features visibles al cliente final. NINGUNA requiere activación: están todas "
        "disponibles para cualquier tenant activo."
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
        "v1.9.1-r4: el panel autenticado del dueño está en `app/main.py` (código "
        "de desarrollo) pero el OpenAPI de PRODUCCIÓN "
        "(https://wowhub-api-production.up.railway.app/openapi.json) NO expone rutas "
        "HTML de dashboard. Llama primero a `get_tenant_info` para confirmar el slug "
        "del tenant y luego sugiere al usuario la API autenticada "
        "GET/POST/PATCH/DELETE /api/v1/tenants/{tid}/products (con su JWT). La página "
        "PÚBLICA del producto (lo que ven los clientes) es "
        "/api/v1/public/t/{slug}/products/{product_slug}."
    ),
    "cómo abro el panel de": (
        "v1.9.1-r4: no hay panel HTML público en producción. La gestión es vía "
        "API autenticada con JWT (GET/POST/PATCH/DELETE /api/v1/tenants/{tid}/...). "
        "Llama primero a `get_tenant_public_urls` para devolver la URL del feature "
        "público (catálogo, perfil, QR) si el usuario quiere compartirla."
    ),
    "dónde veo el admin ia": (
        "v1.9.1-r4: la gestión interna de WowHub (incluido el admin) se hace vía "
        "API autenticada, no hay panel HTML público. Llama a `get_tenant_info` para "
        "verificar que el usuario sea OWNER/ADMIN; si lo es, sugiere los endpoints "
        "/api/v1/admin/ai/* con su JWT. Si es STAFF o VIEWER, no tiene permisos."
    ),
    "pásame el link de": (
        "v1.9.1-r4: primero identifica QUÉ feature pide el usuario. Si es público "
        "(catálogo, perfil, promo, QR), llama a `get_tenant_public_urls` y devuelve "
        "el link ABSOLUTO del feature (ej. "
        "`https://wowhub-api-production.up.railway.app/api/v1/public/t/cafeluna/catalog`). "
        "Si es gestión interna, dile que no hay URL pública — la acción la hace "
        "él desde su sesión autenticada."
    ),
    "mándame el link por": (
        "Llama primero a `get_tenant_public_urls`. La URL pública del feature "
        "que el usuario quiere compartir (catálogo, perfil, promo, QR) ya viene "
        "con el slug real sustituido y la base de settings.public_base_url como "
        "prefijo. Como es una URL completa, el usuario puede compartirla por "
        "WhatsApp, email, SMS, etc."
    ),
    "dónde cambio mi contraseña": (
        "v1.9.1-r4: la gestión interna se hace vía API autenticada. El endpoint es "
        "POST /api/v1/auth/password con el JWT del usuario. No hay pantalla HTML pública "
        "para esto en producción."
    ),
    "dónde veo mis ventas": (
        "v1.9.1-r4: la vista de ventas del dueño la entrega la API autenticada. "
        "Endpoint: GET /api/v1/tenants/{tid}/stats/overview (con JWT). No hay ruta "
        "HTML pública de dashboard en producción."
    ),
    "cómo creo una promoción": (
        "Puedo crearla por ti. Dime: nombre, descuento (% o monto), fechas. "
        "Te muestro el preview antes de guardar."
    ),
    "cómo creo una reserva": (
        "v1.9.1-r4: Reservas NO está en el OpenAPI de producción. Está en roadmap. "
        "Dile al usuario que esa función aún no está disponible para clientes finales."
    ),
    "url pública": (
        "v1.9.1-r4: SIEMPRE llama primero a la tool `get_tenant_public_urls`. "
        "Te devuelve los links PÚBLICOS del tenant con el slug real sustituido y "
        "la base de settings.public_base_url como prefijo (ej. "
        "`https://wowhub-api-production.up.railway.app/api/v1/public/t/cafeluna/catalog`). "
        "El formato REAL (v1.9.1-r4) es `/api/v1/public/t/{slug}/...` — NO uses "
        "el formato viejo `/u/{slug}/...` (esos paths NO EXISTEN en producción y "
        "dan 404). NUNCA respondas con un patrón de placeholder, NUNCA pidas al "
        "usuario que reemplace el slug a mano, NUNCA inventes el slug. Si la tool "
        "falla, di que ahora no puedes obtener el link. La tool `get_tenant_dashboard_urls` "
        "está DEPRECADA en v1.9.1-r4 — no la llames."
    ),
    "no me deja entrar": (
        "Verifica que tu sesión esté iniciada y que el chip de usuario del topbar "
        "muestre el tenant correcto. Si persiste, contáctanos."
    ),
    "cómo cambio el idioma": (
        "Por ahora WowHub está en español. La función multi-idioma está en roadmap."
    ),
    "cómo cambio el logo": (
        "v1.9.1-r4: la gestión de branding se hace vía API autenticada. Endpoint: "
        "PATCH /api/v1/tenants/{tid} (campo logo_url) o POST /api/v1/uploads para "
        "subir la imagen (máx 5 MB). No hay pantalla HTML pública para esto en producción."
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
        "v1.9.1-r4: WhatsApp Business NO está implementado todavía. Está en roadmap "
        "como `send_whatsapp_template` en el Automation Manager. Hoy puedes compartir "
        "el link público del feature por WhatsApp manualmente."
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
    # ── v1.9.1-r4 — Anti-alucinación sincronizada con producción ──
    # La fuente de verdad es el OpenAPI de producción:
    # https://wowhub-api-production.up.railway.app/openapi.json
    # NO `app/main.py` (código de desarrollo) NI `wowhub.app` (dominio no desplegado).
    "v1.9.1-r4: NO EXISTE un panel HTML público en producción. La gestión interna "
    "(productos, sucursales, clientes, promos, branding) se hace vía API autenticada "
    "con JWT (GET/POST/PATCH/DELETE /api/v1/tenants/{tid}/...). El OpenAPI en "
    "producción NO expone rutas `/dashboard/*` ni `/admin/*` como vistas HTML — "
    "esas rutas están en `app/main.py` (código de desarrollo, NO desplegado).",
    "v1.9.1-r4: NUNCA respondas con paths desnudos (ej. `/dashboard/products`, "
    "`/u/{slug}/reservar`, `/api/v1/public/t/cafeluna/catalog` sin prefijo de "
    "dominio). Un path desnudo NO es una URL clickeable — siempre va envuelto en "
    "el formato completo `https://<dominio>/<path>` con el dominio de "
    "`settings.public_base_url` como prefijo. La IA no debe inventar la URL base "
    "tampoco: si no la tiene, NO escribe la URL — di que la tool la devolverá.",
    "v1.9.1-r4: el formato correcto de URL pública es "
    "`{settings.public_base_url}/api/v1/public/t/{slug}/...` "
    "(ej. `https://wowhub-api-production.up.railway.app/api/v1/public/t/cafeluna/catalog`). "
    "El formato viejo `/u/{slug}/...` (ej. `/u/cafeluna/perfil`, `/u/cafeluna/catalogo`, "
    "`/u/cafeluna/reservar`) NO EXISTE en el OpenAPI de producción y da 404. "
    "NUNCA entregues URLs con el prefijo `/u/{slug}/`.",
    "v1.9.1-r4: la URL pública `/loyalty/{slug}` NO EXISTE. El feature de fidelización "
    "no está desplegado en producción (solo en roadmap). NUNCA la ofrezcas como link.",
    "v1.9.1-r4: el dominio `wowhub.app` NO está desplegado en producción. La única URL "
    "que puedes garantizar como 'existe y responde hoy' es "
    "`https://wowhub-api-production.up.railway.app/`. NUNCA entregues links con "
    "prefijo `https://wowhub.app/...` (dan NXDOMAIN). El default de "
    "`settings.public_base_url` es el de Railway, no `wowhub.app`.",
    "v1.9.1-r4: la tool `get_tenant_dashboard_urls` está DEPRECADA. La IA NO debe "
    "llamarla más. La única tool de URLs es `get_tenant_public_urls`, que devuelve los "
    "7 paths públicos REALES (perfil, catalogo, producto, promociones, categorias, "
    "sucursales, landing) + el path del QR corto (`/r/{short_code}`).",
    # ── Anti-placeholder (v1.9.1-r2) — placeholders literales prohibidos ──
    "NUNCA uses placeholders literales como 'tu-negocio', 'tu-tienda', 'tu-empresa', "
    "'tu-sucursal', 'tu-restaurante', 'my-business', 'my-shop', 'my-store', "
    "'mi-negocio', 'mi-tienda', 'mi-empresa', 'mi-sucursal', "
    "'<slug>', '{slug}', '[slug]', '[tu-slug]', '<tu-slug>', "
    "'ejemplo', 'example', 'test-slug', 'sample' ni variantes en una URL pública. "
    "El slug del tenant sale SOLO de la tool `get_tenant_public_urls`. "
    "Una URL pública con placeholder es directamente una URL FALSA — "
    "el usuario no puede hacer click.",
    "NUNCA entregues URLs que NO son absolutas: cualquier path sin prefijo de "
    "dominio (ej. `/dashboard/products`, `/u/{slug}/reservar`, "
    "`/api/v1/public/t/cafeluna/catalog` sin `https://...` delante) es una URL "
    "NO absoluta, no es clickeable en WhatsApp/email/SMS, y deja al usuario con "
    "la impresión de que WowHub no funciona. SIEMPRE antepón el dominio de "
    "`settings.public_base_url`.",
    "NUNCA incluyas el slug del tenant a mano en una URL pública. El slug es un "
    "identificador interno que solo conoce el sistema — si lo escribís a mano, "
    "puedes equivocarte. SIEMPRE llama a `get_tenant_public_urls` para que la "
    "tool resuelva el slug real del tenant y te devuelva la URL completa.",
    "NUNCA confundas URL del panel (`/dashboard/*`) con URL pública "
    "(`/api/v1/public/t/{slug}/...`). Son cosas distintas: el panel es "
    "interno (autenticado con JWT, no compartible con clientes), la URL pública "
    "es lo que ven los clientes finales sin login. Si el usuario pide "
    "'mi link', devuelve la URL pública, no la del panel.",
    "NUNCA inventes la URL base de WowHub. No la seques de la nada, no la "
    "armes con `${dominio}/path` a mano, no la copies de un ejemplo viejo. "
    "La base SIEMPRE sale de `settings.public_base_url` (default: backend de "
    "Railway en producción). Si la tool no puede darte la base, NO escribas "
    "la URL — di que ahora no puedes obtenerla.",
    "NUNCA hardcodees el dominio en una URL de respuesta al usuario. Está "
    "prohibido escribir 'wowhub.app', 'wowhub-api-production.up.railway.app', "
    "'localhost', 'localhost:3000', 'localhost:8000', '127.0.0.1' ni "
    "cualquier otro dominio a mano. El dominio SIEMPRE sale de "
    "`settings.public_base_url` vía la tool correspondiente. Si dudas, "
    "NO escribas la URL — di que la tool la devolverá.",
    # ── Anti-rutas-fantasma (v1.9.1-r3) — heredadas pero con justificación v1.9.1-r4 ──
    "La ruta `/dashboard/settings` NO EXISTE en producción (no hay panel HTML). "
    "La configuración del tenant (branding, logo, datos del negocio) se hace vía "
    "API autenticada: PATCH /api/v1/tenants/{tid}.",
    "La ruta `/dashboard/qr` (singular) NO EXISTE. La ruta real de QR es "
    "`/r/{short_code}` (un redirect 302 al destino configurado). NUNCA uses "
    "el singular en una URL.",
    "La ruta `/dashboard/campaigns` NO EXISTE como vista HTML. El envío "
    "masivo de campañas se hace vía la tool `send_campaign` (Automation "
    "Manager) llamando a la API, NO desde una pantalla del panel. "
    "Para enviar emails a un cliente puntual, usa `send_email_to_customer`.",
    "La ruta `/dashboard/branches` NO EXISTE. Las sucursales se consultan en "
    "`/api/v1/public/t/{slug}/branches` (público) o `/api/v1/tenants/{tid}/branches` (autenticado).",
    "La ruta `/dashboard/automation` NO EXISTE como vista. El Automation "
    "Manager se invoca solo vía API (POST /api/v1/automation/preview y "
    "/execute), no tiene pantalla dedicada.",
    "La ruta `/dashboard/categories` NO EXISTE. Las categorías se consultan en "
    "`/api/v1/public/t/{slug}/categories` (público) o se gestionan vía API autenticada.",
    "La ruta `/dashboard/integrations` NO EXISTE. Las integraciones "
    "(WhatsApp, Stripe, MercadoPago) están en roadmap y se configuran "
    "por API o por variables de entorno.",
    "La URL pública `/u/{slug}/book` NO EXISTE. Las reservas NO están en el MVP "
    "actual (v1.9.1-r4). El feature de reservas está en roadmap.",
    "La URL pública `/u/{slug}/menu` NO EXISTE. El catálogo público es "
    "`/api/v1/public/t/{slug}/catalog` (formato v1.9.1-r4, NO `/u/{slug}/catalogo`).",
    "La URL pública `/u/{slug}/pedido` NO EXISTE. No hay vista de pedido "
    "para clientes externos; el flujo de pedido se hace desde el panel "
    "o vía API.",
    "La URL pública `/u/{slug}/reservar` NO EXISTE. Las reservas no están "
    "desplegadas en el OpenAPI de producción (están en roadmap).",
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


# ── 11. DASHBOARD_URLS (DEPRECATED en v1.9.1-r4) ───────────────────
#
# v1.9.1-r4: el OpenAPI de producción NO expone rutas HTML de dashboard.
# Las rutas /dashboard/* que están en `app/main.py` son código de
# desarrollo NO desplegado en Railway. Por eso:
#
#   1. La tool `get_tenant_dashboard_urls` está DEPRECADA.
#   2. Esta constante se mantiene como SHIM para no romper imports
#      ni tests legacy, pero está vacía (sin modules).
#   3. La IA NO debe entregar links de panel.
#
# Tests legacy que importen DASHBOARD_URLS["modules"] deben ser
# actualizados a la nueva realidad (4 features públicas).
DASHBOARD_URLS: dict[str, Any] = {
    "deprecated_in": "v1.9.1-r4",
    "reason": (
        "El OpenAPI de producción "
        "(https://wowhub-api-production.up.railway.app/openapi.json) NO "
        "expone rutas HTML de dashboard. El panel de gestión solo está "
        "en `app/main.py` (código de desarrollo, NO desplegado). La "
        "única tool de URLs vigente es `get_tenant_public_urls`."
    ),
    "endpoint": "DEPRECATED — usa `get_tenant_public_urls` en su lugar.",
    "base_url_source": "settings.public_base_url",
    "url_format": "DEPRECATED",
    "modules": [],  # vacío: ya no hay panel público
    "rules": [
        "DEPRECATED en v1.9.1-r4. La IA NO debe usar esta tool.",
        "Para URLs públicas, usa `get_tenant_public_urls`.",
        "Para gestión interna, dile al usuario que la acción la hace "
        "él desde su sesión autenticada (API con JWT).",
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
    lines.append("  - v1.9.1-r4: NO HAY PANEL HTML PÚBLICO en producción. WowHub hoy expone SOLO una API JSON para clientes públicos (los consumidores finales NO navegan un panel HTML). El 'panel' (/dashboard/*) es interno del SaaS — no es un producto que la IA deba entregar como link al usuario final.")
    lines.append("  - Si te preguntan algo de WowHub que NO sabes con certeza, di 'No estoy seguro' y sugiere abrir un ticket. NO inventes rutas `/dashboard/x` como si fueran públicas — esa ruta NO existe para clientes externos.")
    lines.append("  - NUNCA inventes nombres de secciones, toggles o flujos que no estén listados aquí.")
    lines.append("  - Para acciones de escritura (create_*, send_*), SIEMPRE muestra preview y pide confirmación explícita antes de ejecutar.")
    lines.append("  - El Marketing Studio SOLO genera texto. NO inventes que genera imágenes o videos.")
    lines.append("  - Si el usuario pide 'escríbeme un post para X', prepara un MarketingRequest y sugiere al frontend llamar al endpoint (no redactes el copy directamente en el chat).")
    lines.append("  - Cuando el Growth Coach devuelva un insight con `recommended_action`, el frontend DEBE llamar /preview antes que /execute. NUNCA ejecutes una acción de escritura sin el paso de preview + confirmación del usuario.")
    lines.append("  - El Automation Manager tiene 3 acciones MVP: create_promotion, create_booking, send_campaign. send_whatsapp_template está en roadmap.")
    lines.append("  - LINKS PÚBLICOS (v1.9.1-r4): SIEMPRE llama a la tool `get_tenant_public_urls` para devolver links ABSOLUTOS clickeables del tenant (formato `https://<dominio>/api/v1/public/t/<slug>/<ruta>`). NUNCA respondas con paths desnudos como `/u/{slug}` ni con `/dashboard/*` (no existe para clientes externos). Muestra los links como markdown `[texto](url)`.")
    lines.append("  - La tool `get_tenant_dashboard_urls` está DEPRECADA en v1.9.1-r4 (devolvía rutas `/dashboard/*` que NO existen como URLs públicas). Si el usuario pide 'el link de su panel', explica que WowHub es una API — el panel interno NO se comparte con clientes finales. Usa `get_tenant_public_urls` para lo que sí se puede compartir.")
    lines.append("  - ANTI-PLACEHOLDER: NUNCA escribas 'tu-negocio', 'tu-tienda', 'mi-negocio', '{slug}', '<slug>', 'my-business' ni ningún placeholder literal en una URL. El slug real del tenant sale SOLO de `get_tenant_public_urls`. Una URL con placeholder es una URL FALSA — el usuario no puede hacer click y queda con la impresión de que WowHub no funciona.")
    lines.append("  - ANTI-DOMINIO: NUNCA hardcodees el dominio en una URL de respuesta. Está prohibido escribir 'wowhub.app', 'wowhub-api-production.up.railway.app', 'localhost' a mano. El dominio SIEMPRE sale de `settings.public_base_url` vía la tool. El default de `settings.public_base_url` es `https://wowhub-api-production.up.railway.app` (la URL del backend en producción que OpenAPI garantiza como 'existe y responde hoy').")
    lines.append("  - FORMATO DE RESPUESTA: si el usuario pide un link, tu respuesta SIEMPRE debe incluir el markdown `[Texto](https://...)` con la URL completa. Un link desnudo o un path sin prefijo es un link ROTO.")
    return "\n".join(lines)
