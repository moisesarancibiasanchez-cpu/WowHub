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

        # v1.9.1-r5: inicializamos tool_calls y tool_results_for_llm
        # ANTES del try para que estén definidos en el bloque `except`
        # y en el post-procesado (líneas 547-549). Antes, si el LLM
        # caía con LLMFallback/LLMError, `tool_calls` quedaba sin
        # definir → UnboundLocalError al pasar por _scrub_slug_placeholders.
        tool_calls: list[dict[str, Any]] = []
        tool_results_for_llm: Optional[list[tuple[str, dict[str, Any], dict[str, Any]]]] = None

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

        # 7.6) Post-procesador anti-{slug}-literal: si la respuesta del
        # LLM contiene "/u/{slug}/..." (placeholder) o "/u/<slug>/..."
        # (path sin dominio), lo reemplazamos con URLs REALES del tenant.
        # El LLM tiende a alucinar estos patrones (los aprendió de su
        # training data) aunque el system prompt lo prohíba, así que esta
        # es la red de seguridad final antes de que el usuario lo vea.
        if assistant_content:
            assistant_content = await self._scrub_slug_placeholders(
                assistant_content, tool_results_for_llm if tool_calls else None,
            )

        # 7.7) Post-procesador anti-rutas-fantasma (v1.9.1-r3): si el LLM
        # emite URLs con paths que NO existen en app/main.py (ej.
        # /dashboard/settings, /dashboard/qr singular, /dashboard/campaigns)
        # o URLs con slugs placeholder hardcodeados (ej. tu-negocio, mi-empresa),
        # las corregimos automáticamente. Esta capa cierra los huecos que
        # `_scrub_slug_placeholders` no cubre.
        if assistant_content:
            assistant_content = self._scrub_fake_routes(assistant_content)

        # 7.8) v1.9.1-r5: red de seguridad anti-respuesta-basura.
        # Bug visto en producción: el LLM a veces devuelve respuestas
        # "pegadas" — solo puntos, espacios, o texto trivial — cuando
        # la pregunta del usuario cae fuera de su toolset (ej. tools
        # alucinados como 'check_availability' que devuelven error).
        # Eso deja al usuario viendo "........" en pantalla.
        # Si el contenido es demasiado corto Y no estamos ya en modo
        # fallback, lo reemplazamos con un mensaje útil del agente.
        if (
            assistant_content
            and len(assistant_content.strip()) < 10
            and not fallback_used
        ):
            logger.warning(
                "[ai] respuesta LLM sospechosa (len=%d, content=%r) — "
                "reemplazando con fallback del agente",
                len(assistant_content.strip()),
                assistant_content[:50],
            )
            assistant_content = sub.fallback
            fallback_used = True
            status = LogStatus.FALLBACK
            error_msg = "llm_returned_garbage"
            error_code = "llm_returned_garbage"

        # 7.9) v1.9.1-r7: red de seguridad ANTI-HALLUCINATION de tool names
        # para features QUE SÍ ESTÁN EN ROADMAP (no en producción).
        #
        # v1.9.1-r6 metía en BLACKLIST los tools de `check_availability`,
        # `create_booking`, `list_bookings` asumiendo que reservas estaba en
        # roadmap. FALSO — el owner confirmó el 2026-08-22 que el servicio
        # de reservas ESTÁ ACTIVO en producción. Esos tools se restauraron
        # en el toolset de los agentes (ver ai_tools.py) y se quitaron
        # del BLACKLIST acá.
        #
        # Esta capa NO depende del LLM: es server-side, regex-based, y
        # es la ÚLTIMA línea de defensa antes de mostrar la respuesta
        # al usuario. Cubre solo las features REALMENTE en roadmap:
        # loyalty/puntos, pedidos/delivery, whatsapp templates, POS.
        #
        # Disparamos el reemplazo si CUALQUIERA de estas condiciones:
        #   a) La respuesta contiene backticks de un tool name en BLACKLIST
        #      (features de roadmap que NO están en producción).
        #   b) El mensaje del usuario menciona keywords de roadmap
        #      (loyalty/puntos, pedidos/delivery, whatsapp template) Y la
        #      respuesta contiene backticks de un tool name, y ese tool NO
        #      existe en TOOL_DISPATCH (tool alucinado puro).
        if assistant_content and not fallback_used:
            from app.services.ai_tools import TOOL_DISPATCH as _TD
            _real_tool_names = set(_TD.keys())

            # (a) BLACKLIST dura — tools de features REALMENTE en roadmap.
            #     Cualquier mención de estos nombres en backticks = replace.
            #     v1.9.1-r7: check_availability/create_booking/list_bookings
            #     QUITAN del BLACKLIST porque reservas está DESPLEGADA.
            _BLACKLIST = {
                "add_loyalty_stamp",    # loyalty (roadmap)
                "redeem_reward",        # loyalty (roadmap)
                "issue_stamp",          # loyalty (roadmap)
                "create_order",         # pedidos/delivery (roadmap)
                "create_delivery",      # delivery (roadmap)
                "send_whatsapp_template",  # automation (roadmap, per app_knowledge)
                "create_pos_sale",      # POS avanzado (roadmap)
            }

            # Extraer backtick-names de la respuesta del LLM
            import re as _re
            _backtick_names = set(
                m.group(1).strip()
                for m in _re.finditer(r"`([^`]+)`", assistant_content)
            )

            _hallucinated_or_roadmap = _backtick_names & _BLACKLIST
            _msg_lower = (message or "").lower()
            # v1.9.1-r7: "reserva/reservar/booking/agendar" QUITADOS de
            # los keywords de roadmap — el feature de reservas está activo.
            _roadmap_keywords = (
                "loyalty", "puntos", "fideliz",
                "pedido", "delivery", "domicilio",
                "whatsapp template", "whatsapp_template",
            )
            _user_asking_roadmap = any(k in _msg_lower for k in _roadmap_keywords)
            # Detectar tools alucinados (mencionados en backticks pero que
            # NO existen en TOOL_DISPATCH). El LLM a veces inventa nombres
            # convincentes (ej. "schedule_post", "auto_respond") — esos
            # también son roadmap_hallucination.
            _hallucinated_tools = {
                n for n in _backtick_names
                if n not in _real_tool_names
                and not n.startswith(("http", "/", "www"))
                and "_" in n  # heurística: nombres de tools suelen tener _
            }

            if _hallucinated_or_roadmap or (
                _user_asking_roadmap
                and (_hallucinated_tools or _backtick_names & _BLACKLIST)
            ):
                logger.warning(
                    "[ai] respuesta LLM con tool names problemáticos "
                    "(blacklist=%s, hallucinated=%s, user_roadmap=%s, "
                    "backticks=%s) — reemplazando con respuesta canónica",
                    _hallucinated_or_roadmap or "[]",
                    _hallucinated_tools or "[]",
                    _user_asking_roadmap,
                    _backtick_names,
                )
                assistant_content = (
                    "Esa función aún no está disponible; está en nuestro "
                    "roadmap. Te aviso cuando esté lista."
                )
                # Mantenemos fallback_used=False (es una respuesta deliberada,
                # no un fallback) pero marcamos log para diagnóstico.
                error_msg = "roadmap_hallucination_blocked"
                error_code = "roadmap_hallucination_blocked"

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

    async def _scrub_slug_placeholders(
        self,
        text: str,
        tool_results: Optional[list[tuple[str, dict[str, Any], dict[str, Any]]]],
    ) -> str:
        """Reemplaza placeholders `{slug}` y paths sin dominio en la respuesta
        del LLM con URLs REALES del tenant.

        El LLM (DeepSeek, GPT-4, etc.) tiende a alucinar el patrón
        `/u/{slug}/reservar` aunque el system prompt se lo prohíba: es un
        patrón de URL tan común en su training data que se le escapa. Esta
        red de seguridad se ejecuta SIEMPRE antes de devolver la respuesta
        al usuario, para garantizar que:

        - Si la respuesta contiene `/u/{slug}/...` o `/u/<slug>/(reservar|book|catalogo)`
          SIN dominio, se reemplaza con la URL completa `https://<base>/u/<slug-real>/...`
          (usando los datos que ya tenemos de `get_tenant_public_urls` o
          llamando a la tool ahora si el LLM no la llamó).
        - Si el tenant no tiene slug, se reemplaza por un mensaje que pide
          configurarlo en Configuración → Branding.

        Args:
            text: respuesta del assistant (ya con `strip_think` aplicado).
            tool_results: lista de (tool_name, args, result) de las tools
                llamadas en este turno. None si el LLM no llamó ninguna.

        Returns:
            texto con los placeholders/paths reemplazados. Si no había
            placeholders, devuelve `text` sin tocar.
        """
        if not text:
            return text

        # Detección rápida: ¿hay algo que valga la pena reemplazar?
        if (
            not _SLUG_LITERAL_RE.search(text)
            and not _SLUG_PATH_RE.search(text)
            and not _SLUG_BARE_RE.search(text)
            and not _SLUG_PAREN_INSTRUCTION_RE.search(text)
        ):
            return text

        # 1) Sacar URLs reales del tool result (si ya se llamó)
        urls_by_key: dict[str, str] = {}
        has_slug = False
        tenant_slug: Optional[str] = None
        if tool_results:
            for name, _args, result in tool_results:
                if name == "get_tenant_public_urls" and isinstance(result, dict):
                    if result.get("has_slug"):
                        has_slug = True
                        tenant_slug = (result.get("tenant") or {}).get("slug")
                        for u in result.get("urls", []) or []:
                            if u.get("key") and u.get("url"):
                                urls_by_key[u["key"]] = u["url"]
                    break

        # 2) Si el LLM no llamó a la tool (o no devolvió URLs), la llamamos
        # nosotros en el post-proceso. Mejor tardar un poco más que entregar
        # un placeholder.
        if not has_slug:
            try:
                result = await TOOL_DISPATCH["get_tenant_public_urls"](self.ctx)
                if isinstance(result, dict) and result.get("has_slug"):
                    has_slug = True
                    tenant_slug = (result.get("tenant") or {}).get("slug")
                    for u in result.get("urls", []) or []:
                        if u.get("key") and u.get("url"):
                            urls_by_key[u["key"]] = u["url"]
                logger.info(
                    "[slug_scrubber] post-tool call: has_slug=%s tenant_slug=%s",
                    has_slug, tenant_slug,
                )
            except Exception as e:
                logger.warning("[slug_scrubber] no se pudo llamar a get_tenant_public_urls: %s", e)

        # 3) Resolver cada match contra la URL real (o fallback)
        if has_slug and urls_by_key:
            reservar_url = (
                urls_by_key.get("reservar")
                or urls_by_key.get("reservar_alias")
                or ""
            )
            catalogo_url = urls_by_key.get("catalogo") or ""
            landing_url = urls_by_key.get("landing") or ""

            def _resolve(m: "_re.Match[str]") -> str:
                s = m.group(0)
                low = s.lower()
                # Prioridad: reservar/book > catalogo > landing
                if "reservar" in low or "/book" in low:
                    return reservar_url or s
                if "catalogo" in low:
                    return catalogo_url or s
                if "/reservar" in low or "/book" in low:
                    return reservar_url or s
                return landing_url or s

            text = _SLUG_LITERAL_RE.sub(_resolve, text)
            text = _SLUG_PATH_RE.sub(_resolve, text)
        else:
            # 4) Tenant sin slug: reemplazar con mensaje accionable.
            # NO mostramos el placeholder (eso era el bug original).
            fallback_msg = (
                "(primero configura tu slug en Configuración → Branding; "
                "ahí te armo tu link público real)"
            )
            text = _SLUG_LITERAL_RE.sub(fallback_msg, text)
            text = _SLUG_PATH_RE.sub(fallback_msg, text)

        # 5) Paréntesis instructivos del tipo "(cambia `{slug}` por …)".
        # Si el LLM ya puso la URL real arriba, este paréntesis la contradice
        # (porque le pide al usuario "reemplazar {slug}"). Lo eliminamos
        # entero. Caso sin slug: dejar el paréntesis también ayuda (es la
        # única pista útil), pero ya quedó reemplazado arriba con
        # `fallback_msg`, así que aquí el match normalmente no aparecerá.
        text = _SLUG_PAREN_INSTRUCTION_RE.sub("", text)

        # 6) `{slug}` "desnudo" que sobreviva fuera de una URL o paréntesis
        # (por ejemplo, suelto como token: "tu {slug} es ..."). Lo
        # sustituimos por el slug real del tenant o, si no hay, por un
        # placeholder neutro que NO parezca código.
        if tenant_slug:
            text = _SLUG_BARE_RE.sub(tenant_slug, text)
        else:
            text = _SLUG_BARE_RE.sub("tu slug", text)

        return text

    def _scrub_fake_routes(self, text: str) -> str:
        """Anti-fake-URL v1.9.1-r3: corrige URLs con rutas o slugs falsos.

        Cubre los huecos que `_scrub_slug_placeholders` no cubre:
        1) URLs con host válido pero slug placeholder hardcodeado
           (ej. `wowhub.app/u/tu-negocio/reservar`).
        2) `/u/{TUSLUG}/...` con el placeholder en MAYÚSCULAS.
        3) URLs del panel con rutas que NO existen en `app/main.py`
           (ej. `/dashboard/settings` → auto-corrige a `/dashboard/site`;
           `/dashboard/qr` → auto-corrige a `/dashboard/qrs`).
        4) URLs del panel con rutas que NO tienen vista (solo API,
           ej. `/dashboard/campaigns`): las marca con un sufijo para que
           el usuario sepa que debe usar la tool correspondiente, no la URL.

        Esta función es SÍNCRONA (no llama a tools ni a la DB) y es
        baratura: corre 3 regexes y reemplaza. Se ejecuta DESPUÉS de
        `_scrub_slug_placeholders` como segunda red de seguridad.
        """
        if not text:
            return text

        # 1) /u/{TUSLUG}/... en MAYÚSCULAS → mensaje neutro
        text = _FAKE_PUBLIC_UPPERCASE_RE.sub(
            "[URL pública con tu slug real — pregúntame y te la paso]", text,
        )

        # 2) Host válido + slug placeholder hardcodeado (tu-, mi-, my-)
        #    → mensaje neutro (mejor que entregar una URL falsa)
        text = _FAKE_PUBLIC_HOST_RE.sub(
            "[URL pública con tu slug real — pregúntame y te la paso]", text,
        )

        # 3) Rutas del panel que NO existen en main.py
        def _panel_repl(m: re.Match) -> str:
            bad_path = m.group("bad")
            # Auto-corregir si tenemos replacement. Usamos prefix-match
            # (no exact match) porque el LLM puede emitir
            # `/dashboard/qr/abc` y queremos auto-corregirlo a
            # `/dashboard/qrs/abc` (preservando el subpath).
            matched_prefix: Optional[str] = None
            for fake_prefix in _FAKE_DASHBOARD_REPLACEMENTS:
                if bad_path == fake_prefix or bad_path.startswith(fake_prefix + "/"):
                    matched_prefix = fake_prefix
                    break
            if matched_prefix is not None:
                real = _FAKE_DASHBOARD_REPLACEMENTS[matched_prefix]
                # Reemplazar SOLO el prefijo, preservando el subpath
                # (ej. `/dashboard/qr/abc` → `/dashboard/qrs/abc`).
                tail = bad_path[len(matched_prefix):]
                return m.group(0).replace(bad_path, real + tail)
            # Si no hay replacement, marcar y dar pista.
            # v1.9.1-r4: el panel HTML está DEPRECADO como link público.
            # El mensaje apunta a la API autenticada o a las tools vigentes.
            hint_map = {
                "/dashboard/campaigns": (
                    " (v1.9.1-r4: no hay panel HTML público. El envío "
                    "masivo se hace vía la tool send_campaign o el endpoint "
                    "POST /api/v1/automation/execute con action=send_campaign)"
                ),
                "/dashboard/branches": (
                    " (v1.9.1-r4: no hay panel HTML público. Las sucursales "
                    "se consultan en get_tenant_info o vía API autenticada "
                    "GET /api/v1/tenants/{tid}/branches)"
                ),
                "/dashboard/automation": (
                    " (v1.9.1-r4: no hay panel HTML público. El Automation "
                    "Manager se invoca vía API: POST /api/v1/automation/preview "
                    "y /execute, no tiene pantalla dedicada)"
                ),
                "/dashboard/categories": (
                    " (v1.9.1-r4: no hay panel HTML público. Las categorías "
                    "se consultan vía API autenticada o se gestionan dentro "
                    "del recurso Productos)"
                ),
                "/dashboard/integrations": (
                    " (v1.9.1-r4: no hay panel HTML público. Las integraciones "
                    "(WhatsApp, Stripe, MercadoPago) están en roadmap y se "
                    "configuran por API o variables de entorno)"
                ),
                "/dashboard/products": (
                    " (v1.9.1-r4: no hay panel HTML público. La gestión de "
                    "productos se hace vía API autenticada "
                    "GET/POST/PATCH/DELETE /api/v1/tenants/{tid}/products)"
                ),
                "/dashboard/orders": (
                    " (v1.9.1-r4: no hay panel HTML público. Los pedidos se "
                    "gestionan vía API autenticada)"
                ),
                "/dashboard/customers": (
                    " (v1.9.1-r4: no hay panel HTML público. Los clientes se "
                    "gestionan vía API autenticada)"
                ),
                "/dashboard/stats": (
                    " (v1.9.1-r4: no hay panel HTML público. Las métricas se "
                    "consultan en GET /api/v1/tenants/{tid}/stats/overview)"
                ),
                "/dashboard/promotions": (
                    " (v1.9.1-r4: no hay panel HTML público. Las promos se "
                    "gestionan vía API autenticada o con la tool create_promotion)"
                ),
                "/dashboard/bookings": (
                    " (v1.9.1-r4: no hay panel HTML público. Las reservas no "
                    "están en el MVP actual; feature en roadmap)"
                ),
                "/dashboard/loyalty": (
                    " (v1.9.1-r4: no hay panel HTML público. La fidelización "
                    "no está desplegada en producción; está en roadmap)"
                ),
                "/dashboard/reservations": (
                    " (v1.9.1-r4: no hay panel HTML público. Las reservas no "
                    "están en el MVP actual; feature en roadmap)"
                ),
            }
            for prefix, hint in hint_map.items():
                if bad_path == prefix or bad_path.startswith(prefix + "/"):
                    return f"[ruta no disponible{hint}]"
            return m.group(0)

        text = _FAKE_DASHBOARD_PATH_RE.sub(_panel_repl, text)
        return text


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


# ── Anti-{slug}-literal: regexes para el post-procesador ────────────
# El LLM tiende a alucinar el patrón `/u/{slug}/reservar` aunque el system
# prompt se lo prohíba. Estos regexes detectan:
#
# v1.9.1-r4: el dominio CANÓNICO es `settings.public_base_url` (default
# `https://wowhub-api-production.up.railway.app`). El viejo `wowhub.app`
# ya NO responde (NXDOMAIN). El formato viejo `/u/{slug}/...` tampoco
# existe (404 en el OpenAPI de producción). La forma REAL es
# `{settings.public_base_url}/api/v1/public/t/{slug}/...`.
#
# 1) `_SLUG_LITERAL_RE` → el placeholder LITERAL `/u/{slug}/...` (con
#    las llaves `{` `}`). Este es el bug original: el LLM lo escribe
#    pidiéndole al usuario que "reemplace {slug} por el nombre del negocio".
#
# 2) `_SLUG_PATH_RE` → el path SIN dominio `/u/<slug-real>/(reservar|book
#    |catalogo)`. Esto pasa cuando el LLM sustituye el slug pero olvida
#    poner el `https://<settings.public_base_url>` delante. Lo reemplazamos
#    también por la URL completa.
#
# 3) `_SLUG_BARE_RE` → `{slug}` "desnudo", fuera de la URL. Esto pasa
#    cuando el LLM ya puso la URL REAL correctamente pero igual añade
#    un paréntesis instructivo tipo "(cambia `{slug}` por el nombre de
#    tu negocio)" o `{slug}` como variable suelta. Lo reemplazamos por
#    el slug real del tenant (o eliminamos la frase completa si está
#    en un paréntesis que ya no aplica).
#
# 4) `_SLUG_PAREN_INSTRUCTION_RE` → paréntesis completos que son una
#    instrucción de "reemplaza {slug} por...". Los eliminamos enteros
#    porque contradicen la URL real que acabamos de mostrar.
#
# La detección se hace ANTES de devolver al usuario (paso 7.6 del flujo
# de `AIOrchestrator.chat`). Ver `AIOrchestrator._scrub_slug_placeholders`.
_SLUG_LITERAL_RE = re.compile(
    r"/u/\{slug\}(?:/(?:reservar|book|catalogo))?",
    re.IGNORECASE,
)
_SLUG_PATH_RE = re.compile(
    r"(?<![\w/:])"                                # boundary: no es parte de otra URL
    r"/u/[A-Za-z0-9][A-Za-z0-9_-]{1,80}"          # /u/<slug>  (1-80 chars, empieza con alfanum)
    r"(?:/(?:reservar|book|catalogo))?"           # opcional: /reservar | /book | /catalogo
    r"(?![\w/-])",                                # boundary: no es parte de path más largo
    re.IGNORECASE,
)
_SLUG_BARE_RE = re.compile(
    r"\{slug\}",                                  # {slug} literal en cualquier contexto
    re.IGNORECASE,
)
# Paréntesis que contienen una instrucción de "reemplaza {slug}".
# Ejemplos que matchea: "(cambia `{slug}` por el nombre de tu negocio)",
# "(reemplaza {slug} con tu slug)", "(sustituye {slug})".
# NO matchea paréntesis legítimos como "(ya está activo)" o "(ejemplo)".
_SLUG_PAREN_INSTRUCTION_RE = re.compile(
    r"\s*\((?:[^()]*\bsubstituy\w*|cambi\w*|reemplaz\w*|sustituy\w*|reemplaz\w*|"
    r"sustituy\w*|remplaz\w*|cambia|cambiar|reemplaza|reemplazar|pon|poner|usa|usar)\b"
    r"[^()]*\{slug\}[^()]*\)",
    re.IGNORECASE,
)


# ── Anti-fake-URL (v1.9.1-r3): placeholders NO-canónicos + rutas fantasma ──
# El LLM puede alucinar variantes NO cubiertas por las regexes de arriba.
# Esta capa adicional detecta:
#
# 1) `_FAKE_PUBLIC_HOST_RE` → URL pública con un slug que NO es placeholder
#    (no tiene `{slug}` ni `<slug>`) pero igual es falso: empieza con
#    "tu-", "mi-", "my-" o es un slug plausible inventado. Cuando se detecta,
#    lo tratamos como un placeholder más: la tool pública lo reemplaza con
#    el slug real.
#
# 2) `_FAKE_PUBLIC_UPPERCASE_RE` → /u/{TUSLUG}/... con el placeholder
#    en mayúsculas. Es el mismo bug que `_SLUG_LITERAL_RE` pero en upper.
#
# 3) `_FAKE_DASHBOARD_PATH_RE` → rutas del panel que NO existen en main.py
#    (settings, qr singular, campaigns, branches, automation, categories,
#    integrations). Si el LLM las emite, se reemplazan por la ruta real
#    o por un mensaje "esa ruta no existe, usa la correcta".
_FAKE_PUBLIC_HOST_RE = re.compile(
    r"(?P<host>wowhub\.app|localhost|127\.0\.0\.1|wowhub-api-production\.up\.railway\.app)"
    r"/u/(?P<slug>tu-[a-záéíóúñ-]+|mi-[a-záéíóúñ-]+|"
    r"my-[a-z-]+|your-[a-z-]+|example|test-[a-z-]+|sample[_-][a-z-]+)",
    re.IGNORECASE,
)
_FAKE_PUBLIC_UPPERCASE_RE = re.compile(
    r"/u/\{[A-Z]+\}(?:/(?:reservar|book|catalogo|menu|pedido))?",
)
# Rutas del panel que NO existen en app/main.py (v1.9.1-r4 — sincronizado
# con app_knowledge.NO_EXISTE). El LLM las emite siguiendo la doc vieja.
#
# v1.9.1-r4: en producción el OpenAPI NO expone rutas HTML de dashboard
# (https://wowhub-api-production.up.railway.app/openapi.json). El "panel"
# autenticado está en app/main.py (código de desarrollo) pero NO se le
# entrega al cliente final. Por eso NINGUNA ruta /dashboard/* tiene
# auto-corrección hacia otra ruta /dashboard/* (todas son obsoletas como
# URLs públicas). El scrubber las reemplaza por mensajes que apuntan a
# la API autenticada o a las tools vigentes.
_FAKE_DASHBOARD_PATH_RE = re.compile(
    r"https?://[^\s)>\]]*"
    r"(?P<bad>/dashboard/(?:settings|qr|campaigns|branches|automation|categories|integrations|products|orders|customers|stats|promotions|bookings|loyalty|reservations)"
    r"(?:/[^\s)>\]]*)?)",
    re.IGNORECASE,
)
# Mapa de ruta falsa → texto correctivo. v1.9.1-r4: ya NO hay auto-fix
# a otra ruta /dashboard/* (porque el panel público está deprecado).
# Cada entry es un mensaje de "esa ruta no existe como link público; usa X".
_FAKE_DASHBOARD_REPLACEMENTS: dict[str, str] = {
    "/dashboard/settings": (
        "[v1.9.1-r4: no hay panel HTML público en producción. La "
        "configuración del tenant se hace vía API autenticada: "
        "PATCH /api/v1/tenants/{tid}]"
    ),
    "/dashboard/qr": (
        "[v1.9.1-r4: no hay panel HTML público en producción. Los QRs se "
        "gestionan vía API autenticada. El link público CORTO de un QR es "
        "/r/{short_code} (formato legacy reemplazado por get_tenant_public_urls)]"
    ),
}
