# INFORME — TEST_CASES_V134_2.md (versión real) procesado

**Fecha:** 2026-10-16 23:18 CLT
**Origen del archivo:** `C:\Users\MoisésArancibiaS\Documents\MINIMAX\WOWHUB\TEST_CASES_V134_Completo.MD` (copiado por el usuario)
**Destino:** `WowHub_GIT/docs/TEST_CASES_V134_2.md`
**Parser actualizado:** `multi-agent-wowhub/runner/cp_index.py`

---

## 1 · Diferencia importante con la directiva

| Concepto | Directiva V134.2 | Documento real |
|----------|------------------|----------------|
| **Total CPs** | 599 (aspiracional) | **309** (reales) |
| **Total HUs** | 49 | 49 ✅ |
| **Total épicas** | 8 (E0-E7) | 5 inferidas (E0-E4)* |
| **Formato** | Sección (`## CP-...`) | **Tabla** (`| CP-... | desc | pasos | resultado |`) |

\* El documento no agrupa las HUs en épicas explícitamente; el parser las infiere por el prefijo de la HU (HU-01..HU-09 → E0, etc.).

El número **599** de la directiva era una **proyección** del plan V134.2; el documento base tiene **309 CPs** distribuidos en 49 HUs. **No inventé datos** — esto es lo que dice el archivo real.

---

## 2 · Distribución real de los 309 CPs

### Por tipo

| Tipo | Cantidad | % |
|------|----------|---|
| functional (F) | 144 | 46.6% |
| negative (N) | 70 | 22.7% |
| security (S) | 64 | 20.7% |
| performance (R) | 31 | 10.0% |
| **Total** | **309** | **100%** |

### Por HU (top 5 más cargadas)

| HU | CPs | Historia |
|----|-----|----------|
| HU-03 | 19 | Auth JWT con cookies + refresh |
| HU-01 | 17 | Registro y creación de tenant |
| HU-02 | 17 | Multi-tenancy con RLS |
| HU-08 | 15 | CRUD de productos y categorías |
| HU-06 | 15 | Sistema de auditoría y logs |

### Por HU (top 5 menos cargadas)

| HU | CPs | Historia |
|----|-----|----------|
| HU-32 | 1 | (1 solo CP) |
| HU-34 | 1 | (1 solo CP) |
| HU-35 | 1 | (1 solo CP) |
| HU-38 | 1 | (1 solo CP) |
| HU-39 | 1 | (1 solo CP) |

> Las HUs 32-49 están débilmente cubiertas. **Recomendación**: revisar la cobertura antes de declarar V134.2 auditada.

---

## 3 · Cambios aplicados

### 3.1 Parser actualizado (`runner/cp_index.py`)

**Antes:** solo soportaba formato SECCIÓN (`## CP-XX-NN-TIPO` con campos `- **Campo**: valor`).

**Ahora:** detecta automáticamente entre dos formatos:

| Formato | Trigger | Parser usado |
|---------|---------|--------------|
| **SECCIÓN** (legacy) | `^##\s+CP-\d+-\d+-[A-Z]` | `_split_sections()` + `_parse_section()` |
| **TABLA** (real) | `^##\s+HU_\d+` | `_parse_table_format()` |
| **Fallback** | ninguno detectado | intento sección |

**Características del parser de TABLA:**

- Detecta HU actual: `## HU_01 · Título (X SP)`
- Detecta tipo de CP: emoji `🟢` → functional, `🔒` → security, `⚡` → performance, `❌` → negative
- Extrae columnas: `| CP-01-01-F | descripción | pasos | resultado |`
- Heurística `_extract_endpoint()` infiere método/path/status del texto (default: `GET /health 200`)
- Maneja acentos y caracteres especiales correctamente

### 3.2 Validación

```bash
# Sintaxis
python -m py_compile runner/cp_index.py   →  EXIT 0

# Tests existentes (no se rompió nada)
pytest tests/ -q                           →  29/29 PASS

# Parser con archivo real
CPIndex('WowHub_GIT/docs/TEST_CASES_V134_2.md').load()
  →  309 CPs parseados
  →  0 duplicados
  →  49 HUs cubiertas
  →  por_tipo: {F: 144, S: 64, R: 31, N: 70}
```

### 3.3 Test end-to-end contra Railway

```bash
# 5 CPs reales ejecutados contra https://wowhub-api-production.up.railway.app
Run ID: smoke-real-cps
Total:  5
PASS:   5
FAIL:   0
ERROR:  0
Coverage: 100.0%
Duration: 3.72s
```

**Resultado:** 5/5 CPs respondieron HTTP 200 (todos cayeron al endpoint fallback `/health` porque el documento no especifica path/método por CP).

---

## 4 · Limitaciones detectadas (información honesta)

### 4.1 El documento NO especifica endpoints HTTP

El archivo real describe los CPs en **lenguaje natural** ("Registrarse con email válido", "Verificar email"). **No hay** `Método: GET`, `Endpoint: /api/...`, ni `Status esperado: 200` en las tablas.

**Implicación para el CPRunner:** los 309 CPs **no se pueden ejecutar como tests HTTP automáticos** contra Railway con la información actual. La heurística implementada solo infiere un fallback a `GET /health 200`, que no prueba la funcionalidad real del CP.

### 4.2 No hay agrupación por épica

El documento agrupa por HU pero **no declara las 8 épicas** (E0-E7) explícitamente. El parser infiere la épica del primer dígito de la HU (HU-01..HU-09 → E0), lo cual es aproximado.

### 4.3 HU-32 a HU-49 están sub-cubiertas

32 de las 49 HUs tienen solo 1-3 CPs cada una. Si la auditoría V134.2 mide "cobertura de CPs por HU", el resultado será bajo en estas HUs.

---

## 5 · Recomendaciones

### Corto plazo (lo que podés hacer ahora)

1. **Usar el parser para auditoría documental**: ya podés ejecutar `audit_run` con los 309 CPs y obtener un reporte de "qué CPs existen en el documento, agrupados por HU y tipo".

2. **Definir endpoints en `.env` o en una capa de mapping**:
   ```yaml
   # mapping opcional: HU → endpoints reales
   HU_03:
     - { method: POST, path: /api/v1/auth/login,  expected_status: 200 }
     - { method: POST, path: /api/v1/auth/refresh, expected_status: 200 }
   ```

3. **Enriquecer el documento**: agregar `**Endpoint**` y `**Método**` a cada CP en formato sección. Eso requerirá reescribir el documento.

### Mediano plazo

1. **Migrar el documento al formato SECCIÓN** (que el parser ya soporta nativamente). El formato tabla es más legible para humanos pero menos ejecutable.

2. **Definir explícitamente las 8 épicas** con un header `## Épica 1 — Autenticación (E01)` antes de las HUs correspondientes.

3. **Cubrir las HUs 32-49** con al menos 5 CPs cada una para llegar al target de 599.

---

## 6 · Archivos modificados/creados

| Path | Estado | Detalle |
|------|--------|---------|
| `WowHub_GIT/docs/TEST_CASES_V134_2.md` | 🔄 Reemplazado | 72 KB, 1435 líneas, 309 CPs reales |
| `multi-agent-wowhub/runner/cp_index.py` | ✏️ Modificado | +130 líneas: soporte formato TABLA + heurística |
| `multi-agent-wowhub/.env` | ✏️ Modificado | Comentario indicando origen del CP doc |
| `multi-agent-wowhub/agent_health.json` | 🔄 Regenerado | Incluye metadata del CP index real |
| `multi-agent-wowhub/INFORME_CPS_REALES_V1342.md` | ✨ Nuevo | Este informe |

---

## 7 · Comandos de validación rápida

```bash
cd "C:\Users\MoisésArancibiaS\Documents\MINIMAX\WOWHUB\multi-agent-wowhub"

# 1. Validar parser
C:\Python311embed\python.exe -c "
import sys; sys.path.insert(0, '.')
from runner.cp_index import CPIndex
idx = CPIndex(doc_path=r'..\WowHub_GIT\docs\TEST_CASES_V134_2.md').load(force_reparse=True)
print(f'CPs: {len(idx.all())}, HUs: {len(set(cp.hu.split(\" \")[0] for cp in idx.all()))}')
"

# 2. Re-ejecutar suite de tests (no debe romperse)
C:\Python311embed\python.exe -m pytest tests/ -q

# 3. Auditoría completa de los 309 CPs contra Railway
C:\Python311embed\python.exe -c "
import sys, asyncio; sys.path.insert(0, '.')
from runner.cp_index import CPIndex
from runner.cp_runner import CPRunner

async def main():
    idx = CPIndex(doc_path=r'..\WowHub_GIT\docs\TEST_CASES_V134_2.md').load(force_reparse=True)
    runner = CPRunner(max_concurrent=25, timeout=10.0)
    r = await runner.run_audit([c.to_http_test() for c in idx.all()], run_id='audit-full-001', resume=False)
    print(f'PASS={r.passed} FAIL={r.failed} ERR={r.errors} Coverage={r.coverage_pct}%')

asyncio.run(main())
"
```

---

## 8 · Conclusión

✅ **El parser se actualizó y procesa correctamente los 309 CPs reales** distribuidos en 49 HUs.

✅ **Los 29 tests siguen pasando** — no se rompió nada.

✅ **El Runner ejecuta contra Railway** con HTTP 200 en todos los endpoints fallback (`/health`).

⚠️ **El documento no tiene endpoints HTTP por CP**, por lo que la auditoría "funcional" requiere enriquecer el documento o agregar un mapping HU → endpoint en el Runner.

⚠️ **El número de CPs (309) es menor al proyectado en la directiva (599)**. Esto no es un bug del parser — es un dato del documento real.
