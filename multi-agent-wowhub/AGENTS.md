# WowHub Multi-Agent — Configuración para MiniMax Code (MCode)

> Usa este archivo para inicializar agentes de MiniMax Code que trabajen sobre el proyecto WowHub.
> Compatible con MiniMax Code, Claude Code y cualquier CLI.
> **Path del proyecto:** `C:\Users\MoisésArancibiaS\Documents\MINIMAX\WOWHUB\multi-agent-wowhub` (Windows) o `/workspace/multi-agent-wowhub/` (Linux/Mac).

## Sistema de Agentes

El sistema `wowhub-multi-agent` tiene 4 agentes especializados:

| Agente | Rol | Modelo | Uso |
|--------|-----|--------|-----|
| `orchestrator` | Coordina flujo, clasifica requests | `premium` | Entrada principal |
| `researcher` | Investiga CPs, HU, épicas | `premium` | Análisis de requisitos |
| `coder` | Implementa features, scripts | `code` | Generación de código |
| `validator` | Valida resultados, auditorías | `fast` | Testing y QA |

## Cómo usar con MiniMax Code

### Opción A: Inicialización completa

**Windows (PowerShell):**
```powershell
cd C:\Users\MoisésArancibiaS\Documents\MINIMAX\WOWHUB\multi-agent-wowhub
C:\Python311embed\python.exe main.py --smoke
```

**Linux/Mac:**
```bash
cd /workspace/multi-agent-wowhub
source setup_connections.sh --check
python main.py --smoke
```

### Opción B: Delegar tareas específicas
```bash
# Auditoría de los 599 CPs
python main.py --audit

# Health report
python main.py --health

# Request específico
python main.py --request "Investigar CP-01-01-F"
```

### Opción C: Como librería Python
```python
import asyncio
import sys
from pathlib import Path
# Path portable: detecta el root del proyecto multi-agent-wowhub
sys.path.insert(0, str(Path(__file__).parent))

from agents.orchestrator import Orchestrator

async def main():
    orch = Orchestrator(session_id="mcode-001")
    result = await orch.execute_user_request("Investigar los CPs de la épica E01")
    print(result)

asyncio.run(main())
```

## Estructura del Proyecto

```
multi-agent-wowhub/
├── agents/
│   ├── base_agent.py     # CoordinatorLLM + MockLLM + BaseAgent
│   ├── orchestrator.py   # Orquestador con clasificacion de requests
│   ├── researcher.py     # Investigacion de CPs/HUs
│   ├── coder.py          # Generacion de codigo
│   └── validator.py      # Validacion y testing
├── state/                # Estado persistido por sesion
├── runner/
│   ├── cp_runner.py      # Ejecutor determinista de CPs (sin LLM)
│   └── cp_index.py       # Parser del documento de CPs
├── tests/                # Suite de tests completa
├── workspace/            # Archivos generados por el coder
├── main.py              # CLI principal
└── setup_connections.sh # Configuracion de entorno
```

## Variables de Entorno

| Variable | Descripción | Default |
|----------|-------------|---------|
| `MM_API_KEY` | API key de MiniMax | `sk-your-api-key-here` |
| `MM_USE_MOCK` | Usar MockLLM (sin costo) | `true` |
| `MM_MODEL_PREMIUM` | Modelo para investigacion | `MiniMax-Text-01` |
| `MM_MODEL_CODE` | Modelo para codigo | `MiniMax-Text-01` |
| `MM_MODEL_FAST` | Modelo para validacion | `MiniMax-Text-01` |
| `MAX_ITERATIONS` | Maximo de iteraciones | `5` |
| `LLM_TIMEOUT_SECONDS` | Timeout por request | `30` |
| `RAILWAY_URL` | API de Railway | `https://wowhub-api-production.up.railway.app` |

## Testing

```bash
# Todos los tests
pytest tests/ -v

# Solo unit tests
pytest tests/test_parser_and_agents.py -v

# Solo e2e
pytest tests/test_mock_e2e.py -v

# Coverage
pytest tests/ --cov=agents --cov=state --cov-report=term-missing
```

## Arquitectura de Performance (FASE 1-3)

```
User Request
    │
    ▼
Orchestrator._classify_request()
    ├── audit  ──► _handle_audit()
    │              ├── Researcher (parallel)
    │              └── Coder (parallel)
    │                  └── Validator
    ├── research ─► Researcher
    ├── code ─────► Researcher → Coder
    ├── validate ─► Validator
    └── general ──► Researcher

CP Runner (FASE 2):
  599 CPs → HTTP requests en paralelo (semaphore 25)
    ├── PASS (sin LLM) ──► resultado directo
    └── FAIL ──► Triage LLM (solo fallos)
```

## Seguridad

- `.env` contiene secretos y está en `.gitignore`
- `.env.example` es la plantilla pública (sin secretos)
- `setup_connections.sh` ahora lee desde `.env`, no tiene secretos hardcodeados
- **NUNCA** commitees `.env`, tokens, o keys reales

## Estado

- **Versión**: 1.1.0
- **Directiva**: V134.2
- **Tests**: 29/29 passing
- **CLI smoke**: PASS
- **Python**: 3.11.9 (embeddable)
