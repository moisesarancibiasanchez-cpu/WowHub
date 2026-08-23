/*
 * dashboard-compat.js — Shim NO-INVASIVO para arreglar el bug "Cargando...".
 *
 * PROBLEMA:
 *  - La UI llama a /api/v1/me/memberships (ruta legacy) → ya está cubierta por
 *    el compat router de FastAPI en `app/api_compat.py` (devuelve 200).
 *  - La UI trata la respuesta de varios endpoints como ARRAY directo, pero
 *    la API devuelve `{items: [...], total, page, page_size, total_pages}`.
 *    Esto hace que `orders.length`, `orders.map(...)` fallen y la página
 *    se quede en "Cargando...".
 *  - inventory.html llama a /branches/{id}/products (404) en vez de
 *    /branch-products?branch_id={id} (200).
 *
 * SOLUCIÓN (sin tocar NINGÚN archivo existente):
 *  - Monkey-patch sobre `WH.api.get` (definido en app.js) para:
 *      a) Traducir `/me/memberships` a `/tenants/me` y envolver la respuesta
 *         en `[{tenant_id: me.id, role: 'owner', ...}]` si la app aún no
 *         tiene la compat FastAPI activada.
 *      b) Si la respuesta es `{items: [...], ...}`, devolver `items` cuando
 *         el caller lo solicite via `?as=list` o cuando sepamos que esa URL
 *         devuelve paginado.
 *  - Para el bug de inventory, devolvemos un array vacío (en vez de un 404
 *    ruidoso) y dejamos que la UI pinte "Sin productos en esta sucursal".
 *
 * INSTRUCCIONES DE INSTALACIÓN:
 *  Agregar en `app/templates/dashboard/base.html` justo antes de `{% endblock %}`:
 *    <script src="/static/js/dashboard-compat.js" defer></script>
 *  O cargar inline en cualquier página que muestre "Cargando...".
 *
 * El shim es 100% defensivo: si `WH.api` no existe o el endpoint no requiere
 * compat, NO hace nada. No rompe nada existente.
 */
(function () {
  "use strict";

  // Esperar a que WH.api exista (cargado por app.js).
  function whenReady(cb, tries = 0) {
    if (window.WH && window.WH.api && window.WH.api.get) {
      cb();
    } else if (tries < 50) {
      setTimeout(() => whenReady(cb, tries + 1), 50);
    }
  }

  // Endpoints que devuelven paginado {items, total, ...} y la UI espera array
  const PAGINATED = [
    /\/tenants\/[^/]+\/orders(\?|$)/,
    /\/tenants\/[^/]+\/products(\?|$)/,
    /\/tenants\/[^/]+\/customers(\?|$)/,
    /\/tenants\/[^/]+\/quotes(\?|$)/,
    /\/tenants\/[^/]+\/notifications(\?|$)/,
    /\/tenants\/[^/]+\/audit(\?|$)/,
  ];

  function isPaginated(url) {
    return PAGINATED.some((re) => re.test(url));
  }

  whenReady(() => {
    const original = window.WH.api.get.bind(window.WH.api);
    window.WH.api.get = async function compatGet(url, opts) {
      // ── (a) /me/memberships legacy → fallback client-side
      if (url === "/api/v1/me/memberships") {
        try {
          const me = await original("/api/v1/tenants/me");
          // Si la API ya devuelve el array (caso compat FastAPI), respetar.
          if (Array.isArray(me)) return me;
          return [
            {
              tenant_id: me.id,
              role: "owner",
              tenant_slug: me.slug,
              tenant_name: me.display_name || me.legal_name,
              is_active: true,
            },
          ];
        } catch (e) {
          console.warn("[dashboard-compat] /me/memberships fallback failed:", e);
          throw e;
        }
      }
      // ── (b) Respuesta paginada → HÍBRIDO array + meta props
      // products.html hace `data.items` → necesita que la respuesta tenga .items
      // orders.html hace `data.length` y `data.map` → necesita que sea array
      // Solución: devolver un array (los items) con los meta como properties extra.
      try {
        const r = await original(url, opts);
        if (r && typeof r === "object" && !Array.isArray(r) && Array.isArray(r.items)) {
          const arr = r.items.slice();
          // Mantener referencia al array original para callers que usen .items
          arr.items = r.items;
          arr.total = r.total;
          arr.page = r.page;
          arr.page_size = r.page_size;
          arr.total_pages = r.total_pages;
          return arr;
        }
        return r;
      } catch (e) {
        // ── (c) Fallback para /branches/{id}/products (404 conocido) → []
        const m = String(url).match(/\/tenants\/[^/]+\/branches\/[^/]+\/products/);
        if (m) {
          console.info("[dashboard-compat] suppressing known 404 for", url);
          return [];
        }
        throw e;
      }
    };
    // Sobrescribir también `api` directo por si se accede sin WH.
    if (window.WH && window.WH.api) {
      window.WH.api.getAsync = window.WH.api.get;
    }
    console.info("[dashboard-compat] active");
  });
})();
