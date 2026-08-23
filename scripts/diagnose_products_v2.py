"""Diagnostica específicamente /dashboard/products después de login."""
import re, json
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8000"
OUT = Path("/tmp/diag_products2")
OUT.mkdir(exist_ok=True, parents=True)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    page = ctx.new_page()

    console_msgs = []
    responses = []

    page.on("console", lambda m: console_msgs.append(f"[{m.type}] {m.text}"))
    page.on("response", lambda r: responses.append((r.status, r.request.method, r.url)))

    # 1) Login via API
    resp = ctx.request.post(f"{BASE}/api/v1/auth/login",
                            data={"email": "demo@wowhub.app", "password": "demo1234"})
    body = resp.json()
    token = body["access_token"]
    print(f"[login API] OK")

    # Set localStorage manually
    page.goto(f"{BASE}/login", wait_until="domcontentloaded")
    page.evaluate(f"""
() => {{
  const t = {json.dumps(body)};
  localStorage.setItem('wowhub.tokens', JSON.stringify(t));
}}
    """)

    # 2) Go to products
    page.goto(f"{BASE}/dashboard/products", wait_until="networkidle", timeout=20000)
    page.wait_for_timeout(3000)

    # 3) Read tbody content
    tbody_text = page.evaluate("document.querySelector('#products-tbody, tbody')?.innerText || ''")
    body_text = page.evaluate("document.body.innerText")

    print("\n=== TBODY TEXT ===")
    print(tbody_text[:1000])
    print("\n=== BODY (search 'Error cargando') ===")
    idx = body_text.find("Error cargando")
    if idx >= 0:
        print(body_text[idx:idx+500])
    else:
        print("(not found)")

    print("\n=== RESPONSES PARA /products ===")
    for s, m, u in responses:
        if "/products" in u and "/api/" in u:
            print(f"  {s} {m} {u}")
    print("\n=== ALL RESPONSES WITH ERROR (>=400) ===")
    for s, m, u in responses:
        if s >= 400:
            print(f"  {s} {m} {u}")
    if not any(s >= 400 for s, _, _ in responses):
        print("  (ninguna)")

    print("\n=== CONSOLE ERRORS ===")
    for m in console_msgs:
        if "error" in m.lower():
            print(m[:400])

    page.screenshot(path=str(OUT / "products.png"), full_page=True)
    browser.close()
