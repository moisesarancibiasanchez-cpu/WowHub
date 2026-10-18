# ⚡ INIT FAST — WowHub Multi-Agent v1.1.0 (≤2 min)

> **Uso:** Pegá este prompt completo en MiniMax Code desde la raíz del proyecto `multi-agent-wowhub/`.
> **Skip:** No crea remote de GitHub (ya existe). No corre auditoría (eso es `audit_run --all`).

---

## 0 · Contexto (declarar una sola vez)

```
PROJECT_ROOT=$(pwd)
PY=${PY:-python}                        # o C:\Python311embed\python.exe si no hay venv
ENV_FILE=$PROJECT_ROOT/.env
HEALTH=$PROJECT_ROOT/agent_health.json
```

**KILL si:** `PROJECT_ROOT` no contiene `agents/base_agent.py` → abortar.

---

## 1 · Pre-flight paralelo (un solo bloque)

```bash
# 1.1 Entorno + .env + python + railway en paralelo
{
  [ -f "$ENV_FILE" ] && grep -q "^MM_API_KEY=" "$ENV_FILE" && echo "✅ .env OK" || echo "❌ .env falta MM_API_KEY"
  command -v $PY >/dev/null && $PY --version || echo "❌ python no encontrado"
  $PY -c "import httpx,pydantic,tenacity,loguru" 2>/dev/null && echo "✅ deps OK" || echo "❌ instalar: pip install -e .[dev]"
  curl -fsS -m 5 https://wowhub-api-production.up.railway.app/health >/dev/null && echo "✅ Railway OK" || echo "⚠️ Railway inalcanzable (no bloqueante)"
} | sort
```

**KILL si:** `.env` falla o `python`/`deps` faltan.

---

## 2 · Forzar modo seguro (idempotente)

```bash
# 2.1 Mock mode hasta validar API real; sobreescribe sin romper el archivo
grep -q "^MM_USE_MOCK=" "$ENV_FILE" && sed -i 's/^MM_USE_MOCK=.*/MM_USE_MOCK=true/' "$ENV_FILE" || echo "MM_USE_MOCK=true" >> "$ENV_FILE"
grep -q "^MAX_ITERATIONS=" "$ENV_FILE" || echo "MAX_ITERATIONS=5" >> "$ENV_FILE"

# 2.2 Imports + tests + init en un solo proceso Python (arranque en frío amortizado)
$PY -c "
import asyncio, json, sys
from agents.orchestrator import Orchestrator

async def main():
    o = Orchestrator(session_id='init-fast')
    _ = (o.researcher, o.coder, o.validator)        # lazy init
    r = await o.execute_user_request('Smoke: list 4 agents')
    health = {
        'session_id': 'init-fast',
        'status': r.get('status'),
        'iterations': r.get('iterations'),
        'agents': {a: getattr(o, a).name for a in ('researcher','coder','validator')},
        'max_iterations': o.max_iterations,
    }
    with open(r'$HEALTH', 'w') as f: json.dump(health, f, indent=2, ensure_ascii=False)
    print(json.dumps(health, ensure_ascii=False))

asyncio.run(main())
"
```

**KILL si:** `status != ok` o algún agente no responde.

---

## 3 · Tests fail-fast (solo si el smoke pasó)

```bash
$PY -m pytest tests/ -q -x --no-header 2>&1 | tail -5
```

**KILL si:** exit code ≠ 0.

---

## 4 · Respuesta final (una sola línea JSON)

```json
{"status":"ready","session_id":"init-fast","smoke":"ok","tests":"<passed>/<total>","health":"agent_health.json","next":"audit_run --all"}
```

Si falla cualquier kill-switch anterior:
```json
{"status":"failed","step":"<1|2|3>","error":"<corto>","action_required":"<qué necesito>"}
```

---

## Anti-patrones evitados (lecciones del proyecto real)

1. **No usar `requests` síncrono** dentro de async → `httpx.AsyncClient` ya integrado en `base_agent.py`.
2. **No hacer fallback silencioso a mock** cuando falla la API → `fail-loud` (raise) ya activado por defecto.
3. **No `cd` repetido** → `PROJECT_ROOT=$(pwd)` una vez, paths relativos después.
4. **No verbose `tail -30`** → `pytest -q` y `2>&1 | tail -5` solo si falla.
5. **No pasos condicionales con `if [ -f ]`** → usar `grep -q` para check-in-place.
6. **No 4 agentes creados con `Orchestrator(...).researcher` separados** → la property lazy ya los crea; el `_ =` solo fuerza la instanciación.
7. **No pedir credenciales al final** → el `.env` debe existir antes del Paso 1; el check lo valida.

---

**Versión:** 1.0 (fast)
**Plantilla derivada de:** `wowhub-app_scripts_v134_2_PROMPT_INICIALIZACION_MULTIAGENT.md` (330 líneas → 50 líneas, ~6× más rápido de ejecutar).
