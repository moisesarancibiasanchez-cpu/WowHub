"""
State management para el Orchestrator del sistema multi-agente WowHub V134.2
"""

import json
import os
import logging
from typing import Dict, Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class OrchestratorState:
    """Gestiona la persistencia del estado del Orchestrator."""
    
    def __init__(self, session_id: str = "default", base_path: Optional[str] = None):
        self.session_id = session_id
        if base_path is None:
            current = Path(__file__).parent
            self.base_path = current.parent
        else:
            self.base_path = Path(base_path)
        
        self.state_dir = self.base_path / "state"
        self.state_dir.mkdir(exist_ok=True)
        
        self.path = self.state_dir / f"session_{session_id}.json"
        self._data: Dict[str, Any] = {
            "session_id": session_id,
            "agents": {},
            "iterations": 0,
            "max_iterations": int(os.getenv("MAX_ITERATIONS", "5")),
            "status": "initialized",
            "history": []
        }
        
        if self.path.exists():
            self.load()
        else:
            self.save()
    
    def load(self) -> None:
        """Carga estado desde archivo."""
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                self._data = json.load(f)
            logger.info(f"Estado cargado desde {self.path}")
        except Exception as e:
            logger.error(f"Error cargando estado: {e}")
    
    def save(self) -> None:
        """Persiste estado en archivo."""
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2, ensure_ascii=False)
            logger.debug(f"Estado guardado en {self.path}")
        except Exception as e:
            logger.error(f"Error guardando estado: {e}")
    
    def get(self, key: str, default: Any = None) -> Any:
        """Obtiene valor del estado."""
        return self._data.get(key, default)
    
    def set(self, key: str, value: Any) -> None:
        """Establece valor en el estado."""
        self._data[key] = value
        self.save()
    
    def update_agent_status(self, agent_name: str, status: str, info: Dict[str, Any] = None) -> None:
        """Actualiza el estado de un agente."""
        if "agents" not in self._data:
            self._data["agents"] = {}
        
        self._data["agents"][agent_name] = {
            "status": status,
            "info": info or {},
            "updated_at": "now"
        }
        self.save()
    
    def increment_iteration(self) -> int:
        """Incrementa el contador de iteraciones."""
        self._data["iterations"] = self._data.get("iterations", 0) + 1
        self.save()
        return self._data["iterations"]
    
    @property
    def iterations(self) -> int:
        return self._data.get("iterations", 0)
    
    @property
    def max_iterations(self) -> int:
        return self._data.get("max_iterations", 5)
    
    @property
    def data(self) -> Dict[str, Any]:
        return self._data.copy()
