"""Verificacion de produccion de WowHub (V2.011).

Ejecuta comprobaciones HTTP reales contra el sitio desplegado y devuelve
codigo de salida 0 si todo esta bien, 1 si hay algun fallo.

Es el ejecutable del "Procedimiento de prueba" del README de release
V2.011: cubre los 4 errores corregidos (products.product_type, WH.Auth
undefined, /dashboard/templates 404 y los ENUM product_status/quote_status),
las 6 rutas restauradas, el Hero Showcase y el estado de la API.

Uso:
    python -m scripts.verify_production
    python -m scripts.verify_production --base https://otro-host

No modifica nada: solo GETs.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request

BASE_DEFAULT = "https://wowhub-api-production.up.railway.app"
TENANT_ID_DEFAULT = "e865866c-6eb7-4394-bf91-723c6b003307"
PUBLIC_SLUGS = ("cafe-norte", "bicifix")

APP_JS = '<script src="/static/js/app.js'
USO_WH = re.compile(r"(?:window\.)?\bWH\.(Auth|api|TokenStore|Toast|Upload|ImagePicker)\b")
SCRIPT_BLOCK = re.compile(r"<script\b[^>]*>(.*?)</script>", re.S)
LINE_COMMENT = re.compile(r"//[^\n]*")
HTML_COMMENT = re.compile(r"<!--.*?-->", re.S)

HERO_FILES = (
    "bookings.png",
    "catalog.png",
    "orders.png",
    "page.png",
    "payments.jpg",
    "promos.png",
    "qr.png",
    "stats.png",
)


def get(base: str, path: str, follow: bool = True):
    """GET simple. Devuelve (status, location, body)."""
    req = urllib.request.Request(base + path, headers={"Accept": "*/*"})

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):
            return None

    opener = urllib.request.build_opener() if follow else urllib.request.build_opener(NoRedirect)
    try:
        with opener.open(req, timeout=45) as r:
            return r.status, r.headers.get("location"), r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("location"), e.read().decode("utf-8", "replace")
    except Exception as exc:  # noqa: BLE001
        return "ERR", None, f"{type(exc).__name__}: {exc}"


def unguarded(js: str) -> list:
    """Usos de WH.<algo> que NO estan protegidos por un guard."""
    js = HTML_COMMENT.sub("", js)
    js = LINE_COMMENT.sub("", js)
    out = []
    for m in USO_WH.finditer(js):
        pre = js[max(0, m.start() - 130):m.start()]
        if "WH &&" in pre or "&& window.WH" in pre:
            continue
        out.append(m.group(0))
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Verificacion de produccion de WowHub")
    parser.add_argument("--base", default=BASE_DEFAULT)
    parser.add_argument("--tenant-id", default=TENANT_ID_DEFAULT)
    args = parser.parse_args()
    base = args.base.rstrip("/")
    tenant_id = args.tenant_id

    fails: list[str] = []

    def check(label: str, cond: bool, detail: str = "") -> None:
        print(f"  {'OK   ' if cond else 'FALLA'} {label}  {detail}")
        if not cond:
            fails.append(f"{label} {detail}")

    print("=" * 74)
    print(f"A) RUTAS RESTAURADAS (Bug 3)  ->  {base}")
    print("=" * 74)
    for path, exp_status, exp_loc in [
        ("/dashboard/templates", 200, None),
        ("/dashboard/v1", 200, None),
        ("/dashboard/settings", 307, "/dashboard/templates"),
        ("/dashboard/production", 307, "/dashboard/kds"),
        ("/dashboard/analytics", 307, "/dashboard/stats"),
        ("/pricing", 307, "/#pricing"),
    ]:
        st, loc, body = get(base, path, follow=False)
        ok = st == exp_status and (exp_loc is None or loc == exp_loc)
        check(f"{path:24s}", ok, f"-> {st} {loc or ''} ({len(body)}b)")

    print()
    print("=" * 74)
    print("B) CONTENIDO DE /dashboard/templates")
    print("=" * 74)
    st, _loc, body = get(base, "/dashboard/templates", follow=False)
    check("HTTP 200", st == 200, f"({len(body)} bytes)")
    for t in ("Moderna", "WowPrint", "Dark", "Default"):
        check(f"plantilla {t}", t in body)
    check("ruta literal /static/css/templates/dashboard.css",
          "/static/css/templates/dashboard.css" in body)
    check("sin url_for('static', filename=...)", "url_for('static'" not in body)
    check("sin mensaje 'negocio inexistente'", "no existe o est\u00e1 inactivo" not in body)

    print()
    print("=" * 74)
    print("C) MESERO VIRTUAL (Bug 2) - orden de carga de scripts")
    print("=" * 74)
    st, _loc, body = get(base, "/dashboard/mesero")
    check("HTTP 200", st == 200, f"({len(body)} bytes)")
    app_js = body.find(APP_JS)
    check("app.js presente", app_js != -1, f"pos={app_js}")
    bad = []
    for m in SCRIPT_BLOCK.finditer(body):
        u = unguarded(m.group(1))
        if u and m.start() < app_js:
            bad.append(f"bloque@{m.start()} usa {sorted(set(u))}")
    check("ningun <script> usa WH sin guard antes de app.js", not bad, str(bad))
    check("JS del mesero presente (loadTenantAndBranches)", "loadTenantAndBranches" in body)
    check("window.WH.Auth.ensureSession presente", "WH.Auth.ensureSession" in body)

    print()
    print("=" * 74)
    print("D) ORDERS (super() restaurado)")
    print("=" * 74)
    st, _loc, body = get(base, "/dashboard/orders")
    check("HTTP 200", st == 200, f"({len(body)} bytes)")
    for m in ("ai.js", "ai-context.js", "dashboard-compat.js", "requireLogin",
              "openNewOrderModal", "submitNewOrder", "wcRefreshProductoSelect"):
        check(f"contiene {m}", m in body)

    print()
    print("=" * 74)
    print("E) PRODUCTS / CATALOGO PUBLICO (Bug 1 y Bug 4)")
    print("=" * 74)
    st, _loc, body = get(base, f"/api/v1/tenants/{tenant_id}/products?order_by=position&page_size=100")
    check("products sin 500", st != 500, f"-> {st}")
    check("sin UndefinedColumn", "UndefinedColumn" not in body)
    check("sin 'product_type' en el error", "product_type" not in body or st == 200)
    print(f"       respuesta: {st} {body[:120]}")

    for slug in PUBLIC_SLUGS:
        st, _loc, body = get(base, f"/api/v1/public/t/{slug}/catalog")
        check(f"catalogo publico {slug}", st == 200, f"-> {st} ({len(body)}b)")
        check(f"  {slug} sin error de ENUM", "invalid input value for enum" not in body)
        check(f"  {slug} sin LookupError de enum", "not among the defined enum values" not in body)

    st, _loc, body = get(base, f"/api/v1/public/t/{PUBLIC_SLUGS[0]}/products/espresso")
    check("producto publico por slug sin LookupError",
          "not among the defined enum values" not in body, f"-> {st}")

    print()
    print("=" * 74)
    print("F) HERO SHOWCASE (no debe cambiar)")
    print("=" * 74)
    st, _loc, home = get(base, "/")
    check("home HTTP 200", st == 200, f"({len(home)} bytes)")
    check("home contiene 'hero-showcase'", "hero-showcase" in home.lower())
    n_tabs = len(re.findall(r'role="tab"', home))
    check("8 tabs ARIA en el home", n_tabs == 8, f"{n_tabs} tabs")
    check("script hero_showcase.js cargado", "hero_showcase.js" in home)

    st, _loc, hero_js = get(base, "/static/js/hero_showcase.js?v=v2.01-hero-showcase")
    check("hero_showcase.js 200", st == 200, f"({len(hero_js)} bytes)")
    check("autoplay 3000 ms", "AUTOPLAY_MS = 3000" in hero_js)
    check("ARIA tabs en el JS", 'role="tab"' in hero_js)

    hero_files = re.findall(r"imgMock\('([^']+)'", hero_js) or list(HERO_FILES)
    check("8 variantes con imagen", len(set(hero_files)) == 8, f"{sorted(set(hero_files))}")
    ok_hero = 0
    for name in sorted(set(hero_files)):
        s, _l, _b = get(base, f"/static/img/hero/{name}")
        if s == 200:
            ok_hero += 1
        else:
            print(f"       ! {name} -> {s}")
    check("las 8 imagenes hero responden 200", ok_hero == 8, f"{ok_hero}/8")

    print()
    print("=" * 74)
    print("G) API / HEALTH")
    print("=" * 74)
    st, _loc, body = get(base, "/health")
    check("health 200", st == 200, body[:90])
    st, _loc, body = get(base, "/openapi.json")
    try:
        paths = len(json.loads(body)["paths"])
        check("openapi paths", paths >= 258, f"{paths} paths")
    except Exception as exc:  # noqa: BLE001
        check("openapi legible", False, str(exc))

    print()
    print("=" * 74)
    if fails:
        print(f"FALLOS ({len(fails)}):")
        for f in fails:
            print("  -", f)
        return 1
    print("OK - validacion online completa sin fallos")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    raise SystemExit(main())
