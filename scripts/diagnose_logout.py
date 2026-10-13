"""Test extendido: ¿el botón SALIR falla por timer? race conditions?"""
import asyncio
import json
from playwright.async_api import async_playwright


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        ctx = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await ctx.new_page()

        requests_log = []
        def on_response(resp):
            if "/api/" in resp.url:
                requests_log.append((resp.status, resp.request.method, resp.url))

        page.on("response", on_response)

        # Login
        await page.goto("http://127.0.0.1:8000/login", wait_until="networkidle", timeout=20000)
        await page.fill('input[name="email"]', "demo@wowhub.app")
        await page.fill('input[name="password"]', "demo1234")
        await page.click('button[type="submit"]')
        await page.wait_for_url("**/dashboard**", timeout=10000)

        # Esperar a que el bell badge haga su primer fetch
        await page.wait_for_timeout(2000)
        print("Estado pre-logout:")
        print(f"  url: {page.url}")
        ls1 = await page.evaluate("JSON.parse(localStorage.getItem('wowhub.tokens') || 'null')")
        print(f"  has access_token: {bool(ls1 and ls1.get('access_token'))}")
        print(f"  has refresh_token: {bool(ls1 and ls1.get('refresh_token'))}")

        cookies_before = await ctx.cookies()
        auth_cookies = [c for c in cookies_before if 'token' in c.get('name', '').lower() or 'auth' in c.get('name', '').lower()]
        print(f"  auth cookies: {[c['name'] for c in auth_cookies]}")

        requests_log.clear()
        print("\nClick SALIR...")
        # Slow-motion: clic + esperar 5s
        await page.click("#logout-btn")
        await page.wait_for_timeout(5000)

        print(f"\nEstado post-logout:")
        print(f"  url: {page.url}")
        ls2 = await page.evaluate("JSON.parse(localStorage.getItem('wowhub.tokens') || 'null')")
        print(f"  has access_token: {bool(ls2 and ls2.get('access_token'))}")
        cookies_after = await ctx.cookies()
        auth_cookies_after = [c for c in cookies_after if 'token' in c.get('name', '').lower() or 'auth' in c.get('name', '').lower()]
        print(f"  auth cookies: {[c['name'] for c in auth_cookies_after]}")

        print(f"\nNetwork during logout ({len(requests_log)} requests):")
        for s, m, u in requests_log:
            print(f"  {m} {s} {u}")

        # Ahora intentar acceder a /dashboard de nuevo
        print("\nIntentando GET /dashboard después de logout...")
        requests_log.clear()
        await page.goto("http://127.0.0.1:8000/dashboard", wait_until="networkidle", timeout=10000)
        print(f"  final url: {page.url}")
        print(f"  dashboard renders content?: ", end="")
        has_content = await page.evaluate("""() => {
            const t = document.body.textContent;
            return t.length > 100 && !t.includes('Cargando');
        }""")
        print(has_content)

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
