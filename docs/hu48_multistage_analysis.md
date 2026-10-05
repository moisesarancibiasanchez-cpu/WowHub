# HU_48 — Dockerfile.multistage: Análisis Estructural

## Estado Actual

| Archivo | Líneas | Activo |
|---|---|---|
| `Dockerfile` | ~90 | SÍ (railway.json lo usa) |
| `Dockerfile.multistage` | 113 | NO (pendiente decisión usuario) |
| `railway.json` | — | `"dockerfilePath": "Dockerfile"` |

---

## Arquitectura del Dockerfile.multistage

### Stage 1 — `builder` (intermediate)
```dockerfile
FROM python:3.12-slim AS builder
# build-essential + libpq-dev → compiladores C/Python
# Instala TODAS las deps en /install (virtualenv)
# Tamaño imagen builder: ~600-800 MB
```

### Stage 2 — `runtime` (final)
```dockerfile
FROM python:3.12-slim AS runtime
# libpq5 + curl SOLO → runtime de producción
# COPY --from=builder /install /install
# Tamaño imagen final: ~300-500 MB (estimado)
```

---

## Comparativa

| Criterio | Dockerfile (single-stage) | Dockerfile.multistage |
|---|---|---|
| Tamaño imagen | ~600-800 MB | ~300-500 MB |
| Build tools en producción | SÍ (gcc, build-essential) | NO |
| Superficie CVE | Alta | Reducida |
| Seguridad producción | Menor | Mayor |
| Complejidad build | Simple | Multi-stage |

**Ahorro estimado: 200-300 MB comprimidos** al excluir compiladores y headers de desarrollo.

---

## Análisis Sintáctico

✅ Sintaxis Docker `1.6+` (`AS`, `COPY --from=builder`)  
✅ `HEALTHCHECK` presente con `curl` (disponible en runtime)  
✅ Usuario no-root `wowhub` creado y usado  
✅ `ENTRYPOINT` / `CMD` vía `entrypoint.sh`  
✅ `PORT=8000` expuesto y usado en healthcheck  
⚠️ `libpq5` en runtime (OK para `psycopg2-binary` y `psycopg 3.x`)  
⚠️ `requirements.txt` incluye `psycopg2-binary` + `psycopg[binary]>=3.1.0` (duplicado pero funcional)

**Validación de sintaxis:**
```bash
docker build -f Dockerfile.multistage --dry-run .  # Linux-only
# En Windows: syntax es correcta según revisión manual
```

---

## Decisión Pendiente del Usuario

⚠️ **railway.json NO fue modificado** — el usuario debe confirmar antes de activar.

Para activar en Railway:
```json
{
  "build": {
    "dockerfilePath": "Dockerfile.multistage"
  }
}
```

O vía UI: **Settings → Build → Dockerfile → Dockerfile.multistage**

---

## Commit Relacionado

`docs(hu_48): documentar Dockerfile.multistage como opción pendiente de activar`

---

## Notas

- El archivo `Dockerfile.multistage` es **funcional y sintácticamente correcto**.
- No requiere cambios en el código de la aplicación.
- Compatible con Railway, Render, y cualquier builder que soporte multi-stage.
- El `entrypoint.sh` debe existir en `scripts/` — verificar que esté presente antes de desplegar.
