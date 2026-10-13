/* ============================================================
 * AI context chips (v2)
 * ------------------------------------------------------------
 * API global:
 *   WH.AIContext.set(ctx)   → guarda un contexto de fila y
 *                             muestra la píldora en el composer.
 *                             ctx = {
 *                               type: "product"|"order"|"customer"|"booking",
 *                               id:   "uuid",
 *                               name: "Café Latte",
 *                               meta: "SKU CAF-001 · $3.500",   // opcional
 *                               data: { ...datos relevantes... } // opcional
 *                             }
 *   WH.AIContext.clear()    → descarta el contexto actual.
 *   WH.AIContext.get()      → devuelve el contexto actual o null.
 *   WH.AIContext.consume()  → devuelve el contexto y lo limpia
 *                             (usado al enviar el mensaje).
 *
 * Auto-binding:
 *   Cualquier elemento con `data-ai-context='<json>'` en el DOM
 *   se vuelve clickeable: al hacer click, llama set() con ese ctx.
 *   El primer nivel puede tener {type,id,name,meta} o ser un objeto
 *   arbitrario (en ese caso se infiere type desde la clase CSS
 *   `.ai-row-chip--<tipo>` o del atributo data-ai-context-type).
 *
 * Integración con el composer:
 *   Cuando hay un contexto activo y el usuario envía, se prepende
 *   al texto un bloque:
 *     [CONTEXTO: {"type":"product","id":"...","name":"...","data":{...}}]
 *   Esto se hace hookeando el evento `submit` del formulario
 *   #ai-composer con captura, ANTES de que ai.js lo procese.
 * ============================================================ */
(function () {
  "use strict";

  // ── Estado global ─────────────────────────────────────
  let current = null;
  let pillEl = null;
  let composerEl = null;
  let hookInstalled = false;

  // ── Helpers ───────────────────────────────────────────
  function $(id) { return document.getElementById(id); }

  function escapeHtml(s) {
    if (s == null) return "";
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function ensurePill() {
    if (pillEl && document.body.contains(pillEl)) return pillEl;
    composerEl = composerEl || $("ai-composer");
    if (!composerEl) return null;
    // Inyectar la píldora antes del composer-row (queda arriba del input)
    pillEl = document.createElement("div");
    pillEl.className = "ai-context-pill";
    pillEl.setAttribute("role", "status");
    pillEl.setAttribute("aria-live", "polite");
    pillEl.innerHTML = `
      <span class="ai-context-pill__ico" aria-hidden="true">
        <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M12 2L9 9l-7 1 5 5-1 7 6-3 6 3-1-7 5-5-7-1z"/>
        </svg>
      </span>
      <span class="ai-context-pill__label"></span>
      <button type="button" class="ai-context-pill__close"
              aria-label="Quitar contexto">
        <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M18 6L6 18M6 6l12 12"/>
        </svg>
      </button>
    `;
    // Insertar antes del primer hijo (composer-row)
    const firstRow = composerEl.querySelector(".ai-composer-row");
    if (firstRow) composerEl.insertBefore(pillEl, firstRow);
    else composerEl.appendChild(pillEl);
    // Wire close
    pillEl.querySelector(".ai-context-pill__close")
      .addEventListener("click", () => WH.AIContext.clear());
    return pillEl;
  }

  function renderPill() {
    const pill = ensurePill();
    if (!pill) return;
    if (!current) {
      pill.classList.remove("is-on");
      pill.querySelector(".ai-context-pill__label").innerHTML = "";
      // Resaltar el chip activo (si existe) → none
      document.querySelectorAll(".ai-row-chip.is-active")
        .forEach(c => c.classList.remove("is-active"));
      return;
    }
    const label = pill.querySelector(".ai-context-pill__label");
    const typeLabel = ({
      product: "Producto",
      order: "Pedido",
      customer: "Cliente",
      booking: "Reserva",
    })[current.type] || (current.type ? current.type[0].toUpperCase() + current.type.slice(1) : "Entidad");
    label.innerHTML =
      `<b>${escapeHtml(typeLabel)}:</b> ${escapeHtml(current.name || "—")}` +
      (current.meta ? ` <span>· ${escapeHtml(current.meta)}</span>` : "");

    pill.classList.add("is-on");

    // Resaltar el chip que disparó el contexto
    document.querySelectorAll(".ai-row-chip.is-active")
      .forEach(c => c.classList.remove("is-active"));
    if (current && current._chipEl) {
      current._chipEl.classList.add("is-active");
    }
  }

  // ── Formato del bloque de contexto para el LLM ───────
  function buildContextBlock(ctx) {
    // Sólo enviamos lo serializable (sin _chipEl, etc.)
    const clean = {
      type: ctx.type,
      id: ctx.id,
      name: ctx.name,
    };
    if (ctx.meta) clean.meta = ctx.meta;
    if (ctx.data && typeof ctx.data === "object") clean.data = ctx.data;
    return "[CONTEXTO: " + JSON.stringify(clean) + "]";
  }

  // ── Hook al submit del composer ──────────────────────
  function installSubmitHook() {
    if (hookInstalled) return;
    const composer = $("ai-composer");
    if (!composer) return;
    hookInstalled = true;

    // Captura ANTES que ai.js (que también hace preventDefault).
    // ai.js hace `composer.addEventListener("submit", ...)`, así que
    // nuestros handlers en fase de captura corren primero y pueden
    // modificar el input ANTES de que ai.js lea `input.value`.
    composer.addEventListener("submit", function () {
      if (!current) return;
      const input = $("ai-input");
      if (!input) return;
      const ctxBlock = buildContextBlock(current);
      const cur = (input.value || "").trim();
      // Si el usuario ya escribió algo, lo dejamos; si no, dejamos sólo
      // el bloque de contexto (el LLM sabrá qué hacer con él).
      input.value = cur ? (cur + "\n\n" + ctxBlock) : ctxBlock;
      // NO limpiamos current aquí — lo limpiamos cuando se envíe OK
      // (lo hace ai.js al renderizar el mensaje). Si hay error,
      // el contexto sigue activo para reintento. Limpiamos ahora
      // visualmente igual para que la píldora desaparezca al enviar.
      WH.AIContext.clear(true /* silent */);
    }, true /* useCapture */);
  }

  // ── API pública ───────────────────────────────────────
  const API = {
    set(ctx) {
      if (!ctx || typeof ctx !== "object") return;
      current = Object.assign({}, ctx);
      renderPill();
      // Si el panel IA está colapsado, lo abrimos y enfocamos
      try {
        const sb = $("ai-sidebar");
        const fab = $("ai-fab");
        if (sb && sb.classList.contains("ai-hidden")) {
          sb.classList.remove("ai-hidden");
        }
        if (fab) fab.classList.add("ai-hidden");
        // Si la sidebar está en FAB-only (móvil), abrir el chat
        // El flag es que tenga la clase .ai-collapsed; si no, dejamos
        // que el usuario abra manualmente. Suficiente con quitar ai-hidden.
      } catch (_) {}
      // Foco al input después de un tick
      setTimeout(() => {
        const input = $("ai-input");
        if (input) input.focus();
      }, 50);
    },
    clear(silent) {
      current = null;
      renderPill();
      if (!silent && window.WH && window.WH.Toast) {
        WH.Toast.show("Contexto de IA quitado", "info", 1500);
      }
    },
    get() { return current; },
    consume() {
      const c = current;
      current = null;
      return c;
    },
    /**
     * Formatea un objeto en bloque de contexto sin enviarlo.
     * Útil para que el código de cada página (ej. admin_loyalty)
     * construya prompts que incluyan datos de la fila sin tener
     * que gestionar el ciclo set/clear manualmente.
     */
    build(ctx) { return buildContextBlock(ctx); },
  };

  // ── Auto-binding: data-ai-context ─────────────────────
  function bindRowChips() {
    // Usamos CAPTURE phase para que este handler se ejecute ANTES que
    // cualquier `onclick="..."` inline en el padre (ej. kanban-card
    // onclick="openOrder(...)"). Si esperamos al bubble phase, el
    // `e.stopPropagation()` del inline onclick en el botón ya cortó
    // el camino. En capture phase llegamos primero, configuramos el
    // contexto y detenemos la propagación → el modal no se abre.
    document.addEventListener("click", function (e) {
      const chip = e.target.closest("[data-ai-context]");
      if (!chip) return;
      e.preventDefault();
      e.stopPropagation();
      const raw = chip.getAttribute("data-ai-context");
      let ctx;
      try {
        ctx = JSON.parse(raw);
      } catch (err) {
        console.warn("[ai-context] data-ai-context no es JSON válido:", raw, err);
        return;
      }
      // Refinar tipo/clase desde data-ai-context-type si no vino en JSON
      if (!ctx.type) {
        const cls = Array.from(chip.classList).find(c => c.startsWith("ai-row-chip--"));
        if (cls) ctx.type = cls.replace("ai-row-chip--", "");
      }
      // Guardar referencia al chip para resaltarlo mientras esté activo
      ctx._chipEl = chip;
      // Si es el mismo chip que ya disparó, toggle: limpiamos
      if (current && current._chipEl === chip &&
          current.id === ctx.id && current.type === ctx.type) {
        API.clear();
        return;
      }
      API.set(ctx);
      // Feedback efímero
      if (window.WH && window.WH.Toast) {
        WH.Toast.show("Contexto cargado al chat IA", "success", 1500);
      }
    }, true /* useCapture */);
  }

  // ── Bootstrap ─────────────────────────────────────────
  function init() {
    ensurePill();
    installSubmitHook();
    bindRowChips();
  }

  // Esperar al DOM (en el momento de carga de este script el body ya
  // existe en todas las páginas de dashboard, pero por si acaso).
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    // Pequeño delay para dar tiempo a ai.js a montar el composer
    setTimeout(init, 0);
  }

  // ── Exponer ───────────────────────────────────────────
  window.WH = window.WH || {};
  window.WH.AIContext = API;
})();
