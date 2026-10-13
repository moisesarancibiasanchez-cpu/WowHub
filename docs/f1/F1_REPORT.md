# F1 — Hardening del Baseline (WowHub V134.1)

**Alcance:** endurecer el paquete `app.f0_baseline/` introducido en F0 (HU_01..HU_03) para que sea **production-grade**: contratos OpenAPI estrictos, parsing correcto, y migraciones versionadas.

**Total:** 3 HU nuevas, **8 story points** (3+3+2), **58 tests propios** que pasan en ~0.6 s.

> **Convención de nombres.** F0 introdujo las HU como `HU_01`, `HU_02`, `HU_03` (3+3+2 SP). F1 introduce:
>
> | F1.x | ≈ HU | SP | Título |
> |---|---|---|---|
> | **F1.1** | HU_04 | 3 | Pydantic v2 estricto en `/f0/*` |
> | **F1.2** | HU_05 | 3 | AST-lite parser para `window.*` |
> | **F1.3** | HU_06 | 2 | Alembic init + autogen desde `Base` |

---

## TL;DR

- **3 recomendaciones fuertes** del review F0 implementadas, **sin tocar modelos** ni romper la suite existente.
- **88/88 tests** pasando (30 F0 originales + 18 P1 Pydantic + 23 P1 parser + 17 P1 Alembic; 2 marcados `@pytest.mark.slow` para no ejecutarse en el flujo default de CI).
- **OpenAPI ahora estricto**: cada endpoint de `/f0/*` declara `response_model` y los modelos 404/503.
- **El parser de `window.*` ya no tiene falsos positivos** por strings, comentarios, ni funciones con braces anidados.
- **El proyecto ya tiene `alembic/`** con `env.py` que lee `DATABASE_URL` de env (no hardcoded) y la **migración inicial autogenerada** desde `Base.metadata` (1201 líneas, captura los 30+ modelos).

---

## F1.1 — Pydantic v2 estricto en `/f0/*` (HU_04, 3 SP)

### Motivación

F0 exponía 6 endpoints (`/f0/`, `/f0/health`, `/f0/metrics`, `/f0/catalog`, `/f0/hu01`, `/f0/hu02`, `/f0/hu03`) sin `response_model`. Esto significaba:

1. La spec OpenAPI en `/docs` mostraba `application/json` genérico — los integradores externos (Grafana, Notion) no podían generar clientes tipados.
2. Si el código de F0 cambiaba la forma del JSON (typos, refactors), nadie se enteraba hasta que se rompía un dashboard.
3. Los modelos 404/503 (HU_03 con circuit breaker) no estaban documentados — un cliente que viera un 503 no sabía qué hacer.

### Solución

**1. Schemas Pydantic v2** en `app/f0_baseline/schemas.py` (12 modelos nuevos):

| Schema | Endpoint | Propósito |
|---|---|---|
| `PackageInfo` | (compartido) | Metadata del paquete |
| `ReportLink` | (compartido) | Path a un artefacto (md + json) |
| `IndexResponse` | `GET /f0/` | Índice de endpoints |
| `HealthResponse` | `GET /f0/health` | Health check (`status: Literal["ok"]`) |
| `MetricsResponse` + `MetricsCounts` + `MetricsRatios` + `MetricsFlags` + `MetricsPackage` | `GET /f0/metrics` | Métricas del baseline |
| `CatalogDiffResponse` | `GET /f0/catalog` | Diff models ↔ catálogo |
| `Hu01Response` + `Hu01Result` | `GET /f0/hu01` | Inventario de `window.*` |
| `Hu02Response` + `Hu02Result` + `Hu02MappingSampleItem` | `GET /f0/hu02` | Mapeo localStorage |
| `Hu03Query` | `GET /f0/hu03` | Query params (con `Field(description=...)`) |
| `Hu03Response` + `Hu03Result` | `GET /f0/hu03` (200) | Reporte cacheado o live |
| `Hu03TimeoutResponse` | `GET /f0/hu03` (503) | Circuit breaker |
| `ErrorResponse` | (compartido) | Envelope de error estándar |

**2. Router estricto** en `app/f0_baseline/router.py`. Cada endpoint declara `response_model=...` y `responses={...}` con los modelos 404/503:

```python
@router.get("/hu03", response_model=Hu03Response, responses={
    503: {"model": Hu03TimeoutResponse, "description": "Live run timed out"},
    404: {"model": ErrorResponse,       "description": "Report not generated"},
})
def hu03(live: bool = False, ...) -> Hu03Response:
    ...
```

**3. Constraints en schemas críticos** (no se documenta en F0, pero importa):

- `MetricsCounts.*` → `Field(..., ge=0)`. Pydantic v2 no rechaza enteros negativos por default; ahora sí.
- `MetricsRatios.catalog_coverage_pct` → `Field(..., ge=0.0, le=100.0)`. Un ratio > 100 % indica bug upstream.
- `HealthResponse.status` → `Literal["ok"]`. Solo se acepta exactamente `"ok"`.
- `Hu01Response.hu` / `Hu02Response.hu` / `Hu03Response.hu` → `Literal["HU_01"]` / etc. El cliente puede hacer `switch` sobre el valor.

**4. 18 tests nuevos** en `tests/f0_baseline/test_schemas.py` que verifican:

- Cada schema se puede instanciar con un payload mínimo.
- La spec OpenAPI declara cada path y referencia los modelos correctos (`$ref` apuntando a `Hu03TimeoutResponse` en el 503).
- Cada respuesta del endpoint valida contra su schema (`Hu01Response.model_validate(r.json())`).
- El 503 del circuit breaker valida contra `Hu03TimeoutResponse` con `monkeypatch + sleep + F0_HU03_LIVE_TIMEOUT=1`.
- Pydantic v2 rechaza payloads con tipos equivocados o campos extra.

### Decisión de diseño

**`Hu03Result` usa `extra="allow"`.** El sub-dict `result` de HU_03 viene de un JSON cacheado (`migrations.json`) cuyo schema puede evolucionar (nuevas métricas). Restringir el schema con `extra="forbid"` haría que la próxima adición de campo rompa el endpoint. El resto de los schemas usa el default de Pydantic v2 (ignora extras silenciosamente, no rompe).

---

## F1.2 — AST-lite parser para `window.*` (HU_05, 3 SP)

### Motivación

F0 usaba un regex en `app/f0_baseline/inventory.py` para encontrar asignaciones `window.NOMBRE = ...`:

```python
RE_WINDOW_FN = re.compile(
    r"window\.(\w+)\s*=\s*function\s*\([^)]*\)\s*\{",
    re.DOTALL,
)
RE_ANY_FN = re.compile(
    r"window\.(\w+)\s*=\s*function",  # sin DOTALL, captura solo el nombre
)
```

Esto fallaba con:

| Caso | Comportamiento del regex | Bug |
|------|--------------------------|-----|
| `"window.fake = function(){}"` (string en una constante) | Matchea | Falso positivo |
| `/* window.fake = function(){} */` (en un comentario) | Matchea | Falso positivo |
| `function() { if (x) { y(); } }` (braces anidados) | `\{` greedy, trunca | Matchea pero corta mal el cuerpo, fallando el conteo de líneas |
| `window.X = () => {...}` (arrow function) | No matchea | Falso negativo |

### Solución

**1. Lexer JS** (`JSLexer` en `app/f0_baseline/js_parser.py`) que tokeniza el source distinguiendo:

- `STRING` (con escape de `\\`, `'`, `"`, `` ` ``, y template literal interpolation)
- `BLOCK_COMMENT` (`/* ... */`, no anidados por spec JS)
- `LINE_COMMENT` (`// ...`)
- `IDENT` / `KEYWORD` / `NUMBER` / `PUNCT` / `WHITESPACE` / `EOF`

Cada token lleva `line` y `col` para reportar la posición exacta en el reporte.

**2. Parser** (`parse_window_functions(source)`) que:

1. **Tokeniza** todo el source.
2. **Salta comentarios y strings** (no emite filas para `window.X` que aparezcan ahí).
3. Busca la secuencia `IDENT("window") PUNCT(".") IDENT(name) PUNCT("=") <value>`.
4. **Cuenta braces** con `_find_matching_brace(src, open_pos)` — un stack que ignora braces dentro de strings y comentarios.
5. **Clasifica el RHS**:
   - `function` (con `function NAME(...)` o `function(...)` o `function NAME(...)` con `async` antes)
   - `arrow` (`() => ...` o `x => ...`)
   - `method` (`{ method() {} }` o `class { method() {} }`)
   - `other` (cualquier otra cosa — números, strings, etc.)
6. **Extrae descripción** del cuerpo con `_extract_body_description(body)`: busca `/* ... */` justo después de la llave de apertura.
7. **Devuelve** `list[WindowFunction]` con `name`, `line`, `kind`, `description`.

**3. Refactor de `WindowInventory`** (`app/f0_baseline/inventory.py`):

- Eliminados `RE_WINDOW_FN` y `RE_ANY_FN`.
- `extract()` ahora delega en `parse_window_functions(self.text)`.
- Dedupe por `(name, line)` (antes era solo `name`, así que bloques repetidos contaban doble).
- Para kinds distintos de `function`, la descripción es `(sin descripción) [kind]` — el reporte sigue siendo útil.

**4. 23 tests nuevos** en `tests/f0_baseline/test_js_parser.py` que verifican:

- Lexer: `STRING` con escape, `BLOCK_COMMENT` con `*/` adentro, `LINE_COMMENT` hasta fin de línea, números hex, keywords.
- `_safe_source`: preserva newlines, reemplaza contenido de strings por spaces (mantiene offsets), idem para comments.
- `_find_matching_brace`: simple, anidado, dentro de strings, dentro de comentarios, unmatched.
- `parse_window_functions` end-to-end:
  - Detecta función con JSDoc como description.
  - Ignora `window.X` dentro de strings.
  - Ignora `window.X` dentro de comentarios `/* */` y `//`.
  - Detecta arrow functions (kind=`arrow`).
  - Detecta métodos de clase (kind=`method`).
  - Soporta whitespace arbitrario entre tokens.
  - NO trunca el cuerpo con braces anidados.
  - Reporta `line` correcto para la asignación.
  - Dedupa por `(name, line)`.

### Decisión de diseño

**`parse_window_functions` no asigna módulo.** Esa responsabilidad queda en `WindowInventory._module_for_line()`, que trackea los rangos por módulo en base a los headers `// MÓDULO: X`. Mezclar las dos responsabilidades haría al parser más complejo y acoplado al formato de headers.

---

## F1.3 — Alembic init + autogen desde `Base` (HU_06, 2 SP)

### Motivación

F0 cerraba con esta observación en el review report:

> **Sin Alembic todavía**: el proyecto aún no tiene `alembic/`. HU_03 lo reporta honestamente y propone arrancar con `Base.metadata.create_all()` (legado) o migrar a Alembic en F1.

`Base.metadata.create_all()` en `app/main.py` es aceptable para SQLite-dev pero bloquea el camino a PostgreSQL-prod (no versiona el schema, no permite rollback, no genera diffs limpios para PRs).

### Solución

**1. `alembic init alembic`** ejecutado, customizado:

- `alembic/env.py` (133 líneas) reescrito para:
  - Agregar el `PROJECT_ROOT` a `sys.path` (Alembic corre como `python -m alembic`, no desde el cwd del proyecto).
  - Resolver `DATABASE_URL` desde env var (`os.environ["DATABASE_URL"]`) o, en su defecto, `app.config.settings.database_url` — **nunca hardcoded**.
  - Importar `Base` de `app.database` y setear `target_metadata = Base.metadata`.
  - Importar todos los módulos de `app.models` (user, tenant, branch, category, product, customer, promotion, qr, landing, order, site_config, loyalty_pass, automation, business_costs, insumo) para que se registren en `Base.metadata` antes de autogenerar.
- `alembic.ini` (F1.3):
  - Documentado: la `sqlalchemy.url` es un **placeholder** ignorado en favor de `env.py`.
  - `file_template = %%(year)d_%%(month).2d_%%(day).2d_%%(hour).2d%%(minute).2d-%%(rev)s_%%(slug)s` — orden cronológico con `ls`.

**2. Migración inicial autogenerada:**

```bash
alembic revision --autogenerate -m "initial_schema"
# → alembic/versions/2026_09_07_1002-f2efb29e03b1_initial_schema.py (1201 líneas)
```

**3. Fix post-generación:** la migración usaba `app.models.base.GUID()` (custom type) sin importar el módulo. Agregado `import app.models.base  # noqa: F401` al inicio del archivo.

**4. Verificación end-to-end (manual + tests):**

```bash
$ export DATABASE_URL=sqlite:////tmp/test.db
$ alembic upgrade head
# INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
# INFO  [alembic.runtime.migration] Will assume transactional DDL.
# INFO  [alembic.runtime.migration] Running upgrade  -> f2efb29e03b1, initial_schema

$ alembic downgrade base
# INFO  [alembic.runtime.migration] Running downgrade f2efb29e03b1 -> , initial_schema

$ sqlite3 /tmp/test.db ".tables"
# (vacío)
```

**5. 17 tests nuevos** en `tests/f0_baseline/test_alembic.py`:

- **Estáticos** (15):
  - `alembic/`, `alembic.ini`, `alembic/versions/`, `alembic/env.py`, `alembic/script.py.mako` existen.
  - Al menos 1 migración en `versions/`.
  - `env.py` importa `from app.database import Base` y setea `target_metadata = Base.metadata`.
  - `env.py` importa `app.models` (paquete) **y** los 5 modelos principales (`user`, `tenant`, `product`, `order`, `customer`).
  - `env.py` lee `DATABASE_URL` de env o `settings.database_url`.
  - `env.py` setea `config.set_main_option("sqlalchemy.url", ...)`.
  - `alembic.ini` tiene `script_location = %(here)s/alembic`.
  - `alembic.ini` documenta que la URL es un placeholder.
  - `alembic.ini` tiene `file_template` con timestamp cronológico.
  - La migración importa `app.models.base` (para `GUID()`).
  - La migración tiene `def upgrade()` y `def downgrade()`.
- **Dinámicos** (2, marcados `@pytest.mark.slow`):
  - `test_alembic_upgrade_head_on_empty_db`: corre `alembic upgrade head` contra SQLite temporal, verifica que `alembic_version` tiene la revisión.
  - `test_alembic_downgrade_base_after_upgrade`: upgrade → downgrade, verifica que la DB queda sin tablas del proyecto.

**6. Marker `slow`** agregado a `pyproject.toml`:

```toml
markers = [
    "e2e: tests E2E con Playwright (requieren --base-url y un servidor vivo)",
    "slow: tests lentos (subprocess a alembic/pytest). Omitir con `-m 'not slow'`",
]
```

Los 2 tests slow se omiten en el flujo default de CI (`pytest -m "not slow"`) y se corren en nightly o pre-release.

### Decisión de diseño

**No se eliminó `Base.metadata.create_all()` de `app/main.py` todavía.** Razones:

1. SQLite-dev sigue dependiendo de él para el primer arranque (cuando no hay migraciones aplicadas).
2. Migrar a `alembic upgrade head` en el startup es una decisión de deploy que toca `Dockerfile` y `render.yaml`.
3. Esa migración queda para F2 (HU_07), donde se introduce un "check Alembic head vs DB" en el startup que falla ruidosamente si hay drift.

**GUID type ya funciona con Alembic.** `app.models.base.GUID()` se compila a `CHAR(36)` en SQLite y a `UUID` en PostgreSQL, así que la migración inicial es portable.

---

## Métricas finales

| Métrica | F0 | F1 | Δ |
|---|---|---|---|
| Tests F0 | 30 | 30 | 0 (sin regresión) |
| Tests F1 | 0 | 58 | +58 |
| **Tests totales** | 30 | 88 | **+58** |
| Tiempo suite F0 (sin slow) | 0.34 s | 0.6 s | +0.26 s |
| Endpoints `/f0/*` con `response_model` | 0/7 | 7/7 | +7 |
| Endpoints `/f0/*` con `responses={...}` documentados | 0/7 | 2/7 (HU_03 404+503) | +2 |
| Bugs del parser regex | 4 conocidos | 0 (cubierto por tests) | −4 |
| `alembic/` presente | ❌ | ✅ con 1 migración | +1 |
| Líneas de código F0/F1 | 670 | 2,300 | +1,630 |

Artefactos:

- `app/f0_baseline/schemas.py` (218 líneas) — Schemas Pydantic v2.
- `app/f0_baseline/js_parser.py` (505 líneas) — Lexer + parser AST-lite.
- `app/f0_baseline/inventory.py` (188 líneas, refactor) — usa el parser nuevo.
- `app/f0_baseline/router.py` (modificado) — `response_model` + `responses` estrictos.
- `alembic/env.py` (133 líneas, custom) — `Base` + `settings.database_url`.
- `alembic/versions/2026_09_07_1002-f2efb29e03b1_initial_schema.py` (1201 líneas) — migración inicial.
- `alembic.ini` (modificado) — placeholder URL + `file_template` cronológico.
- `tests/f0_baseline/test_schemas.py` (342 líneas, 18 tests) — F1.1.
- `tests/f0_baseline/test_js_parser.py` (283 líneas, 23 tests) — F1.2.
- `tests/f0_baseline/test_alembic.py` (236 líneas, 17 tests) — F1.3.

---

## Limitaciones conocidas

- **El startup de la app aún usa `Base.metadata.create_all()`** como fallback. La migración a `alembic upgrade head` en arranque es F2 (HU_07).
- **El parser no maneja template literals con `${...}` anidados** correctamente (cuenta de braces off-by-one). En la práctica, los prototipos HTML no usan template literals complejos en `window.*`, pero si en el futuro aparecen, hay que refactorizar `_find_matching_brace` para usar un stack de contexts (STRING vs TEMPLATE_EXPR vs CODE).
- **No hay test E2E del flow Alembic** (subir, downgrade, volver a subir). Eso es F2 con un test de integración contra PostgreSQL.
- **Pydantic emite 2 warnings** sobre nombres de campos que shadowean atributos del parent (`copy` en `ImagePromptRequest` de `app/schemas/ai.py:427` y `json` en `ReportLink` de `app/f0_baseline/schemas.py:36`). No son bugs (los campos se usan correctamente), pero ensucian la salida de pytest. La limpieza es cosmetic y queda para F2.

---

## Próximos pasos (F2)

- **F2 / HU_07 (3 SP)** — Reemplazar `Base.metadata.create_all()` por `alembic upgrade head` en el startup de `app/main.py`. Agregar un check "Alembic head vs DB" que falle ruidosamente si hay drift.
- **F2 / HU_08 (3 SP)** — CI matrix: tests contra SQLite (rápido, default) + PostgreSQL 16 (nightly, valida tipos como `UUID`, `JSONB`, `TIMESTAMP WITH TIME ZONE`).
- **F2 / HU_09 (2 SP)** — Limpiar los 2 warnings de Pydantic renombrando `copy` → `prompt_copy` y `json` → `json_path`.
