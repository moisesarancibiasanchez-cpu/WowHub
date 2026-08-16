"""Schemas Pydantic del AI Core (WowHub).

Contratos públicos de la API de IA. Versión 0.3.0.
"""
from datetime import datetime
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
