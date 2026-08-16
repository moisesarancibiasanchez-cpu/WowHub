"""AI Core — endpoints para usuarios.

- POST /api/v1/ai/chat            → chat principal (soporta SSE stream)
- GET  /api/v1/ai/agents          → lista sub-agentes
- GET  /api/v1/ai/conversations   → lista conversaciones del usuario
- POST /api/v1/ai/conversations   → crea conversación
- GET  /api/v1/ai/conversations/{id}/messages
- DELETE /api/v1/ai/conversations/{id}
- GET  /api/v1/ai/usage           → rate limit usage del usuario
- GET  /api/v1/ai/status          → estado del LLM (circuit, enabled, etc)
"""
from __future__ import annotations

import json
import logging
from typing import Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.deps import get_current_user
from app.models.ai import (
    AgentKind, AIConversation, AIMessage, ConversationStatus, MessageRole,
)
from app.models.tenant import TenantMembership
from app.models.user import User
from app.schemas.ai import (
    ChatRequest, ChatResponse, ConversationCreate, ConversationListOut,
    ConversationOut, MessageListOut, MessageOut,
)
from app.security import decode_token
from app.services.ai_agents import list_sub_agents
from app.services.ai_orchestrator import (
    AIOrchestrator, RateLimitExceeded, check_daily_limit,
)
from app.services.llm_client import get_circuit

logger = logging.getLogger("wowhub.ai.api")

router = APIRouter(prefix="/ai", tags=["ai"])


# ── Helpers ────────────────────────────────────────────
def _extract_token(request: Request) -> str:
    auth = request.headers.get("authorization") or request.headers.get("Authorization")
    if not auth or not auth.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Falta Authorization Bearer")
    return auth.split(" ", 1)[1].strip()


def _resolve_tenant_id(db: Session, user: User, x_tenant_id: Optional[str]) -> str:
    """Resuelve el tenant_id del usuario (header o primera membresía)."""
    if x_tenant_id:
        # Verificar membresía
        m = db.execute(
            select(TenantMembership).where(
                TenantMembership.user_id == str(user.id),
                TenantMembership.tenant_id == x_tenant_id,
                TenantMembership.is_active == True,  # noqa
            )
        ).scalar_one_or_none()
        if not m:
            raise HTTPException(status_code=403, detail="No tienes acceso a este tenant")
        return x_tenant_id
    # Tomar la primera membresía activa del usuario
    m = db.execute(
        select(TenantMembership)
        .where(TenantMembership.user_id == str(user.id), TenantMembership.is_active == True)  # noqa
        .order_by(TenantMembership.created_at.asc())
        .limit(1)
    ).scalar_one_or_none()
    if not m:
        raise HTTPException(status_code=400, detail="El usuario no pertenece a ningún tenant")
    return str(m.tenant_id)


# ── Endpoints ──────────────────────────────────────────
@router.get("/status")
def get_status(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Estado actual del AI Core: circuit, enabled, agent, rate."""
    used = check_daily_limit(db, str(user.id))  # solo cuenta, no lanza
    return {
        "llm_enabled": settings.llm_enabled,
        "model": settings.llm_model,
        "circuit_state": get_circuit().snapshot(),
        "fallback_enabled": settings.ai_fallback_enabled,
        "rate_limit": {
            "used_today": used,
            "limit": settings.ai_daily_message_limit,
        },
        "context_messages": settings.ai_context_messages,
    }


@router.get("/agents")
def get_agents() -> dict:
    return {"items": list_sub_agents()}


@router.post("/chat", response_model=None)
async def post_chat(
    payload: ChatRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Endpoint principal. Si `stream=true`, devuelve SSE. Si no, JSON."""
    x_tenant = request.headers.get("X-Tenant-Id") or request.headers.get("x-tenant-id")
    tenant_id = _resolve_tenant_id(db, user, x_tenant)
    token = _extract_token(request)

    orch = AIOrchestrator(
        db, user_id=str(user.id), tenant_id=tenant_id, access_token=token,
    )

    if not payload.stream:
        try:
            handoff_payload = None
            if payload.message.handoff:
                handoff_payload = payload.message.handoff.model_dump()
            result = await orch.chat(
                message=payload.message.content,
                conversation_id=payload.message.conversation_id,
                force_agent=payload.message.force_agent,
                handoff=handoff_payload,
            )
            return ChatResponse(
                conversation_id=UUID(result["conversation_id"]),
                message_id=UUID(result["message_id"]),
                agent=AgentKind(result["agent"]),
                content=result["content"],
                fallback=result["fallback"],
                tool_calls=[{"name": n, "args": {}, "result": None} for n in result.get("tool_calls") or []],
                latency_ms=result["latency_ms"],
                tokens_in=result.get("tokens_in"),
                tokens_out=result.get("tokens_out"),
            )
        except RateLimitExceeded as e:
            raise HTTPException(
                status_code=429,
                detail=f"Límite diario alcanzado ({e.used}/{e.limit} mensajes). Vuelve mañana.",
            )
        except HTTPException:
            raise  # las HTTPException ya tienen su formato, no envolver
        except Exception as e:
            # Cualquier error inesperado: devolvemos 200 con fallback de Marketing Studio
            # para que el chat NUNCA rompa la UX del usuario. Loggeamos el traceback
            # para diagnóstico del admin.
            logger.exception("[ai.chat] error no manejado: %s", e)
            # CRÍTICO: rollback para limpiar cualquier transacción pendiente del orchestrator
            # que haya dejado la sesión en mal estado. Sin esto, get_or_create_conversation
            # puede fallar por conflicto de transacción, y el segundo fallback devuelve
            # conversation_id="" → el frontend lo guarda → Pydantic rechaza en el
            # segundo mensaje con 422 (uuid_parsing: invalid length 0).
            try:
                db.rollback()
            except Exception:
                pass
            try:
                from app.services.ai_agents import get_agent
                sub = get_agent((payload.message.force_agent or "marketing").value)
                # Intentar crear/recuperar la conversación para persistir el fallback
                from app.services.ai_orchestrator import (
                    get_or_create_conversation, save_message,
                )
                from app.models.ai import (
                    AgentKind as _AK, MessageRole as _MR, ConversationStatus as _CS,
                )
                conv = get_or_create_conversation(
                    db,
                    user_id=str(user.id),
                    tenant_id=tenant_id,
                    # No usar el conversation_id del payload: pudo haber sido ""
                    # o apuntar a una conversación que no existe. Siempre crear
                    # una nueva para el fallback.
                    conversation_id=None,
                    title=payload.message.content[:80],
                )
                # Marcar error en el log
                from app.services.ai_orchestrator import save_log
                from app.models.ai import LogStatus as _LS
                save_log(
                    db,
                    conversation=conv,
                    user_id=str(user.id),
                    agent=_AK(payload.message.force_agent or "marketing"),
                    status=_LS.ERROR,
                    user_message=payload.message.content,
                    assistant_message=sub.fallback,
                    error=str(e)[:500],
                    error_code="unhandled_exception",
                    latency_ms=0,
                )
                # CRÍTICO: commit para que la conversación y el log persistan.
                # Sin esto, el frontend recibe un conversation_id que no existe
                # en la DB y los siguientes mensajes fallan.
                db.commit()
                db.refresh(conv)
                # Devolver fallback con flag error=true
                return JSONResponse(
                    status_code=200,
                    content={
                        "conversation_id": str(conv.id),
                        "message_id": str(uuid4()),
                        "agent": (payload.message.force_agent or "marketing").value,
                        "content": sub.fallback,
                        "fallback": True,
                        "error": True,
                        "error_message": "Tuvimos un problema técnico. Estamos en ello.",
                        "tool_calls": [],
                        "latency_ms": 0,
                        "tokens_in": None,
                        "tokens_out": None,
                    },
                )
            except Exception as fallback_err:
                # Si hasta el fallback falla, devolvemos 200 con un UUID generado
                # localmente (no persistido) para que el frontend al menos pueda
                # seguir enviando mensajes. NO devolvemos "" porque eso causa 422
                # en el siguiente mensaje (uuid_parsing: invalid length 0).
                logger.exception("[ai.chat] fallback de emergencia también falló: %s", fallback_err)
                try:
                    db.rollback()
                except Exception:
                    pass
                return JSONResponse(
                    status_code=200,
                    content={
                        "conversation_id": str(uuid4()),
                        "message_id": str(uuid4()),
                        "agent": "marketing",
                        "content": "Disculpa, tuve un problema técnico. Inténtalo de nuevo en unos segundos.",
                        "fallback": True,
                        "error": True,
                        "tool_calls": [],
                        "latency_ms": 0,
                    },
                )

    # ── SSE streaming ────────────────────────────────
    async def event_source():
        try:
            handoff_payload = None
            if payload.message.handoff:
                handoff_payload = payload.message.handoff.model_dump()
            result = await orch.chat(
                message=payload.message.content,
                conversation_id=payload.message.conversation_id,
                force_agent=payload.message.force_agent,
                handoff=handoff_payload,
            )
            # Single event "done" con todo el contenido.
            # (El LLM streaming real vendría en una fase 2.)
            data = {
                "type": "done",
                "conversation_id": result["conversation_id"],
                "message_id": result["message_id"],
                "agent": result["agent"],
                "content": result["content"],
                "fallback": result["fallback"],
                "tool_calls": result.get("tool_calls") or [],
                "latency_ms": result["latency_ms"],
                "handoff_executed": result.get("handoff_executed", False),
                "handoff_action": result.get("handoff_action"),
            }
            yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
        except RateLimitExceeded as e:
            err = {"type": "error", "error": f"rate_limited: {e.used}/{e.limit}"}
            yield f"data: {json.dumps(err)}\n\n"
        except Exception as e:
            logger.exception("chat stream error")
            err = {"type": "error", "error": str(e)[:300]}
            yield f"data: {json.dumps(err)}\n\n"

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/conversations", response_model=ConversationListOut)
def list_conversations(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> ConversationListOut:
    x_tenant = request.headers.get("X-Tenant-Id")
    tenant_id = _resolve_tenant_id(db, user, x_tenant)

    base = (
        select(AIConversation)
        .where(
            AIConversation.user_id == str(user.id),
            AIConversation.tenant_id == tenant_id,
        )
        .order_by(AIConversation.last_message_at.desc().nullslast())
    )
    total = db.execute(
        select(func.count()).select_from(base.subquery())
    ).scalar_one() or 0
    rows = db.execute(
        base.offset((page - 1) * page_size).limit(page_size)
    ).scalars().all()

    return ConversationListOut(
        items=[ConversationOut.model_validate(r) for r in rows],
        total=int(total),
        page=page,
        page_size=page_size,
    )


@router.post("/conversations", response_model=ConversationOut, status_code=201)
def create_conversation(
    payload: ConversationCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ConversationOut:
    x_tenant = request.headers.get("X-Tenant-Id")
    tenant_id = _resolve_tenant_id(db, user, x_tenant)
    from app.models.ai import AgentKind as _AK
    c = AIConversation(
        user_id=str(user.id),
        tenant_id=tenant_id,
        title=payload.title or "Nueva conversación",
        agent=payload.agent or _AK.MARKETING,
        status=ConversationStatus.ACTIVE,
        message_count=0,
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return ConversationOut.model_validate(c)


@router.get("/conversations/{conversation_id}/messages", response_model=MessageListOut)
def get_messages(
    conversation_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    limit: int = Query(100, ge=1, le=500),
) -> MessageListOut:
    x_tenant = request.headers.get("X-Tenant-Id")
    tenant_id = _resolve_tenant_id(db, user, x_tenant)
    conv = db.get(AIConversation, conversation_id)
    if not conv or str(conv.user_id) != str(user.id) or str(conv.tenant_id) != tenant_id:
        raise HTTPException(status_code=404, detail="Conversación no encontrada")

    rows = db.execute(
        select(AIMessage)
        .where(AIMessage.conversation_id == conv.id)
        .order_by(AIMessage.created_at.asc())
        .limit(limit)
    ).scalars().all()
    return MessageListOut(
        items=[MessageOut.model_validate(m) for m in rows],
        total=len(rows),
    )


@router.delete("/conversations/{conversation_id}", status_code=204)
def delete_conversation(
    conversation_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> JSONResponse:
    x_tenant = request.headers.get("X-Tenant-Id")
    tenant_id = _resolve_tenant_id(db, user, x_tenant)
    conv = db.get(AIConversation, conversation_id)
    if not conv or str(conv.user_id) != str(user.id) or str(conv.tenant_id) != tenant_id:
        raise HTTPException(status_code=404, detail="Conversación no encontrada")
    conv.status = ConversationStatus.ARCHIVED
    db.commit()
    return JSONResponse(status_code=204, content=None)


@router.get("/usage")
def get_usage(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    used = check_daily_limit(db, str(user.id))  # no lanza
    return {
        "used_today": used,
        "limit": settings.ai_daily_message_limit,
        "remaining": max(0, settings.ai_daily_message_limit - used),
    }
