# Despliegue en GitHub + Render — WowHub V134.1

**Alcance:** instrucciones operativas para que el equipo (o un agente externo) pueda clonar, validar, commitear y desplegar WowHub en producción usando GitHub como SCM y Render como PaaS.

**Audiencia:** dev humano con `git push` + un bot/agente que automatiza la fase F0.

---

## 1. Prerrequisitos

- **Git 2.40+** con acceso de escritura al remoto `git@github.com:moisesarancibiasanchez-cpu/WowHub.git`.
- **Python 3.12** (gestionado con `venv` o `uv`).
- **Docker** (sólo para build local del contenedor; en Render se compila automáticamente).
- **Render account** con el blueprint `render.yaml` ya enlazado (ver §5).

---

## 2. Clonar e instalar

```bash
git clone git@github.com:moisesarancibiasanchez-cpu/WowHub.git wowhub
cd wowhub

# Entorno virtual
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Variables de entorno
cp .env.example .env
# (editar .env — al menos SECRET_KEY y JWT_SECRET con 32+ chars)
```

Validar instalación:

```bash
python -c "from app.main import app; print(len(app.routes), 'rutas')"
# → ~99 rutas
```

---

## 3. Validar la fase F0 localmente

```bash
# 3.1) Tests del paquete F0 (0.34 s, no requiere DB)
python -m pytest tests/f0_baseline/ -v

# 3.2) Pipeline completo (genera artefactos en reports/f0_baseline/)
python -m scripts.f0_baseline.validate_all

# 3.3) Servir y comprobar endpoints
uvicorn app.main:app --reload
# → GET http://localhost:8000/f0/        (índice)
# → GET http://localhost:8000/f0/health
# → GET http://localhost:8000/f0/hu01    (221 funciones)
# → GET http://localhost:8000/f0/hu02    (41 keys → 41 modelos, 100% cobertura)
# → GET http://localhost:8000/f0/hu03    (último reporte cacheado)
```

Salida esperada del pipeline:

```
[3/4] HU_02 — Mapeo localStorage ↔ modelos SQLAlchemy …
[OK] Mapeo: 41 keys → 41 modelos en 0 ms
     modelos con tenant_id: 32
     FKs cruzadas:         75
     cobertura:            100.0%
[4/4] HU_03 — Estado de Alembic + pytest …
     alembic/ existe: False
     alembic upgrade: n/a (no alembic/ en el proyecto)
     pytest collected: 19 tests
     pytest:          ======================== 19 passed in 0.35s ========================
     modelos cargados: 40
 ✓ F0 Baseline completado (8 SP: HU_01=3 + HU_02=3 + HU_03=2)
```

---

## 4. Convención de commits

WowHub sigue **Conventional Commits** con scopes explícitos. Ejemplos válidos:

```bash
git commit -m "feat(f0): add HU_02 localStorage → models mapping"
git commit -m "test(f0): add 19 unit tests for inventory + mapping + router"
git commit -m "fix(f0): resolve AIMetricDaily table via SQLAlchemy 2.0 mappers"
git commit -m "docs(f0): add ANALISIS.md and GITHUB_DEPLOY.md"
git commit -m "chore(deps): pin bcrypt==4.0.1 to avoid passlib incompat"
```

Reglas:
- `feat|fix|docs|test|chore|refactor|perf` (scope opcional).
- Mensaje en **inglés**, < 72 chars en el subject.
- Body envuelto a 72 cols con motivación + impacto.

---

## 5. Despliegue en Render

### 5.1 Blueprint
El repositorio ya incluye `render.yaml` con la definición de:
- **PostgreSQL `wowhub`** (plan starter, región oregon).
- **Web service `wowhub-api`** (Docker runtime).

Para crear el stack desde cero:

1. En Render → **New → Blueprint**.
2. Conectar el repo `moisesarancibiasanchez-cpu/WowHub`.
3. Render detecta `render.yaml` y propone crear:
   - `wowhub` (database)
   - `wowhub-api` (web service)
4. Confirmar y esperar al primer build (~6 min, compila `Dockerfile`).

### 5.2 Variables de entorno requeridas

| Var | Ejemplo | Notas |
|---|---|---|
| `DATABASE_URL` | (auto desde la DB `wowhub`) | `fromDatabase: { name: wowhub, property: connectionString }` |
| `SECRET_KEY` | 32+ chars random | Obligatorio, sin默认值 |
| `JWT_SECRET` | 32+ chars random | Obligatorio |
| `RATE_LIMIT_ENABLED` | `true` | Rate-limit en producción |
| `AUDIT_ENABLED` | `true` | Auditoría en producción |
| `CORS_ORIGINS` | `https://wowhub.cl,https://www.wowhub.cl` | CSV de orígenes permitidos |

En Render: **Dashboard → wowhub-api → Environment → Add Env Var**.

### 5.3 Verificación post-deploy

```bash
# Healthcheck
curl -fsS https://wowhub-api.onrender.com/healthz

# Endpoints F0 (públicos, sin auth)
curl -fsS https://wowhub-api.onrender.com/f0/        | jq .
curl -fsS https://wowhub-api.onrender.com/f0/hu01    | jq .result.total_functions
curl -fsS https://wowhub-api.onrender.com/f0/hu02    | jq .result.coverage_pct
curl -fsS https://wowhub-api.onrender.com/f0/hu03    | jq .result.models_loaded
```

Esperado: `total_functions=221`, `coverage_pct=100.0`, `models_loaded=40`.

---

## 6. CI con GitHub Actions (opcional)

Si quieres que cada PR valide F0 automáticamente, añade `.github/workflows/ci-f0.yml`:

```yaml
name: ci-f0
on:
  pull_request:
    paths:
      - "app/f0_baseline/**"
      - "scripts/f0_baseline/**"
      - "tests/f0_baseline/**"

jobs:
  f0:
    runs-on: ubuntu-latest
    timeout-minutes: 5
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install
        run: pip install -e ".[dev]"
      - name: Run F0 tests
        run: python -m pytest tests/f0_baseline/ -v --tb=short
      - name: Run F0 pipeline
        run: python -m scripts.f0_baseline.validate_all
      - name: Upload artifacts
        uses: actions/upload-artifact@v4
        with:
          name: f0-baseline-report
          path: reports/f0_baseline/
```

**Costo:** 0 USD/mes en plan Free de GitHub Actions (2 000 min/mes, este job gasta ~30 s).

---

## 7. Re-desplegar después de cambios

```bash
# 1) Commit + push
git add app/f0_baseline scripts/f0_baseline tests/f0_baseline docs/f0_baseline \
        render.yaml
git commit -m "feat(f0): <resumen>"
git push origin main

# 2) Render detecta el push → re-build automático (~3-6 min)
# 3) Validar post-deploy (ver §5.3)
```

Si Render no re-deploya (raro, suele pasar con cambios sólo en docs):
- **Dashboard → wowhub-api → Manual Deploy → Deploy latest commit**.

---

## 8. Troubleshooting

| Síntoma | Causa probable | Fix |
|---|---|---|
| `pytest collected: 0 tests` en `hu03.json` | El parser buscaba línea que empezara con dígito y la línea `== 19 tests collected ==` empieza con `=`. | Ya parcheado: regex `(\d+)\s+tests?\s+collected`. |
| `AttributeError: module 'app.f0_baseline' has no attribute 'router'` | Importaste el módulo sin usar `__getattr__` de PEP 562. | Usar `from app.f0_baseline import router` (perezoso) o `import app.f0_baseline.router`. |
| `AIMetricDaily table not found` | El fallback por convención no cubre plurales compuestos (`ai_metric` → `ai_metrics_daily`). | Ya parcheado: `_find_table` itera `Base.registry.mappers` (fuente de verdad). |
| `F0 tests cuelgan > 30 s` | El conftest padre ejecuta `reset_db` (drop_all + create_all sobre 40 tablas) para cada test. | Ya parcheado: `tests/f0_baseline/conftest.py` redefine `reset_db` y `_clear_rate_limit_buckets` como no-ops. |
| `ModuleNotFoundError: No module named 'app'` en CI | Falta `pip install -e .` o el `PYTHONPATH`. | Asegurar que el job instala con `pip install -e ".[dev]"`. |

---

_Generado por `app.f0_baseline` · ver también `ANALISIS.md` para el detalle técnico de cada HU._
