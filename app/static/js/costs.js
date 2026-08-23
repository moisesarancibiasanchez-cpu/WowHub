/* =============================================================
 * Costos (Fase 2 V8) — UI logic
 *
 * Comportamiento:
 *  - Carga la config del tenant al entrar.
 *  - Renderiza las 3 cards resumen + hero "Tu hora vale $X".
 *  - Modal de edición con 3 secciones (Personal / Operación / Básicos+Otros).
 *  - Cálculo en vivo (cost_hour, total_fixed, margen) a medida que el
 *    usuario edita.
 *  - Persistencia vía PUT /api/v1/tenants/{id}/costs.
 *  - Atajos de teclado: Esc cierra el modal.
 *  - A11y: aria-live en el hero, focus trap básico en el modal, labels
 *    asociados a inputs.
 * ============================================================= */
(function () {
  "use strict";

  // ── Estado global de la página ──────────────────────────
  let _config = null;        // BusinessCostsRead (cargado del backend)
  let _fieldsMeta = null;    // Lista de fields-meta
  let _tenantId = null;
  let _isSaving = false;
  let _modalOpen = false;

  // ── Helpers de formato ──────────────────────────────────
  // Formato monetario CLP: $1.234.567  (sin decimales).
  // Asume 1 cent = 1 peso (CLP). Para otras monedas, se puede
  // extender con tenant.currency + cents_per_unit.
  const fmtMoney = (cents) => {
    if (cents == null || isNaN(cents)) return "—";
    const n = Math.round(Number(cents));
    return "$" + n.toLocaleString("es-CL");
  };
  const fmtInt = (n) => {
    if (n == null || isNaN(n)) return "—";
    return Math.round(Number(n)).toLocaleString("es-CL");
  };

  // ── API helpers ─────────────────────────────────────────
  const getToken = () => {
    if (window.WH && window.WH.TokenStore && window.WH.TokenStore.access) {
      return window.WH.TokenStore.access();
    }
    return localStorage.getItem("wowhub_access_token");
  };
  const authHeaders = () => ({
    "Content-Type": "application/json",
    Authorization: "Bearer " + getToken(),
  });

  async function fetchTenant() {
    const session = await WH.Auth.ensureSession();
    const t = session.tenant || WH.Auth.tenant();
    if (!t || !t.id) throw new Error("No hay tenant activo");
    _tenantId = t.id;
  }

  async function api(path, options = {}) {
    const res = await fetch("/api/v1/tenants/" + _tenantId + path, {
      ...options,
      headers: { ...authHeaders(), ...(options.headers || {}) },
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: "Error " + res.status }));
      throw new Error(err.detail || "Error " + res.status);
    }
    return res.json();
  }

  // ── Cálculo client-side (espejo de CostsService) ────────
  // Para feedback instantáneo. El backend siempre re-valida.
  const MONEY_KEYS = [
    "owner_salary_cents", "workers_salary_cents",
    "rent_cents", "electricity_cents", "water_cents", "gas_cents",
    "software_cents", "advertising_cents", "payment_commission_cents",
    "packaging_cents", "maintenance_cents", "depreciation_cents",
  ];
  function computeLiveSummary(cfg) {
    const isNa = cfg.is_na || {};
    let total = 0;
    for (const k of MONEY_KEYS) {
      if (isNa[k]) continue;
      total += Number(cfg[k] || 0);
    }
    const hours = Math.max(1, Number(cfg.productive_hours_per_month || 1));
    const costHour = total > 0 ? Math.ceil(total / hours) : 0;
    return { total, costHour };
  }

  // ── Render principal ────────────────────────────────────
  function renderSummary(cfg) {
    if (!cfg) return;
    const sum = computeLiveSummary(cfg);
    const isNa = cfg.is_na || {};

    // Hero
    const hero = document.getElementById("costs-hero");
    document.getElementById("costs-hero-price").textContent = fmtMoney(sum.costHour);
    document.getElementById("costs-hero-hourly-rate").textContent = fmtMoney(sum.costHour) + " / hora";
    document.getElementById("costs-hero-breakdown").textContent =
      "Sobre " + fmtInt(cfg.productive_hours_per_month) + " horas productivas/mes";
    const ver = document.getElementById("costs-hero-version");
    if (cfg.version) {
      ver.hidden = false;
      ver.textContent = "v" + cfg.version;
    }

    // Cards
    const personal = (!isNa.owner_salary_cents ? cfg.owner_salary_cents : 0)
                   + (!isNa.workers_salary_cents ? cfg.workers_salary_cents : 0);
    const basics = (!isNa.rent_cents ? cfg.rent_cents : 0)
                 + (!isNa.electricity_cents ? cfg.electricity_cents : 0)
                 + (!isNa.water_cents ? cfg.water_cents : 0)
                 + (!isNa.gas_cents ? cfg.gas_cents : 0);
    const others = (!isNa.software_cents ? cfg.software_cents : 0)
                 + (!isNa.advertising_cents ? cfg.advertising_cents : 0)
                 + (!isNa.payment_commission_cents ? cfg.payment_commission_cents : 0)
                 + (!isNa.packaging_cents ? cfg.packaging_cents : 0)
                 + (!isNa.maintenance_cents ? cfg.maintenance_cents : 0)
                 + (!isNa.depreciation_cents ? cfg.depreciation_cents : 0);

    document.getElementById("costs-card-personal").textContent = fmtMoney(personal);
    document.getElementById("costs-card-basics").textContent = fmtMoney(basics);
    document.getElementById("costs-card-others").textContent = fmtMoney(others);
    document.getElementById("costs-card-personal-detail").innerHTML =
      `💼 Sueldo dueño <b>${fmtMoney(isNa.owner_salary_cents ? 0 : cfg.owner_salary_cents)}</b> · ` +
      `Trabajadores <b>${fmtMoney(isNa.workers_salary_cents ? 0 : cfg.workers_salary_cents)}</b>`;
    document.getElementById("costs-card-basics-detail").innerHTML =
      `🏠 Arriendo <b>${fmtMoney(isNa.rent_cents ? 0 : cfg.rent_cents)}</b> · ` +
      `Luz <b>${fmtMoney(isNa.electricity_cents ? 0 : cfg.electricity_cents)}</b> · ` +
      `Agua <b>${fmtMoney(isNa.water_cents ? 0 : cfg.water_cents)}</b>`;
    document.getElementById("costs-card-others-detail").innerHTML =
      `💻 Software <b>${fmtMoney(isNa.software_cents ? 0 : cfg.software_cents)}</b> · ` +
      `Publicidad <b>${fmtMoney(isNa.advertising_cents ? 0 : cfg.advertising_cents)}</b> · ` +
      `Merma <b>${cfg.waste_pct || 0}%</b>`;

    // Métricas auxiliares
    document.getElementById("costs-card-total").textContent = fmtMoney(sum.total);
    document.getElementById("costs-card-total-tag").textContent =
      sum.total > 0 ? "Suma de los anteriores" : "Sin datos — edita para empezar";
    document.getElementById("costs-card-hours").textContent = fmtInt(cfg.productive_hours_per_month) + " h";
    document.getElementById("costs-card-margin").textContent = (cfg.target_margin_pct || 0) + "%";
  }

  // ── Modal: render de campos ─────────────────────────────
  function renderModalBody() {
    const body = document.getElementById("costs-modal-body");
    if (!_fieldsMeta || !_fieldsMeta.length) {
      body.innerHTML = '<div style="text-align:center;padding:30px;color:var(--err)">No se pudieron cargar los campos.</div>';
      return;
    }

    const sections = {
      personal: { title: "Personal", open: true, fields: [] },
      operacion: { title: "Operación (horas y margen)", open: true, fields: [] },
      basicos: { title: "Gastos básicos", open: true, fields: [] },
      otros: { title: "Otros costos fijos", open: true, fields: [] },
    };
    for (const f of _fieldsMeta) {
      if (!sections[f.section]) sections[f.section] = { title: f.section, open: true, fields: [] };
      sections[f.section].fields.push(f);
    }

    let html = "";
    for (const key of Object.keys(sections)) {
      const sec = sections[key];
      if (!sec.fields.length) continue;
      html += `<div class="cost-section open" data-section="${key}">
        <div class="cost-section-head" tabindex="0" role="button" aria-expanded="true">
          <span>${sec.title}</span>
          <span class="arrow" aria-hidden="true">▶</span>
        </div>
        <div class="cost-section-body">
          <div class="cost-form-grid">
            ${sec.fields.map(f => renderField(f)).join("")}
          </div>
        </div>
      </div>`;
    }

    html += `<div class="cost-live-summary" id="costs-live-summary">
      <div class="line"><span>Costo fijo mensual (no NA)</span><strong id="live-total">$0</strong></div>
      <div class="line"><span>Horas productivas</span><strong id="live-hours">160 h</strong></div>
      <div class="line headline"><span>Tu hora vale</span><strong id="live-cost-hour">$0</strong></div>
      <div class="line" style="margin-top:6px"><span>Margen objetivo</span><strong id="live-margin">30%</strong></div>
      <div class="note">El cálculo se actualiza en vivo. La IA usará estos valores
      para sugerir precios de productos considerando insumos + tiempo de producción.</div>
    </div>`;

    body.innerHTML = html;

    // Bindings
    body.querySelectorAll("input[data-field]").forEach(input => {
      input.addEventListener("input", onFieldChange);
    });
    body.querySelectorAll("input[data-na]").forEach(cb => {
      cb.addEventListener("change", onNAToggle);
    });
    body.querySelectorAll(".cost-section-head").forEach(h => {
      const toggle = () => {
        const sec = h.parentElement;
        sec.classList.toggle("open");
        h.setAttribute("aria-expanded", sec.classList.contains("open"));
      };
      h.addEventListener("click", toggle);
      h.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          toggle();
        }
      });
    });

    updateLiveSummary();
  }

  function renderField(f) {
    const isNA = (_config.is_na || {})[f.key] === true;
    const val = _config[f.key] ?? f.default ?? 0;
    const step = f.currency_kind === "money" ? "100" : "1";
    return `<div class="cost-field" data-field-key="${f.key}">
      <label for="cf-${f.key}">
        ${escapeHtml(f.label)}
        ${f.required ? '<span class="req" aria-label="obligatorio">*</span>' : ''}
      </label>
      <input id="cf-${f.key}" type="number" min="0" step="${step}"
        data-field="${f.key}" data-currency-kind="${f.currency_kind}"
        value="${val}" ${isNA ? "disabled" : ""}
        aria-describedby="cf-help-${f.key}">
      <div id="cf-help-${f.key}" class="na-row">
        <input type="checkbox" id="cf-na-${f.key}" data-na="${f.key}" ${isNA ? "checked" : ""}>
        <label for="cf-na-${f.key}">No aplica</label>
      </div>
    </div>`;
  }

  function escapeHtml(s) {
    return String(s || "").replace(/[&<>"']/g, c => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[c]));
  }

  // ── Live update (al escribir o toggle NA) ───────────────
  function onFieldChange() {
    const key = this.dataset.field;
    const kind = this.dataset.currencyKind;
    const v = Math.max(0, Math.floor(Number(this.value || 0)));
    _config[key] = kind === "money" ? v : (kind === "pct" ? Math.min(100, v) : v);
    updateLiveSummary();
  }

  function onNAToggle() {
    const key = this.dataset.na;
    const na = this.checked;
    _config.is_na = _config.is_na || {};
    _config.is_na[key] = na;
    // Disable/enable el input numérico asociado
    const input = document.querySelector(`input[data-field="${key}"]`);
    if (input) input.disabled = na;
    updateLiveSummary();
  }

  function updateLiveSummary() {
    const sum = computeLiveSummary(_config);
    document.getElementById("live-total").textContent = fmtMoney(sum.total);
    document.getElementById("live-hours").textContent = fmtInt(_config.productive_hours_per_month) + " h";
    document.getElementById("live-cost-hour").textContent = fmtMoney(sum.costHour);
    document.getElementById("live-margin").textContent = (_config.target_margin_pct || 0) + "%";
  }

  // ── Modal open/close ────────────────────────────────────
  function openModal() {
    if (!_config || !_fieldsMeta) return;
    _modalOpen = true;
    renderModalBody();
    document.getElementById("costs-modal").classList.add("open");
    document.body.style.overflow = "hidden";
    // focus en el primer input
    setTimeout(() => {
      const first = document.querySelector("#costs-modal-body input[data-field]");
      if (first) first.focus();
    }, 50);
  }
  function closeModal() {
    _modalOpen = false;
    document.getElementById("costs-modal").classList.remove("open");
    document.body.style.overflow = "";
  }

  // ── Guardar ─────────────────────────────────────────────
  async function save() {
    if (_isSaving) return;
    _isSaving = true;
    const saveBtn = document.getElementById("costs-modal-save");
    const orig = saveBtn.innerHTML;
    saveBtn.disabled = true;
    saveBtn.innerHTML = "Guardando…";

    try {
      const payload = { ..._config };
      // Filtrar is_na para enviarlo completo
      payload.is_na = _config.is_na || {};
      // Quitar campos derivados / de servidor
      delete payload.id;
      delete payload.tenant_id;
      delete payload.created_at;
      delete payload.updated_at;
      delete payload.total_fixed_cents;
      delete payload.cost_hour_cents;
      delete payload.version;

      const updated = await api("/costs", {
        method: "PUT",
        body: JSON.stringify(payload),
      });
      _config = updated;
      renderSummary(_config);
      closeModal();
      showToast("✓ Costos guardados · costo hora recalculado");
    } catch (e) {
      console.error("Error guardando costos:", e);
      showToast("❌ No se pudieron guardar los costos: " + e.message, true);
    } finally {
      _isSaving = false;
      saveBtn.disabled = false;
      saveBtn.innerHTML = orig;
    }
  }

  // ── Toast ───────────────────────────────────────────────
  function showToast(msg, isError) {
    const t = document.createElement("div");
    t.className = "cost-toast" + (isError ? " error" : "");
    t.textContent = msg;
    document.body.appendChild(t);
    setTimeout(() => {
      t.style.opacity = "0";
      t.style.transition = "opacity .25s";
      setTimeout(() => t.remove(), 250);
    }, 3200);
  }

  // ── Init ────────────────────────────────────────────────
  async function init() {
    try {
      await fetchTenant();
      // Carga paralela
      const [cfg, meta] = await Promise.all([
        api("/costs"),
        api("/costs/fields-meta"),
      ]);
      _config = cfg;
      _fieldsMeta = meta.fields;
      renderSummary(_config);
    } catch (e) {
      console.error("Error inicializando costos:", e);
      document.getElementById("costs-hero-breakdown").textContent =
        "Error cargando: " + e.message;
    }

    // Event bindings
    document.getElementById("costs-edit").addEventListener("click", openModal);
    document.getElementById("costs-modal-close").addEventListener("click", closeModal);
    document.getElementById("costs-modal-cancel").addEventListener("click", closeModal);
    document.getElementById("costs-modal-save").addEventListener("click", save);
    document.getElementById("costs-reload").addEventListener("click", async () => {
      try {
        _config = await api("/costs");
        renderSummary(_config);
        showToast("✓ Configuración recargada");
      } catch (e) {
        showToast("❌ " + e.message, true);
      }
    });

    // Click fuera del modal → cerrar
    document.getElementById("costs-modal").addEventListener("click", (e) => {
      if (e.target.id === "costs-modal") closeModal();
    });

    // Esc → cerrar
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && _modalOpen) closeModal();
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
