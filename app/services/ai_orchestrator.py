"""Orquestador del AI Core.

Responsabilidades:
1. Verificar rate limit por usuario (AI_DAILY_MESSAGE_LIMIT).
2. Cargar/crear la conversación.
3. Cargar el historial reciente (memoria persistente) — `ai_context_messages`.
4. Clasificar la intención (router LLM o heurístico).
5. Llamar al sub-agente correspondiente con sus tools.
6. Manejar tool_calls (1 round de function calling).
7. Persistir mensajes, log, trazas y métricas.
8. Si el LLM está caído → usar fallback del sub-agente.

Este módulo NO contiene lógica de transporte HTTP — esa vive en `app/api/v1/ai.py`.
"""
from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Optional
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models.ai import (
    AgentKind, AIConversation, AIMessage, AILog, AIMetricDaily, AITrace,
    ConversationStatus, LogStatus, MessageRole,
)
from app.services.ai_agents import (
    ROUTER, SUB_AGENTS, get_agent, heuristic_route,
)
from app.services.ai_tools import (
    AIToolContext, get_tools_for_agent, TOOL_DISPATCH,
)
from app.services.llm_client import (
    LLMClient, LLMError, LLMFallback, LLMMessage, LLMResponse, get_circuit,
)

logger = logging.getLogger("wowhub.ai.orchestrator")


# ── Rate limit ─────────────────────────────────────────
class RateLimitExceeded(Exception):
    def __init__(self, used: int, limit: int):
        self.used = used
        self.limit = limit
        super().__init__(f"Rate limit: {used}/{limit} msgs/día")


def check_daily_limit(db: Session, user_id: str) -> int:
    """Devuelve el conteo de mensajes de hoy del usuario. Lanza si excede."""
    if settings.ai_daily_message_limit <= 0:
        return 0
    start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    stmt = (
        select(func.count(AIMessage.id))
        .where(
            AIMessage.user_id == user_id,
            AIMessage.created_at >= start,
            AIMessage.role == MessageRole.USER,
        )
    )
    used = db.execute(stmt).scalar_one() or 0
    if used >= settings.ai_daily_message_limit:
        raise RateLimitExceeded(int(used), settings.ai_daily_message_limit)
    return int(used)


# ── Memoria ────────────────────────────────────────────
def load_history(db: Session, conversation: AIConversation, limit: int) -> list[dict[str, str]]:
    """Devuelve los últimos `limit` mensajes en formato OpenAI [{role, content}, ...]."""
    stmt = (
        select(AIMessage)
        .where(AIMessage.conversation_id == conversation.id)
        .order_by(AIMessage.created_at.desc())
        .limit(limit)
    )
    rows = list(db.execute(stmt).scalars())
    rows.reverse()
    out: list[dict[str, str]] = []
    for m in rows:
        role = m.role.value if hasattr(m.role, "value") else str(m.role)
        out.append({"role": role, "content": m.content})
    return out


# ── Persistencia ───────────────────────────────────────
def get_or_create_conversation(
    db: Session,
    *,
    user_id: str,
    tenant_id: str,
    conversation_id: Optional[UUID] = None,
    title: Optional[str] = None,
) -> AIConversation:
    if conversation_id:
        c = db.get(AIConversation, conversation_id)
        if c and str(c.user_id) == user_id and str(c.tenant_id) == tenant_id:
            return c
    c = AIConversation(
        user_id=user_id,
        tenant_id=tenant_id,
        title=title or "Nueva conversación",
        agent=AgentKind.ROUTER,
        status=ConversationStatus.ACTIVE,
        message_count=0,
    )
    db.add(c)
    db.flush()
    return c


def save_message(
    db: Session,
    *,
    conversation: AIConversation,
    role: MessageRole,
    content: str,
    agent: Optional[AgentKind] = None,
    tool_name: Optional[str] = None,
    tool_call_id: Optional[str] = None,
    tool_args: Optional[dict] = None,
    tool_result: Optional[dict] = None,
    tokens_in: Optional[int] = None,
    tokens_out: Optional[int] = None,
    latency_ms: Optional[int] = None,
    fallback: bool = False,
) -> AIMessage:
    m = AIMessage(
        conversation_id=conversation.id,
        tenant_id=conversation.tenant_id,
        user_id=conversation.user_id,
        role=role,
        content=content,
        agent=agent,
        tool_name=tool_name,
        tool_call_id=tool_call_id,
        tool_args=tool_args,
        tool_result=tool_result,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        latency_ms=latency_ms,
        fallback=fallback,
    )
    db.add(m)
    conversation.message_count = (conversation.message_count or 0) + 1
    conversation.last_message_at = datetime.now(timezone.utc)
    db.flush()
    return m


def save_log(
    db: Session,
    *,
    conversation: AIConversation,
    user_id: str,
    agent: AgentKind,
    status: LogStatus,
    user_message: str,
    assistant_message: Optional[str],
    error: Optional[str] = None,
    error_code: Optional[str] = None,
    tokens_in: Optional[int] = None,
    tokens_out: Optional[int] = None,
    latency_ms: Optional[int] = None,
    tools_called: Optional[list[str]] = None,
    circuit_before: Optional[str] = None,
    circuit_after: Optional[str] = None,
) -> AILog:
    log = AILog(
        tenant_id=conversation.tenant_id,
        user_id=user_id,
        conversation_id=conversation.id,
        agent=agent,
        status=status,
        user_message=user_message,
        assistant_message=assistant_message,
        error=error,
        error_code=error_code,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        latency_ms=latency_ms,
        tools_called=tools_called,
        circuit_state_before=circuit_before,
        circuit_state_after=circuit_after,
    )
    db.add(log)
    db.flush()
    return log


def save_trace(
    db: Session,
    *,
    log: AILog,
    conversation: AIConversation,
    step: str,
    detail: Optional[dict] = None,
    duration_ms: Optional[int] = None,
) -> AITrace:
    t = AITrace(
        tenant_id=conversation.tenant_id,
        log_id=log.id,
        conversation_id=conversation.id,
        step=step,
        detail=detail,
        duration_ms=duration_ms,
    )
    db.add(t)
    db.flush()
    return t


def update_metric_daily(
    db: Session,
    *,
    tenant_id: str,
    agent: AgentKind,
    status: LogStatus,
    tokens_in: int = 0,
    tokens_out: int = 0,
    latency_ms: int = 0,
    user_id: Optional[str] = None,
) -> None:
    """Upsert de la métrica diaria para (day, tenant, agent).

    IMPORTANTE: `tenant_id` es ahora OBLIGATORIO (keyword-only) para evitar
    el bug histórico de meter el UUID cero que violaba la FK contra `tenants`.
    La fila se busca por (day, tenant_id, agent) para que cada tenant tenga
    su propio contador.
    """
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    stmt = select(AIMetricDaily).where(
        AIMetricDaily.day == today,
        AIMetricDaily.agent == agent,
        AIMetricDaily.tenant_id == tenant_id,
    )
    row = db.execute(stmt).scalar_one_or_none()
    if row is None:
        row = AIMetricDaily(
            tenant_id=tenant_id,
            day=today,
            agent=agent,
            requests=0, success=0, fallback=0, errors=0,
            timeouts=0, rate_limited=0,
            tokens_in=0, tokens_out=0,
            avg_latency_ms=0, p95_latency_ms=0, unique_users=0,
        )
        db.add(row)
        db.flush()
    row.requests += 1
    if status == LogStatus.SUCCESS:
        row.success += 1
    elif status == LogStatus.FALLBACK:
        row.fallback += 1
    elif status == LogStatus.TIMEOUT:
        row.timeouts += 1
        row.errors += 1
    elif status == LogStatus.RATE_LIMITED:
        row.rate_limited += 1
        row.errors += 1
    elif status == LogStatus.ERROR:
        row.errors += 1
    row.tokens_in += tokens_in
    row.tokens_out += tokens_out
    # Media móvil exponencial
    if row.requests > 0:
        row.avg_latency_ms = int(
            (row.avg_latency_ms * (row.requests - 1) + latency_ms) / row.requests
        )
    # Aproximación p95: max histórico como placeholder barato
    if latency_ms > row.p95_latency_ms:
        row.p95_latency_ms = latency_ms


# ── Router: clasificar intención ──────────────────────
async def _classify_intent(
    client: LLMClient,
    message: str,
) -> str:
    """Usa el LLM router para clasificar; si falla, usa heurística."""
    if not settings.llm_enabled:
        return heuristic_route(message)
    try:
        resp = await client.generate(
            [
                LLMMessage(role="system", content=ROUTER.system_prompt),
                LLMMessage(role="user", content=message[:600]),
            ],
            temperature=0.0,
            max_tokens=8,
        )
        candidate = (resp.content or "").strip().lower()
        for a in ("marketing", "growth", "automation", "marketplace"):
            if a in candidate:
                return a
        return heuristic_route(message)
    except LLMError:
        return heuristic_route(message)


# ── Loop principal del orquestador ─────────────────────
class AIOrchestrator:
    def __init__(self, db: Session, *, user_id: str, tenant_id: str, access_token: str):
        self.db = db
        self.user_id = user_id
        self.tenant_id = tenant_id
        self.access_token = access_token
        self.client = LLMClient()
        self.ctx = AIToolContext(
            user_id=user_id, tenant_id=tenant_id, access_token=access_token,
        )

    async def chat(
        self,
        *,
        message: str,
        conversation_id: Optional[UUID] = None,
        force_agent: Optional[AgentKind] = None,
        handoff: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Devuelve un dict con: conversation_id, message_id, agent, content,
        fallback, tool_calls, latency_ms, tokens_in, tokens_out,
        handoff_executed, handoff_action."""
        # 1) Rate limit
        check_daily_limit(self.db, self.user_id)

        # 2) Conversación
        conv = get_or_create_conversation(
            self.db,
            user_id=self.user_id,
            tenant_id=self.tenant_id,
            conversation_id=conversation_id,
            title=message[:80],
        )
        # 3) Guardar mensaje del usuario
        user_msg = save_message(
            self.db,
            conversation=conv,
            role=MessageRole.USER,
            content=message,
        )

        # 3.5) Handoff explícito HELP → AUTOMATION (u otro).
        # Si el cliente envía un handoff con confirmación del usuario,
        # forzamos el agente destino y dejamos una traza clara.
        handoff_executed = False
        handoff_action: Optional[str] = None
        if handoff:
            try:
                target = AgentKind(handoff.get("target_agent") or "automation")
                action = (handoff.get("action") or "").strip()
                params = handoff.get("params") or {}
                preview_text = handoff.get("preview_text") or ""
                if not action:
                    raise ValueError("handoff.action vacío")
                # Forzar el agente destino
                force_agent = target
                handoff_executed = True
                handoff_action = action
                # Inyectar contexto del handoff como un mensaje 'system-like'
                # adicional al usuario para que el LLM sepa qué ejecutar.
                # (Se añade DESPUÉS del system prompt y el historial.)
                self._trace(conv, None, "handoff_received",
                            {"from_client": True, "target_agent": target.value,
                             "action": action, "params": params,
                             "preview_text": preview_text[:500]})
                # Sobrescribir el mensaje del usuario con uno que ya lleva
                # la confirmación incorporada (así el LLM no tiene que pedirla).
                if preview_text:
                    user_msg.content = (
                        f"{message}\n\n"
                        f"[HANDOFF CONFIRMADO] El usuario aceptó la siguiente "
                        f"propuesta del agente anterior:\n---\n{preview_text}\n---\n"
                        f"Acción a ejecutar: {action}.\n"
                        f"Parámetros confirmados: {params}.\n"
                        f"Procede a ejecutarla ahora sin pedir confirmación adicional."
                    )
            except Exception as e:
                logger.exception("Handoff malformado, se ignora: %s", e)
                self._trace(conv, None, "handoff_invalid", {"error": str(e)[:200]})
                # No abortamos: el flujo normal continúa con router normal.

        circuit_before = get_circuit().snapshot()
        tools_called: list[str] = []
        started = time.perf_counter()
        tokens_in: Optional[int] = None
        tokens_out: Optional[int] = None
        agent: AgentKind = force_agent or AgentKind.ROUTER

        # 4) Routing
        try:
            if force_agent:
                agent = force_agent
            else:
                t0 = time.perf_counter()
                routed = await _classify_intent(self.client, message)
                agent = AgentKind(routed)
                self._trace(conv, None, "router_decision",
                            {"routed_to": agent.value, "took_ms": int((time.perf_counter() - t0) * 1000)})
        except Exception as e:
            logger.exception("Router falló, usando heurística: %s", e)
            agent = AgentKind(heuristic_route(message))

        sub = get_agent(agent.value)
        tools = get_tools_for_agent(agent.value)

        # 5) Historial
        history = load_history(self.db, conv, settings.ai_context_messages)

        messages: list[LLMMessage] = [LLMMessage(role="system", content=sub.system_prompt)]
        for h in history:
            messages.append(LLMMessage(role=h["role"], content=h["content"]))

        assistant_content = ""
        fallback_used = False
        status = LogStatus.SUCCESS
        error_msg: Optional[str] = None
        error_code: Optional[str] = None

        # 6) Llamada al LLM (con fallback)
        # max_tokens bajo (450) para forzar respuestas cortas y directas.
        # El system prompt ya instruye brevedad, pero esto es la red de
        # seguridad por si el LLM intenta extenderse.
        try:
            t0 = time.perf_counter()
            resp = await self.client.generate(
                messages,
                tools=tools,
                tool_choice="auto",
                temperature=0.6,
                max_tokens=450,
            )
            tokens_in = resp.tokens_in
            tokens_out = resp.tokens_out
            assistant_content = resp.content or ""
            latency_ms = int((time.perf_counter() - t0) * 1000)
            self._trace(conv, None, "llm_response",
                        {"agent": agent.value, "tokens_in": tokens_in,
                         "tokens_out": tokens_out, "latency_ms": latency_ms})

            # 7) Tool calls (round 1)
            tool_calls = (resp.raw or {}).get("choices", [{}])[0].get("message", {}).get("tool_calls") or []
            if tool_calls:
                # Acumulamos los resultados REALES de cada tool para
                # pasárselos al LLM en la segunda llamada. Antes
                # (summary_text) sólo repetíamos el nombre → el LLM no
                # tenía con qué rellenar los bullets.
                tool_results_for_llm: list[tuple[str, dict[str, Any], dict[str, Any]]] = []
                for tc in tool_calls:
                    fn = tc.get("function") or {}
                    name = fn.get("name") or ""
                    raw_args = fn.get("arguments") or "{}"
                    args = _safe_json(raw_args)
                    tools_called.append(name)
                    if name not in TOOL_DISPATCH:
                        result = {"error": f"Tool '{name}' no existe"}
                    else:
                        try:
                            result = await TOOL_DISPATCH[name](self.ctx, **args)
                        except Exception as e:
                            logger.exception("Tool %s falló", name)
                            result = {"error": f"Tool execution failed: {e}"}
                    self._trace(conv, None, "tool_call",
                                {"name": name, "args": args,
                                 "result_summary": _summary(result)})
                    tool_results_for_llm.append((name, args, result))

                # Segunda llamada al LLM con los resultados
                t1 = time.perf_counter()
                tool_msgs: list[LLMMessage] = list(messages)
                for tc in tool_calls:
                    fn = tc.get("function") or {}
                    tool_msgs.append(LLMMessage(
                        role="assistant",
                        content=fn.get("arguments") or "",
                        name=fn.get("name"),
                    ))
                    # (en OpenAI real, los tool messages referencian tool_call_id)
                # Ahora sí: pasamos los DATOS reales (name + args + result)
                summary_text = "\n".join(
                    _format_tool_result(name, args, result)
                    for name, args, result in tool_results_for_llm
                )
                tool_msgs.append(LLMMessage(
                    role="user",
                    content=(
                        "Estos son los resultados de las herramientas que llamaste. "
                        "Redacta la respuesta final para el usuario en español, "
                        "de forma clara y accionable. Si una tool falló, indícalo "
                        "con transparencia y sugiere el siguiente paso manual.\n\n"
                        f"Resultados:\n{summary_text}"
                    ),
                ))
                resp2 = await self.client.generate(
                    tool_msgs,
                    temperature=0.6,
                    max_tokens=450,
                )
                assistant_content = resp2.content or assistant_content
                tokens_in = (tokens_in or 0) + (resp2.tokens_in or 0)
                tokens_out = (tokens_out or 0) + (resp2.tokens_out or 0)
                latency_ms += int((time.perf_counter() - t1) * 1000)

        except LLMFallback as e:
            fallback_used = True
            status = LogStatus.FALLBACK
            assistant_content = sub.fallback
            error_msg = str(e)
            error_code = e.code
            logger.info("[ai] fallback activado (%s): %s", e.code, e)
        except LLMError as e:
            status = LogStatus.ERROR
            assistant_content = (
                "Disculpa, tuve un problema técnico al procesar tu mensaje. "
                "Inténtalo de nuevo en unos segundos."
            )
            error_msg = str(e)
            error_code = e.code
            logger.exception("[ai] LLM error: %s", e)
        except Exception as e:
            status = LogStatus.ERROR
            assistant_content = "Error inesperado. Inténtalo de nuevo."
            error_msg = str(e)
            error_code = "unexpected"
            logger.exception("[ai] error inesperado")

        latency_total = int((time.perf_counter() - started) * 1000)
        circuit_after = get_circuit().snapshot()

        # 7.5) Limpiar el contenido: nunca devolver bloques <think>
        # al usuario (DeepSeek, Qwen, etc. los emiten en content).
        if assistant_content:
            assistant_content = strip_think(assistant_content)

        # 8) Persistir respuesta del assistant
        asst_msg = save_message(
            self.db,
            conversation=conv,
            role=MessageRole.ASSISTANT,
            content=assistant_content,
            agent=agent,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            latency_ms=latency_total,
            fallback=fallback_used,
        )
        conv.agent = agent

        # 9) Log
        log = save_log(
            self.db,
            conversation=conv,
            user_id=self.user_id,
            agent=agent,
            status=status,
            user_message=message,
            assistant_message=assistant_content,
            error=error_msg,
            error_code=error_code,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            latency_ms=latency_total,
            tools_called=tools_called or None,
            circuit_before=circuit_before,
            circuit_after=circuit_after,
        )
        # Vincular trazas al log
        for t in self.db.execute(
            select(AITrace).where(
                AITrace.conversation_id == conv.id,
                AITrace.log_id.is_(None),
            )
        ).scalars():
            t.log_id = log.id

        # 10) Métrica diaria
        # Si llegara a fallar (ej. tenant inexistente), lo logueamos pero
        # NO abortamos la respuesta del chat. Importante: un fallo aquí
        # dejaría la sesión en estado "errored"; hacemos rollback sólo
        # del cambio de métrica y la dejamos lista para el commit final.
        try:
            update_metric_daily(
                self.db,
                tenant_id=self.tenant_id,
                agent=agent,
                status=status,
                tokens_in=tokens_in or 0,
                tokens_out=tokens_out or 0,
                latency_ms=latency_total,
                user_id=self.user_id,
            )
        except Exception as e:
            logger.warning("No se pudo actualizar métrica: %s", e)
            try:
                self.db.rollback()
                # Re-aplicar los cambios que sí funcionaron (msg + log + traces)
                # en una nueva transacción:
                self.db.add(conv)
                if asst_msg is not None:
                    self.db.add(asst_msg)
                self.db.add(log)
            except Exception as e2:
                logger.error("Rollback tras fallo de métrica también falló: %s", e2)

        self.db.commit()
        self.db.refresh(conv)
        self.db.refresh(asst_msg)

        return {
            "conversation_id": str(conv.id),
            "message_id": str(asst_msg.id),
            "agent": agent.value,
            "content": assistant_content,
            "fallback": fallback_used,
            "tool_calls": tools_called,
            "latency_ms": latency_total,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            # Flags de handoff HELP → AUTOMATION (u otro). El frontend
            # puede usarlos para mostrar un toast o tracking.
            "handoff_executed": handoff_executed,
            "handoff_action": handoff_action,
        }

    # ── Helpers internos ─────────────────────────────
    def _trace(
        self,
        conv: AIConversation,
        log: Optional[AILog],
        step: str,
        detail: Optional[dict] = None,
        duration_ms: Optional[int] = None,
    ) -> None:
        try:
            t = AITrace(
                tenant_id=conv.tenant_id,
                log_id=log.id if log else None,
                conversation_id=conv.id,
                step=step,
                detail=detail,
                duration_ms=duration_ms,
            )
            self.db.add(t)
        except Exception as e:
            logger.warning("No se pudo guardar trace: %s", e)


def _safe_json(s: str) -> dict[str, Any]:
    try:
        return json.loads(s) if s else {}
    except (ValueError, TypeError):
        return {"_raw": s}


def _summary(d: dict[str, Any]) -> dict[str, Any]:
    """Resumen seguro para no inflar la traza."""
    if not isinstance(d, dict):
        return {"_type": type(d).__name__}
    keys = list(d.keys())[:8]
    return {k: d[k] for k in keys}


# ── Limpieza de la respuesta ────────────────────────────
# Algunos modelos (DeepSeek, Qwen "thinking", etc.) emiten bloques
# `<think>...</think>` con su razonamiento interno. Eso NUNCA debe
# llegar al usuario. Lo quitamos en una sola pasada.
_THINK_RE = re.compile(r"<think>.*?</think>\s*", re.DOTALL | re.IGNORECASE)
# Algunos proveedores también sueltan "razonamiento" suelto entre
# <think> sin cerrar, o variantes como <reasoning>...</reasoning>.
_LEAKY_TAGS = ("reasoning", "reflection", "analysis")


def strip_think(text: str) -> str:
    """Quita los bloques de razonamiento interno del LLM.

    - Elimina cualquier `<think>...</think>` (case-insensitive, multilinea).
    - Si por algún motivo el bloque quedó sin cerrar, recorta todo lo
      que viene antes del primer bloque "bien formado" o lo descarta
      entero si parece 100% razonamiento.
    - Devuelve el texto limpio y stripped.
    """
    if not text:
        return text
    cleaned = _THINK_RE.sub("", text)
    # Fallback defensivo: si el modelo abrió <reasoning>...</reasoning>
    # o variantes, también las removemos.
    for tag in _LEAKY_TAGS:
        cleaned = re.sub(
            rf"<{tag}>.*?</{tag}>\s*",
            "",
            cleaned,
            flags=re.DOTALL | re.IGNORECASE,
        )
    return cleaned.strip()


def _format_tool_result(name: str, args: dict[str, Any], result: dict[str, Any]) -> str:
    """Formatea el resultado de una tool para enviarlo de vuelta al LLM.

    La idea: que el LLM reciba los DATOS reales que devolvió la tool,
    no solo el nombre. Si el dict es enorme, lo truncamos para no
    reventar el contexto.
    """
    try:
        payload = json.dumps(result, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        payload = str(result)
    if len(payload) > 1500:
        payload = payload[:1500] + "…(truncado)"
    args_str = json.dumps(args, ensure_ascii=False, default=str) if args else "{}"
    return f"- {name}({args_str}) → {payload}"
