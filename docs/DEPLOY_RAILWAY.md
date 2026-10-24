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

## 7. Almacenamiento persistente (volumen de Railway) — OBLIGATORIO desde V2.014

### 7.0 Por qué

El filesystem de un contenedor de Railway es **efímero**: cada despliegue
reconstruye el contenedor y borra lo que estuviera escrito dentro. Como la
app guarda las imágenes subidas en `/app/storage` (dentro del contenedor),
**cada deploy perdía las imágenes de todos los tenants**.

Comprobado en producción el 2026-10-24: los 12 uploads del tenant de
prueba seguían registrados en la base de datos (`uploads`) pero **ninguno
tenía archivo en disco** → la landing, el catálogo y las campañas se
quedaban sin imágenes.

Esto NO se arregla con código: es configuración de infraestructura. El
código sí quedó preparado (FIX V2.015) para que el volumen sea usable y
para que se pueda diagnosticar.

### 7.1 Paso 1 — Crear el volumen (en el panel de Railway)

1. Entrá a <https://railway.app> → proyecto **WowHub** → servicio **de la
   API** (el que compila el `Dockerfile`, no el de Postgres ni el worker).
2. Pestaña **Volumes**.
3. **Add Volume** / "+ New Volume".
4. **Mount Path**: `/app/storage`
   (exactamente así: el `WORKDIR` de la imagen es `/app` y `STORAGE_PATH`
   por defecto es `./storage` → `/app/storage`).
5. Nombre sugerido: `wowhub-storage`. Pulsá **Add Volume**.

Notas:
- Un volumen se puede montar en **un solo servicio**: montalo en el de la
  API (que es quien sube y sirve los archivos).
- **No se declara en `railway.json`**: el esquema oficial de Railway
  (<https://railway.app/railway.schema.json>) no admite `volumeMounts`
  (sólo `requiredMountPath`). El volumen se gestiona desde el panel.
- Railway cobra por GB de volumen ocupado.

### 7.2 Paso 2 — Permisos (el paso que casi todos se saltan)

Railway monta el volumen con el usuario `root`. La imagen de WowHub corre
como usuario no-root `wowhub` (`USER wowhub` en el `Dockerfile`), así que
**sin este paso las subidas fallan con**:

```
EACCES: permission denied, mkdir '/app/storage/<tenant_id>'
```

(Es la advertencia de la propia doc de Railway: *"Docker images that run as
a non-root UID by default will have permissions issues when performing
operations within an attached volume"*.)

En este repo está resuelto por el **FIX V2.015** (scripts/entrypoint.sh):
si el contenedor arranca como root, el entrypoint le da el volumen al
usuario `wowhub` y **baja privilegios** antes de arrancar uvicorn. La app
sigue corriendo como `wowhub`; sólo el arranque es root.

Para que ese bloque se ejecute hay que poner **una variable** en el
servicio:

- Railway → servicio de la API → **Variables** → agregar:

  ```
  RAILWAY_RUN_UID=0
  ```

Sin `RAILWAY_RUN_UID=0` el contenedor arranca como `wowhub`, no puede
hacer el `chown` y las subidas siguen fallando.

### 7.3 Paso 3 — Desplegar

```bash
git add -A
git commit -m "chore(deploy): volumen persistente en /app/storage"
git push origin main
```

Railway redespliega solo. Si preferís hacerlo desde el panel:
**Deploy → Redeploy**.

### 7.4 Paso 4 — Verificar que el volumen funciona

1. **En el log del deploy** deben aparecer estas dos líneas:

   ```
   ▶ Ajustando permisos del almacenamiento (arranque como root)...
   ▶ Bajando privilegios a 'wowhub' (gosu|setpriv|su)...
   ```

   Si sale "No se encontró gosu/setpriv/su: se sigue como root", el
   contenedor quedó como root: funciona, pero la app perdió el aislamiento.
   Si NO sale la primera línea, `RAILWAY_RUN_UID=0` no llegó al servicio.

2. **Prueba funcional**: subí una imagen desde el dashboard (Productos →
   Nueva imagen) y confirmá que la previsualización aparece.

3. **La prueba que importa** (¿sobrevive a un deploy?):
   - Railway → Deploy → **Redeploy**.
   - Esperá a que el deploy termine.
   - Volvé a abrir la misma imagen en el dashboard.
   - **Si sigue viéndose, el volumen está funcionando.** Si volvió a
     desaparecer, el volumen no está montado o el Mount Path no es
     `/app/storage`.

4. **Diagnóstico desde el servicio** (opcional):

   ```bash
   railway run --service <nombre-del-servicio> python -m scripts.check_missing_uploads
   ```

   Debe listar los archivos que SÍ están en el volumen.

### 7.5 Paso 5 — Resubir las imágenes que ya se perdieron

Los archivos que no están en el volumen no se recuperan con código: hay que
volver a subirlos desde el dashboard.

Para saber cuáles:

```bash
# Desde tu máquina: sólo la base de datos (el disco de producción está
# dentro del contenedor, así que desde acá se ve todo como faltante).
DATABASE_URL=postgresql://... python -m scripts.check_missing_uploads --db-only

# Desde DENTRO del servicio (diagnóstico real del disco):
railway ssh --service <servicio>
python -m scripts.check_missing_uploads
```

El script es de **sólo lectura**: no borra ni modifica nada.

Dónde resubir:
| Dónde | Qué se pierde |
|-------|---------------|
| Productos → imagen del producto | foto del catálogo público |
| Landing → imagen del hero / logo | cabecera y hero de la landing |
| Fidelización → logo de la tarjeta | logo en la tarjeta del cliente |
| Promociones → imagen | promo de la landing |

### 7.6 Rollback

- **Quitar el volumen**: Railway → servicio → **Volumes** → *Detach* /
  *Delete*. La app vuelve a `/app/storage` efímero: **funciona**, pero las
  imágenes se vuelven a perder en cada deploy. Es el estado anterior a
  V2.014, sin cambios de código que revertir.
- **Rollback de código**: `git revert <commit-del-fix-v2.015>` + push. El
  entrypoint vuelve a arrancar sin el ajuste de permisos (y sin bajar
  privilegios); el resto de la app no cambia.

### 7.7 Checklist

| # | Paso | Verificación |
|---|------|--------------|
| 1 | Volumen creado con Mount Path `/app/storage` | Railway → Volumes → aparece montado |
| 2 | `RAILWAY_RUN_UID=0` en las variables del servicio | El log dice "Ajustando permisos…" |
| 3 | Deploy aplicado | El log dice "Bajando privilegios a 'wowhub'" |
| 4 | Subida de imagen de prueba | La previsualización se ve |
| 5 | Redeploy forzado | La imagen **sigue** viéndose |
| 6 | Imágenes perdidas resubidas | `check_missing_uploads --db-only` vs. lo que ves en el dashboard |

---

## 8. Lo que sigue pendiente (no bloquea el deploy)

- **Stripe**: el TO-BE dice "Stripe primario" pero el código sólo tiene
  MercadoPago + mock. Es una decisión de negocio, no un bug.
- **RLS de PostgreSQL**: el aislamiento es 100% a nivel de aplicación
  (31 modelos con `TenantMixin` + filtro consistente). No hay políticas RLS.
- **Worker de Celery**: `render.yaml` no declara un servicio `worker`. Con
  `CELERY_ENABLED=false` (default) los emails se envían de forma síncrona, que
  es el comportamiento anterior. Para Cola asíncrona hay que añadir un
  servicio worker en el dashboard de Railway.
- **Rutas admin duplicadas** en `main.py` (4 guards de auth inline).
