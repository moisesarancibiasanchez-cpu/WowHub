"""Tools del AI Core — SIEMPRE llaman a la API interna de WowHub via HTTP.

Reglas:
- Ninguna tool toca la BD directamente.
- Cada tool tiene un esquema JSON Schema que el LLM entiende.
- El agente se identifica con el JWT del usuario + X-Tenant-Id.
- Errores se devuelven como `{"error": "..."}` para que el LLM pueda responder.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

import httpx

from app.config import settings

logger = logging.getLogger("wowhub.ai.tools")


# ── Helper interno ─────────────────────────────────────
class AIToolContext:
    """Contexto que el orquestador pasa a las tools."""
    def __init__(
        self,
        *,
        user_id: str,
        tenant_id: str,
        access_token: str,
        base_url: str | None = None,
    ) -> None:
        self.user_id = user_id
        self.tenant_id = tenant_id
        self.access_token = access_token
        # base interna: si no se pasa, usar settings.public_base_url
        self.base_url = (base_url or settings.public_base_url).rstrip("/")

    def headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "X-Tenant-Id": self.tenant_id,
            "Content-Type": "application/json",
        }


async def _api_get(ctx: AIToolContext, path: str, params: dict | None = None) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(
            f"{ctx.base_url}{path}",
            params=params or {},
            headers=ctx.headers(),
        )
    return _handle(r, "GET", path)


async def _api_post(ctx: AIToolContext, path: str, json_body: dict) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(
            f"{ctx.base_url}{path}",
            json=json_body,
            headers=ctx.headers(),
        )
    return _handle(r, "POST", path)


async def _api_patch(ctx: AIToolContext, path: str, json_body: dict) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.patch(
            f"{ctx.base_url}{path}",
            json=json_body,
            headers=ctx.headers(),
        )
    return _handle(r, "PATCH", path)


async def _api_delete(ctx: AIToolContext, path: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.delete(
            f"{ctx.base_url}{path}",
            headers=ctx.headers(),
        )
    return _handle(r, "DELETE", path)


def _handle(r: httpx.Response, method: str, path: str) -> dict[str, Any]:
    if r.status_code >= 400:
        snippet = (r.text or "")[:300]
        logger.warning(f"[ai.tools] {method} {path} → {r.status_code}: {snippet}")
        return {"error": f"{method} {path} → HTTP {r.status_code}", "detail": snippet}
    if not r.text:
        return {"ok": True}
    try:
        return r.json()
    except json.JSONDecodeError:
        return {"ok": True, "raw": r.text[:500]}


# ── Implementación de las 7 tools ──────────────────────
async def tool_list_products(ctx: AIToolContext, *, search: str | None = None, status: str | None = None, page_size: int = 20) -> dict[str, Any]:
    """Lista productos del catálogo del tenant actual."""
    return await _api_get(
        ctx,
        f"/api/v1/tenants/{ctx.tenant_id}/products",
        {"search": search, "status": status, "page_size": page_size} if search or status else {"page_size": page_size},
    )


async def tool_get_stats_overview(ctx: AIToolContext, *, days: int = 30) -> dict[str, Any]:
    """Devuelve overview de ventas/órdenes/productos top del tenant."""
    return await _api_get(
        ctx,
        f"/api/v1/tenants/{ctx.tenant_id}/stats/overview",
        {"days": days},
    )


async def tool_list_promotions(ctx: AIToolContext, *, only_active: bool = True) -> dict[str, Any]:
    """Lista promociones activas (o todas) del tenant."""
    return await _api_get(
        ctx,
        f"/api/v1/tenants/{ctx.tenant_id}/promotions",
        {"only_active": str(only_active).lower()},
    )


async def tool_create_promotion(
    ctx: AIToolContext,
    *,
    name: str,
    discount_type: str,  # "percent" | "fixed"
    discount_value: int,  # %  o centavos
    starts_at: str | None = None,
    ends_at: str | None = None,
    product_ids: list[str] | None = None,
    code: str | None = None,
) -> dict[str, Any]:
    """Crea una nueva promoción para el tenant.

    `discount_value`:
    - si `discount_type=percent`, valor entre 1-100 (porcentaje).
    - si `discount_type=fixed`, valor en centavos.
    """
    body: dict[str, Any] = {
        "name": name,
        "discount_type": discount_type,
        "discount_value": int(discount_value),
        "type": "catalog_discount",
    }
    if starts_at:
        body["starts_at"] = starts_at
    if ends_at:
        body["ends_at"] = ends_at
    if product_ids:
        body["product_ids"] = product_ids
    if code:
        body["code"] = code
    return await _api_post(
        ctx,
        f"/api/v1/tenants/{ctx.tenant_id}/promotions",
        body,
    )


async def tool_list_customers(ctx: AIToolContext, *, search: str | None = None, page_size: int = 20) -> dict[str, Any]:
    """Lista clientes del tenant."""
    params: dict[str, Any] = {"page_size": page_size}
    if search:
        params["search"] = search
    return await _api_get(
        ctx,
        f"/api/v1/tenants/{ctx.tenant_id}/customers",
        params,
    )


async def tool_send_email_to_customer(
    ctx: AIToolContext,
    *,
    customer_id: str,
    subject: str,
    body: str,
) -> dict[str, Any]:
    """Envía un email transaccional a un cliente del tenant.

    El contenido se envía al servicio de email configurado (log/smtp/resend).
    """
    return await _api_post(
        ctx,
        f"/api/v1/tenants/{ctx.tenant_id}/customers/{customer_id}/email",
        {"subject": subject, "body": body},
    )


async def tool_get_tenant_info(ctx: AIToolContext) -> dict[str, Any]:
    """Devuelve información del tenant actual (nombre, plan, slugs)."""
    return await _api_get(ctx, f"/api/v1/tenants/{ctx.tenant_id}")


async def tool_get_tenant_public_urls(ctx: AIToolContext) -> dict[str, Any]:
    """Devuelve las URLs PÚBLICAS del tenant actual con el slug REAL sustituido.

    A diferencia de `get_app_help(topic="public_urls")` que devuelve los
    PATRONES con `{slug}` literal, esta tool resuelve `{slug}` por el
    identificador real del tenant y arma las URLs completas listas para
    mostrar al usuario y compartir.

    Casos de uso:
    - "Cuál es mi URL pública"
    - "El link para que mis clientes agenden"
    - "Cómo comparto mi tienda"
    - "Link de mi catálogo"

    Si el tenant todavía no tiene `slug` configurado, devuelve los patrones
    vacíos + un hint para que el LLM sepa que tiene que avisarle al usuario
    que primero debe completar el slug en Configuración.
    """
    try:
        from app.services import app_knowledge
    except Exception as e:  # noqa: BLE001
        logger.exception("[get_tenant_public_urls] no se pudo importar app_knowledge: %s", e)
        return {"error": "app_knowledge no disponible", "fallback": True}

    info = await _api_get(ctx, f"/api/v1/tenants/{ctx.tenant_id}")
    if isinstance(info, dict) and info.get("error"):
        return {
            "error": "No pude leer la información del tenant",
            "detail": info,
            "hint": "Pídele al usuario que verifique su sesión.",
        }

    slug = (info or {}).get("slug") if isinstance(info, dict) else None
    tenant_name = (info or {}).get("name") if isinstance(info, dict) else None

    if not slug:
        # Tenant sin slug: devolvemos los PATRONES para que la IA le avise
        # al usuario y le indique dónde configurarlo.
        return {
            "source": "app_knowledge",
            "topic": "tenant_public_urls",
            "tenant": {"name": tenant_name, "slug": None},
            "has_slug": False,
            "patterns": [
                {"key": u["key"], "pattern": u["pattern"], "description": u["description"]}
                for u in app_knowledge.list_public_urls()
            ],
            "hint": (
                "Este tenant aún no tiene slug configurado. Pídele al usuario "
                "que vaya a Configuración → Branding para definir un slug. "
                "Mientras tanto, muéstrale los patrones como referencia."
            ),
        }

    base = settings.public_base_url.rstrip("/")
    urls: list[dict[str, Any]] = []
    for u in app_knowledge.list_public_urls():
        pattern = u["pattern"]
        full_url = f"{base}{pattern.replace('{slug}', slug)}"
        urls.append({
            "key": u["key"],
            "url": full_url,
            "description": u["description"],
        })

    return {
        "source": "app_knowledge",
        "topic": "tenant_public_urls",
        "tenant": {"name": tenant_name, "slug": slug},
        "has_slug": True,
        "base_url": base,
        "urls": urls,
    }


async def tool_get_tenant_dashboard_urls(ctx: AIToolContext) -> dict[str, Any]:
    """Devuelve las URLs ABSOLUTAS y CLICKABLES del panel del WowHub AI Core.

    A diferencia de `get_app_help(topic="modules")` que devuelve los PATHS
    relativos (`/dashboard/products`), esta tool arma los links COMPLETOS
    con `settings.public_base_url` como prefijo, listos para que el LLM los
    muestre como `[texto](url)` y el usuario haga 1 click.

    Las rutas del panel son las MISMAS para todos los tenants (el contexto
    multi-tenant lo da la sesión/JWT, no el subdominio). Por eso la URL
    base es `public_base_url` y NO incluye el slug del tenant.

    Casos de uso:
    - "Cómo abro el panel de productos"
    - "Dónde veo mis reservas"
    - "El link del Admin IA"
    - "Pasame el link a la configuración"
    - "Mandame el link por WhatsApp" (cross-channel)

    Cada link viene con:
    - `key`: identificador interno (products, promotions, etc.)
    - `url`: link absoluto (https://wowhub.app/dashboard/products)
    - `description`: descripción breve del módulo
    - `requires_role`: rol mínimo necesario (para que la IA sepa si el
      usuario puede acceder; si su rol es menor, igual le muestra el link
      pero con un disclaimer para que verifique).

    Si el AI no puede resolver `settings.public_base_url` (raro, pero
    defensivo), devuelve los paths relativos + un warning para que la IA
    sepa que los links no van a ser clickeables fuera del SPA.
    """
    try:
        from app.services import app_knowledge
    except Exception as e:  # noqa: BLE001
        logger.exception("[get_tenant_dashboard_urls] no se pudo importar app_knowledge: %s", e)
        return {"error": "app_knowledge no disponible", "fallback": True}

    base = (settings.public_base_url or "").rstrip("/")
    if not base:
        # Fallback defensivo: devolver paths relativos con warning.
        return {
            "source": "app_knowledge",
            "topic": "tenant_dashboard_urls",
            "has_base_url": False,
            "warning": "settings.public_base_url no está configurado.",
            "paths": [
                {"key": m["key"], "path": m["path"], "description": m["description"],
                 "requires_role": m.get("requires_role_min", "staff")}
                for m in app_knowledge.list_modules()
            ],
            "hint": (
                "No pude armar URLs absolutas. Muestra los paths como "
                "referencia y avísale al usuario que tiene que estar "
                "logueado en el panel para acceder."
            ),
        }

    urls: list[dict[str, Any]] = []
    for m in app_knowledge.list_modules():
        full_url = f"{base}{m['path']}"
        urls.append({
            "key": m["key"],
            "label": m["label"],
            "url": full_url,
            "description": m["description"],
            "requires_role": _min_role_for_module(m["key"]),
        })

    return {
        "source": "app_knowledge",
        "topic": "tenant_dashboard_urls",
        "has_base_url": True,
        "base_url": base,
        "dashboard_urls": urls,
        "hint": (
            "Muestra los links con markdown `[texto](url)` para que sean "
            "clickeables. NUNCA respondas con paths desnudos ni con "
            "placeholders literales como 'tu-negocio' o '{slug}' — fuera "
            "del SPA no son clickeables y dejan al usuario con un link roto."
        ),
    }


def _min_role_for_module(module_key: str) -> str:
    """Rol mínimo requerido para acceder a un módulo del panel.

    Hoy:
    - superadmin       → is_superuser (a nivel de USUARIO, no membership)
    - admin_ia         → OWNER | ADMIN (de la membership)
    - config + modulos → STAFF+
    - resto            → VIEWER+ (cualquiera con acceso al tenant)

    Esta función existe para que la tool pueda anotar el requisito de rol
    en cada URL. NO bloquea el acceso — el guard server-side en cada
    endpoint hace el check real.
    """
    if module_key == "superadmin":
        return "superuser"
    if module_key == "admin_ia":
        return "admin"
    return "viewer"


# ── Nuevas tools (integración con módulos) ─────────────────────
async def tool_analyze_inventory(
    ctx: AIToolContext,
    *,
    category: str = "all",  # all | low_stock | out_of_stock | overstock | dead_stock | top_selling
    days_dead: int = 60,
    days_top: int = 30,
    overstock_threshold: int = 100,
    limit: int = 30,
) -> dict[str, Any]:
    """Analiza el inventario del tenant y devuelve un resumen accionable.

    Categorías disponibles:
    - all            → todo el catálogo con control de stock
    - low_stock      → productos con stock bajo (alerta)
    - out_of_stock   → productos sin stock
    - overstock      → productos con stock excesivo (> overstock_threshold)
    - dead_stock     → productos sin ventas en `days_dead` días
    - top_selling    → productos más vendidos en `days_top` días
    """
    return await _api_get(
        ctx,
        f"/api/v1/tenants/{ctx.tenant_id}/analytics/inventory",
        {
            "category": category,
            "days_dead": days_dead,
            "days_top": days_top,
            "overstock_threshold": overstock_threshold,
            "limit": limit,
        },
    )


async def tool_get_customer_segments(
    ctx: AIToolContext,
    *,
    segment: str = "all",  # all | inactive | top | new | vip | no_orders
    days_inactive: int = 60,
    days_new: int = 30,
    vip_min_orders: int = 5,
    vip_min_spent_cents: int = 50000,
    limit: int = 50,
) -> dict[str, Any]:
    """Devuelve clientes del tenant segmentados.

    Segmentos:
    - all         → todos los clientes activos
    - inactive    → sin compras en los últimos `days_inactive` días
    - top         → top 20% por gasto total
    - new         → creados en los últimos `days_new` días
    - vip         → >= `vip_min_orders` órdenes Y gasto >= `vip_min_spent_cents`
    - no_orders   → clientes que nunca compraron
    """
    return await _api_get(
        ctx,
        f"/api/v1/tenants/{ctx.tenant_id}/analytics/customer-segments",
        {
            "segment": segment,
            "days_inactive": days_inactive,
            "days_new": days_new,
            "vip_min_orders": vip_min_orders,
            "vip_min_spent_cents": vip_min_spent_cents,
            "limit": limit,
        },
    )


async def tool_send_campaign(
    ctx: AIToolContext,
    *,
    name: str,
    subject: str,
    body: str,
    segment: str = "all",  # all | inactive | top | new | vip | no_orders
    channel: str = "email",  # email | log
    only_marketing_opt_in: bool = True,
    days_inactive: int = 60,
    days_new: int = 30,
    vip_min_orders: int = 5,
    vip_min_spent_cents: int = 50000,
) -> dict[str, Any]:
    """Envía una campaña masiva (email) a un segmento de clientes.

    IMPORTANTE: esta tool envía emails REALES (o los registra si channel='log').
    Úsala SOLO después de que el usuario haya confirmado el preview.
    """
    return await _api_post(
        ctx,
        f"/api/v1/tenants/{ctx.tenant_id}/campaigns",
        {
            "name": name,
            "subject": subject,
            "body": body,
            "segment": segment,
            "channel": channel,
            "only_marketing_opt_in": only_marketing_opt_in,
            "days_inactive": days_inactive,
            "days_new": days_new,
            "vip_min_orders": vip_min_orders,
            "vip_min_spent_cents": vip_min_spent_cents,
        },
    )


# ── Tools de Bookings / Reservas (Fase 2) ─────────────────────
async def tool_list_bookings(
    ctx: AIToolContext,
    *,
    status: str | None = None,  # pending | confirmed | completed | canceled | no_show
    branch_id: str | None = None,
    date_from: str | None = None,  # ISO 8601
    date_to: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """Lista las reservas del tenant. Filtros opcionales por status,
    sucursal y rango de fechas (ISO 8601).

    Útil para preguntas tipo 'qué reservas tengo hoy', 'cuántas cancelaciones',
    'reservas pendientes', etc.
    """
    params: dict[str, Any] = {"limit": limit}
    if status:
        params["status"] = status
    if branch_id:
        params["branch_id"] = branch_id
    if date_from:
        params["date_from"] = date_from
    if date_to:
        params["date_to"] = date_to
    return await _api_get(
        ctx,
        f"/api/v1/tenants/{ctx.tenant_id}/bookings",
        params,
    )


async def tool_check_availability(
    ctx: AIToolContext,
    *,
    branch_id: str | None = None,
    date_from: str,  # ISO 8601
    date_to: str,    # ISO 8601
    duration_minutes: int = 60,
    slot_step_minutes: int = 30,
) -> dict[str, Any]:
    """Consulta los slots disponibles para reservar.

    Devuelve una lista de slots con `available: true/false` y los IDs de
    reservas que causarían conflicto. Sirve para proponer horarios al
    cliente antes de agendar.
    """
    return await _api_post(
        ctx,
        f"/api/v1/tenants/{ctx.tenant_id}/bookings/availability",
        {
            "branch_id": branch_id,
            "date_from": date_from,
            "date_to": date_to,
            "duration_minutes": duration_minutes,
            "slot_step_minutes": slot_step_minutes,
        },
    )


async def tool_create_booking(
    ctx: AIToolContext,
    *,
    customer_name: str,
    customer_phone: str,
    starts_at: str,  # ISO 8601
    ends_at: str,    # ISO 8601
    customer_email: str | None = None,
    branch_id: str | None = None,
    product_id: str | None = None,
    staff_name: str | None = None,
    notes: str | None = None,
    send_confirmation: bool = True,
) -> dict[str, Any]:
    """Crea una reserva en nombre del cliente.

    IMPORTANTE: antes de llamar a esta tool, usa `check_availability` para
    asegurarte de que el slot elegido está libre. Si hay conflicto, el
    endpoint devuelve 409.

    Si la sucursal tiene horarios (`Branch.hours`), la reserva debe caer
    dentro del horario de apertura.
    """
    body: dict[str, Any] = {
        "customer_name": customer_name,
        "customer_phone": customer_phone,
        "starts_at": starts_at,
        "ends_at": ends_at,
    }
    if customer_email:
        body["customer_email"] = customer_email
    if branch_id:
        body["branch_id"] = branch_id
    if product_id:
        body["product_id"] = product_id
    if staff_name:
        body["staff_name"] = staff_name
    if notes:
        body["notes"] = notes
    # No añadimos send_confirmation al body; va como query param.
    return await _api_post(
        ctx,
        f"/api/v1/tenants/{ctx.tenant_id}/bookings?send_confirmation={str(send_confirmation).lower()}",
        body,
    )


# ── Tool de ayuda sobre la plataforma (Guía de WowHub) ─────
async def tool_get_app_help(
    ctx: AIToolContext,
    *,
    topic: str = "general",
    question: str | None = None,
) -> dict[str, Any]:
    """Devuelve información verídica sobre WowHub (NO requiere HTTP).

    Lee de `app.services.app_knowledge`, que es la versión estructurada
    de `docs/CANONICAL_WOWHUB.md`. Esta tool existe para que el agente
    HELP pueda responder preguntas sobre la plataforma sin alucinar.

    Args:
        topic: Categoría de la consulta. Valores útiles:
               - "modules"        → lista de módulos del panel.
               - "public_urls"    → URLs públicas (landing, reservar, etc).
               - "auth"           → info de autenticación.
               - "faq"            → buscar en el FAQ.
               - "no_existe"      → lista de cosas que NO existen.
               - "general"        → resumen completo.
        question: Pregunta libre del usuario (se busca en FAQ si topic='faq').

    Returns:
        Dict con la info solicitada + marca `source: "app_knowledge"`.
    """
    try:
        from app.services import app_knowledge
    except Exception as e:  # noqa: BLE001
        logger.exception("[get_app_help] no se pudo importar app_knowledge: %s", e)
        return {"error": "app_knowledge no disponible", "fallback": True}

    topic_norm = (topic or "general").strip().lower()

    if topic_norm == "modules":
        return {
            "source": "app_knowledge",
            "topic": "modules",
            "modules": app_knowledge.list_modules(),
        }
    if topic_norm == "public_urls":
        return {
            "source": "app_knowledge",
            "topic": "public_urls",
            "urls": app_knowledge.list_public_urls(),
        }
    if topic_norm == "auth":
        return {
            "source": "app_knowledge",
            "topic": "auth",
            "auth_info": app_knowledge.list_auth_info(),
        }
    if topic_norm == "no_existe":
        return {
            "source": "app_knowledge",
            "topic": "no_existe",
            "no_existe": app_knowledge.list_no_existe(),
        }
    if topic_norm == "module" and question:
        mod = app_knowledge.get_module(question)
        if mod:
            return {"source": "app_knowledge", "topic": "module", "module": mod}
        return {"source": "app_knowledge", "topic": "module", "found": False,
                "available": [m["key"] for m in app_knowledge.list_modules()]}
    if topic_norm == "faq":
        # Si viene una pregunta, intentamos matchearla con el FAQ.
        answer = app_knowledge.faq_lookup(question or "")
        if answer:
            return {"source": "app_knowledge", "topic": "faq",
                    "question": question, "answer": answer}
        return {"source": "app_knowledge", "topic": "faq",
                "found": False,
                "hint": "Prueba con: 'cómo activo Reservas', 'dónde cambio mi contraseña', 'URL pública', 'qué módulos hay'."}
    # general → resumen corto
    return {
        "source": "app_knowledge",
        "topic": "general",
        "summary": app_knowledge.render_short_summary(),
    }


# ── Catálogo de tools (JSON Schema) ────────────────────
# Esto es lo que se manda al LLM en `tools=`.
TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "list_products",
            "description": "Lista los productos del catálogo del tenant actual. Usa esto cuando el usuario pregunte por productos, inventario, precios, o quiera buscar algo específico.",
            "parameters": {
                "type": "object",
                "properties": {
                    "search": {"type": "string", "description": "Texto a buscar en nombre/SKU/descripción."},
                    "status": {"type": "string", "enum": ["draft", "active", "out_of_stock", "archived"]},
                    "page_size": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_stats_overview",
            "description": "Devuelve métricas de ventas, órdenes, ticket promedio, top productos y top QRs del tenant. Útil para preguntas de negocio tipo '¿cómo van las ventas?'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {"type": "integer", "minimum": 1, "maximum": 365, "default": 30,
                             "description": "Ventana de tiempo en días."},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_promotions",
            "description": "Lista promociones del tenant, opcionalmente solo las activas.",
            "parameters": {
                "type": "object",
                "properties": {
                    "only_active": {"type": "boolean", "default": True},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_promotion",
            "description": "Crea una nueva promoción para el tenant. Confirma con el usuario antes de ejecutar esta tool.",
            "parameters": {
                "type": "object",
                "required": ["name", "discount_type", "discount_value"],
                "properties": {
                    "name": {"type": "string", "minLength": 2, "maxLength": 120},
                    "discount_type": {"type": "string", "enum": ["percent", "fixed"]},
                    "discount_value": {"type": "integer", "minimum": 1, "description": "% o centavos según discount_type"},
                    "starts_at": {"type": "string", "format": "date-time"},
                    "ends_at": {"type": "string", "format": "date-time"},
                    "product_ids": {"type": "array", "items": {"type": "string"}},
                    "code": {"type": "string", "description": "Código canjeable (opcional)"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_customers",
            "description": "Lista clientes del tenant, opcionalmente filtrando por búsqueda.",
            "parameters": {
                "type": "object",
                "properties": {
                    "search": {"type": "string"},
                    "page_size": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_email_to_customer",
            "description": "Envía un email transaccional a un cliente. Úsala solo cuando el usuario lo pida explícitamente.",
            "parameters": {
                "type": "object",
                "required": ["customer_id", "subject", "body"],
                "properties": {
                    "customer_id": {"type": "string"},
                    "subject": {"type": "string", "minLength": 2, "maxLength": 200},
                    "body": {"type": "string", "minLength": 2, "maxLength": 5000},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_tenant_info",
            "description": "Información general del tenant (nombre comercial, slug, plan, etc.). Útil para personalizar respuestas.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_tenant_public_urls",
            "description": (
                "Devuelve las URLs PÚBLICAS del tenant actual YA CON EL SLUG REAL "
                "sustituido (lista para mostrar y compartir). SIEMPRE usa esta tool "
                "cuando el usuario pregunte por su link para compartir, URL pública, "
                "link de reservas, link de catálogo o cómo compartir su tienda. NO "
                "devuelvas el patrón con `{slug}` literal ni con placeholders como "
                "'tu-negocio', 'tu-tienda', 'mi-negocio', 'my-business', '<slug>' o "
                "'[tu-slug]' — esta tool ya reemplaza el slug por el real del tenant. "
                "Muestra el resultado como markdown `[Texto](https://...)` para que "
                "sea clickeable. NUNCA hardcodees el dominio en una URL de respuesta. "
                "Si el tenant no tiene slug configurado, la tool devuelve los "
                "patrones y un hint para que la IA le pida al usuario configurarlo "
                "en Configuración → Branding."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_tenant_dashboard_urls",
            "description": (
                "⚠️ DEPRECATED en v1.9.1-r4. NO USES esta tool — el OpenAPI de "
                "producción (https://wowhub-api-production.up.railway.app/openapi.json) "
                "NO expone rutas HTML de dashboard. Las rutas `/dashboard/*` que "
                "devolvía esta tool NO existen para clientes externos y dan 404. "
                "Para URLs públicas (lo único que se puede compartir con clientes), "
                "usa `get_tenant_public_urls` en su lugar. Si el usuario pregunta por "
                "el 'panel' o 'admin', explícale que WowHub es una API — la gestión "
                "interna la hace él desde su sesión autenticada."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_inventory",
            "description": "Analiza el inventario del tenant y devuelve un resumen accionable: productos sin stock, con stock bajo, sobre-stock, sin rotación (vendieron hace mucho), o los más vendidos. Útil para preguntas tipo 'qué me falta', 'qué no se vende', 'qué vendío más este mes'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "enum": ["all", "low_stock", "out_of_stock", "overstock", "dead_stock", "top_selling"],
                        "default": "all",
                        "description": "Categoría de inventario a analizar.",
                    },
                    "days_dead": {"type": "integer", "minimum": 1, "maximum": 365, "default": 60,
                                  "description": "Días sin ventas para considerar 'dead_stock'."},
                    "days_top": {"type": "integer", "minimum": 1, "maximum": 365, "default": 30,
                                 "description": "Ventana para 'top_selling'."},
                    "overstock_threshold": {"type": "integer", "minimum": 1, "default": 100,
                                            "description": "Stock por encima del cual se considera 'overstock'."},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 200, "default": 30},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_customer_segments",
            "description": "Devuelve clientes del tenant segmentados: inactivos, top, nuevos, VIP, o que nunca compraron. Útil para 'a quién le puedo avisar', 'mis mejores clientes', 'quién no compra hace tiempo'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "segment": {
                        "type": "string",
                        "enum": ["all", "inactive", "top", "new", "vip", "no_orders"],
                        "default": "all",
                    },
                    "days_inactive": {"type": "integer", "minimum": 1, "maximum": 365, "default": 60},
                    "days_new": {"type": "integer", "minimum": 1, "maximum": 365, "default": 30},
                    "vip_min_orders": {"type": "integer", "minimum": 1, "default": 5},
                    "vip_min_spent_cents": {"type": "integer", "minimum": 0, "default": 50000},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 200, "default": 50},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_campaign",
            "description": "Envía una campaña masiva (email) a un segmento de clientes. IMPORTANTE: primero muestra el preview al usuario y ESPERA su confirmación antes de llamar a esta tool.",
            "parameters": {
                "type": "object",
                "required": ["name", "subject", "body", "segment"],
                "properties": {
                    "name": {"type": "string", "minLength": 2, "maxLength": 120,
                             "description": "Nombre interno de la campaña (auditoría)."},
                    "subject": {"type": "string", "minLength": 2, "maxLength": 200,
                                 "description": "Asunto del email."},
                    "body": {"type": "string", "minLength": 2, "maxLength": 5000,
                             "description": "Cuerpo del email (puede incluir HTML básico)."},
                    "segment": {
                        "type": "string",
                        "enum": ["all", "inactive", "top", "new", "vip", "no_orders"],
                        "description": "A quién enviar.",
                    },
                    "channel": {"type": "string", "enum": ["email", "log"], "default": "email",
                                "description": "email=enviar real, log=solo registrar (dry-run)."},
                    "only_marketing_opt_in": {"type": "boolean", "default": True,
                                              "description": "Si true, solo envía a clientes con accepts_marketing=True."},
                    "days_inactive": {"type": "integer", "minimum": 1, "maximum": 365, "default": 60},
                    "days_new": {"type": "integer", "minimum": 1, "maximum": 365, "default": 30},
                    "vip_min_orders": {"type": "integer", "minimum": 1, "default": 5},
                    "vip_min_spent_cents": {"type": "integer", "minimum": 0, "default": 50000},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_bookings",
            "description": "Lista las reservas del tenant. Permite filtrar por status, sucursal y rango de fechas. Útil para 'qué reservas tengo hoy', 'cuántas cancelaciones', 'reservas pendientes'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": ["pending", "confirmed", "completed", "canceled", "no_show"],
                        "description": "Filtrar por estado de la reserva.",
                    },
                    "branch_id": {"type": "string", "description": "UUID de la sucursal."},
                    "date_from": {"type": "string", "format": "date-time",
                                  "description": "ISO 8601. Reservas que empiezan después de esta fecha."},
                    "date_to": {"type": "string", "format": "date-time",
                                "description": "ISO 8601. Reservas que empiezan antes de esta fecha."},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 500, "default": 50},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_availability",
            "description": "Consulta los slots disponibles para reservar en un rango de fechas. Devuelve slots con `available: true/false` y los IDs de reservas que causan conflicto. Útil para proponer horarios al cliente.",
            "parameters": {
                "type": "object",
                "required": ["date_from", "date_to"],
                "properties": {
                    "branch_id": {"type": "string", "description": "UUID de la sucursal (opcional)."},
                    "date_from": {"type": "string", "format": "date-time",
                                  "description": "ISO 8601. Inicio del rango a consultar."},
                    "date_to": {"type": "string", "format": "date-time",
                                "description": "ISO 8601. Fin del rango a consultar."},
                    "duration_minutes": {"type": "integer", "minimum": 15, "maximum": 480, "default": 60,
                                          "description": "Duración de cada slot en minutos."},
                    "slot_step_minutes": {"type": "integer", "minimum": 5, "maximum": 120, "default": 30,
                                           "description": "Intervalo entre slots a evaluar."},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_booking",
            "description": "Crea una reserva en nombre del cliente. Antes de llamar a esta tool, usa check_availability para confirmar que el slot está libre. Si hay conflicto, el endpoint devuelve 409 y debes proponer otro horario.",
            "parameters": {
                "type": "object",
                "required": ["customer_name", "customer_phone", "starts_at", "ends_at"],
                "properties": {
                    "customer_name": {"type": "string", "minLength": 2, "maxLength": 160},
                    "customer_phone": {"type": "string", "minLength": 8, "maxLength": 40},
                    "customer_email": {"type": "string", "description": "Opcional, para enviar confirmación."},
                    "branch_id": {"type": "string", "description": "UUID de la sucursal."},
                    "product_id": {"type": "string", "description": "UUID del servicio a reservar."},
                    "staff_name": {"type": "string", "maxLength": 120,
                                   "description": "Nombre del profesional que atenderá."},
                    "starts_at": {"type": "string", "format": "date-time",
                                  "description": "ISO 8601. Inicio de la reserva."},
                    "ends_at": {"type": "string", "format": "date-time",
                                "description": "ISO 8601. Fin de la reserva."},
                    "notes": {"type": "string", "maxLength": 2000,
                              "description": "Notas internas (alergias, preferencias, etc)."},
                    "send_confirmation": {"type": "boolean", "default": True,
                                          "description": "Enviar email de confirmación al cliente."},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_app_help",
            "description": (
                "Devuelve información verídica sobre la plataforma WowHub: "
                "módulos del panel, rutas, URLs públicas, FAQ y cosas que NO "
                "existen. SIEMPRE usa esta tool cuando el usuario pregunte "
                "sobre cómo usar WowHub, dónde está algo, cómo se activa un "
                "módulo (ninguno requiere activación), URLs para clientes, "
                "cuenta, configuración, idioma, etc. NO inventes respuestas."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {
                        "type": "string",
                        "enum": ["general", "modules", "module", "public_urls",
                                 "auth", "faq", "no_existe"],
                        "default": "general",
                        "description": (
                            "Categoría de la consulta. 'modules' lista todos "
                            "los módulos del panel. 'module' busca uno "
                            "específico (usar con 'question'). 'public_urls' "
                            "lista URLs públicas (landing, reservar). 'auth' "
                            "info de cuenta/login. 'faq' busca una pregunta "
                            "libre (usar con 'question'). 'no_existe' lista "
                            "cosas que NO existen en WowHub (anti-alucinación)."
                        ),
                    },
                    "question": {
                        "type": "string",
                        "description": (
                            "Pregunta libre del usuario (usar con topic='faq' "
                            "o topic='module')."
                        ),
                    },
                },
            },
        },
    },
]

TOOL_DISPATCH: dict[str, Any] = {
    "list_products": tool_list_products,
    "get_stats_overview": tool_get_stats_overview,
    "list_promotions": tool_list_promotions,
    "create_promotion": tool_create_promotion,
    "list_customers": tool_list_customers,
    "send_email_to_customer": tool_send_email_to_customer,
    "get_tenant_info": tool_get_tenant_info,
    "get_tenant_public_urls": tool_get_tenant_public_urls,
    "get_tenant_dashboard_urls": tool_get_tenant_dashboard_urls,
    "analyze_inventory": tool_analyze_inventory,
    "get_customer_segments": tool_get_customer_segments,
    "send_campaign": tool_send_campaign,
    # Bookings Fase 2
    "list_bookings": tool_list_bookings,
    "check_availability": tool_check_availability,
    "create_booking": tool_create_booking,
    # Guía de WowHub (no hace HTTP, lee de app_knowledge)
    "get_app_help": tool_get_app_help,
}


def get_tools_for_agent(agent: str) -> list[dict[str, Any]]:
    """Filtra tools según el sub-agente. Si el agente no existe, devuelve todas.

    v1.9.1-r4:
    - `get_tenant_public_urls` está en los 5 sub-agentes (es la herramienta
      vigente de URLs públicas con slug real sustituido).
    - `get_tenant_dashboard_urls` está DEPRECADA y NO se distribuye a los
      sub-agentes. Sigue en TOOL_DISPATCH y TOOL_SCHEMAS solo por back-compat
      de tests legacy, pero ningún agente debe poder llamarla.

    v1.9.1-r7 (REVIERTE r6 — el feature de reservas SÍ está desplegado):
    - `list_bookings`, `check_availability` y `create_booking` se
      RESTAURAN en el toolset visible a marketing/growth/automation.
      r6 los había removido asumiendo que reservas estaba en roadmap,
      pero el owner confirmó el 2026-08-22 que el servicio de reservas
      ESTÁ ACTIVO en producción — los endpoints funcionan, los tenants
      pueden crear reservas, y el AI debe poder ayudar a los owners a
      usarlos con walkthroughs cuando lo pidan.
    - El AI ahora PUEDE dar instrucciones sobre cómo usar `check_availability`
      y `create_booking` cuando el usuario lo pida (ej. "dime cómo crear
      una reserva" → walkthrough real con esos tools).
    """
    rules: dict[str, list[str]] = {
        "marketing": [
            "list_products", "list_promotions", "get_stats_overview",
            "get_tenant_info", "analyze_inventory", "get_customer_segments",
            # v1.9.1-r7: bookings RESTAURADOS (feature activo en producción)
            "list_bookings", "check_availability", "create_booking",
            "get_app_help",
            "get_tenant_public_urls",  # v1.9.1-r4: link público del feature
        ],
        "growth": [
            "get_stats_overview", "list_promotions", "list_customers",
            "get_tenant_info", "analyze_inventory", "get_customer_segments",
            # v1.9.1-r7: bookings RESTAURADOS
            "list_bookings", "check_availability", "create_booking",
            "get_app_help",
            "get_tenant_public_urls",
        ],
        "automation": [
            "list_customers", "send_email_to_customer", "list_promotions",
            "get_tenant_info", "get_customer_segments", "send_campaign",
            # v1.9.1-r7: bookings RESTAURADOS
            "list_bookings", "check_availability", "create_booking",
            "get_app_help",
            "get_tenant_public_urls",
        ],
        "marketplace": [
            "list_products", "list_promotions", "get_stats_overview",
            "get_tenant_info", "analyze_inventory",
            "get_app_help",
            "get_tenant_public_urls",
        ],
        # Nuevo: Guía de WowHub. Solo lectura + get_tenant_info para URLs.
        # NO tiene tools de escritura (create_*, send_*) — el handoff a
        # automation es lo que ejecuta la acción, no HELP directamente.
        # v1.9.1-r4: `get_tenant_public_urls` es la herramienta de URLs
        # vigente. `get_tenant_dashboard_urls` está DEPRECADA.
        "help": [
            "get_app_help",
            "get_tenant_info",
            "get_tenant_public_urls",
        ],
    }
    names = rules.get(agent)
    if not names:
        return TOOL_SCHEMAS
    return [t for t in TOOL_SCHEMAS if t["function"]["name"] in names]
