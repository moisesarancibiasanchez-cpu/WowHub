"""Modelos SQLAlchemy del AI Core (WowHub).

Tablas:
- ai_conversations: una sesión de chat por usuario + tenant.
- ai_messages:     mensajes individuales (user / assistant / tool).
- ai_logs:         log estructurado por request (estado, error, tokens).
- ai_traces:       trazas internas paso-a-paso (qué tools se llamaron).
- ai_metrics_daily: métricas agregadas por día y por sub-agente.
"""
import enum
from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import (
    Boolean, DateTime, Enum, ForeignKey, Integer, JSON, String, Text, func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import GUID, BaseModel, TenantMixin


# ── Enums ───────────────────────────────────────────────
class AgentKind(str, enum.Enum):
    """Sub-agente que responde la conversación."""
    MARKETING = "marketing"        # Marketing Studio
    GROWTH = "growth"              # Growth Coach
    AUTOMATION = "automation"      # Automation Manager
    MARKETPLACE = "marketplace"    # Smart Marketplace
    HELP = "help"                  # Guía de WowHub (plataforma)
    ROUTER = "router"              # Mensaje de enrutamiento inicial


class MessageRole(str, enum.Enum):
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"
    SYSTEM = "system"


class ConversationStatus(str, enum.Enum):
    ACTIVE = "active"
    CLOSED = "closed"
    ARCHIVED = "archived"


class LogStatus(str, enum.Enum):
    SUCCESS = "success"
    FALLBACK = "fallback"   # LLM caído → respuesta de fallback
    ERROR = "error"         # Error fatal
    TIMEOUT = "timeout"     # Timeout del LLM
    RATE_LIMITED = "rate_limited"  # 429 del proveedor


# ── ai_conversations ────────────────────────────────────
class AIConversation(BaseModel, TenantMixin):
    """Una sesión de chat de IA de un usuario dentro de un tenant."""
    __tablename__ = "ai_conversations"

    user_id: Mapped[str] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    title: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    agent: Mapped[AgentKind] = mapped_column(
        Enum(AgentKind, name="ai_agent_kind"),
        nullable=False, default=AgentKind.ROUTER,
    )
    status: Mapped[ConversationStatus] = mapped_column(
        Enum(ConversationStatus, name="ai_conversation_status"),
        nullable=False, default=ConversationStatus.ACTIVE,
        index=True,
    )
    # Mensajes en la conversación (denormalizado para orden)
    message_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_message_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "user_id": str(self.user_id),
            "tenant_id": str(self.tenant_id),
            "title": self.title,
            "agent": self.agent.value if self.agent else None,
            "status": self.status.value if self.status else None,
            "message_count": self.message_count,
            "last_message_at": self.last_message_at.isoformat() if self.last_message_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# ── ai_messages ─────────────────────────────────────────
class AIMessage(BaseModel, TenantMixin):
    """Mensaje dentro de una conversación."""
    __tablename__ = "ai_messages"

    conversation_id: Mapped[str] = mapped_column(
        GUID(), ForeignKey("ai_conversations.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    user_id: Mapped[str] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    role: Mapped[MessageRole] = mapped_column(
        Enum(MessageRole, name="ai_message_role"),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Tool call (assistant) o tool result (tool)
    tool_name: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    tool_call_id: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    tool_args: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    tool_result: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    # Metadata del LLM
    agent: Mapped[Optional[AgentKind]] = mapped_column(
        Enum(AgentKind, name="ai_message_agent"), nullable=True,
    )
    tokens_in: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    tokens_out: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    fallback: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "conversation_id": str(self.conversation_id),
            "role": self.role.value if self.role else None,
            "content": self.content,
            "agent": self.agent.value if self.agent else None,
            "tool_name": self.tool_name,
            "tool_call_id": self.tool_call_id,
            "tool_args": self.tool_args,
            "tool_result": self.tool_result,
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "latency_ms": self.latency_ms,
            "fallback": self.fallback,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# ── ai_logs ─────────────────────────────────────────────
class AILog(BaseModel, TenantMixin):
    """Log estructurado de cada request al AI Core."""
    __tablename__ = "ai_logs"

    user_id: Mapped[Optional[str]] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    conversation_id: Mapped[Optional[str]] = mapped_column(
        GUID(), ForeignKey("ai_conversations.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    agent: Mapped[AgentKind] = mapped_column(
        Enum(AgentKind, name="ai_log_agent"), nullable=False, index=True,
    )
    status: Mapped[LogStatus] = mapped_column(
        Enum(LogStatus, name="ai_log_status"), nullable=False, index=True,
    )
    # Request
    user_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Response
    assistant_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Detalles
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error_code: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    tokens_in: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    tokens_out: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    tools_called: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    circuit_state_before: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    circuit_state_after: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    extra: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)


# ── ai_traces ───────────────────────────────────────────
class AITrace(BaseModel, TenantMixin):
    """Trazas internas: cada paso (tool call, decisión del router, etc)."""
    __tablename__ = "ai_traces"

    log_id: Mapped[Optional[str]] = mapped_column(
        GUID(), ForeignKey("ai_logs.id", ondelete="CASCADE"),
        nullable=True, index=True,
    )
    conversation_id: Mapped[Optional[str]] = mapped_column(
        GUID(), ForeignKey("ai_conversations.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    step: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    # "router_decision" | "llm_request" | "llm_response" | "tool_call" | "tool_result" | "fallback"
    detail: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)


# ── ai_metrics_daily ────────────────────────────────────
class AIMetricDaily(BaseModel, TenantMixin):
    """Métricas agregadas por día, tenant y agente."""
    __tablename__ = "ai_metrics_daily"

    day: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True,
    )
    agent: Mapped[AgentKind] = mapped_column(
        Enum(AgentKind, name="ai_metric_agent"), nullable=False, index=True,
    )
    requests: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    success: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    fallback: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    errors: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    timeouts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rate_limited: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tokens_in: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    avg_latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    p95_latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unique_users: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
