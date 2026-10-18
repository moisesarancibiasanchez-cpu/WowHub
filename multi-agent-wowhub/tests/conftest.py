"""
conftest.py — Fixtures globales para pytest
WowHub Multi-Agent System v1.1.0
"""

import sys
import os
from pathlib import Path

# Asegurar que el proyecto esta en el path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Forzar modo mock para todos los tests
os.environ.setdefault("MM_USE_MOCK", "true")
os.environ.setdefault("MAX_ITERATIONS", "5")
os.environ.setdefault("LOG_LEVEL", "WARNING")
