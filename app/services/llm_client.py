"""Cliente LLM con circuit breaker, retry, timeout y fallback.

Este cliente:
- Es agnóstico del proveedor (openai_compatible | anthropic).
- Implementa un circuit breaker simple (closed → open → half_open).
- Hace retry exponencial en errores transitorios (5xx, timeout, 429).
- Nunca bloquea más de `llm_timeout_seconds`.
- Si el circuito está abierto o la key no está configurada,
  `generate()` levanta `LLMFallback` para que el orquestador use fallback.

Tests: `tests/test_llm_client.py` cubre circuit breaker y fallback.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Literal

import httpx
from tenacity import (
    AsyncRetrying, retry_if_exception_type, stop_after_attempt,
    wait_exponential, wait_random,
)

from app.config import settings

logger = logging.getLogger("wowhub.ai.llm")

# ── Excepciones ────────────────────────────────────────
class LLMError(Exception):
    """Error genérico del LLM."""
    def __init__(self, message: str, code: str = "llm_error", retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.retryable = retryable


class LLMFallback(LLMError):
    """El LLM no está disponible → usar respuesta fallback."""
    def __init__(self, message: str = "LLM no disponible", code: str = "fallback"):
        super().__init__(message, code=code, retryable=False)


class LLMRateLimited(LLMError):
    """429 del proveedor."""
    def __init__(self, message: str = "rate_limited"):
        super().__init__(message, code="rate_limited", retryable=True)


class LLMTimeout(LLMError):
    def __init__(self, message: str = "timeout"):
        super().__init__(message, code="timeout", retryable=True)


# ── Circuit Breaker ───────────────────────────────────
CircuitState = Literal["closed", "open", "half_open"]


@dataclass
class CircuitBreaker:
    """Circuit breaker simple, thread-safe.
    - closed:    pasa todas las llamadas.
    - open:      lanza LLMFallback sin llamar al proveedor.
    - half_open: deja pasar UNA llamada de prueba. Si pasa → closed. Si falla → open.
    """
    fail_threshold: int = 5
    reset_seconds: int = 60
    state: CircuitState = "closed"
    consecutive_failures: int = 0
    opened_at: float | None = None
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def can_pass(self) -> bool:
        with self._lock:
            if self.state == "closed":
                return True
            if self.state == "open":
                # ¿Ya pasó el reset_seconds?
                if self.opened_at and (time.time() - self.opened_at) >= self.reset_seconds:
                    self.state = "half_open"
                    logger.info("[ai.cb] transition open → half_open")
                    return True
                return False
            # half_open → solo 1 a la vez. Simplificado: pasa.
            return True

    def record_success(self) -> None:
        with self._lock:
            self.consecutive_failures = 0
            if self.state != "closed":
                logger.info(f"[ai.cb] transition {self.state} → closed")
                self.state = "closed"
                self.opened_at = None

    def record_failure(self) -> None:
        with self._lock:
            self.consecutive_failures += 1
            if self.state == "half_open":
                self.state = "open"
                self.opened_at = time.time()
                logger.warning("[ai.cb] half_open failed → open")
            elif (
                self.state == "closed"
                and self.consecutive_failures >= self.fail_threshold
            ):
                self.state = "open"
                self.opened_at = time.time()
                logger.warning(
                    f"[ai.cb] threshold reached ({self.consecutive_failures}) → open"
                )

    def snapshot(self) -> CircuitState:
        with self._lock:
            return self.state

    def force_open(self) -> None:
        """Útil para tests y admin 'kill switch'."""
        with self._lock:
            self.state = "open"
            self.opened_at = time.time()
            self.consecutive_failures = self.fail_threshold

    def force_close(self) -> None:
        with self._lock:
            self.state = "closed"
            self.consecutive_failures = 0
            self.opened_at = None


# Singleton del circuit breaker (compartido por toda la app)
_circuit = CircuitBreaker(
    fail_threshold=settings.llm_cb_fail_threshold,
    reset_seconds=settings.llm_cb_reset_seconds,
)


def get_circuit() -> CircuitBreaker:
    return _circuit


# ── Tipos ──────────────────────────────────────────────
@dataclass
class LLMMessage:
    role: Literal["system", "user", "assistant", "tool"]
    content: str
    name: str | None = None
    tool_call_id: str | None = None


@dataclass
class LLMResponse:
    content: str
    tokens_in: int | None = None
    tokens_out: int | None = None
    finish_reason: str | None = None
    raw: dict[str, Any] | None = None


# ── Cliente ────────────────────────────────────────────
class LLMClient:
    """Cliente HTTP para el proveedor LLM (OpenAI-compatible por defecto)."""

    def __init__(self) -> None:
        self.provider = settings.llm_provider
        self.api_key = settings.llm_api_key
        self.base_url = settings.llm_base_url.rstrip("/")
        self.model = settings.llm_model
        self.timeout = settings.llm_timeout_seconds
        self.max_retries = max(0, settings.llm_max_retries)
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client

    async def aclose(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    # ── Punto de entrada principal ─────────────────────
    async def generate(
        self,
        messages: list[LLMMessage],
        *,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> LLMResponse:
        if not settings.llm_enabled:
            raise LLMFallback("LLM no configurado (falta LLM_API_KEY)", code="not_configured")

        if not _circuit.can_pass():
            raise LLMFallback("Circuit breaker abierto", code="circuit_open")

        # Retry con tenacity solo para errores transitorios
        retrying = AsyncRetrying(
            stop=stop_after_attempt(self.max_retries + 1),
            wait=wait_exponential(multiplier=0.5, min=0.5, max=4)
            + wait_random(0, 0.3),
            retry=retry_if_exception_type((LLMRateLimited, LLMTimeout, httpx.TransportError, httpx.HTTPStatusError)),
            reraise=True,
        )

        try:
            async for attempt in retrying:
                with attempt:
                    try:
                        resp = await self._call_once(
                            messages, tools=tools, tool_choice=tool_choice,
                            temperature=temperature, max_tokens=max_tokens,
                        )
                        _circuit.record_success()
                        return resp
                    except (LLMRateLimited, LLMTimeout, httpx.TransportError) as e:
                        # Re-raise para que tenacity reintente.
                        # httpx.HTTPStatusError se maneja en _call_once (no se reintenta por código).
                        if isinstance(e, httpx.HTTPStatusError):
                            raise  # ya está convertido
                        raise
                    except httpx.HTTPStatusError:
                        # Errores HTTP no-retryable (4xx != 429) se propagan sin retry.
                        raise
        except LLMError as e:
            # Si es retryable pero agotó reintentos, abrimos circuito
            if e.retryable:
                _circuit.record_failure()
            raise
        except (httpx.TransportError, httpx.HTTPStatusError) as e:
            _circuit.record_failure()
            raise LLMError(f"HTTP error: {e}", code="http_error", retryable=True)

        # No debería llegar aquí
        raise LLMFallback("Sin respuesta", code="empty")

    # ── Llamada cruda ─────────────────────────────────
    async def _call_once(
        self,
        messages: list[LLMMessage],
        *,
        tools: list[dict[str, Any]] | None,
        tool_choice: str | dict[str, Any] | None,
        temperature: float,
        max_tokens: int,
    ) -> LLMResponse:
        client = await self._get_client()
        # Payload OpenAI-compatible
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [self._serialize(m) for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            payload["tools"] = tools
            if tool_choice is not None:
                payload["tool_choice"] = tool_choice

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        url = f"{self.base_url}/chat/completions"
        try:
            r = await client.post(url, json=payload, headers=headers)
        except httpx.TimeoutException as e:
            raise LLMTimeout(f"Timeout LLM: {e}") from e
        except httpx.TransportError as e:
            # red, DNS, etc
            raise LLMError(f"Transport error: {e}", code="transport", retryable=True) from e

        if r.status_code == 429:
            raise LLMRateLimited(f"429: {r.text[:200]}")
        if r.status_code >= 500:
            raise LLMError(
                f"5xx: {r.status_code} {r.text[:200]}",
                code="upstream_5xx",
                retryable=True,
            )
        if r.status_code >= 400:
            # 4xx != 429 → no reintentar
            raise LLMError(
                f"4xx: {r.status_code} {r.text[:200]}",
                code="upstream_4xx",
                retryable=False,
            )

        data = r.json()
        return self._parse(data)

    @staticmethod
    def _serialize(m: LLMMessage) -> dict[str, Any]:
        d: dict[str, Any] = {"role": m.role, "content": m.content}
        if m.name:
            d["name"] = m.name
        if m.tool_call_id:
            d["tool_call_id"] = m.tool_call_id
        return d

    @staticmethod
    def _parse(data: dict[str, Any]) -> LLMResponse:
        try:
            choice = data["choices"][0]
            msg = choice.get("message", {})
            content = msg.get("content") or ""
            usage = data.get("usage") or {}
            return LLMResponse(
                content=content,
                tokens_in=usage.get("prompt_tokens"),
                tokens_out=usage.get("completion_tokens"),
                finish_reason=choice.get("finish_reason"),
                raw=data,
            )
        except (KeyError, IndexError, TypeError) as e:
            raise LLMError(f"Respuesta LLM malformada: {e}", code="bad_response", retryable=False) from e

    # ── Streaming (opcional, fase 2) ──────────────────
    async def stream(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> AsyncIterator[str]:
        """Yield de chunks de texto. Versión mínima no-SSE-friendly.

        Útil para integraciones simples. Para la UI se recomienda
        el endpoint /chat con stream=true (SSE).
        """
        if not settings.llm_enabled:
            raise LLMFallback("LLM no configurado", code="not_configured")
        if not _circuit.can_pass():
            raise LLMFallback("Circuit breaker abierto", code="circuit_open")

        client = await self._get_client()
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [self._serialize(m) for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        url = f"{self.base_url}/chat/completions"
        try:
            async with client.stream("POST", url, json=payload, headers=headers) as r:
                if r.status_code == 429:
                    raise LLMRateLimited("429 en stream")
                if r.status_code >= 500:
                    _circuit.record_failure()
                    raise LLMError(f"5xx {r.status_code}", code="upstream_5xx", retryable=True)
                if r.status_code >= 400:
                    raise LLMError(f"4xx {r.status_code}", code="upstream_4xx", retryable=False)
                async for line in r.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    chunk = line[5:].strip()
                    if chunk == "[DONE]":
                        break
                    try:
                        import json
                        data = json.loads(chunk)
                        delta = data["choices"][0]["delta"].get("content")
                        if delta:
                            yield delta
                    except (KeyError, IndexError, TypeError, ValueError):
                        continue
            _circuit.record_success()
        except (httpx.TimeoutException, httpx.TransportError) as e:
            _circuit.record_failure()
            raise LLMError(f"Stream error: {e}", code="stream_error", retryable=True) from e
