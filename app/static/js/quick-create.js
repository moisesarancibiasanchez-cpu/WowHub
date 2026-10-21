/* =============================================================
 * quick-create.js  v1.0
 * WowHub Quick-Context Creation (max 3 clicks)
 * =============================================================
 *
 * Helper reutilizable que permite CREAR un recurso (cliente,
 * producto, mesa, etc.) desde el contexto actual sin perder
 * el estado del formulario padre. Implementa el principio de
 * "no navigation" y "max 3 clicks por acción".
 *
 * USO:
 *   // 1. Cargar el script una vez en el template:
 *   <script src="/static/js/quick-create.js?v=2026-10-17"></script>
 *
 *   // 2. Incluir el modal compartido en el template:
 *   {% include "_partials/quick_create_modal.html" %}
 *
 *   // 3. En el HTML, añadir un botón "+ Nuevo" junto al selector:
 *   <select name="customer_id" id="customer_id">...</select>
 *   <button type="button" class="qc-btn-new"
 *           data-qc-type="customer"
 *           data-qc-target="#customer_id"
 *           data-qc-label="Cliente">+ Nuevo</button>
 *
 *   // 4. Al hacer clic, abre el modal con el formulario minimo.
 *   //    Despues de crear, el nuevo item se inserta en el <select>
 *   //    y queda auto-seleccionado. El formulario padre NO se cierra.
 *
 * API PUBLICA:
 *   QuickCreate.open('customer', { target: '#customer_id', onCreated: cb })
 *   QuickCreate.bind(selector)  // auto-bind a todos los [data-qc-type]
 * ============================================================= */
(function () {
  "use strict";

  var CONFIG = {
    customer: {
      // ── V2.009 — Usar endpoint inline HU_50 (POST /customers/inline)
      //    dedicado a creacion in-place. Acepta (name|phone|email|name) sin
      //    requerir campos pesados (no tags, no rfm, no source). Schema:
      //    - name: required
      //    - phone: Optional[str]
      //    - email: Optional[str]
      //    - customer_type: "particular" | "empresa" (default "particular")
      //    - marketing_consent: bool (default false)
      //    - notes: Optional[str]
      //    El endpoint valida phone XOR email obligatorio.
      endpoint: function (tid) { return "/api/v1/tenants/" + tid + "/customers/inline"; },
      fieldMap: { /* inline coincide 1:1 */ },
      minFields: [
        { name: "name", label: "Nombre", type: "text", required: true, placeholder: "Ej: Juan Pérez" },
        { name: "phone", label: "Teléfono (opcional)", type: "tel", required: false, placeholder: "+56 9 1234 5678" },
        { name: "email", label: "Email (opcional)", type: "email", required: false, placeholder: "juan@test.com" }
      ],
      validate: function (payload) {
        // El endpoint valida phone XOR email en backend. Aqui duplicamos
        // para feedback instantáneo.
        if (!payload.phone && !payload.email) {
          return "Ingresa al menos teléfono o email.";
        }
        return null;
      },
      // Mapear respuesta → { id, name, ... } consistente.
      map: function (r) {
        return {
          id: r.id || r.uuid,
          name: r.full_name || r.name,
          phone: r.phone || "",
          email: r.email || ""
        };
      },
      label: "Cliente",
      icon: "👤"
    },
    product: {
      // ── V2.009 — Usar endpoint inline HU_51 (POST /products/inline)
      //    que crea y, si add_to_order=True, agrega como OrderItem.
      //    Como aqui NO tenemos aún un order_id (es previo al pedido),
      //    mandamos add_to_order=False. El operador agregara el item
      //    al pedido luego en el mismo flujo.
      endpoint: function (tid) { return "/api/v1/tenants/" + tid + "/products/inline"; },
      // Auto-generar SKU desde el nombre (regla HU_51: SKU es required).
      fieldMap: { "price_cents_ui": "price_cents" },
      preSend: function (payload, form) {
        // payload ya tiene {name, price_cents}.
        // Generar SKU desde nombre: slug limpio + timestamp corto.
        var name = (payload.name || "").trim().toLowerCase();
        var slug = name.replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 24);
        if (!slug) slug = "prod";
        var ts = Date.now().toString(36).slice(-5);
        payload.sku = slug + "-" + ts;
        // product_type default (standard).
        if (!payload.product_type) payload.product_type = "standard";
        // Eliminar helper que no es schema field.
        delete payload.price_cents_ui;
      },
      minFields: [
        { name: "name", label: "Nombre", type: "text", required: true, placeholder: "Ej: Café Americano" },
        { name: "price_cents_ui", label: "Precio (CLP)", type: "number", required: true, min: 0, step: 1, placeholder: "1500" }
      ],
      map: function (r) {
        return {
          id: r.id || r.uuid,
          name: r.name || r.title,
          price_cents: r.price_cents || 0
        };
      },
      label: "Producto",
      icon: "📦"
    }
  };

  function getTenantId() {
    return (document.body && document.body.dataset.tenantId)
        || (window.WH && window.WH.tenant && window.WH.tenant.id)
        || (window.WH_TENANT_ID)
        || null;
  }

  function getToken() {
    if (window.WH && window.WH.api && window.WH.api.token) return window.WH.api.token;
    if (window.WH_TOKEN) return window.WH_TOKEN;
    // Fallback: leer del cookie de sesion
    var m = document.cookie.match(/access_token=([^;]+)/);
    return m ? m[1] : null;
  }

  function el(tag, attrs, children) {
    var e = document.createElement(tag);
    if (attrs) Object.keys(attrs).forEach(function (k) {
      if (k === "class") e.className = attrs[k];
      else if (k === "html") e.innerHTML = attrs[k];
      else if (k.indexOf("on") === 0) e.addEventListener(k.slice(2), attrs[k]);
      else e.setAttribute(k, attrs[k]);
    });
    if (children) children.forEach(function (c) { e.appendChild(c); });
    return e;
  }

  function findSelect(target) {
    if (!target) return null;
    if (typeof target === "string") {
      return document.querySelector(target);
    }
    return target;
  }

  function appendOption(select, item) {
    if (!select) return;
    var opt = el("option");
    opt.value = item.id;
    opt.textContent = item.name + (item.price_cents ? " ($" + (item.price_cents/100) + ")" : "");
    opt.selected = true;
    select.appendChild(opt);
    // Disparar change para que cualquier listener reaccione
    var ev = document.createEvent("HTMLEvents");
    ev.initEvent("change", true, true);
    select.dispatchEvent(ev);
  }

  function showError(form, msg) {
    var existing = form.querySelector(".qc-error");
    if (existing) existing.remove();
    var err = el("div", { class: "qc-error", style: "background:#fee;color:#c00;padding:8px 12px;border-radius:6px;margin:8px 0;font-size:13px;" });
    err.textContent = msg;
    var submit = form.querySelector('[type="submit"]');
    if (submit) form.insertBefore(err, submit.parentElement);
    else form.appendChild(err);
    setTimeout(function () { if (err.parentElement) err.remove(); }, 4000);
  }

  function buildForm(cfg) {
    var form = el("form", { class: "qc-form", onsubmit: function (e) { e.preventDefault(); submitForm(form, cfg); } });

    cfg.minFields.forEach(function (f) {
      var wrap = el("div", { class: "qc-field", style: "margin-bottom: 12px;" });
      var label = el("label", { style: "display:block; font-size:12px; font-weight:700; color:#172033; margin-bottom:4px; text-transform:uppercase; letter-spacing:0.04em;" });
      label.textContent = f.label;
      var input = el("input", {
        type: f.type,
        name: f.name,
        placeholder: f.placeholder || "",
        required: f.required,
        min: f.min,
        step: f.step
      });
      input.style.cssText = "width:100%; padding:10px 12px; border:1px solid #e8ecf3; border-radius:8px; font-size:14px; font-family:inherit;";
      wrap.appendChild(label);
      wrap.appendChild(input);
      form.appendChild(wrap);
    });

    var actions = el("div", { class: "qc-actions", style: "display:flex; gap:8px; justify-content:flex-end; margin-top:16px;" });
    var cancel = el("button", {
      type: "button",
      class: "qc-btn-cancel",
      style: "background:transparent; color:#172033; border:1px solid #e8ecf3; padding:9px 14px; border-radius:8px; font-weight:600; cursor:pointer;",
      onclick: function () { closeModal(); }
    });
    cancel.textContent = "Cancelar";

    var save = el("button", {
      type: "submit",
      class: "qc-btn-save",
      style: "background:#6c5ce7; color:#fff; border:0; padding:9px 14px; border-radius:8px; font-weight:700; cursor:pointer;"
    });
    save.textContent = "Crear y volver";

    actions.appendChild(cancel);
    actions.appendChild(save);
    form.appendChild(actions);
    return form;
  }

  var currentCfg = null;
  var currentTarget = null;
  var currentOnCreated = null;

  function openModal(cfg, target, onCreated) {
    currentCfg = cfg;
    currentTarget = target;
    currentOnCreated = onCreated || null;

    var modal = document.getElementById("qc-modal");
    if (!modal) {
      console.error("[quick-create] Modal #qc-modal no encontrado. Incluí el partial _partials/quick_create_modal.html");
      return;
    }
    var titleEl = document.getElementById("qc-modal-title");
    var iconEl = document.getElementById("qc-modal-icon");
    var bodyEl = document.getElementById("qc-modal-body");
    if (titleEl) titleEl.textContent = cfg.icon + " Crear " + cfg.label;
    if (iconEl) iconEl.textContent = cfg.icon;
    if (bodyEl) {
      bodyEl.innerHTML = "";
      bodyEl.appendChild(buildForm(cfg));
      // Auto-focus primer input
      setTimeout(function () {
        var firstInput = bodyEl.querySelector("input");
        if (firstInput) firstInput.focus();
      }, 50);
    }
    modal.style.display = "flex";
  }

  function closeModal() {
    var modal = document.getElementById("qc-modal");
    if (modal) modal.style.display = "none";
    currentCfg = null;
    currentTarget = null;
    currentOnCreated = null;
  }

  function submitForm(form, cfg) {
    var tenantId = getTenantId();
    if (!tenantId) {
      showError(form, "No se detectó tenant_id. Asegurate de estar en una página con tenant.");
      return;
    }
    var token = getToken();
    var payload = {};
    cfg.minFields.forEach(function (f) {
      var v = form.elements[f.name].value.trim();
      if (!v) return;
      var backendKey = (cfg.fieldMap && cfg.fieldMap[f.name]) || f.name;
      // Conversion CLP -> cents (solo cuando el campo UI es numerico
      // con type=number y queremos cents en backend; los *_cents_ui
      // son centavos puros, los *_clp_ui serian pesos).
      // Regla: si el backendKey acaba en "_cents" y el campo no es
      // *_cents_ui (sufijo preservado literal), multiplicar por 100.
      var isCents = backendKey.indexOf("_cents") >= 0;
      var isAlreadyCentsUi = f.name.indexOf("_cents") >= 0;
      var isPureCents = isCents && isAlreadyCentsUi;
      if (f.type === "number" && isCents && !isPureCents) {
        // UI en CLP, backend en cents. CLP * 100 = cents.
        payload[backendKey] = Math.round(parseFloat(v) * 100) || 0;
      } else if (f.type === "number") {
        // Numero entero plano.
        payload[backendKey] = parseInt(v, 10) || 0;
      } else {
        payload[backendKey] = v;
      }
    });

    // Hook preSend (ej. SKU auto-generado).
    if (typeof cfg.preSend === "function") {
      cfg.preSend(payload, form);
    }

    // Validar requeridos (sobre el nombre UI, no el backendKey).
    var missing = cfg.minFields.filter(function (f) { return f.required && !form.elements[f.name].value.trim(); });
    if (missing.length) {
      showError(form, "Faltan campos requeridos: " + missing.map(function (f) { return f.label; }).join(", "));
      return;
    }
    // Hook validate cross-field (ej. phone XOR email).
    if (typeof cfg.validate === "function") {
      var verr = cfg.validate(payload);
      if (verr) {
        showError(form, verr);
        return;
      }
    }

    var btn = form.querySelector(".qc-btn-save");
    if (btn) { btn.disabled = true; btn.textContent = "Creando…"; }

    fetch(cfg.endpoint(tenantId), {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": token ? "Bearer " + token : ""
      },
      body: JSON.stringify(payload)
    })
    .then(function (r) {
      if (!r.ok) return r.json().then(function (e) { throw new Error(e.detail || r.statusText); });
      return r.json();
    })
    .then(function (created) {
      // Normalizar respuesta via cfg.map() (cliente usa full_name, etc.).
      if (typeof cfg.map === "function") {
        try { created = cfg.map(created); }
        catch (e) { console.warn("[quick-create] map() falló:", e); }
      }
      // Hook de refresh específico (si el template expone uno). Útil
      // cuando el <select> padre debe recargarse desde API para incluir
      // campos calculados (ej: price_cents formateado). Se llama ANTES
      // del appendOption local como red de seguridad.
      var hookName = "wcRefresh" + cfg.label.charAt(0).toUpperCase() + cfg.label.slice(1) + "Select";
      if (typeof window[hookName] === "function") {
        try { window[hookName](created); } catch (e) { console.warn("[quick-create] hook " + hookName + " falló:", e); }
      }

      // Insertar en el <select> target y auto-seleccionar (fallback si
      // no hay hook o si el hook no actualizó el <select>).
      var select = findSelect(currentTarget);
      if (select) appendOption(select, created);

      // Callback custom
      if (typeof currentOnCreated === "function") {
        try { currentOnCreated(created); } catch (e) { console.warn(e); }
      }

      // Cerrar modal, NO cerrar el formulario padre
      closeModal();

      // Toast feedback (silencioso, no invasivo)
      if (window.wcShowToast) wcShowToast("✓ " + cfg.label + " creado: " + (created.name || ""));
    })
    .catch(function (err) {
      showError(form, "Error: " + err.message);
      if (btn) { btn.disabled = false; btn.textContent = "Crear y volver"; }
    });
  }

  function bindOne(btn) {
    if (btn._qcBound) return;
    btn._qcBound = true;
    btn.addEventListener("click", function (e) {
      e.preventDefault();
      e.stopPropagation();
      var type = btn.dataset.qcType;
      var target = btn.dataset.qcTarget;
      var onCreated = btn.dataset.qcOncreated
        ? new Function("item", "return (" + btn.dataset.qcOncreated + ")(item);")
        : null;
      if (!CONFIG[type]) {
        console.warn("[quick-create] tipo desconocido:", type);
        return;
      }
      openModal(CONFIG[type], target, onCreated);
    });
  }

  function bindAll(root) {
    root = root || document;
    var btns = root.querySelectorAll("[data-qc-type]");
    btns.forEach(bindOne);
  }

  // API publica
  window.QuickCreate = {
    open: function (type, opts) {
      var cfg = CONFIG[type];
      if (!cfg) { console.warn("[quick-create] tipo desconocido:", type); return; }
      openModal(cfg, opts && opts.target, opts && opts.onCreated);
    },
    close: closeModal,
    bind: bindAll,
    registerType: function (name, cfg) { CONFIG[name] = cfg; }
  };

  // Auto-bind al cargar
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () { bindAll(); });
  } else {
    bindAll();
  }
})();
