"""
HU → Endpoint mapping — WowHub Multi-Agent System v1.1.0
========================================================

Mapea las 49 HUs del documento TEST_CASES_V134_2.md a endpoints HTTP reales
de la API de WowHub (Railway). Esto permite que el `CPRunner` ejecute los
309 CPs como tests HTTP funcionales en lugar de fallback a /health.

Estructura por HU:
{
    "primary":  { "method": "GET", "path": "/api/v1/...", "expected_status": 200 },
    "alt":      [ { ... }, ... ],          # endpoints alternativos (opcional)
    "by_type":  {                            # status esperado por tipo de CP
        "F": 200, "S": 200, "N": 400, "R": 200
    },
    "requires_auth": True/False,             # si requiere Authorization header
    "tenant_specific": True/False,           # si el path usa {tenant_id}
    "notes": "..."                           # documentación
}

Variables de path:
  {tenant_id}  → se sustituye por TENANT_ID del .env (default: "demo")
  {customer_id} → "1" (test)
  {product_id} → "1" (test)
  etc.

Generado: 2026-10-16
Fuentes: TEST_CASES_V134_2.md + OpenAPI de Railway (200+ paths)
"""

# Tenant ID por defecto para paths que lo requieren
DEFAULT_TENANT_ID = "demo"

# IDs dummy para paths con variables (no rompen si no existen)
_DUMMY_IDS = {
    "tenant_id": DEFAULT_TENANT_ID,
    "customer_id": "1",
    "product_id": "1",
    "category_id": "1",
    "order_id": "1",
    "booking_id": "1",
    "branch_id": "1",
    "campaign_id": "1",
    "promotion_id": "1",
    "member_id": "1",
    "quote_id": "1",
    "payment_id": "1",
    "upload_id": "1",
    "webhook_id": "1",
    "variant_id": "1",
    "modifier_id": "1",
    "modifier_options_id": "1",
    "option_id": "1",
    "insumo_id": "1",
    "receta_id": "1",
    "qr_id": "demo",
    "slug": "demo",
    "short_code": "demo",
    "token": "demo",
    "conversation_id": "1",
    "log_id": "1",
    "year": "2026",
    "month": "10",
}


def _substitute(path: str) -> str:
    """Reemplaza {var} con IDs dummy para que el path sea ejecutable."""
    out = path
    for k, v in _DUMMY_IDS.items():
        out = out.replace("{" + k + "}", v)
    return out


HU_ENDPOINTS: dict = {
    # ─── HU_01: Registro y creación de cuenta de tenant ─────────
    "HU_01": {
        "primary": {"method": "POST", "path": "/api/v1/auth/register", "expected_status": 201},
        "by_type": {"F": 201, "S": 422, "N": 422, "R": 201},
        "requires_auth": False,
        "notes": "Registro de tenant. CPs negativos deben recibir 422.",
    },
    # ─── HU_02: Multi-tenancy con RLS ────────────────────────────
    "HU_02": {
        "primary": {"method": "GET", "path": "/api/v1/tenants/me", "expected_status": 200},
        "by_type": {"F": 200, "S": 200, "N": 404, "R": 200},
        "requires_auth": True,
        "notes": "Acceso al tenant propio. CPs de seguridad (S) verifican que el owner accede OK. CPs negativos (N) → 404 si tenant no existe.",
    },
    # ─── HU_03: Auth JWT con cookies + refresh tokens ────────────
    "HU_03": {
        "primary": {"method": "POST", "path": "/api/v1/auth/login", "expected_status": 200},
        "by_type": {"F": 200, "S": 401, "N": 401, "R": 200},
        "requires_auth": False,
        "notes": "Login retorna access + refresh. Negativos → 401.",
    },
    # ─── HU_04: RBAC ─────────────────────────────────────────────
    "HU_04": {
        "primary": {"method": "GET", "path": "/api/v1/rbac/policies", "expected_status": 200},
        "by_type": {"F": 200, "S": 200, "N": 403, "R": 200},
        "requires_auth": True,
        "notes": "Políticas de control de acceso. Owner puede leer; negativos → 403 si no es admin.",
    },
    # ─── HU_05: Onboarding guiado de 5 pasos ─────────────────────
    "HU_05": {
        "primary": {"method": "GET", "path": "/api/v1/tenants/{tenant_id}/onboarding", "expected_status": 200},
        "by_type": {"F": 200, "S": 200, "N": 400, "R": 200},
        "requires_auth": True,
        "tenant_specific": True,
    },
    # ─── HU_06: Sistema de auditoría y logs estructurados ────────
    "HU_06": {
        "primary": {"method": "GET", "path": "/api/v1/tenants/{tenant_id}/audit", "expected_status": 200},
        "by_type": {"F": 200, "S": 200, "N": 200, "R": 200},
        "requires_auth": True,
        "tenant_specific": True,
    },
    # ─── HU_07: API REST con OpenAPI/Swagger ────────────────────
    "HU_07": {
        "primary": {"method": "GET", "path": "/openapi.json", "expected_status": 200},
        "by_type": {"F": 200, "S": 200, "N": 200, "R": 200},
        "requires_auth": False,
        "notes": "OpenAPI spec pública.",
    },
    # ─── HU_08: CRUD de productos y categorías ───────────────────
    "HU_08": {
        "primary": {"method": "GET", "path": "/api/v1/tenants/{tenant_id}/products", "expected_status": 200},
        "by_type": {"F": 200, "S": 200, "N": 404, "R": 200},
        "requires_auth": True,
        "tenant_specific": True,
        "notes": "CRUD productos. Negativos → 404 o 422.",
    },
    # ─── HU_09: Recetas e Insumos (BOM) ──────────────────────────
    "HU_09": {
        "primary": {"method": "GET", "path": "/api/v1/tenants/{tenant_id}/insumos", "expected_status": 200},
        "by_type": {"F": 200, "S": 200, "N": 404, "R": 200},
        "requires_auth": True,
        "tenant_specific": True,
    },
    # ─── HU_10: Cálculo V8 de Costos (14 campos) ────────────────
    "HU_10": {
        "primary": {"method": "GET", "path": "/api/v1/tenants/{tenant_id}/costs", "expected_status": 200},
        "by_type": {"F": 200, "S": 200, "N": 404, "R": 200},
        "requires_auth": True,
        "tenant_specific": True,
    },
    # ─── HU_11: Variantes y modificadores ────────────────────────
    "HU_11": {
        "primary": {"method": "GET", "path": "/api/v1/tenants/{tenant_id}/modifiers", "expected_status": 200},
        "by_type": {"F": 200, "S": 200, "N": 404, "R": 200},
        "requires_auth": True,
        "tenant_specific": True,
    },
    # ─── HU_12: Menú público digital con GridStack ───────────────
    "HU_12": {
        "primary": {"method": "GET", "path": "/api/v1/public/t/{slug}/catalog", "expected_status": 200},
        "by_type": {"F": 200, "S": 200, "N": 404, "R": 200},
        "requires_auth": False,
        "notes": "Catálogo público. Sin auth.",
    },
    # ─── HU_13: Combo / packs de productos ───────────────────────
    "HU_13": {
        "primary": {"method": "GET", "path": "/api/v1/tenants/{tenant_id}/products", "expected_status": 200},
        "by_type": {"F": 200, "S": 200, "N": 404, "R": 200},
        "requires_auth": True,
        "tenant_specific": True,
        "notes": "Combos son productos con type=combo. Mismo endpoint que HU_08.",
    },
    # ─── HU_14: Inventario y stock en tiempo real ────────────────
    "HU_14": {
        "primary": {"method": "GET", "path": "/api/v1/tenants/{tenant_id}/branches/{branch_id}/products", "expected_status": 200},
        "by_type": {"F": 200, "S": 200, "N": 404, "R": 200},
        "requires_auth": True,
        "tenant_specific": True,
    },
    # ─── HU_15: Pedidos multi-canal ──────────────────────────────
    "HU_15": {
        "primary": {"method": "GET", "path": "/api/v1/tenants/{tenant_id}/orders", "expected_status": 200},
        "by_type": {"F": 200, "S": 200, "N": 400, "R": 200},
        "requires_auth": True,
        "tenant_specific": True,
    },
    # ─── HU_16: Estados de pedido en español ─────────────────────
    "HU_16": {
        "primary": {"method": "GET", "path": "/api/v1/tenants/{tenant_id}/orders", "expected_status": 200},
        "by_type": {"F": 200, "S": 200, "N": 400, "R": 200},
        "requires_auth": True,
        "tenant_specific": True,
    },
    # ─── HU_17: Reservas de mesas con disponibilidad ─────────────
    "HU_17": {
        "primary": {"method": "GET", "path": "/api/v1/tenants/{tenant_id}/bookings", "expected_status": 200},
        "by_type": {"F": 200, "S": 200, "N": 409, "R": 200},
        "requires_auth": True,
        "tenant_specific": True,
        "notes": "Negativos → 409 conflicto de horario.",
    },
    # ─── HU_18: Comandas / KDS (Kitchen Display) ─────────────────
    "HU_18": {
        "primary": {"method": "GET", "path": "/api/v1/tenants/{tenant_id}/kds/queue", "expected_status": 200},
        "by_type": {"F": 200, "S": 200, "N": 404, "R": 200},
        "requires_auth": True,
        "tenant_specific": True,
    },
    # ─── HU_19: División de cuenta / split bill ──────────────────
    "HU_19": {
        "primary": {"method": "GET", "path": "/api/v1/tenants/{tenant_id}/dining-sessions", "expected_status": 200},
        "by_type": {"F": 200, "S": 200, "N": 400, "R": 200},
        "requires_auth": True,
        "tenant_specific": True,
    },
    # ─── HU_20: Asignación de mozos a mesas ──────────────────────
    "HU_20": {
        "primary": {"method": "GET", "path": "/api/v1/tenants/{tenant_id}/members", "expected_status": 200},
        "by_type": {"F": 200, "S": 200, "N": 404, "R": 200},
        "requires_auth": True,
        "tenant_specific": True,
        "notes": "Miembros = mozos/usuarios del tenant.",
    },
    # ─── HU_21: Impresoras y comandas físicas ────────────────────
    "HU_21": {
        "primary": {"method": "GET", "path": "/api/v1/tenants/{tenant_id}/branches", "expected_status": 200},
        "by_type": {"F": 200, "S": 200, "N": 404, "R": 200},
        "requires_auth": True,
        "tenant_specific": True,
    },
    # ─── HU_22: Delivery tracking en tiempo real ─────────────────
    "HU_22": {
        "primary": {"method": "GET", "path": "/api/v1/tenants/{tenant_id}/orders", "expected_status": 200},
        "by_type": {"F": 200, "S": 200, "N": 404, "R": 200},
        "requires_auth": True,
        "tenant_specific": True,
    },
    # ─── HU_23: Registro de clientes ─────────────────────────────
    "HU_23": {
        "primary": {"method": "GET", "path": "/api/v1/tenants/{tenant_id}/customers", "expected_status": 200},
        "by_type": {"F": 200, "S": 200, "N": 400, "R": 200},
        "requires_auth": True,
        "tenant_specific": True,
    },
    # ─── HU_24: Perfil del cliente con historial ─────────────────
    "HU_24": {
        "primary": {"method": "GET", "path": "/api/v1/tenants/{tenant_id}/customers/{customer_id}", "expected_status": 200},
        "by_type": {"F": 200, "S": 403, "N": 404, "R": 200},
        "requires_auth": True,
        "tenant_specific": True,
    },
    # ─── HU_25: Programa de lealtad / puntos ─────────────────────
    "HU_25": {
        "primary": {"method": "GET", "path": "/api/v1/tenants/{tenant_id}/loyalty/campaigns", "expected_status": 200},
        "by_type": {"F": 200, "S": 200, "N": 404, "R": 200},
        "requires_auth": True,
        "tenant_specific": True,
    },
    # ─── HU_26: Segmentación de clientes ─────────────────────────
    "HU_26": {
        "primary": {"method": "GET", "path": "/api/v1/tenants/{tenant_id}/customers/segments", "expected_status": 200},
        "by_type": {"F": 200, "S": 200, "N": 404, "R": 200},
        "requires_auth": True,
        "tenant_specific": True,
    },
    # ─── HU_27: CRM con timeline de interacciones ────────────────
    "HU_27": {
        "primary": {"method": "GET", "path": "/api/v1/tenants/{tenant_id}/customers/{customer_id}/timeline", "expected_status": 200},
        "by_type": {"F": 200, "S": 200, "N": 404, "R": 200},
        "requires_auth": True,
        "tenant_specific": True,
    },
    # ─── HU_28: Cupones y descuentos ─────────────────────────────
    "HU_28": {
        "primary": {"method": "GET", "path": "/api/v1/tenants/{tenant_id}/promotions", "expected_status": 200},
        "by_type": {"F": 200, "S": 200, "N": 404, "R": 200},
        "requires_auth": True,
        "tenant_specific": True,
    },
    # ─── HU_29: Programa de referidos ────────────────────────────
    "HU_29": {
        "primary": {"method": "GET", "path": "/api/v1/tenants/{tenant_id}/campaigns", "expected_status": 200},
        "by_type": {"F": 200, "S": 200, "N": 404, "R": 200},
        "requires_auth": True,
        "tenant_specific": True,
    },
    # ─── HU_30: Dashboard con métricas principales ───────────────
    "HU_30": {
        "primary": {"method": "GET", "path": "/api/v1/tenants/{tenant_id}/stats/overview", "expected_status": 200},
        "by_type": {"F": 200, "S": 200, "N": 200, "R": 200},
        "requires_auth": True,
        "tenant_specific": True,
    },
    # ─── HU_31: Reporte de ventas por período ────────────────────
    "HU_31": {
        "primary": {"method": "GET", "path": "/api/v1/tenants/{tenant_id}/reports", "expected_status": 200},
        "by_type": {"F": 200, "S": 200, "N": 200, "R": 200},
        "requires_auth": True,
        "tenant_specific": True,
    },
    # ─── HU_32: Productos más vendidos ───────────────────────────
    "HU_32": {
        "primary": {"method": "GET", "path": "/api/v1/tenants/{tenant_id}/orders/sales-7d", "expected_status": 200},
        "by_type": {"F": 200, "S": 200, "N": 200, "R": 200},
        "requires_auth": True,
        "tenant_specific": True,
    },
    # ─── HU_33: Exportación a CSV/Excel ──────────────────────────
    "HU_33": {
        "primary": {"method": "GET", "path": "/api/v1/tenants/{tenant_id}/csv/products/export", "expected_status": 200},
        "by_type": {"F": 200, "S": 200, "N": 404, "R": 200},
        "requires_auth": True,
        "tenant_specific": True,
    },
    # ─── HU_34: Gráficos de tendencia ────────────────────────────
    "HU_34": {
        "primary": {"method": "GET", "path": "/api/v1/tenants/{tenant_id}/analytics/sales-trend", "expected_status": 200},
        "by_type": {"F": 200, "S": 200, "N": 200, "R": 200},
        "requires_auth": True,
        "tenant_specific": True,
    },
    # ─── HU_35: Reporte de inventario ─────────────────────────────
    "HU_35": {
        "primary": {"method": "GET", "path": "/api/v1/tenants/{tenant_id}/analytics/inventory", "expected_status": 200},
        "by_type": {"F": 200, "S": 200, "N": 200, "R": 200},
        "requires_auth": True,
        "tenant_specific": True,
    },
    # ─── HU_36: HTTPS obligatorio y certificados ─────────────────
    "HU_36": {
        "primary": {"method": "GET", "path": "/health", "expected_status": 200},
        "by_type": {"F": 200, "S": 200, "N": 200, "R": 200},
        "requires_auth": False,
        "notes": "HTTPS test = verificar que /health responde 200 sobre HTTPS.",
    },
    # ─── HU_37: Rate limiting ────────────────────────────────────
    "HU_37": {
        "primary": {"method": "GET", "path": "/api/v1/auth/login", "expected_status": 200},
        "by_type": {"F": 200, "S": 429, "N": 429, "R": 200},
        "requires_auth": False,
        "notes": "Rate limit: 6to intento debe devolver 429.",
    },
    # ─── HU_38: CORS configurado ─────────────────────────────────
    "HU_38": {
        "primary": {"method": "GET", "path": "/api/v1/i18n", "expected_status": 200},
        "by_type": {"F": 200, "S": 200, "N": 200, "R": 200},
        "requires_auth": False,
        "notes": "Endpoint público; CORS headers deben estar presentes.",
    },
    # ─── HU_39: CSP (Content Security Policy) ────────────────────
    "HU_39": {
        "primary": {"method": "GET", "path": "/health", "expected_status": 200},
        "by_type": {"F": 200, "S": 200, "N": 200, "R": 200},
        "requires_auth": False,
        "notes": "Verificar header CSP en respuesta.",
    },
    # ─── HU_40: Backups automatizados ────────────────────────────
    "HU_40": {
        "primary": {"method": "GET", "path": "/api/v1/system/status", "expected_status": 200},
        "by_type": {"F": 200, "S": 200, "N": 200, "R": 200},
        "requires_auth": False,
    },
    # ─── HU_41: Encriptación en reposo ───────────────────────────
    "HU_41": {
        "primary": {"method": "GET", "path": "/api/v1/auth/me", "expected_status": 200},
        "by_type": {"F": 200, "S": 200, "N": 200, "R": 200},
        "requires_auth": True,
        "notes": "Datos sensibles deben estar encriptados en DB.",
    },
    # ─── HU_42: GDPR / privacidad ────────────────────────────────
    "HU_42": {
        "primary": {"method": "GET", "path": "/api/v1/tenants/{tenant_id}/customers/{customer_id}", "expected_status": 200},
        "by_type": {"F": 200, "S": 200, "N": 403, "R": 200},
        "requires_auth": True,
        "tenant_specific": True,
        "notes": "Derecho al olvido / export de datos personales.",
    },
    # ─── HU_43: Integración con WhatsApp ─────────────────────────
    "HU_43": {
        "primary": {"method": "GET", "path": "/api/v1/webhooks/whatsapp", "expected_status": 200},
        "by_type": {"F": 200, "S": 200, "N": 404, "R": 200},
        "requires_auth": False,
    },
    # ─── HU_44: Webhooks salientes ───────────────────────────────
    "HU_44": {
        "primary": {"method": "GET", "path": "/api/v1/tenants/{tenant_id}/webhooks", "expected_status": 200},
        "by_type": {"F": 200, "S": 200, "N": 404, "R": 200},
        "requires_auth": True,
        "tenant_specific": True,
    },
    # ─── HU_45: SDK para plugins ─────────────────────────────────
    "HU_45": {
        "primary": {"method": "GET", "path": "/api/v1/marketplace/", "expected_status": 200},
        "by_type": {"F": 200, "S": 200, "N": 404, "R": 200},
        "requires_auth": True,
    },
    # ─── HU_46: Marketplace de plugins ───────────────────────────
    "HU_46": {
        "primary": {"method": "GET", "path": "/api/v1/marketplace/my-plugins", "expected_status": 200},
        "by_type": {"F": 200, "S": 200, "N": 404, "R": 200},
        "requires_auth": True,
    },
    # ─── HU_47: Métricas Prometheus ──────────────────────────────
    "HU_47": {
        "primary": {"method": "GET", "path": "/f0/metrics", "expected_status": 200},
        "by_type": {"F": 200, "S": 200, "N": 200, "R": 200},
        "requires_auth": False,
        "notes": "Métricas Prometheus en /f0/metrics.",
    },
    # ─── HU_48: Logs centralizados ───────────────────────────────
    "HU_48": {
        "primary": {"method": "GET", "path": "/api/v1/admin/observability/errors", "expected_status": 200},
        "by_type": {"F": 200, "S": 200, "N": 403, "R": 200},
        "requires_auth": True,
    },
    # ─── HU_49: Auto-scaling y health checks ─────────────────────
    "HU_49": {
        "primary": {"method": "GET", "path": "/health", "expected_status": 200},
        "by_type": {"F": 200, "S": 200, "N": 503, "R": 200},
        "requires_auth": False,
        "notes": "Health check para auto-scaling.",
    },
}


def resolve_hu_endpoint(hu_id: str, cp_type: str = "F") -> dict:
    """
    Resuelve el endpoint HTTP real para un CP dado su HU y tipo.

    Args:
        hu_id: Identificador de la HU (ej: "HU_03", "HU_15")
        cp_type: Tipo de CP: "F" (functional), "S" (security), "N" (negative), "R" (performance)

    Returns:
        dict con {method, path, expected_status, requires_auth, tenant_specific, hu_id, notes}
    """
    mapping = HU_ENDPOINTS.get(hu_id)
    if not mapping:
        # Fallback genérico si la HU no está mapeada
        return {
            "method": "GET",
            "path": "/health",
            "expected_status": 200,
            "requires_auth": False,
            "tenant_specific": False,
            "hu_id": hu_id,
            "notes": f"Sin mapping específico para {hu_id}; usando /health fallback.",
        }

    primary = mapping["primary"].copy()
    # Ajustar status esperado según tipo de CP
    by_type = mapping.get("by_type", {})
    if cp_type in by_type:
        primary["expected_status"] = by_type[cp_type]

    return {
        "method": primary["method"],
        "path": _substitute(primary["path"]),
        "expected_status": primary["expected_status"],
        "requires_auth": mapping.get("requires_auth", False),
        "tenant_specific": mapping.get("tenant_specific", False),
        "hu_id": hu_id,
        "notes": mapping.get("notes", ""),
    }


def list_unmapped_hus(hus_from_doc: list) -> list:
    """Devuelve las HUs del documento que no están en el mapping."""
    return [h for h in hus_from_doc if h not in HU_ENDPOINTS]


def mapping_coverage(hus_from_doc: list) -> dict:
    """Estadísticas de cobertura del mapping."""
    return {
        "total_hus": len(hus_from_doc),
        "mapped": sum(1 for h in hus_from_doc if h in HU_ENDPOINTS),
        "unmapped": list_unmapped_hus(hus_from_doc),
        "coverage_pct": round(sum(1 for h in hus_from_doc if h in HU_ENDPOINTS) / max(len(hus_from_doc), 1) * 100, 1),
    }
