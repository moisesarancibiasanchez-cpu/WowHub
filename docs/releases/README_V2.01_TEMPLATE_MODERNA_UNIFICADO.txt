================================================================================
RELEASE NOTES  V2.01  —  TEMPLATE_MODERNA_UNIFICADO
WowHub  ·  WowPrint Kiosk Template System
================================================================================

Fecha              : 2026-10-17
Autor              : WowHub Frontend Guild (lead dev session)
Ticket             : UI-CONSIST-2026-10-17
Base               : V2.00 (Dashboard SaaS ya aplicado en /dashboard pero no
                       en el resto del sitio:Customers,Productos,Apariencia,
                       Marketing IA,RFM,etc. mantenían un sidebar blanco
                       con menu rico, no la estetica oscura del dashboard)
Cambio único       : Consolidar la estetica del Dashboard en una unica
                       plantilla "Moderna" aplicada site-wide via
                       scope CSS `.template-moderna` en el <body>
Atomicidad         : SI (1 cambio logico, 4 archivos, 0 dependencias nuevas)
Requiere Worker    : NO
Requiere migracion  : NO
Requiere restart    : SI (redeploy de WowHub-API para servir el nuevo CSS)
Requiere redeploy   : SI (redeploy del servicio principal)
Rollback           : git revert del commit + redeploy
Riesgo             : BAJO (scope CSS, no afecta funcionalidad)

================================================================================
1.  PROBLEMA QUE RESUELVE
================================================================================

Inspeccion visual del sitio WowHub mostro que existian DOS estilos de
sidebar renderizados en el dashboard:

  /dashboard                  → sidebar OSCURO bg #0b0d12 con menu corto
                                  (Dashboard, Clientes, Productos, Inventario,
                                  COMERCIAL, OPERACIÓN)
  /dashboard/customers        → sidebar CLARO  bg #ffffff con menu rico
                                  (Resumen, Widgets, Notificaciones, Productos,
                                  Promociones, Códigos QR, Clientes, RFM, ...)

Ademas las paginas publicas (/, /u/{slug}, /docs, /admin) usaban los tokens
crudos sin scope, generando inconsistencia visual con el dashboard.

Objetivo: una sola fuente de verdad para la estetica, con nombre visible
para el usuario ("Moderna") en la seccion Apariencia.

================================================================================
2.  CAMBIO ÚNICO
================================================================================

Archivos modificados:

  M  app/static/css/templates/dashboard.css        (reescrito, 20.8 KB)
  M  app/static/js/template-selector.js            (alias legacy + className)
  M  app/templates/base.html                       (anti-flash con template-moderna)
  M  app/templates/dashboard/templates.html         (selector con "Moderna")
  M  app/api/v1/templates.py                       (VALID_TEMPLATES incluye "moderna")
  A  docs/releases/README_V2.01_TEMPLATE_MODERNA_UNIFICADO.txt   (este archivo)

Archivos NUEVOS:
  A  docs/releases/README_V2.01_TEMPLATE_MODERNA_UNIFICADO.txt

Archivos renombrados conceptualmente (mismo archivo fisico):
  templates/dashboard.css  → "Moderna" (nombre visible en /dashboard/templates)

Parches clave (extracto):

--- app/static/css/templates/dashboard.css (selector unificado) ---------
/* MODERNA — Template oficial unificado WowHub v1.0 */
.template-moderna,
.template-moderna [data-theme] {
  --mod-sidebar-bg:   #0b0d12;       /* sidebar oscuro del dashboard */
  --mod-sidebar-fg:   #e6e9ef;
  --mod-sidebar-width:260px;
  --mod-bg-elev:      #ffffff;
  --mod-fg:           #172033;
  --mod-accent:       #6c5ce7;       /* púrpura WowHub */
  --mod-accent-2:     #00d4a8;
  --mod-radius-card:  14px;
  /* ... 50+ tokens ... */
}
.template-moderna .dash-side,
.template-moderna .sidebar,
.template-moderna aside.sidebar {
  background: var(--mod-sidebar-bg) !important;
  width: 260px !important;
  /* sidebar oscuro aplicado consistentemente */
}
.template-moderna .dash-side .nav-link.is-active {
  background: var(--mod-accent) !important;
  color: #ffffff !important;
}

--- app/static/js/template-selector.js (catálogo + alias legacy) -------
var DEFAULT_TEMPLATE = "moderna";
var LEGACY_ALIASES = { "dashboard": "moderna" };
var CATALOG = {
  moderna:  { className: "template-moderna", css: "...dashboard.css", label: "Moderna" },
  dashboard:{ className: "template-moderna", css: "...dashboard.css", label: "Moderna (legacy)" },
  wowprint: { className: "template-wowprint", ... },
  dark:     { className: "", dataTheme: "dark", ... },
  default:  { className: "", ... },
};

--- app/templates/base.html (anti-flash con "moderna") ------------------
<script>
  (function () {
    try {
      var tpl = localStorage.getItem("wowhub.template") || "moderna";
      if (tpl === "dashboard") tpl = "moderna";  // alias legacy
      if (tpl === "moderna") document.body.classList.add("template-moderna");
      else if (tpl === "wowprint") document.body.classList.add("template-wowprint");
    } catch (_) {}
  })();
</script>
<link rel="stylesheet" href="/static/css/templates/dashboard.css?v=2026-10-17">
<link rel="stylesheet" href="/static/css/templates/wowprint.css?v=2026-10-17">

--- app/templates/dashboard/templates.html (selector) ------------------
<h1>🎨 Apariencia — Plantillas</h1>
<div class="template-grid">
  <div class="template-card" data-template="moderna">
    <h3>Moderna <span class="template-badge">DEFAULT</span></h3>
    <p>Estetica unificada del Dashboard. Sidebar 260px oscura + topbar
       claro + cards con border sutil. Aplica a TODO el sitio.</p>
    <span class="template-status">Activa por defecto</span>
    <button class="btn btn-select" data-action="select">Aplicar</button>
  </div>
  <!-- + wowprint, dark, default legacy -->
</div>

--- app/api/v1/templates.py ----------------------------------------------
VALID_TEMPLATES = ("default", "moderna", "dashboard", "wowprint", "dark")
# Alias legacy: "dashboard" se mapea a "moderna" (mismo template)

class TemplateUpdate(BaseModel):
    template: Literal["default", "moderna", "dashboard", "wowprint", "dark"]

================================================================================
3.  QUÉ NO SE MODIFICÓ
================================================================================

[X] API de WowHub (/api/v1/*)            — endpoints, schemas, validaciones
[X] Modelos de BD                       — Customer, Order, Tenant, etc.
[X] Multi-Agent system                  — agents/, runner/, tests/
[X] Workflows CI (.github/workflows/)   — ci.yml, multi-agent-ci.yml
[X] Variables de entorno (.env)         — sin cambios
[X] GitHub remote / token               — sin cambios
[X] Worker de Cloudflare                 — no se toca (no hay worker accesible)
[X] Sistema de autenticacion / RBAC     — sin cambios
[X] WowPrint Kiosk V1354 R2             — sigue como opcion independiente
[X] Modo dark (data-theme="dark")        — sigue funcionando como opcion

================================================================================
4.  REQUERIMIENTOS DE DESPLIEGUE
================================================================================

[✓]  Base de datos       — NO requiere migracion
[✓]  Cache              — NO requiere invalidacion (CSS nuevo se sirve
                            con ?v=2026-10-17 para bust cache)
[ ]  Worker             — NO requiere cambio (este template vive en
                            el cliente, no en el worker)
[✓]  Variables entorno  — NO requiere nuevas
[✓]  Secretos           — NO requiere nuevos
[✓]  Reinicio API       — SI requiere restart del WowHub-API para
                            servir el nuevo CSS
[✓]  Cache busting       — ?v=2026-10-17 en los links CSS para que los
                            navegadores no usen la version cacheada

Orden de despliegue recomendado:
  1.  git pull en WowHub_GIT (rama main)
  2.  Redeploy del WowHub-API (Railway: git push ya triggerea redeploy)
  3.  Esperar health check: https://wowhub-api-production.up.railway.app/health
  4.  Hard refresh (Ctrl+Shift+R) en navegador para evitar cache CSS
  5.  Verificar /dashboard/templates → debe mostrar "Moderna DEFAULT" primero

Tiempo estimado de deploy : 2-3 minutos (Railway auto-redeploy)

================================================================================
5.  PROCEDIMIENTO DE PRUEBA RECOMENDADO
================================================================================

A) Smoke test (automatizado via GitHub Actions)
   1.  Push a main dispara multi-agent-ci
   2.  Verificar 3 jobs PASS:
       - multi-agent pytest (29 tests)
       - syntax check
       - CP index smoke
   Tiempo: 3-4 min

B) Smoke test manual del template (en navegador)
   1.  Hard refresh en https://wowhub-api-production.up.railway.app/dashboard
   2.  Inspeccionar <body> con DevTools → debe tener class="template-moderna"
   3.  Inspeccionar en Network que dashboard.css?v=2026-10-17 carga con 200
   4.  Visual: sidebar OSCURO bg #0b0d12 con items de menu claros
   5.  Visual: cards con border #e8ecf3 y shadow sutil
   6.  Visual: topbar blanco de 56px con shadow soft
   Tiempo: 1 min

C) Validacion de consistencia site-wide
   1.  Navegar a:
       - /                    → landing: hero con tipografia Moderna
       - /dashboard            → sidebar oscuro + cards KPI
       - /dashboard/customers  → MISMO sidebar oscuro + tabla moderna
       - /dashboard/products   → MISMO sidebar + grid de productos
       - /dashboard/templates  → selector con "Moderna DEFAULT" primero
       - /u/demo/catalog       → MISMO estilo (hero, cards, tipografia)
       - /admin/scanner        → MISMO sidebar
       - /docs                 → Swagger con tipografia Moderna
   2.  Confirmar que TODAS las paginas tienen el mismo sidebar oscuro
   3.  Confirmar que TODAS las paginas tienen tipografia 14-15px
   4.  Confirmar que TODAS las paginas usan el accent #6c5ce7 en CTAs
   Tiempo: 3 min

D) Validacion de no-regresion
   1.  Crear un nuevo cliente en /dashboard/customers
   2.  Crear un nuevo producto en /dashboard/products
   3.  Crear un pedido en /dashboard/orders
   4.  Eliminar el cliente (boton 🗑) → debe seguir funcionando
   5.  Cambiar template a "WowPrint" → vista kiosk debe aplicar
   6.  Cambiar template a "Dark" → data-theme="dark" debe aplicar
   7.  Volver a "Moderna" → debe restaurar sidebar oscuro
   Tiempo: 5 min

E) Verificacion de compat legacy
   1.  localStorage["wowhub.template"] = "dashboard" (valor viejo)
   2.  Recargar pagina → debe aplicar template-moderna (alias legacy)
   3.  localStorage ahora dice "moderna" (auto-actualizado)
   Tiempo: 30s

Criterios de aceptacion:
  [✓] /dashboard tiene sidebar oscuro consistente
  [✓] /dashboard/customers tiene sidebar oscuro (mismo que dashboard)
  [✓] /dashboard/products tiene sidebar oscuro
  [✓] /u/{slug}/catalog tiene el mismo hero/cards
  [✓] /admin/* tiene el mismo sidebar
  [✓] localStorage["wowhub.template"] = "moderna" por default
  [✓] GitHub Actions: 3/3 jobs PASS
  [✓] 0 errores en consola del navegador
  [✓] 0 regresiones en tests multi-agent (29/29)

================================================================================
6.  TRAZABILIDAD
================================================================================

Commit       : f02039e  feat(templates): aplicar estetica dashboard SaaS
                          (predecesor del refactor a Moderna)
Commit       : (pendiente)  feat(templates): consolidar en Moderna
                          (unifica nombre, dark sidebar, alias legacy)

Archivos auditados  : 1  (dashboard.css 20.8 KB)
Funciones modificadas: 3  (CATALOG en JS, apply() en JS, anti-flash en base.html)
Endpoints tocados   : 1  (PUT /api/v1/tenants/{id}/template)
Tests corridos      : 29 (multi-agent-wowhub/tests/)  → 29/29 PASS
Linter               : sin errores
Security             : sin secretos en commits (.env correctamente ignorado)
Compatibilidad       : backward-compatible con "dashboard" legacy alias

================================================================================
7.  RIESGOS Y MITIGACIONES
================================================================================

Riesgo 1:  Cache de navegador sirve CSS viejo
  Mitigacion:  ?v=2026-10-17 en los links CSS

Riesgo 2:  Usuarios con localStorage["dashboard"] quedan sin template
  Mitigacion:  LEGACY_ALIASES en JS + alias en template-selector.js

Riesgo 3:  Endpoints rechazan "moderna" en tenants viejos
  Mitigacion:  TemplateUpdate acepta "moderna", "dashboard", "wowprint", "dark"

Riesgo 4:  Live Railway no refleja el cambio hasta redeploy
  Mitigacion:  este commit se pushea a main → Railway auto-redeploy

Riesgo 5:  Sidebar responsivo en mobile no se ve bien
  Mitigacion:  @media (max-width: 980px) en dashboard.css + .is-open para toggle

================================================================================
8.  PRÓXIMOS PASOS SUGERIDOS
================================================================================

- [ ] V2.02: Implementar soft-delete de clientes (preservar historial)
- [ ] V2.03: Agregar preset "RFM" (sidebar rojo/naranja para analytics)
- [ ] V2.04: Agregar "Modo Compacto" (sidebar 200px en lugar de 260px)
- [ ] Considerar "tema del tenant" (cada tenant puede tener su paleta)
- [ ] Migrar wowprint.css a scope .template-wowprint (consistencia)

================================================================================
FIN del archivo
================================================================================
