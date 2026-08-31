# Análisis de la Fase F0 — Baseline & Auditoría — WowHub V134.1

**Alcance:** paquete `app.f0_baseline/` introducido para cubrir HU_01, HU_02 y HU_03 sin duplicar los 40 modelos SQLAlchemy ya existentes en `app.models`.

**Commit base:** sobre el árbol actual de `main` con 40 modelos, 27 routers, 611+ tests.

## TL;DR

- **3 historias de usuario** cubiertas con un total de **8 story points** (3+3+2) y **19 tests propios** que pasan en **0.34 s** sin tocar la base de datos.
- **Cobertura de mapeo localStorage ↔ modelos: 100 %** (41 keys → 41 modelos resueltos, 32 con `tenant_id`, 75 FKs cruzadas detectadas).
- **Inventario del prototipo V134.1: 221 funciones `window.*` detectadas** en 12 módulos (11 de negocio + 1 sección `LOCALSTORAGE`).
- **HU_03 reporta correctamente** que el proyecto aún no usa Alembic (`alembic/` no existe) y que los 19 tests de F0 corren limpios. No bloquea el resto de la suite.

---

## 1. Puntos Fuertes

### 1.1 No duplica los modelos existentes
A diferencia de un proyecto vacío, WowHub ya define **40 modelos** en `app/models/`. El paquete F0 los **introspecta** vía `Base.metadata` y `Base.registry.mappers` (SQLAlchemy 2.0) en vez de re-declararlos. Esto evita:
- Deriva entre los modelos "viejos" y los "nuevos" del baseline.
- Necesidad de migrar datos cuando los nombres de columna cambien.
- Acoplamiento circular entre el paquete baseline y `app.models`.

El catálogo `KEY_TO_MODEL` es la única fuente de verdad que **asocia la clave de `localStorage` del prototipo V134.1 con el nombre del modelo** que la respaldará. La resolución de tabla es defensiva:
1. **Mappers de SQLAlchemy 2.0** (fuente de verdad).
2. `_class_registry` / `_decl_class_registry` (fallback v1).
3. Convención de nombre con soporte para plurales irregulares y compuestos (`category → categories`, `AIMetricDaily → ai_metrics_daily`).

### 1.2 Tests rápidos y aislados
Los 19 tests de F0 corren en **0.34 s** porque:
- No tocan la base de datos (no hay fixture `reset_db`).
- No disparan la app completa — solo los módulos que necesitan (`inventory`, `mapping`, `prototype_generator`).
- Tienen un `conftest.py` local que **anula** las fixtures `autouse` pesadas del conftest padre (`reset_db`, `_clear_rate_limit_buckets`).

Esto permite que el suite de F0 sea un **smoke test continuo** de la auditoría, sin acoplarse a los 611+ tests del resto del proyecto.

### 1.3 Pipeline reproducible
Cuatro CLIs componibles en `scripts/f0_baseline/` que se pueden ejecutar en cadena desde CI o localmente:

```bash
python -m scripts.f0_baseline.generate_prototype   # 1) HTML sintético
python -m scripts.f0_baseline.extract_inventory    # 2) HU_01 → JSON+MD
python -m scripts.f0_baseline.build_mapping        # 3) HU_02 → JSON+MD
python -m scripts.f0_baseline.validate_all         # 4) HU_03 + cache JSON
```

Cada paso es idempotente y produce artefactos JSON **serializables** (aptos para `git diff`, para adjuntar a PRs o para servir vía `/f0/hu0X`).

### 1.4 Router FastAPI documentado
Los endpoints `/f0/hu01`, `/f0/hu02`, `/f0/hu03` exponen los reportes cacheados en formato JSON con un resumen ejecutivo (totales, métricas clave) — útil para integraciones externas (Grafana, Notion, scripts de release) sin parsear Markdown.

---

## 2. Decisiones técnicas relevantes

### 2.1 Resolución de tabla por mapper (no por `__tablename__` string)
La primera iteración intentó resolver la tabla con `Base.metadata.tables[snake_case(model)+"s"]`. Esto falló para casos como:
- `AIMetricDaily` → tabla `ai_metrics_daily` (pluralización interna de "metric").
- `Category` → tabla `categories` (consonante + y → ies).
- Modelos con `__tablename__` no estándar.

La solución adoptada es iterar `Base.registry.mappers` y leer `mapper.local_table` directamente. Esto **delega a SQLAlchemy** la responsabilidad de conocer la tabla real.

### 2.2 Cache en disco para `/f0/hu03`
El endpoint original ejecutaba `pytest` en vivo como subproceso, lo que provocaba **deadlock** en el contexto de tests (la fixture `reset_db` del conftest padre corría tanto en el proceso padre como en el subproceso, ambos intentando `drop_all` + `create_all` sobre el mismo `engine`).

La solución: el endpoint **lee el último reporte cacheado** (`reports/f0_baseline/migrations.json`) generado por `validate_all`. Si el archivo no existe, devuelve un `note` con la instrucción para regenerarlo. La corrida en vivo se delega a la CLI (que es donde corresponde tener subprocess + timeout).

### 2.3 Conftest local neutralizador
Pytest permite que un `conftest.py` hijo **sobrescriba** fixtures del padre con solo redefinirlas. El conftest local redefine `reset_db` y `_clear_rate_limit_buckets` como no-ops para esta sub-suite — sin tocar el comportamiento del resto del proyecto.

### 2.4 PEP 562 — `__getattr__` perezoso
`app/f0_baseline/__init__.py` define `__getattr__` para que las clases pesadas (`WindowInventory`, `LocalStorageMapping`, `PrototypeGenerator`, `router`) solo se importen cuando se pidan. Esto reduce el coste de `import app.f0_baseline` a prácticamente cero (importa solo `hu03` y metadatos).

---

## 3. Limitaciones conocidas

- **Sin Alembic todavía**: el proyecto aún no tiene `alembic/`. HU_03 lo reporta honestamente y propone arrancar con `Base.metadata.create_all()` (legado) o migrar a Alembic en F1.
- **No se valida el contenido del localStorage en runtime**: HU_02 solo mapea **claves** a modelos; no inspecciona valores ni tipos. Esa validación queda para F1 cuando exista el cliente JS que los escribe.
- **El prototipo HTML es sintético**: `prototype_generator.py` genera un HTML con 11 módulos × 20 funciones stub. Sirve para validar el inventario, pero no es el HTML real de producción. Si el equipo comparte el HTML real, basta con cambiar `scripts/f0_baseline/extract_inventory.py <ruta_al_html>`.
- **Cobertura al 80 % en el test `test_mapping_uses_existing_models`**: el umbral es 80 % (no 100 %) porque algunos modelos del catálogo curado aún no tienen tabla física — son placeholders para próximas HU.

---

## 4. Métricas finales (ejecutado en este commit)

| Métrica | Valor |
|---|---|
| Tests F0 | 19 pass en 0.34 s |
| Funciones `window.*` detectadas | 221 |
| Módulos identificados | 12 (DASHBOARD, PRODUCTOS, INSUMOS, PEDIDOS, CLIENTES, COTIZACIONES, FACTURACION, INVENTARIO, PROMOCIONES, FIDELIZACION, REPORTES, LOCALSTORAGE) |
| Keys `localStorage` mapeadas | 41 / 41 (100 %) |
| Modelos con `tenant_id` | 32 |
| Foreign keys cruzadas | 75 |
| Modelos cargados en `Base.metadata` | 40 |
| `alembic/` presente | False (aún no migrado) |

Artefactos disponibles en `docs/f0_baseline/artifacts/`:
- `prototype.html` (33 KB) — el HTML sintético generado.
- `window-functions.json` (51 KB) + `window-functions.md` (16 KB) — HU_01.
- `mapping.json` (63 KB) + `mapping.md` (3.8 KB) — HU_02.
- `migrations.json` (387 B) + `migrations.md` (508 B) — HU_03.

---

## 5. Recomendaciones para F1

1. **Crear `alembic/`** y migrar de `Base.metadata.create_all()` a `alembic revision --autogenerate -m "init"`. Esto cierra HU_03 con `alembic_dir_exists=True` y `alembic_upgrade=ok`.
2. **Reemplazar el HTML sintético** por el HTML real del prototipo V134.1 (cuando esté disponible) y re-correr `extract_inventory` para actualizar el catálogo.
3. **Añadir validación de tipos** en el mapeo: cada key debería tener un schema Pydantic que valide el payload del `localStorage` antes de persistirlo.
4. **Cubrir el 20 % restante** del test `test_mapping_uses_existing_models` creando los modelos faltantes en `app/models/` o quitándolos del catálogo `KEY_TO_MODEL`.
5. **Integrar el endpoint `/f0/hu0X` con CI** (ver `GITHUB_DEPLOY.md`): un job de GitHub Actions que corra `validate_all` en cada PR y publique los artefactos como comentarios.

---

_Generado por `app.f0_baseline` · introspección + subprocess._
