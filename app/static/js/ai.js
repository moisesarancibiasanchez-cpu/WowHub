/* AI Core — chat UI (vanilla JS, sin framework) */
(function () {
  "use strict";

  // ── Estado ─────────────────────────────────────
  const state = {
    conversationId: null,
    agent: "marketing",   // agente por defecto
    sending: false,
    limit: 100,
    used: 0,
  };

  const $ = (id) => document.getElementById(id);
  const thread = $("ai-thread");
  const input  = $("ai-input");
  const composer = $("ai-composer");

  // ── Auth helpers (reutiliza WH.api y WH.Auth si existen) ──
  function authHeader() {
    // El API client global ya adjunta Authorization
    return null;
  }

  async function aiApi(path, opts = {}) {
    const method = (opts.method || "GET").toUpperCase();
    // Bypass total del cliente global: fetch directo con headers correctos.
    // (El cliente global en app.js usa spread de opts que en algunos navegadores
    //  pierde el body cuando se pasa como objeto → Pydantic recibía "[object Object]")
    const token = (window.WH && window.WH.TokenStore && window.WH.TokenStore.access)
      ? window.WH.TokenStore.access()
      : localStorage.getItem("wowhub_access_token");
    const tenant = (window.WH && window.WH.TokenStore && window.WH.TokenStore.currentTenant)
      ? window.WH.TokenStore.currentTenant()
      : (() => { try { return JSON.parse(localStorage.getItem("wowhub_current_tenant")); } catch { return null; } })();
    const headers = Object.assign(
      { "Accept": "application/json" },
      opts.headers || {},
    );
    if (token) headers["Authorization"] = "Bearer " + token;
    if (tenant && tenant.tenant_id) headers["X-Tenant-Id"] = tenant.tenant_id;
    let body;
    if (opts.body !== undefined && opts.body !== null) {
      headers["Content-Type"] = "application/json";
      body = typeof opts.body === "string" ? opts.body : JSON.stringify(opts.body);
    }
    const r = await fetch(path, { method, headers, body });
    if (!r.ok) {
      const text = await r.text();
      throw new Error("HTTP " + r.status + ": " + text.slice(0, 500));
    }
    return r.status === 204 ? null : r.json();
  }

  // ── Render: mensajes ──────────────────────────
  function escapeHtml(s) {
    return (s || "").replace(/[&<>"']/g, (c) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[c]));
  }

  function renderUserMsg(text) {
    const tpl = $("tpl-msg-user");
    const node = tpl.content.firstElementChild.cloneNode(true);
    node.querySelector(".ai-msg-bubble").textContent = text;
    thread.appendChild(node);
    scrollToBottom();
    return node;
  }

  function renderAssistantMsg(meta, text, opts = {}) {
    const tpl = $("tpl-msg-assistant");
    const node = tpl.content.firstElementChild.cloneNode(true);
    const metaEl = node.querySelector(".ai-msg-meta");
    const bubble = node.querySelector(".ai-msg-bubble");
    const labels = {
      marketing: "🎨 Marketing Studio",
      growth: "📈 Growth Coach",
      automation: "⚙️ Automation Manager",
      marketplace: "🛒 Smart Marketplace",
    };
    metaEl.innerHTML = `<span>${labels[meta] || meta}</span>` +
      (opts.fallback ? ' · <span style="color:var(--ai-warn)">fallback</span>' : "") +
      (opts.latency_ms ? ` · <span>${opts.latency_ms}ms</span>` : "");
    bubble.innerHTML = formatMarkdown(text || "");
    if (opts.fallback) bubble.classList.add("ai-msg-fallback");
    if (opts.typing) node.classList.add("ai-msg-typing");
    thread.appendChild(node);
    scrollToBottom();
    return node;
  }

  function formatMarkdown(s) {
    // Mini-markdown: **bold**, *italic*, saltos de línea, listas con -
    s = escapeHtml(s);
    s = s.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    s = s.replace(/\*([^*]+)\*/g, "<em>$1</em>");
    s = s.replace(/^(- .+)$/gm, "<div>• $1.slice(2)</div>".replace("$1.slice(2)", ""));
    s = s.replace(/^- (.+)$/gm, "<div>• $1</div>");
    s = s.replace(/\n/g, "<br>");
    return s;
  }

  function scrollToBottom() {
    thread.scrollTop = thread.scrollHeight;
  }

  // ── Limpia mensajes de error de Pydantic/FastAPI ──
  function prettyError(e) {
    const raw = (e && e.message) || String(e);
    // FastAPI 422: detalle es un array de objetos
    const m = raw.match(/HTTP\s+(\d+):\s*(\[.*\])/s);
    if (m) {
      try {
        const arr = JSON.parse(m[2]);
        if (Array.isArray(arr) && arr[0] && arr[0].msg) {
          const code = m[1];
          const msgs = arr.map((x) => x.msg).filter(Boolean);
          if (code === "422") {
            return "La solicitud no es válida. Revisa los datos enviados e inténtalo de nuevo.";
          }
          return `Error ${code}: ${msgs.join("; ")}`;
        }
      } catch (_) {}
    }
    // Errores específicos
    if (/401/.test(raw))  return "Tu sesión expiró. Inicia sesión de nuevo.";
    if (/403/.test(raw))  return "No tienes permisos para esta acción.";
    if (/404/.test(raw))  return "Recurso no encontrado.";
    if (/429/.test(raw))  return "Has alcanzado el límite diario de mensajes.";
    if (/5\d\d/.test(raw)) return "El servicio está teniendo problemas. Intenta en unos segundos.";
    return raw.replace(/^HTTP\s+\d+:\s*/, "").slice(0, 200);
  }

  // ── Conversaciones ────────────────────────────
  async function loadConversations() {
    const list = $("ai-convs");
    try {
      const data = await aiApi("/api/v1/ai/conversations?page=1&page_size=30");
      if (!data.items || !data.items.length) {
        list.innerHTML = '<p class="ai-empty">Sin conversaciones aún. ¡Empieza una!</p>';
        return;
      }
      list.innerHTML = "";
      const tpl = $("tpl-conv-item");
      for (const c of data.items) {
        const node = tpl.content.firstElementChild.cloneNode(true);
        node.dataset.id = c.id;
        node.querySelector(".ai-conv-title").textContent = c.title || "Conversación";
        const dt = c.last_message_at ? new Date(c.last_message_at) : new Date(c.created_at);
        node.querySelector(".ai-conv-meta").textContent =
          `${c.agent || "—"} · ${c.message_count} msgs · ${dt.toLocaleDateString()}`;
        if (state.conversationId === c.id) node.classList.add("ai-active");
        node.addEventListener("click", () => loadConversation(c.id));
        list.appendChild(node);
      }
    } catch (e) {
      list.innerHTML = `<p class="ai-empty">Error: ${escapeHtml(e.message)}</p>`;
    }
  }

  async function loadConversation(id) {
    try {
      const data = await aiApi("/api/v1/ai/conversations/" + id + "/messages?limit=200");
      thread.innerHTML = "";
      for (const m of data.items) {
        if (m.role === "user") renderUserMsg(m.content);
        else if (m.role === "assistant") {
          renderAssistantMsg(m.agent || "assistant", m.content, { fallback: m.fallback });
        }
      }
      state.conversationId = id;
      // Marcar activo en sidebar
      document.querySelectorAll(".ai-conv-item").forEach((n) => {
        n.classList.toggle("ai-active", n.dataset.id === id);
      });
    } catch (e) {
      console.error(e);
      alert("No pude cargar la conversación: " + e.message);
    }
  }

  // ── Agentes ──────────────────────────────────
  function bindAgentChips() {
    document.querySelectorAll(".ai-agent-chip").forEach((chip) => {
      chip.addEventListener("click", () => {
        document.querySelectorAll(".ai-agent-chip").forEach((c) => c.classList.remove("ai-active"));
        chip.classList.add("ai-active");
        state.agent = chip.dataset.agent;
        const labels = {
          marketing: ["Marketing Studio", "Tu copiloto de marketing y promociones."],
          growth:    ["Growth Coach",     "Estrategia y análisis para crecer."],
          automation:["Automation Manager","Automatiza tareas repetitivas."],
          marketplace:["Smart Marketplace","Optimiza tu catálogo y conversiones."],
        };
        $("ai-current-agent").textContent = labels[state.agent][0];
        $("ai-current-sub").textContent   = labels[state.agent][1];
      });
    });
    // Activar el chip por defecto
    const def = document.querySelector(`.ai-agent-chip[data-agent="${state.agent}"]`);
    if (def) def.classList.add("ai-active");
  }

  // ── Status ───────────────────────────────────
  async function loadStatus() {
    try {
      const s = await aiApi("/api/v1/ai/status");
      const pill = $("ai-circuit-pill");
      pill.textContent = "● " + (s.llm_enabled ? "LLM OK" : "LLM no configurado");
      pill.classList.toggle("ai-warn", s.circuit_state === "open");
      pill.classList.toggle("ai-err",  s.circuit_state === "open" || !s.llm_enabled);
      state.limit = s.rate_limit.limit;
      state.used  = s.rate_limit.used_today;
      $("ai-usage").textContent = `Hoy: ${state.used} / ${state.limit} mensajes`;
    } catch (e) {
      $("ai-circuit-pill").textContent = "● Error";
      $("ai-circuit-pill").classList.add("ai-err");
    }
  }

  // ── Sugerencias ──────────────────────────────
  function bindSuggestions() {
    document.querySelectorAll(".ai-suggest").forEach((b) => {
      b.addEventListener("click", () => {
        input.value = b.dataset.prompt;
        input.focus();
        autosize();
      });
    });
  }

  // ── Composer ─────────────────────────────────
  function autosize() {
    input.style.height = "auto";
    input.style.height = Math.min(input.scrollHeight, 200) + "px";
  }

  input.addEventListener("input", autosize);
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      composer.requestSubmit();
    }
  });

  composer.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (state.sending) return;
    const text = input.value.trim();
    if (!text) return;
    input.value = ""; autosize();
    state.sending = true;
    $("ai-send").disabled = true;

    // Ocultar welcome si está visible
    const w = $("ai-welcome"); if (w) w.style.display = "none";

    renderUserMsg(text);
    const placeholder = renderAssistantMsg(state.agent, "…", { typing: true });

    try {
      // Usamos el modo no-streaming por simplicidad y robustez.
      // (El SSE se puede añadir después sin romper el contrato.)
      const body = {
        message: { content: text, conversation_id: state.conversationId, force_agent: state.agent },
        stream: false,
      };
      const resp = await aiApi("/api/v1/ai/chat", { method: "POST", body });
      // Reemplazar placeholder
      placeholder.remove();
      renderAssistantMsg(resp.agent, resp.content, {
        fallback: resp.fallback,
        latency_ms: resp.latency_ms,
      });
      state.conversationId = resp.conversation_id;
      // Refrescar sidebar
      loadConversations();
      loadStatus();
    } catch (e) {
      placeholder.remove();
      renderAssistantMsg(state.agent, "⚠️ " + prettyError(e), { fallback: true });
    } finally {
      state.sending = false;
      $("ai-send").disabled = false;
      input.focus();
    }
  });

  // ── Nueva conversación ──────────────────────
  $("ai-new-chat").addEventListener("click", () => {
    state.conversationId = null;
    thread.innerHTML = "";
    const w = document.createElement("div");
    w.id = "ai-welcome";
    w.className = "ai-welcome";
    w.innerHTML = '<h2>Nueva conversación</h2><p>Pregúntame lo que quieras.</p>';
    thread.appendChild(w);
    input.focus();
  });

  // ── Init ─────────────────────────────────────
  document.addEventListener("DOMContentLoaded", async () => {
    bindAgentChips();
    bindSuggestions();
    await Promise.all([loadConversations(), loadStatus()]);
  });
})();
