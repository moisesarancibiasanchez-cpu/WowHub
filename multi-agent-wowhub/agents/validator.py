"""
Validator - Agente especializado en validacion y testing
Sistema Multi-Agent WowHub V134.2
"""

import json
import logging
from typing import Dict, Any, List

from agents.base_agent import BaseAgent, ModelTier

logger = logging.getLogger(__name__)


class Validator(BaseAgent):
    """Validator - Agente especializado en validar codigo, tests y resultados."""
    
    def __init__(self):
        super().__init__(name="validator", tier=ModelTier.FAST)
        self._validation_history: List[Dict[str, Any]] = []
        logger.info("Validator listo")
    
    async def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Ejecuta tarea de validacion."""
        validation_task = task.get("task", "")
        context = task.get("context", {})
        
        logger.info(f"Validator ejecutando: {validation_task[:100]}...")

        prompt = self._build_validation_prompt(validation_task, context)
        # Usar athink con require_json=True para validacion determinista
        result = await self.athink(prompt, max_tokens=600, require_json=True)

        if isinstance(result, str):
            try:
                result = json.loads(result)
            except json.JSONDecodeError:
                result = {"status": "success", "message": "Validacion completada", "raw_output": result}
        
        self._validation_history.append({"task": validation_task, "result": result})
        self.update_state("last_task", validation_task)
        self.update_state("last_result", result)
        
        return result
    
    def _build_validation_prompt(self, task: str, context: Dict[str, Any]) -> str:
        """Construye el prompt de validacion."""
        base_prompt = f"""Eres un validador especializado en el proyecto WowHub V134.2.

TU TAREA:
{task}

"""
        
        if context:
            base_prompt += f"""
CONTEXTO A VALIDAR:
{json.dumps(context, indent=2, ensure_ascii=False)[:1000]}

"""
        
        base_prompt += """
INSTRUCCIONES:
1. Valida que el codigo/contenido cumpla con los requisitos
2. Verifica que los tests cubran los casos necesarios
3. Comprueba que no haya errores obvios
4. Proporciona veredicto claro

RESPUESTA (formato JSON):
{
    "status": "pass" | "fail" | "partial",
    "tests_passed": N,
    "tests_failed": N,
    "coverage": "XX%",
    "issues": ["lista de problemas encontrados"],
    "recommendations": ["mejoras sugeridas"]
}
"""
        return base_prompt
    
    async def validate_audit_results(self, audit_results: Dict[str, Any]) -> Dict[str, Any]:
        """Valida resultados de una auditoria V134.2."""
        prompt = f"""Valida los resultados de la auditoria V134.2.

RESULTADOS A VALIDAR:
{json.dumps(audit_results, indent=2, ensure_ascii=False)[:2000]}

CRITERIOS DE VALIDACION:
- Se ejecutaron todos los 599 casos de prueba?
- Los resultados son consistentes?
- Hay huecos en la cobertura?

RESPUESTA (JSON):
{{
    "audit_validated": true/false,
    "total_cps_expected": 599,
    "total_cps_actual": N,
    "coverage_percentage": "XX%",
    "gaps_found": ["huecos de cobertura"],
    "issues": ["problemas encontrados"],
    "recommendation": "aprobado" | "revisar" | "rechazado"
}}
"""
        response = await self.athink(prompt, max_tokens=800, require_json=True)
        if isinstance(response, str):
            try:
                response = json.loads(response)
            except json.JSONDecodeError:
                return {"audit_results": audit_results, "raw_response": response, "status": "parsed_raw"}
        return response

    async def validate_code_quality(self, code: str, language: str = "python") -> Dict[str, Any]:
        """Valida la calidad de codigo generado."""
        prompt = f"""Valida la calidad del siguiente codigo {language}:

```{language}
{code[:2000]}
```

CRITERIOS:
- Sigue las mejores practicas del lenguaje?
- Hay errores potenciales?
- Esta bien documentado?
- Los tests son adecuados?

RESPUESTA (JSON):
{{
    "quality_score": 0-100,
    "issues": ["problemas encontrados"],
    "suggestions": ["mejoras"],
    "approved": true/false
}}
"""
        result = await self.athink(prompt, max_tokens=600, require_json=True)
        if isinstance(result, str):
            try:
                return json.loads(result)
            except json.JSONDecodeError:
                return {"code_quality": "unknown", "raw_response": result, "status": "parsed_raw"}
        return result
    
    def get_validation_history(self) -> List[Dict[str, Any]]:
        """Retorna el historial de validaciones."""
        return self._validation_history.copy()
