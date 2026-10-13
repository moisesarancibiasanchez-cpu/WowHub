"""Diagnostica la página Productos y captura el error real de carga.

Inicia sesión con un usuario demo, navega a /dashboard/products, captura:
  - El HTML del body
  - Los errores de consola
  - Las requests de red con su status code
  - El texto del contenedor de error (si existe)
"""
import sys
import json
import re
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8000"
OUT = Path("/tmp/diag_products")
OUT.mkdir(exist_ok=True, parents=True)


def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()

        console_msgs = []
        net_reqs = []
        net_responses = []

        page.on("console", lambda m: console_msgs.append(f"[{m.type}] {m.text}"))
        page.on("request", lambda r: net_reqs.append(f"{r.method} {r.url}"))
        page.on(
            "response",
            lambda r: net_responses.append(
                {"status": r.status, "method": r.request.method, "url": r.url}
            ),
        )

        # 1) Login
        page.goto(f"{BASE}/login", wait_until="networkidle")
        page.fill('input[name="email"]', "demo@wowhub.app")
        page.fill('input[name="password"]', "demo1234")
        page.click('button[type="submit"]')
        page.wait_for_url(re.compile(r"/dashboard"), timeout=15000)
        print(f"[login] OK → {page.url}")

        # 2) Navigate to Products
        page.goto(f"{BASE}/dashboard/products", wait_until="networkidle", timeout=15000)
        page.wait_for_timeout(2500)  # esperar a que termine la carga JS

        # 3) Capturar todo
        body = page.evaluate("document.body.innerText")
        screenshot = OUT / "products.png"
        page.screenshot(path=str(screenshot), full_page=True)

        # Buscar el mensaje de error
        error_match = re.search(r"Error cargando:?[\s\S]{0,300}", body)
        error_text = error_match.group(0) if error_match else "(no encontrado)"

        # Buscar el container específico
        error_container = page.evaluate("""
() => {
  const candidates = document.querySelectorAll('[id*="error"], [class*="error"], #products-list, #products-grid, #catalogo, .products-error, .alert');
  const out = [];
  for (const c of candidates) {
    if (c.offsetHeight > 0 || c.innerText && c.innerText.trim()) {
      out.push({ tag: c.tagName, id: c.id, class: c.className, text: c.innerText.slice(0, 500) });
    }
  }
  return out;
}
        """)

        result = {
            "url": page.url,
            "title": page.title(),
            "error_text_in_body": error_text,
            "error_containers": error_container,
            "screenshot": str(screenshot),
        }

        (OUT / "result.json").write_text(json.dumps(result, indent=2, ensure_ascii=False))
        (OUT / "console.log").write_text("\n".join(console_msgs))
        (OUT / "requests.log").write_text("\n".join(net_reqs))
        (OUT / "responses.log").write_text(
            "\n".join(f"{r['status']} {r['method']} {r['url']}" for r in net_responses)
        )

        # Filtrar solo las responses con error
        err_resps = [r for r in net_responses if r["status"] >= 400]
        print("\n=== ERRORES DE CONSOLA ===")
        for m in console_msgs:
            if "error" in m.lower() or "warn" in m.lower():
                print(m[:300])
        print("\n=== RESPONSES CON ERROR (>=400) ===")
        for r in err_resps:
            print(f"  {r['status']} {r['method']} {r['url']}")
        if not err_resps:
            print("  (ninguna)")
        print("\n=== TEXTO DE ERROR EN BODY ===")
        print(error_text[:500])
        print("\n=== CONTENEDORES DE ERROR ===")
        for c in error_container[:10]:
            print(f"  {c['tag']}#{c['id']}.{c['class'][:60]}: {c['text'][:200]}")
        print(f"\nScreenshot: {screenshot}")

        browser.close()
        return 0 if not err_resps else 1


if __name__ == "__main__":
    sys.exit(run())
