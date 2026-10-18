"""
Researcher - Agente especializado en investigacion y analisis
Sistema Multi-Agent WowHub V134.2
"""

import json
import logging
import os
from typing import Dict, Any
from pathlib import Path

from agents.base_agent import BaseAgent, ModelTier

logger = logging.getLogger(__name__)


class Researcher(BaseAgent):
    """Researcher - Agente especializado en investigar, analizar y buscar informacion."""
    
    def __init__(self):
        super().__init__(name="researcher", tier=ModelTier.PREMIUM)

        # Cargar .env si existe (para tener CP_DOC en os.environ)
        try:
            from dotenv import load_dotenv
            env_path = Path(__file__).parent.parent / ".env"
            if env_path.exists():
                load_dotenv(env_path, override=False)
        except ImportError:
            pass

        current = Path(__file__).parent.parent
        self.cp_doc_path = current / "TEST_CASES_V134_2.md"

        if not self.cp_doc_path.exists():
            # Buscar CP_DOC en orden de prioridad
            cp_doc_env = os.environ.get("CP_DOC", "")
            if cp_doc_env:
                # Si es relativo, resolver contra el project root (multi-agent-wowhub/)
                cp_doc_path = Path(cp_doc_env)
                if not cp_doc_path.is_absolute():
                    cp_doc_path = (current / cp_doc_env).resolve()
                candidates = [cp_doc_path]
            else:
                # Rutas relativas al proyecto
                project_root = current.parent
                candidates = [
                    project_root / "TEST_CASES_V134_2.md",
                    project_root.parent / "WowHub_GIT" / "docs" / "TEST_CASES_V134_2.md",
                    project_root.parent / "WowHub_GIT" / "TEST_CASES_V134_2.md",
                ]
            for candidate in candidates:
                if candidate.exists():
                    self.cp_doc_path = candidate
                    logger.info(f"CP doc encontrado en: {candidate}")
                    break
        
        if self.cp_doc_path.exists():
            logger.info(f"Researcher listo (cp_doc={self.cp_doc_path})")
        else:
            logger.warning(
                f"Researcher listo SIN CP doc. "
                f"Definir CP_DOC en .env o colocar TEST_CASES_V134_2.md "
                f"en la raiz del proyecto. Buscado: {self.cp_doc_path}"
            )
    
    async def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Ejecuta tarea de investigacion."""
        research_task = task.get("task", "")
        context = task.get("context", {})
        
        logger.info(f"Researcher ejecutando: {research_task[:100]}...")

        prompt = self._build_research_prompt(research_task, context)
        result = await self.athink(prompt, max_tokens=800, require_json=True)

        if isinstance(result, str):
            try:
                result = json.loads(result)
            except json.JSONDecodeError:
                result = {"status": "success", "findings": [result], "sources": [], "confidence": 0.7}
        
        self.update_state("last_research", research_task)
        self.update_state("last_result", result)
        
        return result
    
    def _build_research_prompt(self, task: str, context: Dict[str, Any]) -> str:
        """Construye el prompt de investigacion."""
        base_prompt = f"""Eres un investigador especializado en el proyecto WowHub V134.2.

CONTEXTO DEL PROYECTO:
- Sistema de gestion de negocio unificado
- 49 Historias de Usuario, 8 Epicas
- 599 Casos de Prueba (CP)
- Auditado contra directiva V134.2

TU TAREA:
{task}

"""
        
        if context:
            base_prompt += f"""
CONTEXTO DE AGENTES PREVIOS:
{json.dumps(context, indent=2, ensure_ascii=False)}

"""
        
        base_prompt += """
INSTRUCCIONES:
1. Analiza la tarea solicitada
2. Si es sobre casos de prueba, referencia los CPs relevantes (formato CP-XX-NN-TIPO)
3. Proporciona hallazgos concretos y accionables
4. Indica nivel de confianza (0.0 - 1.0)

RESPUESTA (formato JSON):
{
    "status": "success" | "partial" | "failed",
    "findings": ["lista de hallazgos"],
    "sources": ["fuentes consultadas"],
    "confidence": 0.0-1.0,
    "recommendations": ["opcional - recomendaciones"]
}
"""
        return base_prompt
    
    async def research_cp(self, cp_id: str) -> Dict[str, Any]:
        """Investiga un caso de prueba especifico."""
        prompt = f"""Busca informacion sobre el caso de prueba: {cp_id}

En el documento TEST_CASES_V134_2.md, encuentra:
- Descripcion del CP
- Pasos a seguir
- Resultado esperado
- Epica y HU relacionada

RESPUESTA (JSON):
{{
    "cp_id": "{cp_id}",
    "description": "...",
    "steps": ["..."],
    "expected_result": "...",
    "epic": "...",
    "hu": "..."
}}
"""
        result = await self.athink(prompt, max_tokens=500, require_json=True)
        if isinstance(result, str):
            try:
                return json.loads(result)
            except json.JSONDecodeError:
                return {"cp_id": cp_id, "description": result, "status": "parsed_raw"}
        return result
    
    async def research_by_epic(self, epic: str) -> Dict[str, Any]:
        """Investiga todos los casos de prueba de una epica."""
        prompt = f"""Investiga todos los casos de prueba relacionados con la epica: {epic}

RESPUESTA (JSON):
{{
    "epic": "{epic}",
    "total_cps": N,
    "breakdown": {{"functional": N, "security": N, "performance": N, "negative": N}},
    "story_points": N
}}
"""
        result = await self.athink(prompt, max_tokens=600, require_json=True)
        if isinstance(result, str):
            try:
                return json.loads(result)
            except json.JSONDecodeError:
                return {"epic": epic, "raw_response": result, "status": "parsed_raw"}
        return result
