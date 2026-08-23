"""Schemas Pydantic del AI Core (WowHub).

Contratos públicos de la API de IA. Versión 0.3.0.
"""
from datetime import datetime, timezone
from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.ai import (
    AgentKind, ConversationStatus, LogStatus, MessageRole,
)


# ── Chat: request / response ────────────────────────────
class HandoffPayload(BaseModel):
    """Payload de handoff entre agentes (ej. HELP → AUTOMATION).

    Cuando el cliente envía un handoff, el orquestador:
    1. Cambia el agente activo al `target_agent` (típicamente "automation").
    2. Inyecta el `action` y `params` como contexto para que el agente
       objetivo ejecute la acción confirmada por el usuario.
    3. Devuelve un campo `handoff_executed: true` en la respuesta.

    El cliente debe mostrar un preview claro al usuario ANTES de enviar
    el handoff. Esta es la confirmación explícita que el orquestador
    exigía ya para tools de escritura (create_*, send_*).
    """
    target_agent: AgentKind = Field(
        ..., description="Agente que ejecutará la acción (ej. AUTOMATION)."
    )
    action: str = Field(
        ..., min_length=1, max_length=120,
        description="Nombre semántico de la acción (ej. 'create_booking')."
    )
    params: dict[str, Any] = Field(
        default_factory=dict,
        description="Parámetros confirmados por el usuario para la acción.",
    )
    # Texto opcional que el usuario vio y confirmó. Se persiste en el log.
    preview_text: Optional[str] = None


class ChatMessageIn(BaseModel):
    """Mensaje entrante del usuario (request)."""
    content: str = Field(..., min_length=1, max_length=4000)
    # Opcional: continuar una conversación existente
    conversation_id: Optional[UUID] = None
    # Forzar sub-agente (si no, el router decide)
    force_agent: Optional[AgentKind] = None
    # Handoff explícito (ej. HELP → AUTOMATION) con confirmación del usuario.
    handoff: Optional[HandoffPayload] = None


class ChatRequest(BaseModel):
    """Body de POST /api/v1/ai/chat."""
    message: ChatMessageIn
    # Si true, devuelve SSE; si false, devuelve ChatResponse
    stream: bool = False


class ToolCallOut(BaseModel):
    name: str
    args: dict[str, Any] = Field(default_factory=dict)
    result: Optional[dict[str, Any]] = None


class ChatResponse(BaseModel):
    """Respuesta no-streaming."""
    conversation_id: UUID
    message_id: UUID
    agent: AgentKind
    content: str
    fallback: bool = False
    tool_calls: list[ToolCallOut] = Field(default_factory=list)
    latency_ms: int = 0
    tokens_in: Optional[int] = None
    tokens_out: Optional[int] = None


# ── Conversation ────────────────────────────────────────
class ConversationOut(BaseModel):
    id: UUID
    user_id: UUID
    tenant_id: UUID
    title: Optional[str] = None
    agent: AgentKind
    status: ConversationStatus
    message_count: int
    last_message_at: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ConversationCreate(BaseModel):
    title: Optional[str] = None
    agent: Optional[AgentKind] = None


class MessageOut(BaseModel):
    id: UUID
    conversation_id: UUID
    role: MessageRole
    content: str
    agent: Optional[AgentKind] = None
    tool_name: Optional[str] = None
    tool_call_id: Optional[str] = None
    tool_args: Optional[dict[str, Any]] = None
    tool_result: Optional[dict[str, Any]] = None
    tokens_in: Optional[int] = None
    tokens_out: Optional[int] = None
    latency_ms: Optional[int] = None
    fallback: bool = False
    created_at: datetime

    model_config = {"from_attributes": True}


class ConversationListOut(BaseModel):
    items: list[ConversationOut]
    total: int
    page: int
    page_size: int


class MessageListOut(BaseModel):
    items: list[MessageOut]
    total: int


# ── Admin ───────────────────────────────────────────────
class LogOut(BaseModel):
    id: UUID
    user_id: Optional[UUID] = None
    conversation_id: Optional[UUID] = None
    agent: AgentKind
    status: LogStatus
    user_message: Optional[str] = None
    assistant_message: Optional[str] = None
    error: Optional[str] = None
    error_code: Optional[str] = None
    tokens_in: Optional[int] = None
    tokens_out: Optional[int] = None
    latency_ms: Optional[int] = None
    tools_called: Optional[list[str]] = None
    circuit_state_before: Optional[str] = None
    circuit_state_after: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class LogListOut(BaseModel):
    items: list[LogOut]
    total: int
    page: int
    page_size: int


class TraceOut(BaseModel):
    id: UUID
    log_id: Optional[UUID] = None
    conversation_id: Optional[UUID] = None
    step: str
    detail: Optional[dict[str, Any]] = None
    duration_ms: Optional[int] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class TraceListOut(BaseModel):
    items: list[TraceOut]
    total: int


class MetricDailyOut(BaseModel):
    day: datetime
    agent: AgentKind
    requests: int
    success: int
    fallback: int
    errors: int
    timeouts: int
    rate_limited: int
    tokens_in: int
    tokens_out: int
    avg_latency_ms: int
    p95_latency_ms: int
    unique_users: int

    model_config = {"from_attributes": True}


class AIOverviewOut(BaseModel):
    """Resumen ejecutivo para el dashboard admin."""
    last_24h: MetricDailyOut
    last_7d: list[MetricDailyOut]
    circuit_state: str
    llm_enabled: bool
    llm_model: Optional[str] = None
    llm_provider: Optional[str] = None
    total_conversations: int
    total_messages: int
    active_users_7d: int


# ── Streaming (SSE) ─────────────────────────────────────
class StreamEvent(BaseModel):
    """Un chunk de la respuesta stream. Se serializa como JSON-line o SSE."""
    type: Literal["start", "token", "tool_call", "tool_result", "done", "error", "fallback"]
    agent: Optional[AgentKind] = None
    conversation_id: Optional[UUID] = None
    message_id: Optional[UUID] = None
    content: Optional[str] = None
    tool: Optional[ToolCallOut] = None
    error: Optional[str] = None
    fallback: bool = False
    latency_ms: Optional[int] = None


# ── Marketing Studio ─────────────────────────────────────
# WowHub AI Core™ — Marketing Studio (Cap. 19.1)
# Endpoint: POST /api/v1/ai/marketing/generate
# Genera copy de marketing contextual al negocio (texto + hashtags +
# variantes alternativas) usando el LLM. Tiene fallback con templates
# pre-armados para cuando el LLM no está disponible.
from enum import Enum


class MarketingIntent(str, Enum):
    """Tipo de contenido que se quiere generar."""
    INSTAGRAM_POST = "instagram_post"           # Post de Instagram (caption)
    INSTAGRAM_STORY = "instagram_story"          # Story con texto corto
    INSTAGRAM_REEL = "instagram_reel"            # Guion de Reel
    FACEBOOK_POST = "facebook_post"              # Post de Facebook
    WHATSAPP_BROADCAST = "whatsapp_broadcast"    # Difusión por WhatsApp Business
    WHATSAPP_STATUS = "whatsapp_status"          # Estado de WhatsApp
    EMAIL_SUBJECT = "email_subject"              # Asunto de email (1-2 líneas)
    EMAIL_BODY = "email_body"                    # Cuerpo de email promocional
    SMS = "sms"                                  # SMS promocional (≤160 chars)
    PRODUCT_DESCRIPTION = "product_description"  # Descripción de producto del catálogo
    PROMOTION_HEADLINE = "promotion_headline"    # Titular corto de promoción
    PROMOTION_BODY = "promotion_body"            # Cuerpo descriptivo de promoción
    GENERAL = "general"                          # Texto libre (default)


class MarketingTone(str, Enum):
    """Tono del copy."""
    FRIENDLY = "friendly"          # Cálido, cercano, "tú"
    PROFESSIONAL = "professional"  # Formal pero accesible
    URGENT = "urgent"              # Con sentido de urgencia (oferta限时)
    PLAYFUL = "playful"            # Divertido, con humor ligero
    LUXURY = "luxury"              # Premium, exclusivo
    CASUAL = "casual"              # Relajado, coloquial
    INSPIRATIONAL = "inspirational"  # Motivacional, aspiracional


class MarketingAudience(str, Enum):
    """Segmento objetivo del copy."""
    ALL = "all"                    # Todos los clientes
    EXISTING = "existing"          # Clientes actuales
    PROSPECTS = "prospects"        # Potenciales clientes
    VIP = "vip"                    # Clientes VIP / top
    INACTIVE = "inactive"          # Clientes inactivos (winback)
    NEW = "new"                    # Clientes nuevos
    LOCAL = "local"                # Audiencia local/barrio


class MarketingContext(BaseModel):
    """Contexto del negocio que se inyecta al prompt del LLM.
    Todos los campos son opcionales: con menos contexto, el copy será
    más genérico. Con más, será más personalizado."""
    business_name: Optional[str] = Field(
        None, max_length=120,
        description="Nombre del negocio. Si se omite, se intenta resolver del tenant."
    )
    business_type: Optional[str] = Field(
        None, max_length=120,
        description="Tipo de negocio (ej. 'cafetería', 'peluquería', 'tienda de ropa')."
    )
    city: Optional[str] = Field(
        None, max_length=80,
        description="Ciudad o barrio del negocio (para cercanía)."
    )
    product_name: Optional[str] = Field(
        None, max_length=120,
        description="Nombre del producto o servicio a promocionar (si aplica)."
    )
    product_features: Optional[list[str]] = Field(
        default=None, max_length=8,
        description="Bullets cortos de features del producto (max 8, ≤60 chars c/u)."
    )
    price: Optional[str] = Field(
        None, max_length=60,
        description="Precio o rango (ej. '$15.000', '2x $20.000')."
    )
    promotion_details: Optional[str] = Field(
        None, max_length=300,
        description="Detalles concretos de la promo (ej. '20% off, válido hasta el 30/11')."
    )
    cta: Optional[str] = Field(
        None, max_length=80,
        description="Call-to-action deseado (ej. 'Reservá ahora', 'Comprá hoy')."
    )
    public_url: Optional[str] = Field(
        None, max_length=300,
        description="URL pública del negocio (la REAL, ya con el slug sustituido)."
    )
    extra_notes: Optional[str] = Field(
        None, max_length=500,
        description="Notas adicionales que el usuario quiera incluir."
    )


class MarketingRequest(BaseModel):
    """Body de POST /api/v1/ai/marketing/generate."""
    intent: MarketingIntent = Field(
        default=MarketingIntent.GENERAL,
        description="Qué tipo de copy se quiere generar."
    )
    topic: str = Field(
        ..., min_length=3, max_length=400,
        description="Tema o idea central del copy (ej. 'promoción 2x1 en café')."
    )
    tone: MarketingTone = Field(
        default=MarketingTone.FRIENDLY,
        description="Tono del copy."
    )
    audience: MarketingAudience = Field(
        default=MarketingAudience.ALL,
        description="Segmento objetivo."
    )
    keywords: Optional[list[str]] = Field(
        default=None, max_length=12,
        description="Palabras clave a incluir (opcional, max 12)."
    )
    include_emojis: bool = Field(
        default=True,
        description="Si se permiten emojis en el copy."
    )
    include_hashtags: bool = Field(
        default=False,
        description="Si se deben incluir hashtags al final."
    )
    hashtag_count: int = Field(
        default=5, ge=0, le=20,
        description="Cantidad de hashtags a generar (0 = no generar)."
    )
    language: str = Field(
        default="es", min_length=2, max_length=5,
        description="Código de idioma (ISO 639-1, default 'es')."
    )
    max_length: Optional[int] = Field(
        default=None, ge=20, le=4000,
        description="Límite opcional de caracteres del contenido principal."
    )
    variants: int = Field(
        default=3, ge=1, le=5,
        description="Cantidad de variantes a generar (1-5). Default 3."
    )
    context: MarketingContext = Field(
        default_factory=MarketingContext,
        description="Contexto del negocio (nombre, producto, precio, etc.)."
    )


class MarketingVariant(BaseModel):
    """Una variante de copy."""
    index: int = Field(..., ge=1, le=10, description="Índice de la variante (1-based).")
    content: str = Field(..., description="El copy generado para esta variante.")
    hashtags: list[str] = Field(
        default_factory=list,
        description="Hashtags sugeridos para esta variante (si include_hashtags=true)."
    )
    character_count: int = Field(..., ge=0, description="Largo en caracteres del content.")


class MarketingResponse(BaseModel):
    """Respuesta de POST /api/v1/ai/marketing/generate."""
    id: UUID = Field(
        default_factory=lambda: __import__("uuid").uuid4(),
        description="ID único de la generación (no se persiste por ahora)."
    )
    intent: MarketingIntent
    topic: str
    tone: MarketingTone
    audience: MarketingAudience
    primary: MarketingVariant = Field(
        ...,
        description="La mejor variante (índice 1 por defecto). Es la recomendada."
    )
    variants: list[MarketingVariant] = Field(
        default_factory=list,
        description="Todas las variantes generadas (incluye la primary)."
    )
    hashtags: list[str] = Field(
        default_factory=list,
        description="Hashtags globales sugeridos (deduplicados, de todas las variantes)."
    )
    fallback: bool = Field(
        False,
        description="True si se usó fallback (LLM no disponible). El copy es template."
    )
    model: Optional[str] = Field(
        None,
        description="Modelo LLM usado (None si fue fallback)."
    )
    tokens_in: Optional[int] = None
    tokens_out: Optional[int] = None
    latency_ms: int = 0
    # Contexto efectivo que se usó (resuelto desde tenant si el usuario no lo pasó)
    resolved_context: Optional[dict] = Field(
        None,
        description="Contexto del negocio que se terminó usando (mezcla de request + tenant)."
    )


# ── Image Prompt (Marketing Studio — auxiliar) ─────────────────────
# Endpoint: POST /api/v1/ai/marketing/image-prompt
# Genera un prompt descriptivo de imagen para acompañar el copy de
# marketing. Útil para crear creatividades en Midjourney/DALL-E/
# Stable Diffusion. NO genera la imagen: solo el prompt textual.

class ImagePromptRequest(BaseModel):
    """Body de POST /api/v1/ai/marketing/image-prompt.

    El usuario pasa el copy ya generado y le pedimos al LLM que
    proponga una imagen para acompañarlo. Si el LLM no está disponible,
    el servicio devuelve un prompt construido localmente (fallback).
    """
    copy: str = Field(
        ..., min_length=10, max_length=2000,
        description="Copy de marketing ya generado (la variante visualizada).",
    )
    intent: MarketingIntent = Field(
        default=MarketingIntent.INSTAGRAM_POST,
        description="Canal/formato del copy (afecta aspect ratio sugerido).",
    )
    tone: MarketingTone = Field(
        default=MarketingTone.FRIENDLY,
        description="Tono del copy (afecta el estilo visual del prompt).",
    )
    audience: MarketingAudience = Field(
        default=MarketingAudience.ALL,
        description="Audiencia objetivo (afecta el sujeto visual).",
    )
    extra_notes: Optional[str] = Field(
        default=None, max_length=400,
        description="Indicaciones adicionales (ej. 'usar mi producto X').",
    )


class ImagePromptResponse(BaseModel):
    """Respuesta de POST /api/v1/ai/marketing/image-prompt."""
    prompt: str = Field(
        ...,
        description="Prompt descriptivo de la imagen (en inglés, listo para Midjourney/DALL-E).",
    )
    aspect_ratio: str = Field(
        "1:1",
        description="Aspect ratio sugerido para el canal (ej. '1:1', '9:16', '16:9').",
    )
    style: str = Field(
        "photorealistic",
        description="Estilo visual sugerido (photorealistic, illustration, flat, etc.).",
    )
    fallback: bool = Field(
        False,
        description="True si se construyó localmente (LLM no disponible).",
    )


# ── Growth Coach (WowHub AI Core™ — Cap. 19.2) ────────────────────
# Análisis proactivo de la "Memoria de Negocio" (ventas, inventario,
# clientes, promociones, reservas) que devuelve insights accionables.
# Endpoint: POST /api/v1/ai/growth/analyze

class GrowthFocus(str):
    """Placeholder; usamos Literal en su lugar (Pydantic v2 + tipado limpio)."""
    pass


# En Pydantic v2 los "enums de string" se modelan mejor con str + Literal.
GrowthFocusLiteral = Literal[
    "overview",     # vista 360 del negocio (default)
    "sales",        # ingresos, ticket promedio, tendencias
    "inventory",    # stock bajo, muerto, top selling
    "customers",    # segmentos, inactivos, VIPs
    "promotions",   # activas, frecuencia, impacto
    "bookings",     # reservas, cancelaciones, servicios top
    "mixed",        # prioriza diversidad de categorías (1-2 por categoría)
]


class GrowthAnalysisRequest(BaseModel):
    """Request de POST /api/v1/ai/growth/analyze."""
    focus: Literal[
        "overview", "sales", "inventory", "customers",
        "promotions", "bookings", "mixed",
    ] = Field(
        "overview",
        description=(
            "Área del negocio a analizar. 'overview' = 360° general. "
            "'mixed' = 1-2 insights por categoría (útil para vista semanal)."
        ),
    )
    lookback_days: int = Field(
        30,
        ge=7,
        le=180,
        description="Ventana de análisis en días (mín 7, máx 180). Default 30.",
    )
    language: str = Field(
        "es",
        min_length=2,
        max_length=8,
        description="Idioma del summary y de las recomendaciones (ISO 639-1).",
    )
    max_insights: int = Field(
        8,
        ge=3,
        le=20,
        description="Cantidad máxima de insights a devolver. Default 8, máx 20.",
    )


class GrowthInsightType:
    """Tipos de insight (string constants)."""
    OPPORTUNITY = "opportunity"        # oportunidad de crecer
    WARNING = "warning"                # alerta que requiere atención
    ANOMALY = "anomaly"                # comportamiento fuera de patrón
    RECOMMENDATION = "recommendation"  # sugerencia accionable
    INSIGHT = "insight"                # observación informativa


class GrowthInsightCategory:
    """Categorías del insight (a qué parte del negocio aplica)."""
    SALES = "sales"
    INVENTORY = "inventory"
    CUSTOMERS = "customers"
    PROMOTIONS = "promotions"
    BOOKINGS = "bookings"
    OPERATIONS = "operations"


class GrowthInsightPriority:
    """Prioridad del insight (el endpoint los ordena por esto desc)."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class GrowthInsight(BaseModel):
    """Un insight accionable generado por el Growth Coach."""
    id: UUID = Field(
        default_factory=lambda: __import__("uuid").uuid4(),
        description="ID único del insight (no se persiste por ahora).",
    )
    type: Literal[
        "opportunity", "warning", "anomaly", "recommendation", "insight",
    ] = Field(
        ...,
        description=(
            "Tipo: opportunity (crecer), warning (alerta), anomaly (fuera de patrón), "
            "recommendation (acción concreta), insight (observación)."
        ),
    )
    priority: Literal["low", "medium", "high", "urgent"] = Field(
        ...,
        description="Prioridad operativa. El endpoint ordena por esto descendente.",
    )
    category: Literal[
        "sales", "inventory", "customers", "promotions", "bookings", "operations",
    ] = Field(
        ...,
        description="Categoría del insight (a qué módulo del dashboard apunta).",
    )
    title: str = Field(
        ...,
        min_length=5,
        max_length=120,
        description="Título corto del insight (≤120 chars, listo para mostrar como heading).",
    )
    description: str = Field(
        ...,
        min_length=10,
        max_length=1000,
        description="Descripción de 1-3 oraciones que explica el insight.",
    )
    evidence: list[str] = Field(
        default_factory=list,
        description=(
            "Lista de datos puntuales que respaldan el insight "
            "(ej. ['Ingresos últimos 7 días: $1.2M', 'Hace 30 días: $1.8M'])."
        ),
    )
    recommended_actions: list[str] = Field(
        default_factory=list,
        description=(
            "Lista de acciones sugeridas (1-5). La UI puede renderizarlas como "
            "checklist o como 'Quick action' que lleva al módulo correspondiente."
        ),
    )
    linked_module: Optional[str] = Field(
        None,
        max_length=64,
        description=(
            "Slug del módulo al que apunta la acción principal "
            "(ej. 'promotions', 'products', 'bookings'). None si no aplica."
        ),
    )
    metric_impact_estimate: Optional[str] = Field(
        None,
        max_length=120,
        description=(
            "Estimación rough del impacto (ej. '+10-15% ingresos', 'recuperar 8 clientes inactivos'). "
            "Opcional y aproximado — el LLM NO debe prometer cifras exactas."
        ),
    )


class BusinessMemorySnapshot(BaseModel):
    """Snapshot de la 'Memoria de Negocio' que se le pasó al LLM.

    Se devuelve en la response para que la UI/debug vean EXACTAMENTE qué
    datos usó el Growth Coach para generar los insights (transparencia
    anti-alucinación).
    """
    tenant_id: str
    tenant_name: Optional[str] = None
    tenant_slug: Optional[str] = None
    lookback_days: int
    generated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )
    # Cada sección es un dict libre para no atar el schema al formato
    # exacto del LLM o de los servicios de analytics. La idea es
    # documentar QUÉ se miró, no imponer un shape rígido.
    sales: dict[str, Any] = Field(
        default_factory=dict,
        description="Métricas de ventas: total_revenue, order_count, avg_ticket, daily_revenue[], comparison_vs_prev.",
    )
    inventory: dict[str, Any] = Field(
        default_factory=dict,
        description="Estado de inventario: total_products, low_stock, out_of_stock, top_selling, dead_stock.",
    )
    customers: dict[str, Any] = Field(
        default_factory=dict,
        description="Segmentos: total_customers, segments{new,vip,inactive,top}, avg_orders_per_customer.",
    )
    promotions: dict[str, Any] = Field(
        default_factory=dict,
        description="Promociones: total, active, recent.",
    )
    bookings: dict[str, Any] = Field(
        default_factory=dict,
        description="Reservas: total, upcoming, cancellation_rate, top_services.",
    )
    data_completeness: dict[str, bool] = Field(
        default_factory=dict,
        description=(
            "Mapa sección→bool indicando si había datos suficientes. "
            "Sirve para que la UI muestre 'Sin datos de inventario' en lugar "
            "de inventar insights sobre secciones vacías."
        ),
    )


class GrowthAnalysisResponse(BaseModel):
    """Response de POST /api/v1/ai/growth/analyze."""
    id: UUID = Field(
        default_factory=lambda: __import__("uuid").uuid4(),
        description="ID único del análisis (no se persiste por ahora).",
    )
    focus: str
    lookback_days: int
    language: str
    summary: str = Field(
        ...,
        min_length=10,
        max_length=1000,
        description="Resumen ejecutivo de 1-3 oraciones sobre el estado del negocio.",
    )
    insights: list[GrowthInsight] = Field(
        default_factory=list,
        description="Lista de insights (ordenados por priority desc, max=req.max_insights).",
    )
    business_memory: BusinessMemorySnapshot = Field(
        ...,
        description="Snapshot de los datos analizados (transparencia anti-alucinación).",
    )
    generated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )
    fallback: bool = Field(
        False,
        description="True si se usó fallback determinístico (LLM no disponible).",
    )
    fallback_reason: Optional[str] = Field(
        None,
        max_length=200,
        description="Razón del fallback (ej. 'circuit_open', 'not_configured', 'invalid_json').",
    )
    model: Optional[str] = Field(
        None,
        description="Modelo LLM usado (None si fue fallback).",
    )
    tokens_in: Optional[int] = None
    tokens_out: Optional[int] = None
    latency_ms: int = 0
