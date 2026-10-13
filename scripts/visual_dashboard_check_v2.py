"""
Verificación visual v2: más espera + captura console logs
"""
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

OUT = Path("/workspace/wowhub-app/tmp/screens2")
OUT.mkdir(parents=True, exist_ok=True)

PAGES = [
    ("products",      "/dashboard/products"),
    ("notifications", "/dashboard/notifications"),
    ("orders",        "/dashboard/orders"),
    ("inventory",     "/dashboard/inventory"),
    ("quotes",        "/dashboard/quotes"),
    ("pipeline",      "/dashboard/pipeline"),
    ("customers",     "/dashboard/customers"),
    ("promotions",    "/dashboard/promotions"),
    ("bookings",      "/dashboard/bookings"),
]


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        ctx = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await ctx.new_page()

        console_msgs = []
        page.on("console", lambda msg: console_msgs.append(f"[{msg.type}] {msg.text}"))
        page.on("pageerror", lambda exc: console_msgs.append(f"[pageerror] {exc}"))

        # Login
        await page.goto("http://127.0.0.1:8000/login", wait_until="networkidle", timeout=20000)
        await page.fill('input[name="email"]', "demo@wowhub.app")
        await page.fill('input[name="password"]', "demo1234")
        await page.click('button[type="submit"]')
        await page.wait_for_url("**/dashboard**", timeout=10000)

        results = []
        for name, path in PAGES:
            console_msgs.clear()
            try:
                await page.goto(f"http://127.0.0.1:8000{path}", wait_until="networkidle", timeout=15000)
                await page.wait_for_timeout(3500)  # dar 3.5s para todos los fetches
                row_count = await page.evaluate("""() => {
                    const tables = document.querySelectorAll('table tbody tr');
                    return Array.from(tables).filter(r => !r.textContent.includes('Cargando')).length;
                }""")
                still_loading = await page.evaluate("""() => {
                    const txt = document.body.textContent;
                    return (txt.match(/Cargando[^<]{0,30}/g) || []).slice(0, 3);
                }""")
                status = "✅" if row_count > 0 and not still_loading else "❌"
                results.append((name, row_count, still_loading, status))
                print(f"  {status} {name:14s} rows={row_count}  loading={still_loading}")
                # Show console errors if any
                errs = [m for m in console_msgs if m.startswith("[error]") or m.startswith("[pageerror]")]
                for e in errs[:3]:
                    print(f"      ⚠ {e[:200]}")
                await page.screenshot(path=str(OUT / f"page_{name}.png"), full_page=False)
            except Exception as e:
                print(f"  ❌ {name:14s} ERROR: {e}")
                results.append((name, 0, [str(e)], "❌"))

        await browser.close()
        ok = sum(1 for r in results if r[3] == "✅")
        print(f"\nOK: {ok}/{len(results)}")


if __name__ == "__main__":
    asyncio.run(main())
