"""
Tests del refactor de modales del dashboard.

Cubre:
  1. Contrato estático: app.js expone Modal, Confirm, debounce, escapeHtml,
     Auth.resetSession.
  2. CSS: las clases .wh-modal-* existen.
  3. products.html: usa WH.Modal / WH.Confirm / WH.escapeHtml y NO usa
     `confirm(` nativo ni el viejo `.modal-overlay hidden`.
  4. costs.js: el bug `_tenantId = t.id` está arreglado (ahora `t.tenant_id`).
  5. Funcional (Node): Modal/Confirm/debounce/escapeHtml se comportan bien.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
APP_JS = REPO / "app" / "static" / "js" / "app.js"
APP_CSS = REPO / "app" / "static" / "css" / "app.css"
COSTS_JS = REPO / "app" / "static" / "js" / "costs.js"
PRODUCTS_HTML = REPO / "app" / "templates" / "dashboard" / "products.html"


# ── 1. app.js expone la API nueva ─────────────────────────
class TestAppJsExports:
    @pytest.fixture
    def source(self):
        return APP_JS.read_text(encoding="utf-8")

    def test_app_js_exists(self):
        assert APP_JS.exists(), "app.js debe existir"

    def test_escapeHtml_is_defined(self, source):
        assert re.search(r"function\s+escapeHtml\s*\(", source), \
            "Falta `function escapeHtml(...)` en app.js"

    def test_debounce_is_defined(self, source):
        assert re.search(r"function\s+debounce\s*\(", source), \
            "Falta `function debounce(...)` en app.js"

    def test_Modal_module_is_defined(self, source):
        assert re.search(r"const\s+Modal\s*=\s*\(function", source), \
            "Falta `const Modal = (function ...)` en app.js"

    def test_Confirm_module_is_defined(self, source):
        assert re.search(r"const\s+Confirm\s*=\s*\{", source), \
            "Falta `const Confirm = { ... }` en app.js"

    def test_Auth_resetSession_is_defined(self, source):
        assert re.search(r"resetSession\s*\(\s*\)\s*\{", source), \
            "Falta `Auth.resetSession()` en app.js"

    def test_Auth_logout_calls_resetSession(self, source):
        # El bloque de logout debe invalidar la sesión cacheada
        m = re.search(r"async\s+logout\s*\(\s*\)\s*\{(.*?)\n\s*\}", source, re.S)
        assert m, "Falta el bloque async logout() en Auth"
        assert "resetSession" in m.group(1), \
            "Auth.logout debe llamar a this.resetSession() para invalidar el cache"

    def test_window_WH_exports_new_helpers(self, source):
        # El export final debe listar los nuevos miembros
        m = re.search(r"window\.WH\s*=\s*\{(.*?)\}", source, re.S)
        assert m, "Falta window.WH = { ... }"
        body = m.group(1)
        for name in ("Modal", "Confirm", "debounce", "escapeHtml", "escapeAttr"):
            assert name in body, f"window.WH no expone {name!r}"

    def test_no_dead_precedence_bug(self, source):
        # El bug original era `!path.startsWith(...) === false` ejecutado
        # dentro de un `if`. Verificamos que NO exista un `if` que use ese
        # patrón exacto (ignorando los comentarios que sí pueden explicarlo).
        # Quitamos los `// ...` antes de buscar.
        code = re.sub(r"//[^\n]*", "", source)
        assert not re.search(r"if\s*\(.*!path\.startsWith.*===\s*false", code, re.S), \
            "Sigue presente el `if (!path.startsWith(...) === false)` muerto"


# ── 2. app.css tiene los estilos del modal nuevo ─────────
class TestAppCssModal:
    @pytest.fixture
    def source(self):
        return APP_CSS.read_text(encoding="utf-8")

    def test_css_exists(self):
        assert APP_CSS.exists()

    def test_wh_modal_overlay_styled(self, source):
        assert re.search(r"\.wh-modal-overlay\s*\{", source)
        # Tomamos sólo el bloque hasta el primer `}` y verificamos que
        # tenga `position: fixed` (sin escape regex, comparación literal).
        block = source.split("wh-modal-overlay", 1)[1].split("}", 1)[0]
        assert "position: fixed" in block
        assert "inset: 0" in block

    def test_wh_modal_dialog_styled(self, source):
        assert re.search(r"\.wh-modal-dialog\s*\{", source)

    def test_wh_modal_size_lg(self, source):
        assert re.search(r"\.wh-modal-dialog\.wh-modal-lg\s*\{", source)

    def test_wh_modal_anim_keyframes(self, source):
        assert "@keyframes wh-modal-fade" in source
        assert "@keyframes wh-modal-slide" in source

    def test_btn_danger_styled(self, source):
        assert re.search(r"\.btn\.btn-danger\s*\{", source), \
            "Falta el estilo de .btn.btn-danger (usado por WH.Confirm)"


# ── 3. products.html usa la nueva API ─────────────────────
class TestProductsHtmlContract:
    @pytest.fixture
    def source(self):
        return PRODUCTS_HTML.read_text(encoding="utf-8")

    def test_products_html_exists(self):
        assert PRODUCTS_HTML.exists()

    def test_uses_WH_Modal_open(self, source):
        assert re.search(r"\bModal\.open\s*\(", source), \
            "products.html debe usar `Modal.open(...)`"

    def test_uses_WH_Confirm_show(self, source):
        assert re.search(r"\bConfirm\.show\s*\(", source), \
            "products.html debe usar `Confirm.show(...)`"

    def test_uses_WH_escapeHtml(self, source):
        assert "escapeHtml" in source, \
            "products.html debe escapar datos del backend con escapeHtml"

    def test_no_native_confirm(self, source):
        # Antes había `if (!confirm(...))` que era inaccesible.
        # Permitimos la palabra "confirm" sólo dentro de strings o nombres
        # como `WH.Confirm`. La forma prohibida es `confirm(` como llamada.
        assert not re.search(r"(?<!\w)confirm\s*\(", source), \
            "products.html no debe llamar a `confirm(` nativo"

    def test_no_legacy_modal_overlay(self, source):
        # El modal viejo estaba marcado con `class="modal-overlay hidden"`.
        # Tras el refactor no debe quedar esa marca en el HTML servido.
        assert 'class="modal-overlay hidden"' not in source
        assert "modal-overlay" not in source, \
            "products.html no debe seguir usando `.modal-overlay` legacy"

    def test_form_is_in_template(self, source):
        # El form debe estar en un <template> para clonarlo al abrir el modal.
        assert re.search(r'<template\s+id="product-form-tpl"', source), \
            "Falta <template id=\"product-form-tpl\"> para clonar el form"

    def test_uses_WH_debounce(self, source):
        assert "debounce(" in source, \
            "products.html debe usar la versión canónica `debounce` de WH"

    def test_danger_modal_size(self, source):
        # El modal de edición debe pedir tamaño `lg` (es ancho)
        assert re.search(r"size:\s*[\"']lg[\"']", source)


# ── 4. costs.js tiene el fix de tenant_id ────────────────
class TestCostsJsTenantFix:
    @pytest.fixture
    def source(self):
        return COSTS_JS.read_text(encoding="utf-8")

    def test_costs_js_exists(self):
        assert COSTS_JS.exists()

    def test_uses_tenant_id_not_id(self, source):
        # El bloque fetchTenant debe leer t.tenant_id, no t.id. Quitamos
        # los comentarios para que el assert no se confunda con menciones
        # explicativas del bug histórico.
        m = re.search(r"async\s+function\s+fetchTenant\s*\(\s*\)\s*\{(.*?)\n\s*\}", source, re.S)
        assert m, "Falta fetchTenant() en costs.js"
        body = m.group(1)
        # Quitamos los comentarios `//` para no falsear el assert.
        code = re.sub(r"//[^\n]*", "", body)
        assert "t.tenant_id" in code, \
            "fetchTenant debe leer t.tenant_id (no t.id) — bug fix"
        assert "t.id" not in code, \
            "fetchTenant no debe seguir leyendo t.id (causa 'No hay tenant activo')"

    def test_escapeHtml_delegates(self, source):
        # Debe delegar a WH.escapeHtml para tener una única implementación
        assert re.search(r"function\s+escapeHtml\s*\(", source)
        assert "WH.escapeHtml" in source, \
            "La función local escapeHtml debe delegar a WH.escapeHtml"


# ── 5. Tests funcionales con Node ─────────────────────────
# Levantan app.js dentro de Node con un DOM mínimo (sin jsdom) y verifican
# que las nuevas funciones exportadas se comportan correctamente.
class TestAppJsRuntime:
    @pytest.fixture(scope="class")
    def node_env(self, tmp_path_factory):
        """Crea un mini-DOM y un script Node que requiere app.js."""
        if shutil.which("node") is None:
            pytest.skip("Node no está disponible")
        tmp = tmp_path_factory.mktemp("wh_modal")
        dom_path = tmp / "dom.js"
        driver_path = tmp / "driver.js"
        # DOM mínimo (suficiente para que app.js no truene al definir
        # Toast, ImagePicker, Upload, Auth, etc.)
        dom_path.write_text(
            """
            const _els = new Map();
            class El {
              constructor(tag) {
                this.tagName = (tag || 'div').toUpperCase();
                this.children = [];
                this.dataset = {};
                this.style = new Proxy({}, { set: () => true, get: () => '' });
                this.classList = {
                  _set: new Set(),
                  add(c) { this._set.add(c); },
                  remove(c) { this._set.delete(c); },
                  contains(c) { return this._set.has(c); },
                  toggle(c) { this._set.has(c) ? this._set.delete(c) : this._set.add(c); },
                };
                this.listeners = {};
                this.parentNode = null;
                this.value = '';
                this.textContent = '';
                this._innerHTML = '';
                this._open = false;
              }
              get innerHTML() { return this._innerHTML; }
              set innerHTML(v) { this._innerHTML = v; this.children = []; }
              get open() { return this._open; }
              set open(v) { this._open = v; }
              appendChild(c) { c.parentNode = this; this.children.push(c); return c; }
              addEventListener(ev, fn) { (this.listeners[ev] = this.listeners[ev] || []).push(fn); }
              removeEventListener(ev, fn) {
                const arr = this.listeners[ev] || [];
                const i = arr.indexOf(fn);
                if (i >= 0) arr.splice(i, 1);
              }
              querySelector() { return null; }
              querySelectorAll() { return []; }
              setAttribute(k, v) { this.dataset[k] = v; }
              removeAttribute(k) { delete this.dataset[k]; }
              focus() { this._focused = true; }
              get offsetParent() { return this._open ? this : null; }
            }
            const document = {
              _body: new El('body'),
              createElement: (t) => new El(t),
              getElementById: (id) => _els.get(id) || null,
              addEventListener: () => {},
              removeEventListener: () => {},
              body: { appendChild: () => {}, style: {} },
            };
            const localStorage = {
              _store: {},
              getItem(k) { return this._store[k] || null; },
              setItem(k, v) { this._store[k] = String(v); },
              removeItem(k) { delete this._store[k]; },
              clear() { this._store = {}; },
            };
            const window = {};
            global.window = window;
            global.document = document;
            global.localStorage = localStorage;
            global.fetch = async () => ({ ok: true, status: 200, json: async () => ({}), text: async () => '' });
            global.Intl = Intl;
            global.atob = (s) => Buffer.from(s, 'base64').toString('binary');
            global.btoa = (s) => Buffer.from(s, 'binary').toString('base64');
            global.console = console;
            // Shim mínimo de Node (la interfaz DOM): cualquier cosa que
            // app.js consulte con `body instanceof Node` debe pasar.
            global.Node = function Node() {};
            global.Node.prototype = Object.create(Object.prototype);
            """,
            encoding="utf-8",
        )
        return tmp

    def _run(self, node_env, script):
        import json
        driver = node_env / "driver.js"
        app_js_literal = json.dumps(str(APP_JS))
        driver.write_text(
            f"""
            require('./dom.js');
            const fs = require('fs');
            const path = require('path');
            const appJs = fs.readFileSync(
              path.resolve({app_js_literal}),
              'utf-8'
            );
            // Reemplazar el `if (Auth.isLoggedIn()) startAutoRefresh();` final
            // para que no intente refrescar tokens sin red.
            const safe = appJs.replace(
              "if (Auth.isLoggedIn()) startAutoRefresh();",
              "// disabled in test"
            );
            eval(safe);
            {script}
            """,
            encoding="utf-8",
        )
        proc = subprocess.run(
            ["node", str(driver)],
            capture_output=True, text=True, timeout=30,
            cwd=str(node_env),
        )
        return proc

    def test_escapeHtml_escapes_specials(self, node_env):
        proc = self._run(
            node_env,
            """
            const out = JSON.stringify({
              amp: window.WH.escapeHtml('a & b'),
              lt: window.WH.escapeHtml('<script>'),
              gt: window.WH.escapeHtml('1 > 0'),
              quotes: window.WH.escapeHtml('"hi"'),
              nullish: window.WH.escapeHtml(null),
            });
            process.stdout.write(out);
            """,
        )
        assert proc.returncode == 0, proc.stderr
        import json
        data = json.loads(proc.stdout)
        assert data["amp"] == "a &amp; b"
        assert data["lt"] == "&lt;script&gt;"
        assert data["gt"] == "1 &gt; 0"
        assert data["nullish"] == ""

    def test_debounce_coalesces_calls(self, node_env):
        proc = self._run(
            node_env,
            """
            let calls = 0;
            const fn = window.WH.debounce(() => { calls++; }, 50);
            fn(); fn(); fn();
            setTimeout(() => {
              process.stdout.write(JSON.stringify({ calls }));
            }, 120);
            """,
        )
        assert proc.returncode == 0, proc.stderr
        import json
        data = json.loads(proc.stdout)
        # 3 llamadas deben coalescer en 1 sola ejecución
        assert data["calls"] == 1, f"Debounce debe coalescer, se llamaron {data['calls']} veces"

    def test_Auth_resetSession_invalidates_cache(self, node_env):
        proc = self._run(
            node_env,
            """
            const Auth = window.WH.Auth;
            // Forzar un cache simulado
            Auth._sessionPromise = Promise.resolve({ user: { id: 1 }, tenant: null, access_token: 'x' });
            const before = Auth._sessionPromise !== null;
            Auth.resetSession();
            const after = Auth._sessionPromise;
            process.stdout.write(JSON.stringify({ before, afterNull: after === null }));
            """,
        )
        assert proc.returncode == 0, proc.stderr
        import json
        data = json.loads(proc.stdout)
        assert data["before"] is True
        assert data["afterNull"] is True, "resetSession debe poner _sessionPromise = null"

    def test_Modal_exposes_open_and_close(self, node_env):
        proc = self._run(
            node_env,
            """
            const out = {
              hasOpen: typeof window.WH.Modal.open === 'function',
              hasClose: typeof window.WH.Modal.close === 'function',
            };
            const m = window.WH.Modal.open({ title: 'T', body: 'hola' });
            out.afterOpen = typeof m.close === 'function';
            m.close();
            out.afterClose = true;
            process.stdout.write(JSON.stringify(out));
            """,
        )
        assert proc.returncode == 0, proc.stderr
        import json
        data = json.loads(proc.stdout)
        assert data["hasOpen"] and data["hasClose"], "Modal debe exponer open/close"
        assert data["afterOpen"] is True, "Modal.open debe devolver un handle con .close()"

    def test_Confirm_exposes_show(self, node_env):
        proc = self._run(
            node_env,
            """
            const out = { hasShow: typeof window.WH.Confirm.show === 'function' };
            process.stdout.write(JSON.stringify(out));
            """,
        )
        assert proc.returncode == 0, proc.stderr
        import json
        data = json.loads(proc.stdout)
        assert data["hasShow"], "Confirm debe exponer .show(...)"
