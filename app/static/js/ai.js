/* AI Core — Sidebar derecho fijo, siempre visible
   ------------------------------------------------------------------
   - Sin lista de conversaciones (es persistente, vive en backend)
   - Maneja los nuevos bloques: tarjeta de promo, prompt de diseño,
     CTA de subida de imagen
   - Móvil: FAB para reabrir el sidebar cuando está cerrado
   - La barra de escritura NUNCA se oculta (composer con position: sticky)
*/
(function () {
  "use strict";

  // ── Estado ─────────────────────────────────────
  const state = {
    conversationId: null,
    agent: "marketing",
    sending: false,
    limit: 100,
    used: 0,
    pendingImage: null,    // { file, url, name } cuando el usuario adjunta imagen
    pickedPromo: null,     // { title, meta, why } cuando el usuario eligió una promo
  };

  // ── Helpers DOM ────────────────────────────────
  const $ = (id) => document.getElementById(id);
  const thread = $("ai-thread");
  const input  = $("ai-input");
  const composer = $("ai-composer");
  const sidebar = $("ai-sidebar");
  const fab     = $("ai-fab");
  const welcome = $("ai-welcome");
  const suggestions = $("ai-suggestions");
  const usage = $("ai-usage");

  function scrollToBottom() {
    if (!thread) return;
    thread.scrollTop = thread.scrollHeight;
  }

  function escapeHtml(s) {
    return (s || "").replace(/[&<>"']/g, (c) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[c]));
  }

  // ── API ────────────────────────────────────────
  async function aiApi(path, opts = {}) {
    const method = (opts.method || "GET").toUpperCase();
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

  function currentTenantId() {
    if (window.WH && window.WH.TokenStore && window.WH.TokenStore.currentTenant) {
      const t = window.WH.TokenStore.currentTenant();
      return t && t.tenant_id;
    }
    try { return JSON.parse(localStorage.getItem("wowhub_current_tenant")).tenant_id; }
    catch { return null; }
  }

  function prettyError(e) {
    const raw = (e && e.message) || String(e);
    const m = raw.match(/HTTP\s+(\d+):\s*(\[.*\])/s);
    if (m) {
      try {
        const arr = JSON.parse(m[2]);
        if (Array.isArray(arr) && arr[0] && arr[0].msg) {
          if (m[1] === "422") return "La solicitud no es válida. Revisa los datos enviados.";
          return `Error ${m[1]}: ${arr.map((x) => x.msg).filter(Boolean).join("; ")}`;
        }
      } catch (_) {}
    }
    if (/401/.test(raw))  return "Tu sesión expiró. Inicia sesión de nuevo.";
    if (/403/.test(raw))  return "No tienes permisos para esta acción.";
    if (/404/.test(raw))  return "Recurso no encontrado.";
    if (/429/.test(raw))  return "Has alcanzado el límite diario de mensajes.";
    if (/5\d\d/.test(raw)) return "El servicio está teniendo problemas. Intenta en unos segundos.";
    return raw.replace(/^HTTP\s+\d+:\s*/, "").slice(0, 200);
  }

  // ── Render: mensajes ──────────────────────────
  function renderUserMsg(text) {
    const tpl = $("tpl-msg-user");
    if (!tpl) return null;
    const node = tpl.content.firstElementChild.cloneNode(true);
    node.querySelector(".ai-msg-bubble").textContent = text;
    thread.appendChild(node);
    scrollToBottom();
    return node;
  }

  function renderAssistantMsg(text, opts = {}) {
    const tpl = $("tpl-msg-assistant");
    if (!tpl) return null;
    const node = tpl.content.firstElementChild.cloneNode(true);
    const bubble = node.querySelector(".ai-msg-bubble");
    bubble.innerHTML = formatMarkdown(text || "");
    if (opts.fallback) bubble.classList.add("ai-msg-fallback");
    if (opts.typing) node.classList.add("ai-msg-typing");
    thread.appendChild(node);
    scrollToBottom();
    return node;
  }

  function formatMarkdown(s) {
    s = escapeHtml(s);
    s = s.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    s = s.replace(/\*([^*]+)\*/g, "<em>$1</em>");
    s = s.replace(/^- (.+)$/gm, "<div>• $1</div>");
    s = s.replace(/\n/g, "<br>");
    return s;
  }

  // ── Render: tarjeta de opción de promoción ────
  function renderPromoCard(option) {
    const tpl = $("tpl-msg-promo-card");
    if (!tpl) return null;
    const node = tpl.content.firstElementChild.cloneNode(true);
    node.querySelector(".ai-promo-card-title").textContent = option.title || option.name || "Opción";
    node.querySelector(".ai-promo-card-meta").textContent  = option.meta || option.summary || "";
    node.querySelector(".ai-promo-card-why").textContent   = option.why  || option.reason || "";
    const btn = node.querySelector(".ai-promo-pick");
    if (btn) {
      btn.dataset.title = option.title || option.name || "";
      btn.dataset.meta  = option.meta  || option.summary || "";
      btn.dataset.why   = option.why   || option.reason || "";
    }
    thread.appendChild(node);
    scrollToBottom();
    return node;
  }

  // ── Render: prompt de diseño (copia y pega) ──
  function renderDesignPrompt(promptText) {
    const tpl = $("tpl-msg-design-prompt");
    if (!tpl) return null;
    const node = tpl.content.firstElementChild.cloneNode(true);
    node.querySelector(".ai-design-prompt-body").textContent = promptText || "";
    thread.appendChild(node);
    scrollToBottom();
    return node;
  }

  // ── Render: CTA para subir imagen (paso 3) ────
  function renderUploadCta() {
    const tpl = $("tpl-msg-image-upload");
    if (!tpl) return null;
    const node = tpl.content.firstElementChild.cloneNode(true);
    thread.appendChild(node);
    scrollToBottom();
    return node;
  }

  // ── Detección: el orquestador devuelve un string con bloques ─
  // Formato simple de los nuevos prompts:
  //   :::promo|{"title":"…","meta":"…","why":"…"}:::
  //   :::promo|{...}:::
  //   :::design|texto del prompt:::
  //   :::upload:::
  // Esto permite al LLM emitir bloques estructurados sin complicar
  // el JSON de respuesta.
  function parseBlocks(content) {
    if (!content) return { text: "", promos: [], design: null, upload: false };
    let text = content;
    const promos = [];
    let design = null;
    let upload = false;

    const promoRe = /:::promo\|([\s\S]*?):::/g;
    text = text.replace(promoRe, (_, json) => {
      try {
        const obj = JSON.parse(json);
        promos.push(obj);
      } catch (e) { /* ignore */ }
      return "";
    });

    const designRe = /:::design\|([\s\S]*?):::/g;
    text = text.replace(designRe, (_, body) => {
      design = (body || "").trim();
      return "";
    });

    const uploadRe = /:::upload:::/g;
    text = text.replace(uploadRe, () => {
      upload = true;
      return "";
    });

    return { text: text.trim(), promos, design, upload };
  }

  // ── Estado de UI ──────────────────────────────
  function hideWelcomeAndSuggestions() {
    if (welcome) welcome.style.display = "none";
    if (suggestions) suggestions.style.display = "none";
  }

  function resetConversationUI() {
    if (!thread) return;
    thread.innerHTML = "";
    if (welcome) {
      welcome.style.display = "";
    }
    if (suggestions) suggestions.style.display = "";
    state.conversationId = null;
    state.pendingImage = null;
    state.pickedPromo = null;
    setAttachUI();
  }

  // ── Adjuntar imagen (en el composer) ──────────
  function setAttachUI() {
    const nameEl = $("ai-attach-name");
    const btn = $("ai-attach-btn");
    if (state.pendingImage) {
      if (nameEl) {
        nameEl.textContent = "📎 " + (state.pendingImage.name || "imagen");
        nameEl.hidden = false;
      }
      if (btn) btn.classList.add("is-active");
    } else {
      if (nameEl) { nameEl.textContent = ""; nameEl.hidden = true; }
      if (btn) btn.classList.remove("is-active");
    }
  }

  function pickImageFile(file) {
    if (!file) return;
    if (!file.type || !file.type.startsWith("image/")) {
      alert("Solo se permiten imágenes (JPG, PNG, WebP).");
      return;
    }
    if (file.size > 8 * 1024 * 1024) {
      alert("La imagen es muy pesada. Máximo 8 MB.");
      return;
    }
    state.pendingImage = { file, name: file.name };
    setAttachUI();
  }

  // ── Carga de imagen al backend ────────────────
  async function uploadImageToServer(file) {
    const tenantId = currentTenantId();
    if (!tenantId) throw new Error("No hay tenant activo");
    const fd = new FormData();
    fd.append("file", file);
    fd.append("purpose", "promotion");
    const token = (window.WH && window.WH.TokenStore && window.WH.TokenStore.access)
      ? window.WH.TokenStore.access()
      : localStorage.getItem("wowhub_access_token");
    const r = await fetch(`/api/v1/tenants/${tenantId}/uploads`, {
      method: "POST",
      headers: {
        "Authorization": "Bearer " + token,
        "X-Tenant-Id": tenantId,
      },
      body: fd,
    });
    if (!r.ok) {
      const t = await r.text();
      throw new Error("HTTP " + r.status + ": " + t.slice(0, 300));
    }
    return r.json();
  }

  // ── Crear promoción en el backend ─────────────
  async function createPromotionServer(payload) {
    const tenantId = currentTenantId();
    if (!tenantId) throw new Error("No hay tenant activo");
    return aiApi(`/api/v1/tenants/${tenantId}/promotions`, {
      method: "POST",
      body: payload,
    });
  }

  // ── Agentes ───────────────────────────────────
  const AGENT_LABELS = {
    marketing:  { name: "Asistente de Marketing", sub: "Te ayuda a crear promociones y avisos." },
    growth:     { name: "Asistente de Crecimiento", sub: "Te ayuda a entender tus ventas y crecer." },
    automation: { name: "Asistente de Tareas", sub: "Te ayuda a enviar mensajes automáticos." },
    marketplace:{ name: "Asistente de Catálogo", sub: "Te ayuda a ordenar productos y precios." },
  };

  function bindAgentChips() {
    document.querySelectorAll(".ai-agent-chip").forEach((chip) => {
      chip.addEventListener("click", () => {
        document.querySelectorAll(".ai-agent-chip").forEach((c) => c.classList.remove("ai-active"));
        chip.classList.add("ai-active");
        state.agent = chip.dataset.agent;
        const labels = AGENT_LABELS[state.agent] || AGENT_LABELS.marketing;
        const nameEl = $("ai-current-agent");
        const subEl  = $("ai-current-sub");
        if (nameEl) nameEl.textContent = labels.name;
        if (subEl)  subEl.textContent  = labels.sub;
      });
    });
    // Activar chip por defecto
    const def = document.querySelector(`.ai-agent-chip[data-agent="${state.agent}"]`);
    if (def) def.classList.add("ai-active");
  }

  // ── Status / uso diario ───────────────────────
  async function loadStatus() {
    try {
      const s = await aiApi("/api/v1/ai/status");
      state.limit = s.rate_limit.limit;
      state.used  = s.rate_limit.used_today;
      if (usage) usage.textContent = `Hoy: ${state.used} / ${state.limit} mensajes`;
    } catch (e) {
      if (usage) usage.textContent = "Hoy: —";
    }
  }

  // ── Sugerencias ──────────────────────────────
  function bindSuggestions() {
    document.querySelectorAll(".ai-suggest").forEach((b) => {
      b.addEventListener("click", () => {
        if (input) {
          input.value = b.dataset.prompt || b.textContent.trim();
          input.focus();
          autosize();
        }
      });
    });
  }

  // ── Composer ─────────────────────────────────
  function autosize() {
    if (!input) return;
    input.style.height = "auto";
    input.style.height = Math.min(input.scrollHeight, 120) + "px";
  }

  if (input) input.addEventListener("input", autosize);
  if (input) input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (composer) composer.requestSubmit();
    }
  });

  if (composer) composer.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (state.sending) return;
    const text = (input.value || "").trim();
    if (!text && !state.pendingImage) return;

    state.sending = true;
    const sendBtn = $("ai-send");
    if (sendBtn) sendBtn.disabled = true;

    hideWelcomeAndSuggestions();

    // Si el usuario eligió una opción de promoción y subió imagen,
    // construimos el texto con contexto para el backend.
    let composedText = text;
    if (state.pickedPromo) {
      const tag = `[OPCIÓN ELEGIDA: ${state.pickedPromo.title}` +
        (state.pickedPromo.meta ? ` (${state.pickedPromo.meta})` : "") + "]";
      composedText = (composedText ? composedText + "\n\n" : "") + tag;
    }
    if (state.pendingImage) {
      composedText = (composedText ? composedText + "\n\n" : "") +
        "[El usuario adjuntó una imagen: " + state.pendingImage.name + "]";
    }

    // Mostrar en el chat
    let userLabel = text;
    if (state.pickedPromo && !userLabel) userLabel = "Elegí: " + state.pickedPromo.title;
    if (state.pendingImage && !userLabel) userLabel = "📎 " + state.pendingImage.name;
    if (!userLabel) userLabel = "…";
    renderUserMsg(userLabel);

    const placeholder = renderAssistantMsg("…", { typing: true });

    try {
      const body = {
        message: { content: composedText, conversation_id: state.conversationId, force_agent: state.agent },
        stream: false,
      };
      const resp = await aiApi("/api/v1/ai/chat", { method: "POST", body });
      placeholder.remove();
      state.conversationId = resp.conversation_id;

      const { text: cleanText, promos, design, upload } = parseBlocks(resp.content);
      renderAssistantMsg(cleanText || resp.content, {
        fallback: resp.fallback,
      });
      promos.forEach((p) => renderPromoCard(p));
      if (design) renderDesignPrompt(design);
      if (upload) renderUploadCta();

      // Limpiar inputs
      input.value = "";
      autosize();
      state.pendingImage = null;
      state.pickedPromo = null;
      setAttachUI();
      loadStatus();
    } catch (e) {
      placeholder.remove();
      renderAssistantMsg("⚠️ " + prettyError(e), { fallback: true });
    } finally {
      state.sending = false;
      if (sendBtn) sendBtn.disabled = false;
      if (input) input.focus();
    }
  });

  // ── Adjuntar imagen desde el composer ─────────
  const attachBtn = $("ai-attach-btn");
  const attachInput = $("ai-attach-input");
  if (attachBtn && attachInput) {
    attachBtn.addEventListener("click", () => attachInput.click());
    attachInput.addEventListener("change", (e) => {
      const f = e.target.files && e.target.files[0];
      if (f) pickImageFile(f);
      // Permite re-seleccionar el mismo archivo
      e.target.value = "";
    });
  }

  // ── Click handler delegado para mensajes especiales ──
  if (thread) {
    thread.addEventListener("click", async (e) => {
      const target = e.target;
      if (!(target instanceof HTMLElement)) return;

      // 1) Botón "Elegir esta opción" en tarjeta de promo
      const pickBtn = target.closest(".ai-promo-pick");
      if (pickBtn) {
        state.pickedPromo = {
          title: pickBtn.dataset.title || "",
          meta:  pickBtn.dataset.meta  || "",
          why:   pickBtn.dataset.why   || "",
        };
        if (input) {
          input.value = "Quiero esta promoción. Ahora dame el prompt de diseño.";
          input.focus();
          autosize();
        }
        // Feedback visual: marcar elegida
        thread.querySelectorAll(".ai-promo-card").forEach((c) => c.classList.remove("ai-picked"));
        pickBtn.closest(".ai-promo-card").classList.add("ai-picked");
        return;
      }

      // 2) Botón "Copiar prompt"
      const copyBtn = target.closest(".ai-copy-prompt");
      if (copyBtn) {
        const pre = copyBtn.parentElement.querySelector(".ai-design-prompt-body");
        if (pre) {
          try {
            await navigator.clipboard.writeText(pre.textContent || "");
            copyBtn.classList.add("is-copied");
            copyBtn.textContent = "✓ Copiado";
            setTimeout(() => {
              copyBtn.classList.remove("is-copied");
              copyBtn.textContent = "Copiar prompt";
            }, 2000);
          } catch (err) {
            // Fallback
            const ta = document.createElement("textarea");
            ta.value = pre.textContent || "";
            document.body.appendChild(ta);
            ta.select();
            try { document.execCommand("copy"); } catch (_) {}
            document.body.removeChild(ta);
            copyBtn.classList.add("is-copied");
            copyBtn.textContent = "✓ Copiado";
            setTimeout(() => {
              copyBtn.classList.remove("is-copied");
              copyBtn.textContent = "Copiar prompt";
            }, 2000);
          }
        }
        return;
      }

      // 3) Input de subida de imagen (dentro del CTA)
      const fileInput = target.closest(".ai-upload-cta-input");
      if (fileInput) {
        // Dejamos que el <label> abra el file picker, y manejamos el change globalmente
      }
    });

    // Handler global para los inputs de subida de los CTAs
    thread.addEventListener("change", async (e) => {
      const target = e.target;
      if (!(target instanceof HTMLInputElement)) return;
      if (!target.classList.contains("ai-upload-cta-input")) return;
      const file = target.files && target.files[0];
      if (!file) return;
      const cta = target.closest(".ai-upload-cta");
      const titleEl = cta ? cta.querySelector(".ai-upload-cta-title") : null;
      if (titleEl) titleEl.textContent = "Subiendo imagen…";
      try {
        const up = await uploadImageToServer(file);
        if (titleEl) {
          titleEl.textContent = "✅ Imagen subida";
        }
        // Opcional: enviamos al backend para que la IA confirme la creación de la promo
        if (state.pickedPromo) {
          renderAssistantMsg(
            "Recibí tu imagen. Cuando confirmes, creo la promoción con el nombre **" +
            state.pickedPromo.title + "** y esta imagen."
          );
        }
        // Guardamos la URL en el state por si luego queremos crear la promo automáticamente
        state.pendingImage = {
          file,
          name: file.name,
          url: up && (up.public_url || up.url) || null,
          uploadId: up && (up.id || up.upload_id) || null,
        };
      } catch (err) {
        if (titleEl) titleEl.textContent = "❌ No pude subirla";
        renderAssistantMsg("⚠️ Error subiendo la imagen: " + prettyError(err), { fallback: true });
      } finally {
        target.value = "";
      }
    });
  }

  // ── Nueva conversación ──────────────────────
  const newChatBtn = $("ai-new-chat");
  if (newChatBtn) {
    newChatBtn.addEventListener("click", () => {
      resetConversationUI();
      if (input) input.focus();
    });
  }

  // ── Móvil: FAB + cerrar con click fuera ─────
  function openSidebarMobile() {
    if (!sidebar) return;
    sidebar.classList.add("ai-open");
    if (fab) fab.classList.add("ai-hidden");
  }
  function closeSidebarMobile() {
    if (!sidebar) return;
    sidebar.classList.remove("ai-open");
    if (fab) fab.classList.remove("ai-hidden");
  }
  if (fab) fab.addEventListener("click", openSidebarMobile);

  // ── Maximizar / Restaurar (pantalla completa del chat) ──
  // Cuando se maximiza, el AI sidebar ocupa todo el espacio entre el
  // sidebar izquierdo y el borde derecho. El sidebar izquierdo y el
  // topbar SIGUEN VISIBLES. El contenido central (.dash-main) se oculta.
  function isMaximized() {
    return sidebar && sidebar.classList.contains("ai-maximized");
  }
  function applyMaximizedUI() {
    const max = isMaximized();
    const maxBtn = $("ai-maximize");
    const fullBtn = $("ai-fullscreen-btn");
    const fullLabel = fullBtn ? fullBtn.querySelector(".ai-fullscreen-label") : null;
    // Cambiar aria/title para accesibilidad
    if (maxBtn) {
      maxBtn.setAttribute("aria-label", max ? "Restaurar a sidebar" : "Expandir a toda la ventana");
      maxBtn.setAttribute("title", max ? "Restaurar a sidebar" : "Expandir a toda la ventana");
    }
    if (fullBtn) {
      fullBtn.setAttribute("aria-label", max ? "Restaurar a sidebar" : "Expandir a toda la ventana");
      fullBtn.setAttribute("title", max ? "Restaurar a sidebar" : "Expandir a toda la ventana");
      if (fullLabel) fullLabel.textContent = max ? "Restaurar" : "Pantalla completa";
    }
  }
  function toggleMaximize() {
    if (!sidebar) return;
    sidebar.classList.toggle("ai-maximized");
    applyMaximizedUI();
    // Si el chat estaba al fondo, se queda al fondo al expandir.
    scrollToBottom();
    if (input) input.focus();
  }
  const maxBtnHeader = $("ai-maximize");
  const fullBtnBottom = $("ai-fullscreen-btn");
  if (maxBtnHeader) maxBtnHeader.addEventListener("click", toggleMaximize);
  if (fullBtnBottom) fullBtnBottom.addEventListener("click", toggleMaximize);
  // Atajo: Esc restaura si está maximizado
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && isMaximized()) {
      toggleMaximize();
    }
  });
  // Estado inicial de la UI (por si el browser recuerda la clase)
  applyMaximizedUI();

  // ── Historial de conversaciones ─────────────────────
  // Lista de conversaciones previas (cargadas del backend) y helpers
  // para abrir el drawer, cargar mensajes, eliminar, etc.
  const historyPanel  = $("ai-history");
  const historyList   = $("ai-history-list");
  const historyEmpty  = $("ai-history-empty");
  const historyBtn    = $("ai-history-btn");
  const historyBack   = $("ai-history-back");
  const historyNewBtn = $("ai-history-new");

  // Mapeo de agentes → emoji + nombre corto
  const AGENT_GLYPH = {
    marketing:    "🎨",
    growth:       "📈",
    automation:   "✉️",
    marketplace:  "🛒",
    router:       "🧭",
  };
  const AGENT_NAME = {
    marketing:    "Marketing",
    growth:       "Crecimiento",
    automation:   "Tareas",
    marketplace:  "Catálogo",
    router:       "Router",
  };

  function showHistoryPanel() {
    if (!historyPanel) return;
    historyPanel.hidden = false;
    loadConversationList();
  }
  function hideHistoryPanel() {
    if (!historyPanel) return;
    historyPanel.hidden = true;
  }
  function isHistoryOpen() {
    return historyPanel && !historyPanel.hidden;
  }

  function formatRelativeDate(iso) {
    if (!iso) return "";
    const d = new Date(iso);
    if (isNaN(d.getTime())) return "";
    const now = new Date();
    const diffMs = now - d;
    const diffMin = Math.floor(diffMs / 60000);
    const diffH = Math.floor(diffMs / 3600000);
    const diffD = Math.floor(diffMs / 86400000);
    if (diffMin < 1)  return "ahora";
    if (diffMin < 60) return `hace ${diffMin} min`;
    if (diffH  < 24)  return `hace ${diffH} h`;
    if (diffD === 1)  return "ayer";
    if (diffD < 7)    return `hace ${diffD} días`;
    return d.toLocaleDateString("es", { day: "numeric", month: "short" });
  }

  function renderHistoryItem(conv) {
    const tpl = $("tpl-history-item");
    if (!tpl) return null;
    const node = tpl.content.firstElementChild.cloneNode(true);
    node.dataset.id    = conv.id;
    node.dataset.agent = conv.agent || "marketing";
    const titleEl = node.querySelector(".ai-history-item-title");
    const metaEl  = node.querySelector(".ai-history-item-meta");
    const iconEl  = node.querySelector(".ai-history-item-icon");
    if (titleEl) titleEl.textContent = conv.title || "Nueva conversación";
    if (iconEl)  iconEl.textContent  = AGENT_GLYPH[conv.agent] || "💬";
    if (metaEl) {
      const agentName = AGENT_NAME[conv.agent] || "Asistente";
      const count = conv.message_count || 0;
      const rel = formatRelativeDate(conv.last_message_at || conv.created_at);
      metaEl.innerHTML = `<span>${agentName}</span><span>·</span><span>${count} ${count === 1 ? "msg" : "msgs"}</span>` + (rel ? `<span>·</span><span>${rel}</span>` : "");
    }
    // Marcar activa si es la actual
    if (state.conversationId && String(state.conversationId) === String(conv.id)) {
      node.classList.add("is-active");
    }
    return node;
  }

  async function loadConversationList() {
    if (!historyList) return;
    historyList.innerHTML = "";
    const loading = document.createElement("div");
    loading.className = "ai-history-empty";
    loading.innerHTML = '<p>Cargando conversaciones…</p>';
    historyList.appendChild(loading);
    try {
      const data = await aiApi("/api/v1/ai/conversations?page=1&page_size=50");
      historyList.innerHTML = "";
      const items = (data && data.items) || [];
      if (items.length === 0) {
        if (historyEmpty) {
          historyList.appendChild(historyEmpty);
        } else {
          const empty = document.createElement("div");
          empty.className = "ai-history-empty";
          empty.innerHTML = '<div class="ai-history-empty-ico" aria-hidden="true">💬</div><p>Aún no tienes conversaciones guardadas.</p><small>Empieza una nueva conversación y aparecerá aquí.</small>';
          historyList.appendChild(empty);
        }
        return;
      }
      items.forEach((c) => {
        const node = renderHistoryItem(c);
        if (node) historyList.appendChild(node);
      });
    } catch (e) {
      historyList.innerHTML = "";
      const err = document.createElement("div");
      err.className = "ai-history-empty";
      err.innerHTML = '<p>⚠️ No pude cargar las conversaciones.</p><small>' + escapeHtml(prettyError(e)) + '</small>';
      historyList.appendChild(err);
    }
  }

  // Click handler: abrir o eliminar una conversación del historial
  if (historyList) {
    historyList.addEventListener("click", async (e) => {
      const target = e.target;
      if (!(target instanceof HTMLElement)) return;

      // 1) Botón de eliminar (no abre la conversación)
      const delBtn = target.closest(".ai-history-item-del");
      if (delBtn) {
        e.stopPropagation();
        const item = delBtn.closest(".ai-history-item");
        if (!item) return;
        const id = item.dataset.id;
        if (!id) return;
        if (!confirm("¿Eliminar esta conversación? Ya no podrás verla en el historial.")) return;
        try {
          await aiApi(`/api/v1/ai/conversations/${id}`, { method: "DELETE" });
          item.remove();
          // Si era la conversación activa, limpiamos el chat
          if (state.conversationId && String(state.conversationId) === String(id)) {
            resetConversationUI();
          }
          // Si quedó vacío, mostramos el empty
          if (!historyList.querySelector(".ai-history-item")) {
            if (historyEmpty) historyList.appendChild(historyEmpty);
          }
        } catch (err) {
          alert("No pude eliminar la conversación: " + prettyError(err));
        }
        return;
      }

      // 2) Click en el item: abrir la conversación
      const item = target.closest(".ai-history-item");
      if (item) {
        const id = item.dataset.id;
        if (!id) return;
        await openPastConversation(id);
        hideHistoryPanel();
      }
    });
  }

  // Carga los mensajes de una conversación pasada y los pinta en el chat
  async function openPastConversation(conversationId) {
    if (!thread) return;
    // Limpia el chat actual y desactiva el estado "nueva conversación"
    thread.innerHTML = "";
    hideWelcomeAndSuggestions();
    // Mensaje temporal mientras carga
    const loading = renderAssistantMsg("Cargando conversación…", { typing: true });
    state.conversationId = conversationId;
    state.pendingImage = null;
    state.pickedPromo = null;
    setAttachUI();
    try {
      const data = await aiApi(`/api/v1/ai/conversations/${conversationId}/messages?limit=200`);
      loading.remove();
      const items = (data && data.items) || [];
      if (items.length === 0) {
        renderAssistantMsg("Esta conversación no tiene mensajes.");
        return;
      }
      // Renderizamos los mensajes en orden
      let lastAgent = "marketing";
      items.forEach((m) => {
        if (m.role === "user") {
          renderUserMsg(m.content || "");
        } else if (m.role === "assistant") {
          renderAssistantMsg(m.content || "");
          if (m.agent) lastAgent = m.agent;
        }
        // role "tool" y "system" los ignoramos en la vista del usuario
      });
      // Sincronizar el chip de agente activo
      const chip = document.querySelector(`.ai-agent-chip[data-agent="${lastAgent}"]`);
      if (chip) {
        document.querySelectorAll(".ai-agent-chip").forEach((c) => c.classList.remove("ai-active"));
        chip.classList.add("ai-active");
        state.agent = lastAgent;
        const labels = AGENT_LABELS[state.agent] || AGENT_LABELS.marketing;
        const nameEl = $("ai-current-agent");
        const subEl  = $("ai-current-sub");
        if (nameEl) nameEl.textContent = labels.name;
        if (subEl)  subEl.textContent  = labels.sub;
      }
      scrollToBottom();
    } catch (err) {
      loading.remove();
      renderAssistantMsg("⚠️ " + prettyError(err), { fallback: true });
    }
  }

  // Botones del drawer de historial
  if (historyBtn) {
    historyBtn.addEventListener("click", () => {
      if (isHistoryOpen()) hideHistoryPanel();
      else showHistoryPanel();
    });
  }
  if (historyBack) {
    historyBack.addEventListener("click", hideHistoryPanel);
  }
  if (historyNewBtn) {
    historyNewBtn.addEventListener("click", () => {
      hideHistoryPanel();
      resetConversationUI();
      if (input) input.focus();
    });
  }

  // ── Init ─────────────────────────────────────
  document.addEventListener("DOMContentLoaded", () => {
    bindAgentChips();
    bindSuggestions();
    loadStatus();
    autosize();
  });
})();
