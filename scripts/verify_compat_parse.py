"""Verifica que el override de _parse en dashboard-compat.js enriquece el Error.

Simula fetches con varios códigos de estado y comprueba que el error capturado
ahora incluye 'HTTP <code>' y la URL, incluyendo el caso del bug de Railway donde
el body viene sin `detail` y `res.statusText` está vacío.
"""
import http.server
import socketserver
import threading
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path("/workspace/wowhub-app/app/static")
PORT = 8799

# ── 1) Servir estáticos en background ─────────────────────────────
class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)
    def log_message(self, *a, **k): pass  # silenciar

socketserver.TCPServer.allow_reuse_address = True
httpd = socketserver.TCPServer(("127.0.0.1", PORT), Handler)
t = threading.Thread(target=httpd.serve_forever, daemon=True)
t.start()
time.sleep(0.3)
BASE = f"http://127.0.0.1:{PORT}"
print(f"[server] listening on {BASE}")

# ── 2) HTML de prueba (sin f-string para evitar doble escapado) ──
TEST_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><title>parse test</title></head>
<body>
<pre id="out">pending</pre>
<script>
window.__results = [];
function log(name, ok, info) {
  window.__results.push({name: name, ok: ok, info: info});
  document.getElementById('out').textContent =
    window.__results.map(function(r){
      return (r.ok ? 'OK ' : 'FAIL ') + r.name + ' :: ' + r.info;
    }).join('\\n');
}
</script>
<script src="__BASE__/js/app.js"></script>
<script src="__BASE__/js/dashboard-compat.js"></script>
<script>
setTimeout(async function () {
  try {
    if (!window.WH || !window.WH.api || !window.WH.api._parse) {
      log('setup', false, 'WH.api._parse no existe');
      return;
    }
    log('setup', true, 'WH.api._parse OK');

    // Test 1: 404 con body {detail: ''} y statusText 'Not Found'
    try {
      await window.WH.api._parse(new Response(
        JSON.stringify({detail: ''}),
        {status: 404, statusText: 'Not Found', headers: {'content-type': 'application/json'}}
      ));
      log('test1_404_normal', false, 'debio lanzar');
    } catch (e) {
      var hasHttp = /HTTP 404/.test(e.message);
      var hasStatusText = /Not Found/.test(e.message);
      var ok = hasHttp && hasStatusText && e.status === 404;
      log('test1_404_normal', ok, e.message);
    }

    // Test 2: 404 con body sin detail y statusText '' (caso Railway bug)
    try {
      await window.WH.api._parse(new Response(
        JSON.stringify({}),
        {status: 404, statusText: '', headers: {'content-type': 'application/json'}}
      ));
      log('test2_404_empty', false, 'debio lanzar');
    } catch (e) {
      var hasHttp = /HTTP 404/.test(e.message);
      var ok = hasHttp && e.status === 404;
      log('test2_404_empty', ok, e.message);
    }

    // Test 3: 401 con body {detail: 'Token expirado'}
    try {
      await window.WH.api._parse(new Response(
        JSON.stringify({detail: 'Token expirado'}),
        {status: 401, statusText: 'Unauthorized', headers: {'content-type': 'application/json'}}
      ));
      log('test3_401_with_detail', false, 'debio lanzar');
    } catch (e) {
      var ok = /HTTP 401/.test(e.message)
            && /Token expirado/.test(e.message)
            && e.status === 401;
      log('test3_401_with_detail', ok, e.message);
    }

    // Test 4: 500 con body texto plano
    try {
      await window.WH.api._parse(new Response(
        'Internal Server Error',
        {status: 500, statusText: 'Internal Server Error', headers: {'content-type': 'text/plain'}}
      ));
      log('test4_500_text', false, 'debio lanzar');
    } catch (e) {
      var ok = /HTTP 500/.test(e.message) && e.status === 500;
      log('test4_500_text', ok, e.message);
    }

    // Test 5: 200 OK (no debe lanzar)
    try {
      var r = await window.WH.api._parse(new Response(
        JSON.stringify({ok: true}),
        {status: 200, headers: {'content-type': 'application/json'}}
      ));
      var ok = r && r.ok === true;
      log('test5_200_ok', ok, JSON.stringify(r));
    } catch (e) {
      log('test5_200_ok', false, 'NO debio lanzar: ' + e.message);
    }

    // Test 6: 204 No Content
    try {
      var r = await window.WH.api._parse(new Response(null, {status: 204}));
      var ok = r === null;
      log('test6_204', ok, JSON.stringify(r));
    } catch (e) {
      log('test6_204', false, 'NO debio lanzar: ' + e.message);
    }
  } catch (e) {
    log('fatal', false, String(e));
  }
}, 200);
</script>
</body></html>
""".replace("__BASE__", BASE)

test_html_path = ROOT.parent.parent / "scripts" / "_test_parse.html"
test_html_path.parent.mkdir(parents=True, exist_ok=True)
test_html_path.write_text(TEST_HTML, encoding="utf-8")

# ── 3) Cargar la página vía Playwright ────────────────────────────
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context()
    page = ctx.new_page()
    page.goto(f"file://{test_html_path}", wait_until="domcontentloaded")
    page.wait_for_function("window.__results && window.__results.length >= 7", timeout=10000)
    results = page.evaluate("window.__results")
    for r in results:
        marker = "OK  " if r["ok"] else "FAIL"
        print(f"  {marker} {r['name']}: {r['info']}")
    browser.close()

httpd.shutdown()
print(f"[server] stopped")

failed = [r for r in results if not r["ok"]]
if failed:
    print(f"\nFAIL: {len(failed)} test(s) failed")
    raise SystemExit(1)
print(f"\nOK: all {len(results)} tests passed")
