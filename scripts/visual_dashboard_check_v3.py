"""v3: Captura TODAS las network requests y filtra errores."""
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

OUT = Path("/workspace/wowhub-app/tmp/screens3")
OUT.mkdir(parents=True, exist_ok=True)

PAGES = [
    ("products",      "/dashboard/products"),
    ("notifications", "/dashboard/notifications"),
    ("orders",        "/dashboard/orders"),
    ("inventory",     "/dashboard/inventory"),
    ("quotes",        "/dashboard/quotes"),
    ("pipeline",      "/dashboard/pipeline"),
    ("promotions",    "/dashboard/promotions"),
    ("bookings",      "/dashboard/bookings"),
]


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        ctx = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await ctx.new_page()

        requests_log = []

        def on_response(resp):
            try:
                url = resp.url
                if "/api/v1/" in url and "127.0.0.1" in url:
                    requests_log.append((resp.status, url))
            except: pass

        page.on("response", on_response)

        # Login
        await page.goto("http://127.0.0.1:8000/login", wait_until="networkidle", timeout=20000)
        await page.fill('input[name="email"]', "demo@wowhub.app")
        await page.fill('input[name="password"]', "demo1234")
        await page.click('button[type="submit"]')
        await page.wait_for_url("**/dashboard**", timeout=10000)

        for name, path in PAGES:
            requests_log.clear()
            try:
                await page.goto(f"http://127.0.0.1:8000{path}", wait_until="networkidle", timeout=15000)
                await page.wait_for_timeout(3000)
                row_count = await page.evaluate("""() => {
                    const tables = document.querySelectorAll('table tbody tr');
                    return Array.from(tables).filter(r => !r.textContent.match(/Cargando|Ver sitio/)).length;
                }""")
                still_loading = await page.evaluate("""() => {
                    // Look for actual <p> with Cargando inside specific containers
                    const matches = [];
                    document.querySelectorAll('p, div, td').forEach(el => {
                        const t = el.textContent.trim();
                        if (t === 'Cargando…' || t === 'Cargando notificaciones…' || /^Cargando\\s*\\.\\.\\.?$/.test(t)) {
                            matches.push(t);
                        }
                    });
                    return matches.slice(0, 5);
                }""")
                errs = [(s, u) for s, u in requests_log if s >= 400]
                status = "✅" if (row_count > 0 and not still_loading and not errs) else "❌"
                print(f"  {status} {name:14s} rows={row_count}  loading={still_loading}  errs={len(errs)}")
                for s, u in errs[:3]:
                    print(f"      ❌ {s} {u}")
            except Exception as e:
                print(f"  ❌ {name:14s} EXC: {e}")
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
