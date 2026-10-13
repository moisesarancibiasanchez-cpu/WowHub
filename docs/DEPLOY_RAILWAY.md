# ============================================================================
# GUÍA DE DESPLIEGUE — WowHub en Railway
# ============================================================================
# Fecha: 2026-09-27
# Motivo: la API en https://wowhub-api-production.up.railway.app/ devolvía
#         HTTP 502 en 8/8 endpoints (`x-railway-fallback: true` = deploy caído).
# ============================================================================

## 1. Causa probable del 502

El repositorio NO tenía manifiesto de despliegue para Railway (sólo
`render.yaml`, y el `Dockerfile` decía "para Render"). Sin manifiesto, el
proyecto Railway no tenía forma de saber qué builder usar ni qué comando de
arranque ejecutar, lo que hace fallar el deploy de forma opaca.

Además, aunque hubiera compilado, el contenedor habría arrancado con el
esquema de base de datos roto, porque:

- El `Dockerfile` NO instalaba `alembic` (la lista de `pip install` estaba
  hardcodeada y lo omitía).
- El `Dockerfile` NO copiaba `alembic/` ni `alembic.ini` a la imagen.
- `entrypoint.sh` hacía `alembic upgrade head 2>/dev/null || echo "…create_all"`,
  que se tragaba el error y caía a `create_all()`.

Todo esto está corregido en este repositorio.

## 2. Cambios de despliegue aplicados

| Archivo | Cambio |
|---------|--------|
| `railway.json` | **NUEVO** — manifiesto de despliegue (builder, startCommand, healthcheck) |
| `Dockerfile` | Instala `alembic`; copia `alembic/` + `alembic.ini`; usa `requirements.txt` como fuente única; añade `prometheus-fastapi-instrumentator` |
| `scripts/entrypoint.sh` | `alembic upgrade head` ahora es **fail-fast** (`exit 1`); seed de demo opt-in con `SEED_DEMO_DATA`; workers vía `WEB_CONCURRENCY` |
| `pyproject.toml` | Añadidas las deps que faltaban (celery, redis, sentry, otel, prometheus, boto3); `packages` incluye los subpaquetes de `app` |
| `.github/workflows/ci.yml` | `f0-smoke` usaba `/tmp/.venv/bin/python` (ruta local inexistente en CI) → ahora usa el intérprete del PATH; añadido `needs: [pytest]` |

## 3. Variables de entorno OBLIGATORIAS en Railway

La aplicación **aborta el arranque** en producción si falta cualquiera de
estas (implementado en `app/config.py::_reject_placeholder_secrets_in_production`):

```bash
# Generar valores reales:
python -c "import secrets; print(secrets.token_urlsafe(48))"

APP_ENV=production
DEBUG=false
SECRET_KEY=<valor aleatorio de 48+ chars>
JWT_SECRET=<valor aleatorio de 48+ chars>
WEBHOOK_SECRET=<valor aleatorio de 48+ chars>
STORAGE_PUBLIC=false          # obligatorio: /storage público expone archivos de todos los tenants
```

Opcionales pero recomendadas:

```bash
DATABASE_URL=postgresql://...            # Railway lo inyecta si vinculás el plugin Postgres
SEED_DEMO_DATA=false                     # nunca true en producción
PUBLIC_BASE_URL=https://wowhub-api-production.up.railway.app
OTEL_EXPORTER_OTLP_ENDPOINT=             # sin esto las trazas se descartan
OTEL_SERVICE_NAME=wowhub-api
SENTRY_DSN=                              # sin esto no hay tracking de errores
REDIS_URL=redis://...                    # para Celery
CELERY_ENABLED=true
```

## 4. Publicar los cambios

```bash
git add -A
git commit -m "fix: restaurar Alembic en el build, fail-fast de secretos, cerrar 3 fugas cross-tenant, exponer /metrics"
git push origin main
```

Railway detecta el push y redespliega automáticamente (si el proyecto está
vinculado al repositorio). Verificá el deploy en el dashboard de Railway.

## 5. Verificar tras el deploy

```bash
# Todos deben devolver 200
curl -i https://wowhub-api-production.up.railway.app/health
curl -s https://wowhub-api-production.up.railway.app/openapi.json | head -c 200
curl -i https://wowhub-api-production.up.railway.app/metrics | head -5

# Debe devolver 403 (DDL bloqueado)
curl -i "https://wowhub-api-production.up.railway.app/f0/hu03?live=true"

# Debe devolver 401 (ya no es público)
curl -i "https://wowhub-api-production.up.railway.app/api/v1/tenants/<uuid>/search/products?q=test"
```

Si `/health` sigue dando 502, el log del deploy en Railway dirá por qué. Con
`railway.json` presente y el `startCommand` explícito, el error ahora es
diagnosticable (antes no lo era).

## 6. Checklist de seguridad aplicado

| Corrección | Verificación |
|-----------|--------------|
| Fuga cross-tenant en `search.py` (sin auth) | smoke test: 401 sin token |
| IDOR en `marketplace.py` (`X-Tenant-Id` sin validar) | `_resolve_tenant` valida `TenantMembership` |
| Fuga en `admin_ai.py` (logs de IA sin scope) | usa `_resolve_tenant_scope` |
| `default_role=OWNER` exponía config global | default ahora `STAFF`; guards consultan `TenantMembership.role` |
| `GET /f0/hu03?live=true` ejecutaba DLM sin auth | 403 en producción |
| Credenciales admin en producción | seed opt-in con `SEED_DEMO_DATA` |
| `/storage` público | `STORAGE_PUBLIC=false` obligatorio + endpoint autenticado |
| Secretos placeholder | fail-fast en producción |
| Alembic ausente del build | instalado y copiado; fail-fast |

## 7. Lo que sigue pendiente (no bloquea el deploy)

- **Stripe**: el TO-BE dice "Stripe primario" pero el código sólo tiene
  MercadoPago + mock. Es una decisión de negocio, no un bug.
- **RLS de PostgreSQL**: el aislamiento es 100% a nivel de aplicación
  (31 modelos con `TenantMixin` + filtro consistente). No hay políticas RLS.
- **Worker de Celery**: `render.yaml` no declara un servicio `worker`. Con
  `CELERY_ENABLED=false` (default) los emails se envían de forma síncrona, que
  es el comportamiento anterior. Para Cola asíncrona hay que añadir un
  servicio worker en el dashboard de Railway.
- **Rutas admin duplicadas** en `main.py` (4 guards de auth inline).
