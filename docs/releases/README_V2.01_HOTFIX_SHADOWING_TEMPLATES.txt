================================================================================
  WowHub V2.01 — HOTFIX Shadowing `templates` (Jinja2Templates vs APIRouter)
  README de cambios — Changelog atómico
================================================================================

FECHA         : 2026-10-18
VERSION       : V2.01 (HOTFIX critico — worker de Railway crasheando)
ALCANCE       : 2 archivos modificados, 2 lineas de codigo + 1 export
TRAZABILIDAD  : logs de Railway muestran que el worker de uvicorn crashea
                 en el arranque con:
                   AttributeError: 'Jinja2Templates' object has no attribute 'router'
                   File "/app/app/main.py", line 257, in <module>
                     app.include_router(templates.router, prefix="/api/v1")

================================================================================
  BASE
================================================================================
El commit anterior (84da373, "V2.01 Audit General: registrar
templates.router") intento arreglar la persistencia de la eleccion de
plantilla registrando el router de api/v1/templates.py en main.py.

El commit fallo porque:
  (a) El modulo `templates` (APIRouter) se importaba con el mismo nombre
      que la variable local `templates` (Jinja2Templates) definida
      220 lineas mas abajo en main.py (linea 77):
          templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
      Esto produce shadowing: el import queda sobrescrito por la variable.

  (b) Ademas, `app/api/v1/__init__.py` NO exponia `templates` en su bloque
      de imports. La convencion del proyecto es que main.py importa
      routers via `from app.api.v1 import (auth, branches, ..., templates)`.
      Faltaba `templates` en esa lista.

Resultado en runtime:
  1) Python importa `app.api.v1.templates` (submodulo valido).
  2) En main.py linea 77 se reasigna el nombre `templates` a una
     instancia de Jinja2Templates.
  3) En main.py linea 257, `templates.router` busca `.router` en la
     instancia Jinja2Templates -> NO EXISTE -> AttributeError.
  4) uvicorn detecta el error en su proceso hijo y lo mata con
     "Child process [14] died".
  5) Loop infinito: el supervisor de uvicorn reintenta arrancar el
     proceso, falla igual, lo mata, reintenta...

El bug paso inadvertido en local porque los 29 tests pytest NO
ejercen el arranque de uvicorn (solo testean parsers + agentes).
Railway lo detecto al deployar.

================================================================================
  CAMBIO UNICO
================================================================================

1) SHADOWING FIX — renombrar el import del modulo API
   Archivo MODIFICADO: app/main.py (linea 57)

   ANTES:
       from app.api.v1 import (
           ...
           admin_observability,  # HU_07
           templates,             # V2.01 — Plantillas estéticas
       )

   DESPUES:
       from app.api.v1 import (
           ...
           admin_observability,  # HU_07
           templates as templates_api,  # V2.01 — Plantillas estéticas.
                                         # Se renombra para NO chocar con la
                                         # variable `templates` (Jinja2Templates)
                                         # definida mas abajo en este archivo.
       )

   Esto evita el shadowing: el modulo importado queda ligado al
   nombre `templates_api`, mientras que `templates` sigue siendo
   la instancia de Jinja2Templates usada por TemplateResponse().

2) USO CORRECTO — actualizar el include_router
   Archivo MODIFICADO: app/main.py (linea 259)

   ANTES:
       app.include_router(templates.router, prefix="/api/v1")  # V2.01

   DESPUES:
       app.include_router(templates_api.router, prefix="/api/v1")  # V2.01

   Ahora `.router` se resuelve en el modulo `app.api.v1.templates`
   (que SI tiene `.router` porque es un APIRouter FastAPI), no en
   la instancia Jinja2Templates.

3) EXPORTAR EL ROUTER — agregarlo al __init__.py del paquete
   Archivo MODIFICADO: app/api/v1/__init__.py (linea 23)

   ANTES:
       from app.api.v1 import (  # noqa: F401
           auth, branches, categories, ..., admin_observability,
       )
       # Faltaba `templates` en este listado

   DESPUES:
       from app.api.v1 import (  # noqa: F401
           auth, branches, categories, ..., admin_observability,
           templates,  # V2.01 — Selector de plantillas estéticas del dashboard
       )

   Esto asegura consistencia con la convencion del proyecto y
   explicita la dependencia del paquete. Aunque Python importa el
   submodulo via `from app.api.v1 import templates` (fallback de
   import), agregarlo al __init__.py:
     - Lo hace visible para `dir(app.api.v1)`
     - Acelera el import (no necesita buscar submodulos)
     - Cumple el mismo patron que los 39 otros routers

================================================================================
  QUE NO SE MODIFICO
================================================================================
  - app/api/v1/templates.py (NO tocado — el router ya estaba bien)
  - app/templates/dashboard/templates.html (NO tocado)
  - app/templates/base.html y dashboard/base.html (NO tocados)
  - app/static/js/template-selector.js (NO tocado — sigue llamando
    a `/api/v1/tenants/{id}/template` con el metodo correcto)
  - Cualquier CSS (dashboard.css, wowprint.css) — sin cambios
  - Los 29 tests pytest — sin cambios, siguen pasando
  - Los otros 38 routers del proyecto — sin cambios
  - La variable local `templates` (Jinja2Templates) — preservada tal
    cual para no romper los 31 usos de `templates.TemplateResponse(...)`
    en main.py
  - Ningun endpoint, schema, modelo Alembic, variable de config

================================================================================
  REQUERIMIENTOS DE DESPLIEGUE
================================================================================
  Worker: SI requiere reinicio.
    - app/main.py MODIFICADO (import + include_router).
    - app/api/v1/__init__.py MODIFICADO (1 export agregado).
    - uvicorn debe reimportar app.main para cargar el fix.
    - CRITICO: este fix es para que el worker ARRANQUE. Sin este
      deploy, el sitio no responde (500 o connection refused).

  Migraciones DB: NO requiere.
    - Cero cambios de schema. Cero ALTER TABLE. Cero Alembic.

  Config / env vars: NO requiere.

  Caches / CDN: NO requiere purga.

  Hard refresh en navegador: NO obligatorio (cambio solo en backend).

  IMPORTANTE — Verificacion post-deploy:
    1) Railway debe mostrar el worker arrancando sin errores.
    2) curl https://wowhub-api-production.up.railway.app/api/v1/status
       debe devolver 200 (antes daba 502 por el crash).
    3) /dashboard/templates debe cargar sin 500.

================================================================================
  PROCEDIMIENTO DE PRUEBA RECOMENDADO
================================================================================
A) Verificar que el worker arranca (sin logs de uvicorn)

   # Local:
   cd /path/to/wowhub
   uvicorn app.main:app --port 8000 --reload
   # Esperado: "Application startup complete" sin tracebacks.
   # Antes: "AttributeError: 'Jinja2Templates' object has no attribute 'router'"

   # En el archivo de log:
   # grep -i "AttributeError\|Child process" logs/*.log
   # Esperado: 0 matches.

B) Verificar que el router esta correctamente montado

   # Inspeccion directa via Python:
   python -c "
   import sys; sys.path.insert(0, '.')
   from app.main import app
   rutas_template = [r for r in app.routes if hasattr(r, 'path') and '/template' in r.path]
   for r in rutas_template: print(r.methods, r.path)
   "
   # Esperado:
   # {'GET', 'HEAD'} /api/v1/tenants/{tenant_id}/template
   # {'PUT', 'HEAD'} /api/v1/tenants/{tenant_id}/template

C) Smoke test del endpoint

   # 1) Login
   TOK=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
     -H "Content-Type: application/json" \
     -d '{"email":"owner@test.com","password":"x"}' | jq -r .access_token)

   TID="<uuid-tenant>"

   # 2) GET template actual
   curl -s -i "http://localhost:8000/api/v1/tenants/$TID/template" \
     -H "Authorization: Bearer $TOK"
   # Esperado: 200 OK, body {"template":"default", ...}

   # 3) PUT template nuevo
   curl -s -i -X PUT "http://localhost:8000/api/v1/tenants/$TID/template" \
     -H "Authorization: Bearer $TOK" -H "Content-Type: application/json" \
     -d '{"template":"moderna"}'
   # Esperado: 200 OK, body {"ok":true, "template":"moderna", ...}

   # 4) Verificar que el front puede persistir
   # Login en /dashboard, ir a Apariencia, seleccionar Moderna.
   # DevTools Network: PUT /api/v1/tenants/{tid}/template debe devolver 200.

D) Regresion completa

   1. pytest multi-agent-wowhub/ -v → 29/29 debe seguir pasando.
   2. uvicorn app.main:app --port 8000 → arranca sin tracebacks.
   3. GET /api/v1/status → 200 (antes 502).
   4. GET /dashboard → 200 con sidebar Moderna.
   5. GET /dashboard/templates → 200 con 4 cards.
   6. Cambiar plantilla desde UI → verificar persistencia backend.

================================================================================
  ARCHIVOS TOCADOS (resumen)
================================================================================
  A) NUEVOS:
     + docs/releases/README_V2.01_HOTFIX_SHADOWING_TEMPLATES.txt (este archivo)

  B) MODIFICADOS:
     ~ app/main.py                                          (2 lineas:
                                                                rename import +
                                                                rename uso)
     ~ app/api/v1/__init__.py                               (+1 linea:
                                                                1 export nuevo)

  Total: +1 archivo nuevo, 2 modificados. 3 lineas netas de codigo.

================================================================================
  RIESGOS Y ROLLBACK
================================================================================
  Riesgo muy bajo.
    - El shadowing es un bug bien conocido de Python. La convencion
      es prefijar el nombre del modulo cuando choca con una variable
      local (`templates as templates_api`).
    - El export agregado a __init__.py es consistente con los 39 otros
      routers que ya siguen este patron.
    - 0 cambios funcionales: el endpoint existia, solo que ahora se
      monta correctamente.

  Rollback:
    1) Revertir este commit.
    2) NO recomendado: dejaria el worker crasheando.
    3) Si fuera absolutamente necesario volver atras: ademas del
       revert, renombrar las 2 lineas para que coincidan con el commit
       anterior (cosa que el worker vuelva a fallar).

================================================================================
  FIN DEL README — V2.01 HOTFIX Shadowing Templates
================================================================================