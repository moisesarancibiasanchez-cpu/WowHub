"""
CP Runner — Ejecutor determinista de Casos de Prueba sin LLM
WowHub Multi-Agent System v1.1.0 — FASE 2

Arquitectura:
  1. El Orchestrator recibe una tarea de auditoria
  2. El CP Runner ejecuta cada CP contra Railway en paralelo (semaphore)
  3. Solo los CPs que FALLAN van al LLM para triage
  4. El Validator recibe el resultado del runner + el triage del LLM

Esto reduce las llamadas LLM de ~599 a ~10-50 (solo fallos).
"""

import os
import json
import asyncio
import logging
import hashlib
import time
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path
from dataclasses import dataclass, field, asdict
from enum import Enum

import httpx

logger = logging.getLogger(__name__)


class CPStatus(str, Enum):
    PASS    = "pass"
    FAIL    = "fail"
    ERROR   = "error"   # error de red o timeout
    SKIP    = "skip"
    PENDING = "pending"


@dataclass
class TestCaseResult:
    """Resultado de un caso de prueba individual."""
    cp_id:         str
    status:        CPStatus
    http_code:     Optional[int]  = None
    response_time: Optional[float] = None   # segundos
    error_msg:     Optional[str]   = None
    expected:      Optional[str]   = None
    actual:       Optional[str]   = None
    retry_count:   int            = 0


@dataclass
class AuditRunResult:
    """Resultado completo de una corrida de auditoria."""
    run_id:          str
    started_at:      float
    completed_at:    Optional[float] = None
    total_cps:       int            = 0
    passed:          int            = 0
    failed:          int            = 0
    errors:          int            = 0
    skipped:         int            = 0
    coverage_pct:    float          = 0.0
    results:        List[TestCaseResult] = field(default_factory=list)
    failed_cps:     List[str]       = field(default_factory=list)
    error_cps:      List[str]       = field(default_factory=list)
    llm_calls_saved: int            = 0    # CPs ejecutados sin LLM

    @property
    def duration(self) -> float:
        if self.completed_at:
            return self.completed_at - self.started_at
        return time.time() - self.started_at

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["duration"] = self.duration
        return d


class CPRunner:
    """
    Ejecutor de casos de prueba contra la API de Railway.

    Características:
    - Concurrencia limitada con semaphore (max 25 simultáneas)
    - Retry con backoff exponencial (max 2 reintentos por CP)
    - Caché de resultados por hash del CP (runs reanudables)
    - Solo los CPs fallidos se envían al LLM para triage
    """

    def __init__(
        self,
        railway_url:    Optional[str]  = None,
        api_key:        Optional[str]  = None,
        max_concurrent: int           = 25,
        max_retries:    int           = 2,
        timeout:        float         = 10.0,
        cache_dir:      Optional[str] = None,
        use_hu_mapping: bool         = True,
        auth_email:     Optional[str] = None,
        auth_password:  Optional[str] = None,
    ):
        self.railway_url = (railway_url
            or os.getenv("RAILWAY_URL", "https://wowhub-api-production.up.railway.app"))
        self.api_key = api_key or os.getenv("MM_API_KEY", "")
        self.max_concurrent = max_concurrent
        self.max_retries    = max_retries
        self.timeout        = timeout
        self.cache_dir      = Path(cache_dir or os.getenv("CACHE_DIR", "./cache"))
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._use_hu_mapping = use_hu_mapping
        # Credenciales para auto-login (opcional)
        self._auth_email    = auth_email    or os.getenv("TEST_USER_EMAIL",    "")
        self._auth_password = auth_password or os.getenv("TEST_USER_PASSWORD", "")

        self._client: Optional[httpx.AsyncClient] = None
        self._semaphore: Optional[asyncio.Semaphore] = None
        self._auth_token: Optional[str] = None

    # ------------------------------------------------------------------
    # Cliente HTTP (singleton async)
    # ------------------------------------------------------------------
    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            limits = httpx.Limits(
                max_connections    = self.max_concurrent + 10,
                max_keepalive_connections = self.max_concurrent,
            )
            self._client = httpx.AsyncClient(
                timeout  = httpx.Timeout(self.timeout, connect=5.0),
                limits   = limits,
                headers  = {"Content-Type": "application/json"},
            )
        return self._client

    def close(self):
        if self._client is not None and not self._client.is_closed:
            asyncio.run(self._client.aclose())

    # ------------------------------------------------------------------
    # Auto-login: obtiene un token JWT real para tests que requieren auth
    # ------------------------------------------------------------------
    async def login(self, email: Optional[str] = None, password: Optional[str] = None) -> Optional[str]:
        """
        Hace POST /api/v1/auth/login con las credenciales y guarda el token.
        Retorna el access_token o None si falla.
        """
        email = email or self._auth_email
        password = password or self._auth_password
        if not email or not password:
            logger.warning("login(): no hay credenciales (email/password)")
            return None
        try:
            client = self._get_client()
            resp = await client.post(
                f"{self.railway_url.rstrip('/')}/api/v1/auth/login",
                json={"email": email, "password": password},
                timeout=self.timeout,
            )
            if resp.status_code == 200:
                data = resp.json()
                token = data.get("access_token") or data.get("token")
                if token:
                    self._auth_token = token
                    logger.info(f"login OK (token guardado, {len(token)} chars)")
                    return token
                logger.warning(f"login OK pero sin access_token: {data}")
            else:
                logger.warning(f"login fallo: HTTP {resp.status_code} - {resp.text[:200]}")
        except Exception as exc:
            logger.error(f"login error: {exc}")
        return None

    # ------------------------------------------------------------------
    # Caché de runs
    # ------------------------------------------------------------------
    def _run_cache_path(self, run_id: str) -> Path:
        return self.cache_dir / f"run_{run_id}.json"

    def _cp_cache_path(self, cp_id: str) -> Path:
        h = hashlib.sha256(cp_id.encode()).hexdigest()[:12]
        return self.cache_dir / f"cp_{h}.json"

    def save_run(self, result: AuditRunResult) -> None:
        path = self._run_cache_path(result.run_id)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(result.to_dict(), f, indent=2, ensure_ascii=False)
        logger.info(f"Run guardado en {path}")

    def load_run(self, run_id: str) -> Optional[AuditRunResult]:
        path = self._run_cache_path(run_id)
        if not path.exists():
            return None
        with open(path, "r", encoding="utf-8") as f:
            d = json.load(f)
        # Reconstruir desde dict
        d["results"] = [TestCaseResult(**r) for r in d.get("results", [])]
        return AuditRunResult(**d)

    def save_cp_result(self, cp_result: TestCaseResult) -> None:
        path = self._cp_cache_path(cp_result.cp_id)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(asdict(cp_result), f, indent=2)

    # ------------------------------------------------------------------
    # Ejecucion de un CP individual
    # ------------------------------------------------------------------
    async def _execute_cp(
        self,
        cp: Dict[str, Any],
        client: httpx.AsyncClient,
        auth_token: Optional[str] = None,
    ) -> TestCaseResult:
        """
        Ejecuta un CP contra Railway con soporte de backoff ante 429.
        """
        """
        Ejecuta un CP contra Railway.

        El CP tiene la estructura:
        {
            "id": "CP-01-01-F",
            "method": "GET|POST|...",
            "path": "/api/...",
            "expected_status": 200,
            "expected_body_contains": "...",   # opcional
            "hu_id": "HU_15",                  # opcional, usado para el mapping
            "type":  "functional",              # opcional
            "requires_auth": True/False,        # opcional
        }
        """
        cp_id     = cp.get("id", "UNKNOWN")
        # Si tiene hu_id, usar el mapping HU→endpoint; si no, usar lo del CP
        hu_id = cp.get("hu_id")
        cp_type_char = cp_id.split("-")[-1] if "-" in cp_id else "F"

        if hu_id and self._use_hu_mapping:
            try:
                from runner.hu_endpoint_map import resolve_hu_endpoint
                resolved = resolve_hu_endpoint(hu_id, cp_type_char)
                method      = resolved["method"]
                path        = resolved["path"]
                exp_status  = resolved["expected_status"]
                # Si el CP requiere auth y tenemos token, lo agregamos
                requires_auth = resolved.get("requires_auth", False)
            except Exception as exc:
                logger.debug(f"[{cp_id}] mapping fallback: {exc}")
                method    = cp.get("method", "GET").upper()
                path      = cp.get("path", "/health")
                exp_status = cp.get("expected_status", 200)
                requires_auth = cp.get("requires_auth", False)
        else:
            method    = cp.get("method", "GET").upper()
            path      = cp.get("path", "/health")
            exp_status = cp.get("expected_status", 200)
            requires_auth = cp.get("requires_auth", False)

        exp_contains = cp.get("expected_body_contains")
        body      = cp.get("body")
        headers   = cp.get("headers", {})

        # Si no hay body y el método lo requiere, usar fixture
        if body is None and method.upper() in ("POST", "PUT", "PATCH"):
            try:
                from runner.fixtures import get_body
                ctx = {
                    "auth_email": self._auth_email,
                    "auth_password": self._auth_password,
                }
                body = get_body(method, path, ctx, cp_type=cp_type_char)
            except Exception as exc:
                logger.debug(f"[{cp_id}] fixtures fallback error: {exc}")
                body = {}

        # Construir URL completa
        url = f"{self.railway_url.rstrip('/')}/{path.lstrip('/')}"

        extra_headers = {}
        # Prioridad: 1) token de la sesión (login real), 2) MM_API_KEY, 3) sin auth
        if requires_auth and auth_token:
            extra_headers["Authorization"] = f"Bearer {auth_token}"
        elif self.api_key and self.api_key != "sk-your-api-key-here":
            extra_headers["Authorization"] = f"Bearer {self.api_key}"
        extra_headers.update(headers)

        for attempt in range(1, self.max_retries + 1):
            t0 = time.perf_counter()
            try:
                if method == "GET":
                    resp = await client.get(url, headers=extra_headers, timeout=self.timeout)
                elif method == "POST":
                    resp = await client.post(url, headers=extra_headers, json=body, timeout=self.timeout)
                elif method == "PUT":
                    resp = await client.put(url, headers=extra_headers, json=body, timeout=self.timeout)
                elif method == "DELETE":
                    resp = await client.delete(url, headers=extra_headers, timeout=self.timeout)
                else:
                    resp = await client.request(method, url, headers=extra_headers, json=body, timeout=self.timeout)

                elapsed = time.perf_counter() - t0
                status_ok = resp.status_code == exp_status
                body_ok = (
                    exp_contains is None
                    or exp_contains in resp.text
                )

                if status_ok and body_ok:
                    return TestCaseResult(
                        cp_id      = cp_id,
                        status     = CPStatus.PASS,
                        http_code  = resp.status_code,
                        response_time = round(elapsed, 3),
                    )
                # Si es 429 (rate limit) y tenemos reintentos, esperar
                if resp.status_code == 429 and attempt < self.max_retries:
                    retry_after = int(resp.headers.get("retry-after", "5"))
                    await asyncio.sleep(min(retry_after, 30))
                    continue
                # Si es 5xx, también reintentar
                if resp.status_code >= 500 and attempt < self.max_retries:
                    await asyncio.sleep(1.0 * attempt)
                    continue
                return TestCaseResult(
                    cp_id      = cp_id,
                    status     = CPStatus.FAIL,
                    http_code  = resp.status_code,
                    response_time = round(elapsed, 3),
                    expected   = f"status={exp_status}" + (f", body~'{exp_contains}'" if exp_contains else ""),
                    actual     = f"status={resp.status_code}, body~'{resp.text[:200]}'",
                )

            except httpx.TimeoutException:
                elapsed = time.perf_counter() - t0
                if attempt == self.max_retries:
                    return TestCaseResult(
                        cp_id      = cp_id,
                        status     = CPStatus.ERROR,
                        response_time = round(elapsed, 3),
                        error_msg  = f"Timeout ({self.timeout}s) tras {attempt} intentos",
                        retry_count = attempt - 1,
                    )
                await asyncio.sleep(0.5 * attempt)  # backoff simple

            except httpx.RequestError as exc:
                elapsed = time.perf_counter() - t0
                if attempt == self.max_retries:
                    return TestCaseResult(
                        cp_id      = cp_id,
                        status     = CPStatus.ERROR,
                        response_time = round(elapsed, 3),
                        error_msg  = f"RequestError: {exc}",
                        retry_count = attempt - 1,
                    )
                await asyncio.sleep(0.5 * attempt)

        # No debería llegar aquí
        return TestCaseResult(cp_id=cp_id, status=CPStatus.ERROR, error_msg="Max retries exceeded")

    # ------------------------------------------------------------------
    # Ejecucion de auditoria completa
    # ------------------------------------------------------------------
    async def run_audit(
        self,
        test_cases: List[Dict[str, Any]],
        run_id:     Optional[str]  = None,
        resume:     bool           = True,
        auth_token: Optional[str]  = None,
    ) -> AuditRunResult:
        """
        Ejecuta todos los CPs en paralelo (limitado por semaphore).

        Args:
            test_cases: lista de dicts con estructura de CP
            run_id: identificador de esta corrida (para caché)
            resume: si True, intenta reanudar un run anterior
        """
        if run_id is None:
            run_id = hashlib.sha256(
                f"{time.time()}".encode()
            ).hexdigest()[:12]

        # Intentar reanudar run anterior
        if resume:
            prev = self.load_run(run_id)
            if prev and prev.completed_at is None:
                logger.info(f"Reanudando run {run_id} con {len(prev.results)} CPs ya ejecutados")
                result = prev
            else:
                result = AuditRunResult(
                    run_id     = run_id,
                    started_at = time.time(),
                    total_cps  = len(test_cases),
                )
        else:
            result = AuditRunResult(
                run_id     = run_id,
                started_at = time.time(),
                total_cps  = len(test_cases),
            )

        # Crear mapa de CPs ya ejecutados (para resume)
        done_map: Dict[str, TestCaseResult] = {
            r.cp_id: r for r in result.results
        }

        client    = self._get_client()
        semaphore = asyncio.Semaphore(self.max_concurrent)

        # Auto-login si hay credenciales y no se proporcionó token
        if not auth_token and not self._auth_token and (self._auth_email and self._auth_password):
            logger.info("run_audit: intentando auto-login...")
            await self.login()

        # Si tenemos token de auth, usarlo para todos los CPs que lo requieran
        effective_token = auth_token or self._auth_token

        async def run_one(cp: Dict[str, Any]) -> TestCaseResult:
            async with semaphore:
                return await self._execute_cp(cp, client, auth_token=effective_token)

        # Ejecutar solo los CPs faltantes
        pending_cps = [cp for cp in test_cases if cp.get("id") not in done_map]

        logger.info(
            f"Iniciando auditoria: {len(pending_cps)} CPs nuevos "
            f"({len(done_map)} ya ejecutados en run {run_id}, "
            f"concurrencia={self.max_concurrent})"
        )

        tasks = [run_one(cp) for cp in pending_cps]
        new_results: List[TestCaseResult] = await asyncio.gather(*tasks)

        # Integrar resultados
        for r in new_results:
            done_map[r.cp_id] = r

        result.results = list(done_map.values())
        result.failed_cps  = [r.cp_id for r in new_results if r.status == CPStatus.FAIL]
        result.error_cps   = [r.cp_id for r in new_results if r.status == CPStatus.ERROR]
        result.passed      = sum(1 for r in result.results if r.status == CPStatus.PASS)
        result.failed      = len(result.failed_cps)
        result.errors      = len(result.error_cps)
        result.skipped     = sum(1 for r in result.results if r.status == CPStatus.SKIP)
        result.completed_at = time.time()
        result.coverage_pct = round(result.passed / result.total_cps * 100, 1)
        result.llm_calls_saved = result.total_cps - len(result.failed_cps) - len(result.error_cps)

        self.save_run(result)
        logger.info(
            f"Auditoria {run_id} completada: "
            f"{result.passed}/{result.total_cps} PASS "
            f"({result.coverage_pct}%), "
            f"{result.failed} FAIL, {result.errors} ERROR, "
            f"LLM calls saved: {result.llm_calls_saved}"
        )

        return result

    # ------------------------------------------------------------------
    # Triage de fallos — solo para los CPs que fallaron
    # ------------------------------------------------------------------
    async def triage_failures(
        self,
        failed_results: List[TestCaseResult],
        llm_client,   # MockLLM con acomplete()
        tier: str     = "premium",
    ) -> Dict[str, Any]:
        """
        Recibe los CPs fallidos y devuelve un resumen categorizado
        para el Validator. Esto es lo UNICO que va al LLM.
        """
        if not failed_results:
            return {"status": "no_failures", "groups": []}

        # Agrupar por tipo de error
        groups: Dict[str, List[str]] = {}
        for r in failed_results:
            key = self._classify_failure(r)
            groups.setdefault(key, []).append(r.cp_id)

        triage_prompt = f"""Analiza los siguientes errores de la auditoria WowHub V134.2.

ERRORES POR TIPO:
{json.dumps(groups, indent=2, ensure_ascii=False)}

DETALLES:
{json.dumps([asdict(r) for r in failed_results], indent=2, ensure_ascii=False)}

Para cada grupo, indica:
1. Causa probable
2. Urgencia (alta/media/baja)
3. Accion recomendada

RESPUESTA (JSON):
{{
    "groups": [
        {{
            "error_type": "...",
            "cp_ids": ["..."],
            "probable_cause": "...",
            "urgency": "high|medium|low",
            "recommended_action": "..."
        }}
    ],
    "total_failures": N,
    "audit_can_proceed": true/false
}}
"""
        raw = await llm_client.acomplete(triage_prompt, max_tokens=1000)
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {"status": "parse_error", "raw": raw, "groups": []}
