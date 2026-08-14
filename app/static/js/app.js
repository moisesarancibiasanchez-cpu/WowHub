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
window.WH = { api, publicApi, Toast, Auth, TokenStore, formatMoney, formatDate, startAutoRefresh };
