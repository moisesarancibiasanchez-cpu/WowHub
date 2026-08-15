// WowHub client utilities
// - Token storage (localStorage)
// - API wrapper con Bearer
// - Toast helper
// - Logout

const TOKEN_KEY = "wowhub.tokens";
const TENANT_KEY = "wowhub.currentTenant";

const TokenStore = {
  get() {
    try { return JSON.parse(localStorage.getItem(TOKEN_KEY) || "null"); } catch { return null; }
  },
  set(tokens) { localStorage.setItem(TOKEN_KEY, JSON.stringify(tokens)); },
  clear() { localStorage.removeItem(TOKEN_KEY); localStorage.removeItem(TENANT_KEY); },
  access() { return this.get()?.access_token; },
  refresh() { return this.get()?.refresh_token; },
  currentTenant() { return this.get()?.current_tenant || null; },
};

const api = {
  async request(path, opts = {}) {
    const headers = { "Content-Type": "application/json", ...(opts.headers || {}) };
    const tk = TokenStore.access();
    if (tk) headers.Authorization = `Bearer ${tk}`;
    const tid = TokenStore.currentTenant()?.tenant_id;
    if (tid && !path.includes("/auth/") && !path.startsWith("/api/v1/public/") && !path.startsWith("/api/v1/tenants") === false) {
      // send tenant id for tenant-scoped endpoints
    }
    const res = await fetch(path, { ...opts, headers });
    if (res.status === 401 && !path.includes("/auth/")) {
      // intentar refresh
      const refreshed = await this.tryRefresh();
      if (refreshed) {
        headers.Authorization = `Bearer ${TokenStore.access()}`;
        const retry = await fetch(path, { ...opts, headers });
        return this._parse(retry);
      }
      TokenStore.clear();
      window.location.href = "/login";
      return;
    }
    return this._parse(res);
  },
  async tryRefresh() {
    const r = TokenStore.get()?.refresh_token;
    if (!r) return false;
    try {
      const res = await fetch("/api/v1/auth/refresh", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: r }),
      });
      if (!res.ok) return false;
      const data = await res.json();
      TokenStore.set(data);
      return true;
    } catch { return false; }
  },
  async _parse(res) {
    if (res.status === 204) return null;
    const ct = res.headers.get("content-type") || "";
    const data = ct.includes("application/json") ? await res.json() : await res.text();
    if (!res.ok) {
      const detail = (data && data.detail) || res.statusText;
      throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
    }
    return data;
  },
  get(path) { return this.request(path); },
  post(path, body) { return this.request(path, { method: "POST", body: JSON.stringify(body) }); },
  put(path, body) { return this.request(path, { method: "PUT", body: JSON.stringify(body) }); },
  patch(path, body) { return this.request(path, { method: "PATCH", body: JSON.stringify(body) }); },
  del(path) { return this.request(path, { method: "DELETE" }); },
};

// Public API (no auth)
const publicApi = {
  async get(path) {
    const res = await fetch(path);
    if (!res.ok) throw new Error("Error al cargar datos");
    return res.json();
  },
};

const Toast = {
  show(message, type = "success") {
    let c = document.getElementById("toast-container");
    if (!c) { c = document.createElement("div"); c.id = "toast-container"; document.body.appendChild(c); }
    const t = document.createElement("div");
    t.className = `toast toast-${type}`;
    t.textContent = message;
    c.appendChild(t);
    setTimeout(() => { t.style.opacity = "0"; t.style.transition = "opacity 0.2s"; setTimeout(() => t.remove(), 200); }, 3500);
  },
};

// ── Upload helper ─────────────────────────────────────────────
// Sube imágenes (JPG/PNG, max 3 MB) al backend y devuelve la URL pública.
// Se usa desde cualquier template vía WH.Upload.image(file, {purpose}).
const Upload = {
  // Límites (deben coincidir con app/services/upload_service.py)
  MAX_BYTES: 3 * 1024 * 1024,
  ALLOWED_MIME: new Set(["image/jpeg", "image/png"]),

  validate(file) {
    if (!file) throw new Error("No se seleccionó ningún archivo.");
    if (!this.ALLOWED_MIME.has(file.type)) {
      throw new Error(`Tipo no permitido (${file.type || "?"}). Solo JPG o PNG.`);
    }
    if (file.size > this.MAX_BYTES) {
      const mb = (file.size / 1024 / 1024).toFixed(1);
      throw new Error(`La imagen pesa ${mb} MB. El máximo es 3 MB.`);
    }
  },

  // Sube un File y devuelve {url, width, height, ...} (lo que devuelva el server).
  // Lanza Error si falla (validación cliente o server).
  async image(file, opts = {}) {
    this.validate(file);
    const tenant = TokenStore.currentTenant();
    if (!tenant || !tenant.tenant_id) {
      throw new Error("No hay un negocio activo. Vuelve a iniciar sesión.");
    }
    const fd = new FormData();
    fd.append("file", file);
    if (opts.purpose) fd.append("purpose", opts.purpose);
    if (opts.entity_type) fd.append("entity_type", opts.entity_type);
    if (opts.entity_id) fd.append("entity_id", opts.entity_id);

    const tk = TokenStore.access();
    const res = await fetch(
      `/api/v1/tenants/${tenant.tenant_id}/uploads`,
      { method: "POST", body: fd, headers: tk ? { Authorization: `Bearer ${tk}` } : {} }
    );
    const ct = res.headers.get("content-type") || "";
    const data = ct.includes("application/json") ? await res.json() : await res.text();
    if (!res.ok) {
      const detail = (data && data.detail) || res.statusText;
      throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
    }
    return data; // UploadOut: {url, width, height, ...}
  },
};

// ── ImagePicker component ────────────────────────────────────
// Reemplaza el <input type="url"> clásico por un selector con:
//   - Drag & drop
//   - Click → file picker
//   - Preview de la imagen actual
//   - Botón "Quitar" para volver a null
//   - Sube automáticamente al server al elegir y guarda la URL en un
//     <input type="hidden"> (targetInput) que el form ya sabe leer.
//
// Uso:
//   <div data-image-picker
//        data-target="p_image_url"        ← id del <input> donde dejar la URL
//        data-purpose="product_image"
//        data-max-size-mb="3"
//        data-accept="image/jpeg,image/png">
//   </div>
//   <input type="hidden" id="p_image_url">
const ImagePicker = {
  // Convierte bytes a "1.4 MB" legible
  fmtSize(bytes) {
    if (bytes < 1024) return bytes + " B";
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(0) + " KB";
    return (bytes / 1024 / 1024).toFixed(1) + " MB";
  },

  // Inicializa todos los <div data-image-picker> de la página.
  initAll(root = document) {
    root.querySelectorAll("[data-image-picker]").forEach((host) => this.mount(host));
  },

  // Helper: refresca el preview del picker que apunta a `targetId`
  // (útil cuando el valor del input cambia programáticamente: editar un
  // producto, abrir un modal, etc.)
  setValue(targetId, url) {
    const host = document.querySelector(
      `[data-image-picker][data-target="${targetId}"]`
    );
    if (host && host._whPicker) host._whPicker.setPreview(url || null);
  },

  mount(host) {
    if (host._whPicker) return; // idempotente
    const targetId = host.dataset.target;
    const purpose = host.dataset.purpose || "general";
    const maxMb = Number(host.dataset.maxSizeMb || 3);
    const accept = host.dataset.accept || "image/jpeg,image/png";
    const target = targetId ? document.getElementById(targetId) : null;

    host.innerHTML = `
      <div class="ip-drop" tabindex="0" role="button" aria-label="Subir imagen">
        <input type="file" class="ip-file" accept="${accept}" hidden>
        <div class="ip-preview" data-empty="true">
          <div class="ip-empty">
            <svg viewBox="0 0 24 24" width="40" height="40" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect>
              <circle cx="8.5" cy="8.5" r="1.5"></circle>
              <polyline points="21 15 16 10 5 21"></polyline>
            </svg>
            <div class="ip-empty-title">Subir imagen</div>
            <div class="ip-empty-sub">Arrastra un archivo o haz click. JPG o PNG, máx ${maxMb} MB.</div>
          </div>
        </div>
        <div class="ip-progress" hidden><div class="ip-progress-bar"></div></div>
        <div class="ip-error" hidden></div>
        <div class="ip-actions">
          <button type="button" class="btn btn-sm ip-pick">Elegir archivo</button>
          <button type="button" class="btn btn-sm btn-ghost ip-remove" hidden>Quitar</button>
          <span class="ip-filename text-muted"></span>
        </div>
      </div>
    `;

    const drop = host.querySelector(".ip-drop");
    const fileInput = host.querySelector(".ip-file");
    const preview = host.querySelector(".ip-preview");
    const empty = host.querySelector(".ip-empty");
    const pickBtn = host.querySelector(".ip-pick");
    const removeBtn = host.querySelector(".ip-remove");
    const filenameEl = host.querySelector(".ip-filename");
    const progress = host.querySelector(".ip-progress");
    const progressBar = host.querySelector(".ip-progress-bar");
    const errorEl = host.querySelector(".ip-error");

    function setPreview(url) {
      if (url) {
        preview.dataset.empty = "false";
        preview.innerHTML = `<img src="${escapeAttr(url)}" alt="" style="max-width:100%;max-height:240px;display:block;border-radius:6px;">`;
        removeBtn.hidden = false;
        empty.style.display = "none";
      } else {
        preview.dataset.empty = "true";
        preview.innerHTML = "";
        preview.appendChild(empty);
        empty.style.display = "";
        removeBtn.hidden = true;
        filenameEl.textContent = "";
      }
    }

    function setError(msg) {
      if (msg) {
        errorEl.hidden = false;
        errorEl.textContent = msg;
      } else {
        errorEl.hidden = true;
        errorEl.textContent = "";
      }
    }

    function setUploading(on) {
      progress.hidden = !on;
      if (on) progressBar.style.width = "0%";
      pickBtn.disabled = !!on;
      drop.classList.toggle("ip-uploading", !!on);
    }

    async function uploadFile(file) {
      setError("");
      filenameEl.textContent = file.name + " · " + ImagePicker.fmtSize(file.size);
      // Validación rápida en cliente (la autoridad está en el server)
      const allowed = accept.split(",").map((s) => s.trim());
      if (!allowed.includes(file.type)) {
        setError("Tipo no permitido. Solo " + allowed.join(" o ") + ".");
        return;
      }
      if (file.size > maxMb * 1024 * 1024) {
        setError("La imagen supera " + maxMb + " MB.");
        return;
      }

      setUploading(true);
      // Animación fake de progreso (fetch no expone progreso sin XHR; suficiente
      // como feedback visual — el server responde en <2s en el 99% de los casos).
      let pct = 0;
      const tick = setInterval(() => {
        pct = Math.min(pct + 12, 85);
        progressBar.style.width = pct + "%";
      }, 120);

      try {
        const out = await Upload.image(file, { purpose });
        if (target) target.value = out.url;
        progressBar.style.width = "100%";
        setPreview(out.url);
        host.dispatchEvent(new CustomEvent("image-uploaded", { detail: out, bubbles: true }));
        if (window.WH && window.WH.Toast) window.WH.Toast.show("Imagen subida ✓", "success");
      } catch (e) {
        setError(e.message || "Error al subir la imagen.");
        if (window.WH && window.WH.Toast) window.WH.Toast.show(e.message || "Error al subir", "error");
      } finally {
        clearInterval(tick);
        setTimeout(() => { setUploading(false); }, 250);
      }
    }

    // Click anywhere on the drop zone → open file picker
    drop.addEventListener("click", (e) => {
      if (e.target.closest(".ip-remove")) return;
      if (e.target.closest(".ip-pick")) { fileInput.click(); return; }
      if (!host.classList.contains("ip-uploading")) fileInput.click();
    });
    // Keyboard accessibility
    drop.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); fileInput.click(); }
    });
    pickBtn.addEventListener("click", (e) => { e.stopPropagation(); fileInput.click(); });
    fileInput.addEventListener("change", (e) => {
      const f = e.target.files && e.target.files[0];
      if (f) uploadFile(f);
      fileInput.value = ""; // permite re-subir el mismo archivo
    });
    // Drag & drop
    ["dragenter", "dragover"].forEach((ev) =>
      drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add("ip-drag"); })
    );
    ["dragleave", "drop"].forEach((ev) =>
      drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.remove("ip-drag"); })
    );
    drop.addEventListener("drop", (e) => {
      const f = e.dataTransfer.files && e.dataTransfer.files[0];
      if (f) uploadFile(f);
    });
    removeBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      if (target) target.value = "";
      setPreview(null);
      host.dispatchEvent(new CustomEvent("image-removed", { bubbles: true }));
    });

    // Estado inicial: si el target ya tiene valor, pintamos el preview
    if (target && target.value) setPreview(target.value);

    // API pública por instancia
    host._whPicker = { setPreview, setError, uploadFile };
  },
};

function escapeAttr(s) {
  return String(s == null ? "" : s).replace(/[&<>"']/g, (m) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[m]));
}

const Auth = {
  isLoggedIn() { return !!TokenStore.access(); },
  logout() { TokenStore.clear(); window.location.href = "/login"; },
  user() { return TokenStore.get()?.user; },
  tenant() { return TokenStore.currentTenant(); },
  requireLogin() { if (!this.isLoggedIn()) { window.location.href = "/login?next=" + encodeURIComponent(location.pathname); } },

  // Devuelve {user, tenant, access_token} desde localStorage y, si falta
  // `current_tenant`, rehidrata desde el server con /api/v1/auth/me/session
  // (usa el access_token vigente).
  // Cachea el promise para no pegarle al endpoint varias veces en la misma página.
  _sessionPromise: null,
  ensureSession() {
    if (this._sessionPromise) return this._sessionPromise;
    this._sessionPromise = (async () => {
      const access = TokenStore.access();
      let user = Auth.user();
      let tenant = Auth.tenant();
      if (user && tenant && tenant.tenant_id) return { user, tenant, access_token: access };
      if (!access) return { user, tenant, access_token: access };
      try {
        const session = await api.get("/api/v1/auth/me/session");
        if (session) {
          const tokens = TokenStore.get() || {};
          if (session.user) tokens.user = session.user;
          if (session.current_tenant) tokens.current_tenant = session.current_tenant;
          TokenStore.set(tokens);
          return { user: tokens.user, tenant: tokens.current_tenant, access_token: access };
        }
      } catch (e) {
        console.warn("[WowHub] No se pudo rehidratar la sesión:", e);
      }
      return { user, tenant, access_token: access };
    })();
    return this._sessionPromise;
  },
};

function formatMoney(cents, currency = "CLP") {
  const value = cents / 100;
  if (currency === "CLP") {
    return new Intl.NumberFormat("es-CL", { style: "currency", currency: "CLP", maximumFractionDigits: 0 }).format(value);
  }
  return new Intl.NumberFormat("es-CL", { style: "currency", currency }).format(value);
}

function formatDate(iso) {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("es-CL", { year: "numeric", month: "short", day: "numeric" });
}

// Auto-refresh on focus
let refreshInterval = null;
function startAutoRefresh() {
  if (refreshInterval) return;
  refreshInterval = setInterval(() => {
    if (Auth.isLoggedIn()) api.tryRefresh();
  }, 14 * 60 * 1000); // 14 min
}
if (Auth.isLoggedIn()) startAutoRefresh();

// Expose
window.WH = { api, publicApi, Toast, Upload, ImagePicker, Auth, TokenStore, formatMoney, formatDate, startAutoRefresh };
