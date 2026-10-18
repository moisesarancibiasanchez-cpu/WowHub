"""
Base Agent - Clase padre y CoordinatorLLM para el sistema multi-agente WowHub V134.2

Fases implementadas:
  FASE 1 — Fiabilidad: async real con httpx, retry con backoff, fail-loud,
            salida estructurada con esquema JSON, tiers diferenciados por modelo.
"""

import os
import json
import time
import logging
from typing import Optional, Dict, Any, List
from abc import ABC, abstractmethod
from enum import Enum

import httpx

logger = logging.getLogger(__name__)


class ModelTier(str, Enum):
    """Tiers de modelo diferenciados por proposito."""
    PREMIUM = "premium"   # planification e investigacion compleja
    CODE    = "code"      # generacion y revision de codigo
    FAST    = "fast"      # triage, validacion, resumen


# ---- Configuracion de tiers (pueden overridearse por env) ----
TIER_DEFAULTS: Dict[ModelTier, Dict[str, Any]] = {
    ModelTier.PREMIUM: {
        "model":       os.getenv("MM_MODEL_PREMIUM", "MiniMax-Text-01"),
        "temperature": 0.7,
        "max_tokens":  2000,
    },
    ModelTier.CODE: {
        "model":       os.getenv("MM_MODEL_CODE", "MiniMax-Text-01"),
        "temperature": 0.3,   # mas deterministico para codigo
        "max_tokens":  3000,
    },
    ModelTier.FAST: {
        "model":       os.getenv("MM_MODEL_FAST", "MiniMax-Text-01"),
        "temperature": 0.1,   # casi deterministico para validacion
        "max_tokens":  800,
    },
}


class StructuredOutputError(Exception):
    """Se lanza cuando el LLM no devuelve JSON valido tras los reintentos."""


class LLMAPIError(Exception):
    """Error de la API del LLM (status no-200, timeout, etc)."""


class MockLLM:
    """Mock LLM para desarrollo sin consumo de API real."""

    def __init__(self, model: str = "MiniMax-Text-01", tier: ModelTier = ModelTier.PREMIUM):
        self.model = model
        self.tier  = tier
        self.use_mock = os.getenv("MM_USE_MOCK", "true").lower() in ("1", "true", "yes")
        self._client: Optional[httpx.AsyncClient] = None

    # ------------------------------------------------------------------
    # API PUBLICA — sincrona para compatibilidad con BaseAgent.think()
    # ------------------------------------------------------------------
    def complete(self, prompt: str, max_tokens: int = 500) -> str:
        """Wrapper sincrono: delega a la version async."""
        try:
            return asyncio_run(_acomplete(self, prompt, max_tokens))
        except Exception as exc:
            if not self.use_mock:
                raise   # fail-loud en modo real
            return self._mock_response(prompt)

    # ------------------------------------------------------------------
    # API ASYNC — para uso directo con await
    # ------------------------------------------------------------------
    async def acomplete(self, prompt: str, max_tokens: int = 500) -> str:
        """Completado async con retry y fallo ruidoso."""
        if self.use_mock:
            return self._mock_response(prompt)

        for attempt in range(1, _max_retries() + 1):
            try:
                return await _do_api_call(
                    client      = self._get_client(),
                    model       = TIER_DEFAULTS[self.tier]["model"],
                    prompt      = prompt,
                    temperature = TIER_DEFAULTS[self.tier]["temperature"],
                    max_tokens  = max_tokens,
                    timeout     = _llm_timeout(),
                )
            except LLMAPIError as exc:
                logger.warning(f"Intento {attempt}/{_max_retries()} falló: {exc}")
                if attempt == _max_retries():
                    raise   # fail-loud: propagar en vez de ocultar con mock
                await _backoff(attempt)

        # No debería llegar aqui, pero por seguridad:
        return self._mock_response(prompt)

    # ------------------------------------------------------------------
    # CLIENTE HTTP (singleton async)
    # ------------------------------------------------------------------
    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            limits = httpx.Limits(max_connections=20, max_keepalive_connections=10)
            self._client = httpx.AsyncClient(
                timeout  = httpx.Timeout(_llm_timeout(), connect=10.0),
                limits   = limits,
                headers  = {"Content-Type": "application/json"},
            )
        return self._client

    # ------------------------------------------------------------------
    # MOCK RESPONSE — respuestas predecibles para tests
    # ------------------------------------------------------------------
    def _mock_response(self, prompt: str) -> str:
        prompt_lower = prompt.lower()

        if "research" in prompt_lower or "investig" in prompt_lower:
            return json.dumps({
                "status":    "success",
                "findings":  [
                    "CP-01-01-F: Verificacion de usuario existe — PASS",
                    "CP-02-03-S: Validacion de acceso no autorizado — PASS",
                ],
                "sources":   ["TEST_CASES_V134_2.md"],
                "confidence": 0.95,
            })
        elif "code" in prompt_lower or "implement" in prompt_lower:
            return json.dumps({
                "status":        "success",
                "files_created": ["src/feature.py"],
                "changes":       ["Agregada funcion de autenticacion"],
                "verified":      True,
            })
        elif "valid" in prompt_lower or "verify" in prompt_lower or "test" in prompt_lower:
            return json.dumps({
                "status":        "success",
                "tests_passed":  9,
                "tests_failed":  0,
                "coverage":      "100%",
            })
        elif "audit" in prompt_lower:
            return json.dumps({
                "status":          "success",
                "total_cps":       599,
                "cps_passed":      599,
                "cps_failed":      0,
                "coverage_pct":    100,
                "duration_seconds": 1.2,
            })
        else:
            return json.dumps({
                "status":  "success",
                "message": "Respuesta mock del agente",
                "agent":   "MockLLM",
                "tier":    self.tier.value,
            })

    def close(self):
        if self._client is not None and not self._client.is_closed:
            asyncio_run(self._client.aclose())


# =============================================================================
# Funciones helpers — hidupas fuera de clases para testabilidad
# =============================================================================

def _max_retries() -> int:
    return int(os.getenv("LLM_MAX_RETRIES", "2"))

def _llm_timeout() -> int:
    return int(os.getenv("LLM_TIMEOUT_SECONDS", "30"))

async def _backoff(attempt: int):
    """Backoff exponencial con jitter."""
    import random
    delay = min(2 ** attempt + random.uniform(0, 1), 30)
    await asyncio_sleep(delay)

async def _do_api_call(
    client: httpx.AsyncClient,
    model: str,
    prompt: str,
    temperature: float,
    max_tokens: int,
    timeout: int,
) -> str:
    """Ejecuta una llamada real a la API de MiniMax con manejo de errores."""
    api_key  = os.getenv("MM_API_KEY", "")
    base_url = os.getenv("MM_BASE_URL", "https://api.minimaxi.com/v1").rstrip("/")

    if not api_key or api_key == "sk-your-api-key-here":
        raise LLMAPIError("MM_API_KEY no configurada o es placeholder")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type":  "application/json",
    }
    payload = {
        "model":       model,
        "messages":    [{"role": "user", "content": prompt}],
        "max_tokens":  max_tokens,
        "temperature": temperature,
    }

    try:
        response = await client.post(
            f"{base_url}/chat/completions",
            headers  = headers,
            json     = payload,
            timeout  = httpx.Timeout(timeout, connect=10.0),
        )
    except httpx.TimeoutException:
        raise LLMAPIError(f"Timeout ({timeout}s) en peticion a {base_url}")
    except httpx.RequestError as exc:
        raise LLMAPIError(f"Error de conexion: {exc}")

    if response.status_code == 401 or response.status_code == 403:
        raise LLMAPIError(f"Auth fallida (HTTP {response.status_code}) — API key invalida o expirada")
    if response.status_code >= 500:
        raise LLMAPIError(f"Error del servidor (HTTP {response.status_code})")

    try:
        result = response.json()
    except Exception:
        raise LLMAPIError(f"Respuesta no es JSON valido: {response.text[:200]}")

    try:
        return result["choices"][0]["message"]["content"]
    except (KeyError, IndexError):
        raise LLMAPIError(f"Estructura de respuesta inesperada: {result}")


async def _repair_json(raw: str, max_attempts: int = 2) -> dict:
    """
    Intenta reparar JSON mal formado devuelve el dict parseado.
    Si no se puede reparar tras max_attempts, lanza StructuredOutputError.
    """
    for attempt in range(max_attempts):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            # Intentar extraer el bloque JSON de una respuesta mixta
            cleaned = raw.strip()
            # Quitar texto antes de { o despues de }
            first_brace  = cleaned.find("{")
            last_brace   = cleaned.rfind("}")
            if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
                cleaned = cleaned[first_brace : last_brace + 1]
            try:
                return json.loads(cleaned)
            except json.JSONDecodeError:
                if attempt == max_attempts - 1:
                    break
                await asyncio_sleep(0.3)

    raise StructuredOutputError(
        f"No se pudo parsear JSON tras {max_attempts} intentos. "
        f"Contenido: {raw[:300]}"
    )


# ---- polyfills para asyncio desde contexto sync ----
import asyncio as _asyncio

def asyncio_run(coro):
    try:
        loop = _asyncio.get_running_loop()
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(_asyncio.run, coro)
            return future.result()
    except RuntimeError:
        return _asyncio.run(coro)

async def asyncio_sleep(delay):
    await _asyncio.sleep(delay)


# =============================================================================
# CoordinatorLLM — gestor singleton de instancias LLM por tier
# =============================================================================

class CoordinatorLLM:
    """CoordinatorLLM — Gestiona las llamadas al LLM para todos los agentes."""

    _instance: Optional["CoordinatorLLM"] = None

    def __init__(self):
        self.use_mock = os.getenv("MM_USE_MOCK", "true").lower() in ("1", "true", "yes")
        self.max_iterations = int(os.getenv("MAX_ITERATIONS", "5"))

        # Una instancia MockLLM por tier (singleton interno)
        self._llm_instances: Dict[ModelTier, MockLLM] = {}
        for tier in ModelTier:
            self._llm_instances[tier] = MockLLM(
                model = TIER_DEFAULTS[tier]["model"],
                tier  = tier,
            )

        logger.info(
            f"CoordinatorLLM inicializado (mock={self.use_mock}, "
            f"max_iterations={self.max_iterations})"
        )

    @classmethod
    def get_instance(cls) -> "CoordinatorLLM":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def get_llm(self, tier: ModelTier = ModelTier.PREMIUM) -> MockLLM:
        return self._llm_instances[tier]

    # ---- Llamada directa que intenta parseo estructurado ----
    def complete(
        self,
        prompt:      str,
        tier:        ModelTier = ModelTier.PREMIUM,
        max_tokens:  int       = None,
        require_json: bool    = False,
    ) -> str:
        """Ejecuta completado sincrono. Si require_json=True, parsea y reintenta."""
        llm = self.get_llm(tier)
        effective_max = max_tokens or TIER_DEFAULTS[tier]["max_tokens"]

        if not require_json:
            return llm.complete(prompt, effective_max)

        # Con require_json: reintentar parseo antes de devolver
        raw = llm.complete(prompt, effective_max)
        try:
            parsed = asyncio_run(_repair_json(raw))
            return json.dumps(parsed, ensure_ascii=False)
        except StructuredOutputError:
            # Un reintento con pista de reparacion
            fix_prompt = (
                raw
                + "\n\nNOTA: la respuesta anterior no es JSON valido. "
                + "Devuelve SOLO un objeto JSON sin texto adicional."
            )
            raw2 = llm.complete(fix_prompt, effective_max)
            parsed = asyncio_run(_repair_json(raw2, max_attempts=2))
            return json.dumps(parsed, ensure_ascii=False)

    # ---- Llamada asincrona directa ----
    async def acomplete(
        self,
        prompt:     str,
        tier:       ModelTier = ModelTier.PREMIUM,
        max_tokens: int       = None,
    ) -> str:
        llm      = self.get_llm(tier)
        effective = max_tokens or TIER_DEFAULTS[tier]["max_tokens"]
        return await llm.acomplete(prompt, effective)

    def close(self):
        for llm in self._llm_instances.values():
            llm.close()


# =============================================================================
# BaseAgent — clase abstracta padre para todos los agentes
# =============================================================================

class BaseAgent(ABC):
    """BaseAgent — Clase abstracta padre para todos los agentes especializados."""

    def __init__(self, name: str, tier: ModelTier = ModelTier.PREMIUM):
        self.name   = name
        self.tier   = tier
        self.coordinator = CoordinatorLLM.get_instance()
        self._state: Dict[str, Any] = {}
        self._history: List[Dict[str, Any]] = []
        logger.info(f"Agent '{name}' inicializado (tier={tier.value})")

    @abstractmethod
    async def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Ejecuta la tarea asignada al agente."""
        pass

    def think(self, prompt: str, max_tokens: int = None, require_json: bool = False) -> str:
        """
        Invoca el LLM con el prompt dado.
        - require_json=True -> intenta parseo estructurado, repara si es invalido.
        """
        return self.coordinator.complete(
            prompt      = prompt,
            tier        = self.tier,
            max_tokens  = max_tokens,
            require_json = require_json,
        )

    async def athink(
        self, prompt: str, max_tokens: int = None, require_json: bool = False
    ) -> Dict[str, Any]:
        """
        Versión async de think() que devuelve dict parseado.
        Si require_json=True, el resultado ya es un dict; si no, es str.
        """
        llm      = self.coordinator.get_llm(self.tier)
        effective = max_tokens or TIER_DEFAULTS[self.tier]["max_tokens"]
        raw      = await llm.acomplete(prompt, effective)

        if not require_json:
            return raw  # str

        try:
            return await _repair_json(raw)
        except StructuredOutputError as exc:
            logger.error(f"{self.name}: JSON invalido no reparable: {exc}")
            return {"status": "error", "raw": raw, "error": str(exc)}

    def update_state(self, key: str, value: Any) -> None:
        self._state[key]  = value
        self._history.append({
            "timestamp": time.time(),
            "agent":     self.name,
            "key":       key,
            "value":     str(value)[:200],
        })

    def get_state(self, key: str) -> Any:
        return self._state.get(key)

    def get_history(self) -> List[Dict[str, Any]]:
        return self._history.copy()

    def reset(self) -> None:
        self._state.clear()
        self._history.clear()
        logger.info(f"Agent '{self.name}' reseteado")
