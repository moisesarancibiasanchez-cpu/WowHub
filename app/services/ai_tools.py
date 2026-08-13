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
]

TOOL_DISPATCH: dict[str, Any] = {
    "list_products": tool_list_products,
    "get_stats_overview": tool_get_stats_overview,
    "list_promotions": tool_list_promotions,
    "create_promotion": tool_create_promotion,
    "list_customers": tool_list_customers,
    "send_email_to_customer": tool_send_email_to_customer,
    "get_tenant_info": tool_get_tenant_info,
}


def get_tools_for_agent(agent: str) -> list[dict[str, Any]]:
    """Filtra tools según el sub-agente. Si el agente no existe, devuelve todas."""
    rules: dict[str, list[str]] = {
        "marketing":   ["list_products", "list_promotions", "get_stats_overview", "get_tenant_info"],
        "growth":      ["get_stats_overview", "list_promotions", "list_customers", "get_tenant_info"],
        "automation":  ["list_customers", "send_email_to_customer", "list_promotions", "get_tenant_info"],
        "marketplace": ["list_products", "list_promotions", "get_stats_overview", "get_tenant_info"],
    }
    names = rules.get(agent)
    if not names:
        return TOOL_SCHEMAS
    return [t for t in TOOL_SCHEMAS if t["function"]["name"] in names]
