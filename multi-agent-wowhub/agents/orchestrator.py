"""
Orchestrator - Agente principal que coordina Researcher, Coder y Validator
Sistema Multi-Agent WowHub V134.2

Fases implementadas:
  FASE 1 — Fiabilidad: async real con await en lugar de encadenamiento serial
  FASE 0-E — Bugfix: _classify_request evalua 'audit' ANTES de 'research'
              (antes "auditoria" matcheaba 'research' por la palabra "caso de prueba")
"""

import os
import json
import logging
import asyncio
from typing import Dict, Any, Optional
from pathlib import Path

from agents.base_agent import BaseAgent, ModelTier, TIER_DEFAULTS
from state import OrchestratorState

logger = logging.getLogger(__name__)


class Orchestrator(BaseAgent):
    """Orchestrator — Coordina el flujo de trabajo entre los 3 sub-agentes."""

    def __init__(self, session_id: str = "default"):
        super().__init__(name="orchestrator", tier=ModelTier.PREMIUM)

        self.session_id     = session_id
        self.max_iterations = int(os.getenv("MAX_ITERATIONS", "5"))

        self.state = OrchestratorState(session_id=session_id)

        self._researcher: Optional["Researcher"] = None
        self._coder:     Optional["Coder"]       = None
        self._validator: Optional["Validator"]   = None

        logger.info(
            f"Orchestrator '{session_id}' listo "
            f"(max_iterations={self.max_iterations})"
        )

    # ------------------------------------------------------------------
    # Lazy loading de sub-agentes
    # ------------------------------------------------------------------
    @property
    def researcher(self) -> "Researcher":
        if self._researcher is None:
            from agents.researcher import Researcher
            self._researcher = Researcher()
            self.state.update_agent_status("researcher", "initialized", {"name": "researcher"})
        return self._researcher

    @property
    def coder(self) -> "Coder":
        if self._coder is None:
            from agents.coder import Coder
            self._coder = Coder()
            self.state.update_agent_status("coder", "initialized", {"name": "coder"})
        return self._coder

    @property
    def validator(self) -> "Validator":
        if self._validator is None:
            from agents.validator import Validator
            self._validator = Validator()
            self.state.update_agent_status("validator", "initialized", {"name": "validator"})
        return self._validator

    # ------------------------------------------------------------------
    # Ejecucion principal
    # ------------------------------------------------------------------
    async def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Ejecuta una tarea recibida del usuario.
        Usa async/await real para paralelizar cuando es posible.
        """
        request   = task.get("request", "")
        task_type = self._classify_request(request)

        logger.info(f"Orquestando tarea tipo='{task_type}': {request[:100]}...")

        # Seleccionar el handler async
        handler_map = {
            "audit":   self._handle_audit,
            "research": self._handle_research,
            "code":    self._handle_code,
            "validate": self._handle_validate,
        }
        handler = handler_map.get(task_type, self._handle_general)

        result = await handler(request)

        self.state.increment_iteration()
        self.state.set("last_task",   request)
        self.state.set("last_result", result)

        return {
            "status":    "ok",
            "task_type": task_type,
            "iterations": self.state.iterations,
            "result":    result,
        }

    async def execute_user_request(self, request: str) -> Dict[str, Any]:
        return await self.execute({"request": request})

    # ------------------------------------------------------------------
    # Clasificador de requests — AUDIT primero (bugfix)
    # ------------------------------------------------------------------
    def _classify_request(self, request: str) -> str:
        """
        Clasifica el tipo de request para determinar el flujo.
        ORDEN IMPORTANTE: audit > research > code > validate > general
        """
        r = request.lower()

        # AUDIT va primero: "auditoria", "audit", "v134", "directiva"
        if any(w in r for w in ["audit", "auditoria", "v134", "directiva", "599", "casos de prueba"]):
            return "audit"

        # RESEARCH: investigacion, busqueda, analisis
        if any(w in r for w in ["investig", "buscar", "research", "analiz", "cp-", "epica", "historia de usuario"]):
            return "research"

        # CODE: generacion, implementacion
        if any(w in r for w in ["codig", "implement", "code", "crear", "funcion", "clase", "feature"]):
            return "code"

        # VALIDATE: validacion, testing, verificacion
        if any(w in r for w in ["valid", "verific", "test", "prueba"]):
            return "validate"

        return "general"

    # ------------------------------------------------------------------
    # Handlers async — cada uno puede lanzar excepciones (fail-loud)
    # ------------------------------------------------------------------
    async def _handle_research(self, request: str) -> Dict[str, Any]:
        result = await self.researcher.execute({"task": request})
        return {"agent": "researcher", "output": result}

    async def _handle_code(self, request: str) -> Dict[str, Any]:
        """
        Flujo code: primero researcher para contexto, luego coder.
        Ambos se ejecutan en serie porque el contexto del researcher
        alimenta al coder.
        """
        research_result = await self.researcher.execute({"task": f"Contexto para: {request}"})
        code_result    = await self.coder.execute(
            {"task": request, "context": research_result}
        )
        return {
            "agent":  "coder",
            "research": research_result,
            "output":  code_result,
        }

    async def _handle_validate(self, request: str) -> Dict[str, Any]:
        result = await self.validator.execute({"task": request})
        return {"agent": "validator", "output": result}

    async def _handle_audit(self, request: str) -> Dict[str, Any]:
        """
        Flujo audit: los 3 agentes en paralelo (la investigacion y preparacion
        son independientes del validator que recibe el output del coder).
        """
        # Ejecutar researcher y coder en paralelo
        research_task = self.researcher.execute({
            "task":    "Investigar casos de prueba V134.2 (formato CP-XX-NN-TIPO)",
            "context": "599 CPs, 49 HUs, 8 epicas",
        })
        code_task = self.coder.execute({
            "task:":   "Preparar scripts de auditoria V134.2",
            "context": {},
        })

        research_result, code_result = await asyncio.gather(research_task, code_task)

        # Validator recibe el resultado combinado
        validation_result = await self.validator.execute({
            "task":    "Validar scripts de auditoria V134.2",
            "context": {"research": research_result, "code": code_result},
        })

        return {
            "agent":     "orchestrator",
            "research":   research_result,
            "code":      code_result,
            "validation": validation_result,
            "summary":   "Auditoria V134.2 completada",
        }

    async def _handle_general(self, request: str) -> Dict[str, Any]:
        result = await self.researcher.execute({"task": request})
        return {"agent": "researcher", "output": result}

    def get_health_report(self) -> Dict[str, Any]:
        return {
            "session_id":        self.session_id,
            "max_iterations":    self.max_iterations,
            "current_iteration": self.state.iterations,
            "agents": {
                "orchestrator": {
                    "model":  TIER_DEFAULTS[ModelTier.PREMIUM]["model"],
                    "status": "ok",
                    "name":   self.name,
                },
                "researcher": {
                    "model":  TIER_DEFAULTS[ModelTier.PREMIUM]["model"],
                    "status": "ok" if self._researcher else "not_initialized",
                    "name":   "researcher" if self._researcher else None,
                },
                "coder": {
                    "model":  TIER_DEFAULTS[ModelTier.CODE]["model"],
                    "status": "ok" if self._coder else "not_initialized",
                    "name":   "coder" if self._coder else None,
                },
                "validator": {
                    "model":  TIER_DEFAULTS[ModelTier.FAST]["model"],
                    "status": "ok" if self._validator else "not_initialized",
                    "name":   "validator" if self._validator else None,
                },
            },
            "state_file": str(self.state.path),
        }
