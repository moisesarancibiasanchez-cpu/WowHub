/* =============================================================
 * template-selector.js
 * Aplica la plantilla estética seleccionada en el dashboard de
 * WowHub y la persiste por tenant + por dispositivo.
 *
 * Catálogo de plantillas (debe coincidir con dashboard/templates.html):
 *   - default   → sin clase especial (tokens.css puro)
 *   - dashboard → .template-dashboard (SaaS WowHub - DEFAULT site-wide)
 *   - wowprint  → .template-wowprint (WowPrint V1354 R2, kiosk)
 *   - dark      → data-theme="dark" sobre default
 *
 * API:
 *   TemplateSelector.apply('wowprint')  // aplica
 *   TemplateSelector.current()          // 'wowprint' | 'default' | 'dashboard' | 'dark' | null
 *   TemplateSelector.reset()            // vuelve al default (dashboard)
 * ============================================================= */
(function () {
  "use strict";

  var STORAGE_KEY = "wowhub.template";
  var API_BASE = (typeof window !== "undefined" && window.WH_API) || "/api/v1";
  var DEFAULT_TEMPLATE = "dashboard";

  var CATALOG = {
    default:  { className: "",                 dataTheme: null,        css: null,                                         label: "WowHub Default" },
    dashboard:{ className: "template-dashboard",   dataTheme: null,    css: "/static/css/templates/dashboard.css",      label: "Dashboard SaaS" },
    wowprint: { className: "template-wowprint",    dataTheme: null,    css: "/static/css/templates/wowprint.css",       label: "WowPrint Kiosk" },
    dark:     { className: "",                 dataTheme: "dark",      css: null,                                         label: "Dark Mode" }
  };

  function ensureCssLoaded(templateId) {
    var def = CATALOG[templateId];
    if (!def || !def.css) return Promise.resolve();
    return new Promise(function (resolve) {
      var href = def.css;
      var exists = Array.prototype.some.call(
        document.querySelectorAll('link[rel="stylesheet"]'),
        function (l) { return l.href.indexOf(href) !== -1; }
      );
      if (exists) return resolve();
      var link = document.createElement("link");
      link.rel = "stylesheet";
      link.href = href;
      link.dataset.template = templateId;
      link.onload = function () { resolve(); };
      link.onerror = function () { resolve(); };
      document.head.appendChild(link);
    });
  }

  function apply(templateId) {
    var def = CATALOG[templateId];
    if (!def) {
      console.warn("[template-selector] template desconocido:", templateId);
      return;
    }
    var body = document.body;
    var html = document.documentElement;

    // Limpia clases/data-theme previos
    Object.keys(CATALOG).forEach(function (k) {
      var d = CATALOG[k];
      if (d.className) body.classList.remove(d.className);
    });
    // Limpiar data-theme si el nuevo template no es dark
    if (!def.dataTheme && html.dataset.theme) {
      html.removeAttribute("data-theme");
    }

    return ensureCssLoaded(templateId).then(function () {
      if (def.className) body.classList.add(def.className);
      if (def.dataTheme) {
        html.dataset.theme = def.dataTheme;
      }
      try { localStorage.setItem(STORAGE_KEY, templateId); } catch (e) {}
      // Persistir en backend (fire-and-forget, no bloquea la UI)
      try {
        var tenantId = (document.body.dataset.tenantId) || null;
        if (tenantId && window.fetch) {
          fetch(API_BASE + "/tenants/" + tenantId + "/template", {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ template: templateId })
          }).catch(function () { /* offline-first: la elección local sigue activa */ });
        }
      } catch (e) { /* noop */ }
    });
  }

  function current() {
    try { return localStorage.getItem(STORAGE_KEY); } catch (e) { return null; }
  }

  function reset() { return apply(DEFAULT_TEMPLATE); }

  // Auto-apply al cargar
  document.addEventListener("DOMContentLoaded", function () {
    var saved = current();
    if (saved && CATALOG[saved]) {
      apply(saved);
    } else {
      // Sin selección previa: aplicar dashboard SaaS por defecto (site-wide)
      apply(DEFAULT_TEMPLATE);
    }
    // Conectar botones [data-action="select"] dentro de tarjetas [data-template]
    document.querySelectorAll("[data-template]").forEach(function (card) {
      var id = card.dataset.template;
      var btn = card.querySelector('[data-action="select"]');
      if (!btn) return;
      btn.addEventListener("click", function (e) {
        e.preventDefault();
        apply(id).then(function () {
          // Marcar visualmente la tarjeta activa
          document.querySelectorAll("[data-template]").forEach(function (c) {
            c.classList.remove("is-active");
          });
          card.classList.add("is-active");
          // Toast feedback si existe
          var toast = document.getElementById("toast");
          if (toast) {
            toast.textContent = "✓ Plantilla '" + id + "' aplicada";
            toast.classList.add("show");
            setTimeout(function () { toast.classList.remove("show"); }, 1800);
          }
        });
      });
    });
  });

  // Exposición pública
  window.TemplateSelector = {
    apply: apply,
    current: current,
    reset: reset,
    catalog: CATALOG
  };
})();
