"""Captura screenshots de las páginas que funcionan post-fix."""
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

OUT = Path("/workspace/wowhub-app/tmp/working_screens")
OUT.mkdir(parents=True, exist_ok=True)

PAGES = [
    ("01_dashboard_resumen", "/dashboard"),
    ("02_products",          "/dashboard/products"),
    ("03_customers",         "/dashboard/customers"),
    ("04_bookings",          "/dashboard/bookings"),
]


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        ctx = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await ctx.new_page()

        await page.goto("http://127.0.0.1:8000/login", wait_until="networkidle", timeout=20000)
        await page.fill('input[name="email"]', "demo@wowhub.app")
        await page.fill('input[name="password"]', "demo1234")
        await page.click('button[type="submit"]')
        await page.wait_for_url("**/dashboard**", timeout=10000)

        for name, path in PAGES:
            await page.goto(f"http://127.0.0.1:8000{path}", wait_until="networkidle", timeout=15000)
            await page.wait_for_timeout(3000)
            await page.screenshot(path=str(OUT / f"{name}.png"), full_page=True)
            print(f"  📸 {name}.png")
        await browser.close()
        print(f"\nScreenshots saved to {OUT}")


if __name__ == "__main__":
    asyncio.run(main())
