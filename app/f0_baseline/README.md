# `app.f0_baseline` — Fase 0: Baseline & Auditoría

Paquete de **auditoría declarativa** del monolito WowHub. Cubre las 3 primeras
HU del plan (HU_01, HU_02, HU_03) sin duplicar los 40 modelos ya existentes en
`app.models`. Total: **8 story points**, **20 tests** en 0.42 s, **0 DB**.

---

## TL;DR

```bash
# Pipeline reproducible (4 pasos, idempotente)
python -m scripts.f0_baseline.generate_prototype
python -m scripts.f0_baseline.extract_inventory
python -m scripts.f0_baseline.build_mapping
python -m scripts.f0_baseline.validate_all

# O todo en uno
python -m scripts.f0_baseline.validate_all
```

Artefactos resultantes en `reports/f0_baseline/`:
- `window-functions.json` + `.md` (HU_01)
- `mapping.json` + `.md` (HU_02)
- `migrations.json` + `.md` (HU_03, cache para `/f0/hu03`)

---

## Endpoints HTTP

Todos bajo `prefix="/f0"`, tag `F0 — Baseline & Auditoría`.

| Método | Path | Propósito |
|---|---|---|
| GET | `/f0/` | Índice con info del paquete y lista de endpoints |
| GET | `/f0/health` | Healthcheck (status, package, version) |
| GET | `/f0/metrics` | Métricas estilo Prometheus en JSON (counts, ratios, flags) |
| GET | `/f0/catalog` | Diff `KEY_TO_MODEL` ↔ `Base.metadata` (orphan_models, catalog_only) |
| GET | `/f0/hu01` | HU_01 — Inventario de funciones `window.*` (3 SP) |
| GET | `/f0/hu02` | HU_02 — Mapeo localStorage ↔ modelos (3 SP) |
| GET | `/f0/hu03?live=true` | HU_03 — Estado Alembic + pytest (2 SP) |

> ⚠️ Si vas a exponer el API públicamente, **protege `/f0/*` con auth** (los
> endpoints filtran el catálogo de modelos y FKs — reconocimiento útil para
> un atacante). Pendiente para F1.

### `?live=true` con circuit breaker

El parámetro `?live=true` en `/f0/hu03` ejecuta `pytest` + `alembic` en vivo.
Sin circuit breaker, si `pytest` se cuelga, el cliente espera hasta 120 s.

Con la variable de entorno **`F0_HU03_LIVE_TIMEOUT`** (default 30 s), el
endpoint devuelve **`503 Service Unavailable`** con `error: "live_timeout"`
si la corrida excede el límite:

```bash
curl -s http://localhost:8000/f0/hu03?live=true
# → 200 con {hu, result: {...}} si termina a tiempo
# → 503 con {error: "live_timeout", timeout_s, detail} si excede

F0_HU03_LIVE_TIMEOUT=60 python -m uvicorn app.main:app
```

---

## Uso programático

```python
# Lazy-loading via PEP 562 __getattr__
from app.f0_baseline import (
    WindowInventory,       # HU_01
    LocalStorageMapping,   # HU_02
    PrototypeGenerator,    # generador HTML sintético
    router,                # FastAPI router (incluir en app.main)
)

# HU_01 — Inventario de funciones window.*
from pathlib import Path
inv = WindowInventory.from_html(Path("prototypes/f0_baseline/demo.html"))
rows = inv.extract()
md = inv.to_markdown(rows, elapsed_ms=12)

# HU_02 — Mapeo localStorage ↔ modelos
m = LocalStorageMapping()
report = m.run()  # incluye JSON, stats, markdown
print(report["stats"])
# → {keys_in_html: 41, models: 41, models_with_tenant_id: 32,
#    cross_foreign_keys: 75, coverage_pct: 100.0, elapsed_ms: 8}

# HU_03 — Estado Alembic + pytest
from app.f0_baseline.hu03 import build_report, to_markdown
report = build_report()  # corre alembic + pytest
print(to_markdown(report))
```

---

## Estructura

```
app/f0_baseline/
├── __init__.py            # PEP 562 __getattr__ + metadatos
├── inventory.py           # HU_01: WindowInventory
├── mapping.py             # HU_02: LocalStorageMapping + KEY_TO_MODEL
├── hu03.py                # HU_03: Hu03Report + build_report()
├── router.py              # FastAPI router (/f0/*)
└── prototype_generator.py # HTML sintético (semilla del inventario)

scripts/f0_baseline/
├── generate_prototype.py  # CLI paso 1
├── extract_inventory.py   # CLI paso 2 (HU_01)
├── build_mapping.py       # CLI paso 3 (HU_02)
└── validate_all.py        # CLI orquestador

tests/f0_baseline/         # 20 tests, 0 DB, 0.42 s
├── conftest.py            # neutraliza fixtures autouse pesadas
├── test_inventory.py
├── test_mapping.py        # incluye test_no_orphan_models
├── test_prototype_generator.py
└── test_router.py         # incluye /f0/metrics, /f0/catalog, circuit breaker
```

---

## Catálogo `KEY_TO_MODEL`

Único punto de verdad de la asociación `clave localStorage → modelo
SQLAlchemy`. Editar aquí al añadir una nueva clave de UI:

```python
# app/f0_baseline/mapping.py
KEY_TO_MODEL: dict[str, dict[str, str]] = {
    "wowhub.tenant":  {"model": "Tenant",  "module": "core",     "kind": "object"},
    "wowhub.order":   {"model": "Order",   "module": "sales",    "kind": "array"},
    # ...
}
```

**Cómo añadir una nueva entrada**:
1. Crear el modelo en `app/models/<modulo>.py`.
2. Añadir la entrada en `KEY_TO_MODEL` con `model`, `module`, `kind` ("object" o "array").
3. (Opcional) Añadir el `localStorage.setItem(...)` correspondiente en
   `LOCALSTORAGE_DEMO` dentro de `prototype_generator.py` para que el HTML
   sintético lo siembre.
4. Re-correr `python -m scripts.f0_baseline.validate_all` y revisar `/f0/catalog`.

**Si añades un modelo que NO se siembra en localStorage** (p. ej. entidad
interna, log de plataforma, configuración global), añádelo a
`INTERNAL_MODELS_ALLOWLIST` en `router.py` para que `test_no_orphan_models`
no falle. Ejemplos actuales: `Tenant`, `User`, `AuthToken`, `AuditLog`,
`LegalConsent`, `SiteConfig`, `OnboardingState`.

---

## Variables de entorno

| Variable | Default | Propósito |
|---|---|---|
| `F0_PYTEST_TARGET` | `tests/f0_baseline/` | Path que `hu03.build_report()` recolecta con `--collect-only` |
| `F0_PYTEST_RUN_TARGET` | mismo que `F0_PYTEST_TARGET` | Path que `hu03.build_report()` corre con pytest |
| `F0_PYTEST_SKIP_RUN` | `false` | Si `1/true/yes`, salta la corrida de pytest (solo collect) |
| `F0_HU03_LIVE_TIMEOUT` | `30` | Segundos antes de que `?live=true` devuelva 503 |

---

## Tests

```bash
# Sub-suite F0 (rápida, 0 DB)
pytest tests/f0_baseline/ -v
# → 20 passed in 0.42s

# Suite completa (incluye CI)
pytest tests/
# → 681 passed, 2 failed (pre-existentes en test_marketing_studio.py), 2 skipped
```

### Tests destacados

- `test_no_orphan_models_in_metadata` — detecta modelos en `app.models` no catalogados.
- `test_no_catalog_only_entries` — detecta entradas del catálogo sin modelo físico.
- `test_router_hu03_live_returns_503_on_timeout` — verifica el circuit breaker.
- `test_router_metrics_handles_missing_cache` — métricas robustas sin cache.

---

## CI

El workflow `.github/workflows/ci.yml` corre **3 jobs en paralelo** en cada
PR y push a `main`:

1. **`pytest`** — suite completa (`pytest tests/ --maxfail=20`).
2. **`f0-pipeline`** — regenera artefactos y los sube como `actions/upload-artifact`.
3. **`f0-smoke`** — `TestClient` + verificación de `/openapi.json` contiene `/f0/*`.

`concurrency` group cancela runs obsoletos cuando llega un push nuevo.

---

## Limitaciones conocidas y roadmap F1

Ver [`docs/f0_baseline/ANALISIS.md`](../../docs/f0_baseline/ANALISIS.md) y
[`docs/reports/f0_review_report.md`](../../docs/reports/f0_review_report.md).

| Punto | Estado | Roadmap |
|---|---|---|
| Prototipo HTML sintético (no real) | Pendiente | F1: reemplazar por HTML real V134.1 |
| Validación de payloads con Pydantic | Pendiente | F1: schemas por key |
| Parser AST JS (en vez de regex) | Pendiente | F1: esprima / tree-sitter |
| Crear `alembic/` | Pendiente | F1: `alembic init` + `revision --autogenerate` |
| Auth en `/f0/*` | Pendiente | F1: `require_admin` dependency |

---

_Maintained by WowHub V134.1 · autor del paquete: MiniMax Agent_
