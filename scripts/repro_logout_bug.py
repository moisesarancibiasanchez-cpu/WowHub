"""Reproduce el bug del botón SALIR (logout) con Playwright headless.

Captura: console logs, network requests, location changes, errores JS.
"""
import asyncio
import json
from pathlib import Path
from playwright.async_api import async_playwright

OUT = Path("/workspace/wowhub-app/tmp/logout_repro")
OUT.mkdir(parents=True, exist_ok=True)


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        ctx = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await ctx.new_page()

        # Capturar TODO
        console_msgs = []
        requests_log = []
        page_errors = []

        def on_console(msg):
            console_msgs.append(f"[{msg.type}] {msg.text}")

        def on_response(resp):
            try:
                if "/api/" in resp.url or "/auth/" in resp.url:
                    requests_log.append((resp.status, resp.request.method, resp.url))
            except: pass

        def on_pageerror(exc):
            page_errors.append(str(exc))

        page.on("console", on_console)
        page.on("response", on_response)
        page.on("pageerror", on_pageerror)

        # 1. Login
        print("--- LOGIN ---")
        await page.goto("http://127.0.0.1:8000/login", wait_until="networkidle", timeout=20000)
        await page.fill('input[name="email"]', "demo@wowhub.app")
        await page.fill('input[name="password"]', "demo1234")
        await page.click('button[type="submit"]')
        await page.wait_for_url("**/dashboard**", timeout=10000)
        print(f"  landed at: {page.url}")

        # 2. Verificar que el botón existe y es clickeable
        logout_btn = await page.query_selector("#logout-btn")
        print(f"  logout-btn exists: {logout_btn is not None}")
        if logout_btn:
            text = await logout_btn.inner_text()
            print(f"  logout-btn text: '{text}'")
            visible = await logout_btn.is_visible()
            print(f"  logout-btn visible: {visible}")

        # 3. Limpiar logs y hacer click
        console_msgs.clear()
        requests_log.clear()
        page_errors.clear()
        print("\n--- CLICK SALIR ---")

        await page.click("#logout-btn")
        # Esperar un poco para ver el resultado
        await page.wait_for_timeout(3000)

        # 4. Estado final
        print(f"  final URL: {page.url}")
        print(f"  console msgs: {console_msgs[:10]}")
        print(f"  page errors: {page_errors[:5]}")
        print(f"  requests related to logout/auth:")
        for s, m, u in requests_log:
            if "auth" in u or "logout" in u:
                print(f"    {m} {s} {u}")

        # 5. ¿Seguimos logueados? Intentar /api/v1/auth/me
        try:
            r = await page.evaluate("""async () => {
                const tk = JSON.parse(localStorage.getItem('wowhub.tokens') || 'null');
                if (!tk) return {logged_in: false, reason: 'no token in localStorage'};
                try {
                    const r = await fetch('/api/v1/auth/me', {
                        headers: { Authorization: 'Bearer ' + tk.access_token }
                    });
                    return {logged_in: r.ok, status: r.status};
                } catch (e) {
                    return {logged_in: false, error: e.message};
                }
            }""")
            print(f"\n  post-logout state: {r}")
        except Exception as e:
            print(f"  eval error: {e}")

        await page.screenshot(path=str(OUT / "after_logout.png"), full_page=True)
        print(f"\n  📸 screenshot: {OUT}/after_logout.png")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
