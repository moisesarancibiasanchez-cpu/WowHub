"""
Coder - Agente especializado en implementacion y generacion de codigo
Sistema Multi-Agent WowHub V134.2
"""

import json
import logging
from typing import Dict, Any
from pathlib import Path

from agents.base_agent import BaseAgent, ModelTier

logger = logging.getLogger(__name__)


class Coder(BaseAgent):
    """Coder - Agente especializado en implementar, modificar y generar codigo."""
    
    def __init__(self):
        super().__init__(name="coder", tier=ModelTier.CODE)
        
        current = Path(__file__).parent.parent
        self.workspace_path = current / "workspace"
        self.workspace_path.mkdir(exist_ok=True)
        
        logger.info(f"Coder listo (workspace={self.workspace_path})")
    
    async def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Ejecuta tarea de codificacion."""
        code_task = task.get("task", "")
        context = task.get("context", {})
        
        logger.info(f"Coder ejecutando: {code_task[:100]}...")

        prompt = self._build_code_prompt(code_task, context)
        result = await self.athink(prompt, max_tokens=1000, require_json=True)

        if isinstance(result, str):
            try:
                result = json.loads(result)
            except json.JSONDecodeError:
                result = {"status": "success", "message": "Codigo generado (respuesta raw)", "raw_output": result, "files_created": []}
        
        self.update_state("last_task", code_task)
        self.update_state("last_result", result)
        
        return result
    
    def _build_code_prompt(self, task: str, context: Dict[str, Any]) -> str:
        """Construye el prompt de codificacion."""
        base_prompt = f"""Eres un coder especializado en el proyecto WowHub V134.2.

CONTEXTO:
- Sistema de gestion de negocio (productos, CRM, reportes)
- Python/FastAPI backend
- PostgreSQL database
- 49 Historias de Usuario implementadas

TU TAREA:
{task}

"""
        
        if context:
            findings = context.get("findings", [])
            if isinstance(findings, list):
                findings_str = "\n".join(f"- {f}" for f in findings[:5])
                base_prompt += f"""
CONTEXTO DE INVESTIGACION PREVIA:
{findings_str}

"""
        
        base_prompt += """
INSTRUCCIONES:
1. Analiza que necesita implementarse
2. Si requiere crear archivos, especifica path y contenido
3. Si requiere modificar archivos existentes, indica que cambiar
4. Proporciona el codigo completo cuando sea posible

RESPUESTA (formato JSON):
{
    "status": "success" | "partial" | "needs_review",
    "files_created": ["lista de archivos creados"],
    "files_modified": ["lista de archivos modificados"],
    "changes": ["descripcion de cambios"],
    "code_snippets": {"path/file.py": "contenido"},
    "verified": true/false,
    "next_steps": ["pasos siguientes"]
}
"""
        return base_prompt
    
    async def implement_feature(self, feature: str, hu_id: str) -> Dict[str, Any]:
        """Implementa una caracteristica especifica de una Historia de Usuario."""
        prompt = f"""Implementa la caracteristica '{feature}' para la Historia de Usuario {hu_id}.

Usa FastAPI para endpoints, SQLAlchemy para modelos de DB, Pydantic para validacion.

RESPUESTA (JSON):
{{
    "hu_id": "{hu_id}",
    "feature": "{feature}",
    "status": "implemented",
    "files": {{"path/archivo.py": "contenido completo"}},
    "tests_added": ["paths de tests"],
    "verified": true
}}
"""
        response = self.think(prompt, max_tokens=1500)
        
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            return {"hu_id": hu_id, "feature": feature, "raw_response": response, "status": "parsed_raw"}
    
    async def create_test(self, test_name: str, cp_id: str) -> Dict[str, Any]:
        """Crea un test unitario para un caso de prueba especifico."""
        prompt = f"""Crea un test unitario para el caso de prueba {cp_id}.

Nombre del test: {test_name}

Usa pytest con fixtures para setup/teardown y assertions claras.

RESPUESTA (JSON):
{{
    "cp_id": "{cp_id}",
    "test_name": "{test_name}",
    "status": "created",
    "test_code": "contenido completo del test",
    "file_path": "tests/test_{cp_id}.py"
}}
"""
        response = self.think(prompt, max_tokens=800)
        
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            return {"cp_id": cp_id, "test_name": test_name, "raw_response": response, "status": "parsed_raw"}
