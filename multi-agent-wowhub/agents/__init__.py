"""
WowHub Multi-Agent System v1.1.0
4 agentes especializados: Orchestrator, Researcher, Coder, Validator
"""

from agents.base_agent import BaseAgent, CoordinatorLLM, MockLLM
from agents.orchestrator import Orchestrator
from agents.researcher import Researcher
from agents.coder import Coder
from agents.validator import Validator

__version__ = "1.1.0"
__all__ = [
    "BaseAgent",
    "CoordinatorLLM", 
    "MockLLM",
    "Orchestrator",
    "Researcher",
    "Coder",
    "Validator",
]
