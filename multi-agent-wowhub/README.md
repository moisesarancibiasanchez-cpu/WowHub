# WowHub Multi-Agent System v1.1.0

> Sistema multi-agente especializado para auditoria y gestion del proyecto WowHub, alineado con la Directiva V134.2 (599 Casos de Prueba / 49 Historias de Usuario / 8 Epicas).

## Arquitectura

```
+------------------+
|   ORCHESTRATOR   |
+--------+---------+
         |
    +----+----+----+
    |         |    |
    v         v    v
RESEARCHER  CODER  VALIDATOR
```

## Agentes

| Agente | Rol | Modelo |
|--------|-----|--------|
| Orchestrator | Coordina el flujo entre agentes | MM_MODEL_PREMIUM |
| Researcher | Investiga y analiza casos de prueba | MM_MODEL_PREMIUM |
| Coder | Implementa codigo y features | MM_MODEL_CODE |
| Validator | Valida y ejecuta tests | MM_MODEL_FAST |

## Inicio Rapido

```bash
cd multi-agent-wowhub
pip install -e .
python main.py --smoke
```

## Comandos CLI

```bash
python main.py --smoke          # Smoke test
python main.py --request "..."  # Ejecutar request
python main.py --health         # Health report
python main.py --audit          # Auditoria V134.2
```

## Testing

```bash
pytest tests/ -v
```

## Estado

- **Version**: 1.1.0
- **Directiva**: V134.2
- **Cobertura**: 599 CPs / 49 HUs / 8 Epicas
- **Modo**: MockLLM (desarrollo)
