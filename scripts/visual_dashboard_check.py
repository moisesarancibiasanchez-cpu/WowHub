"""
Verificación visual con Playwright headless:
  1. Login con demo@wowhub.app
  2. Visitar /dashboard, /dashboard/products, /dashboard/notifications, /dashboard/orders
  3. Esperar a que las tablas se rendericen
  4. Guardar screenshots
  5. Contar filas reales en la tabla
"""
import asyncio
import json
import os
import sys
from pathlib import Path
from playwright.async_api import async_playwright

OUT = Path("/workspace/wowhub-app/tmp/screens")
OUT.mkdir(parents=True, exist_ok=True)

PAGES = [
    ("products",     "/dashboard/products"),
    ("notifications", "/dashboard/notifications"),
    ("orders",        "/dashboard/orders"),
    ("inventory",     "/dashboard/inventory"),
    ("quotes",        "/dashboard/quotes"),
]


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        ctx = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await ctx.new_page()

        # 1) Login
        await page.goto("http://127.0.0.1:8000/login", wait_until="networkidle", timeout=20000)
        # Find the form fields
        await page.fill('input[name="email"]', "demo@wowhub.app")
        await page.fill('input[name="password"]', "demo1234")
        # Submit
        await page.click('button[type="submit"]')
        await page.wait_for_url("**/dashboard**", timeout=10000)
        await page.screenshot(path=str(OUT / "00_dashboard.png"), full_page=True)
        print(f"✅ Logged in. Landed at: {page.url}")

        # 2) Each page
        results = []
        for name, path in PAGES:
            url = f"http://127.0.0.1:8000{path}"
            try:
                await page.goto(url, wait_until="networkidle", timeout=15000)
                # Give the JS time to fetch + render
                await page.wait_for_timeout(1500)
                # Count rows in any table
                row_count = await page.evaluate("""() => {
                    const tables = document.querySelectorAll('table tbody tr');
                    return Array.from(tables).filter(r => !r.textContent.includes('Cargando')).length;
                }""")
                still_loading = await page.evaluate("""() => {
                    return document.body.textContent.match(/Cargando[^<]{0,20}/g) || [];
                }""")
                await page.screenshot(path=str(OUT / f"page_{name}.png"), full_page=True)
                status = "✅" if row_count > 0 and not still_loading else "❌"
                results.append((name, path, row_count, still_loading, status))
                print(f"  {status} {name:14s} rows={row_count}  loading_blocks={len(still_loading)}")
            except Exception as e:
                print(f"  ❌ {name:14s} ERROR: {e}")
                results.append((name, path, 0, [str(e)], "❌"))

        await browser.close()

        # Summary
        print("\n=== Resumen ===")
        ok = sum(1 for r in results if r[4] == "✅")
        print(f"OK: {ok} / {len(results)}")
        for r in results:
            print(f"  {r[4]} {r[0]:14s} rows={r[2]}  loading_blocks={r[3]}")


if __name__ == "__main__":
    asyncio.run(main())
