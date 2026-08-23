"""
Diagnose dashboard "Cargando..." root cause.

Reproduce el flujo exacto del front-end:
  1. POST /api/v1/auth/login
  2. GET  /api/v1/auth/me  (NO /me/memberships)
  3. GET  /api/v1/tenants/me  → toma el primer tenant_id
  4. Por cada endpoint que la página llama, hace GET y reporta el resultado.

Salida: tabla con status + items. Cualquier 4xx/5xx se marca como 🔴.
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from typing import Tuple

BASE = "http://127.0.0.1:8000"
EMAIL = "demo@wowhub.app"
PWD = "demo1234"


def http(method: str, path: str, token: str | None = None, body: dict | None = None) -> Tuple[int, str, dict | list | None]:
    url = f"{BASE}{path}"
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"} if body is not None else {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            raw = r.read()
            try:
                return r.status, r.reason, json.loads(raw) if raw else None
            except json.JSONDecodeError:
                return r.status, r.reason, {"_raw": raw[:200].decode(errors="replace")}
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, e.reason, json.loads(raw) if raw else None
        except json.JSONDecodeError:
            return e.code, e.reason, {"_raw": raw[:200].decode(errors="replace")}
    except Exception as e:
        return 0, f"{type(e).__name__}: {e}", None


def color(s: str) -> str:
    # Minimal ANSI: green / red / yellow
    return s


def count(j: dict | list | None) -> str:
    if j is None:
        return "—"
    if isinstance(j, list):
        return f"list[{len(j)}]"
    if isinstance(j, dict):
        if "items" in j and isinstance(j["items"], list):
            return f"items={len(j['items'])} total={j.get('total','?')}"
        if "notifications" in j and isinstance(j["notifications"], list):
            return f"n={len(j['notifications'])} total={j.get('total','?')}"
        if "campaigns" in j and isinstance(j["campaigns"], list):
            return f"campaigns={len(j['campaigns'])}"
        if "tenant" in j:
            return f"tenant OK"
        return f"keys={list(j.keys())[:5]}"
    return "?"


def main() -> int:
    # 1. Login
    code, reason, body = http("POST", "/api/v1/auth/login", body={"email": EMAIL, "password": PWD})
    if code != 200 or not isinstance(body, dict) or "access_token" not in body:
        print(f"❌ LOGIN FAILED  {code}  {reason}  {body}")
        return 1
    token = body["access_token"]
    print(f"✅ LOGIN OK   token={token[:16]}…")

    # 2. /auth/me
    code, reason, body = http("GET", "/api/v1/auth/me", token=token)
    me_ok = code == 200 and isinstance(body, dict) and body.get("id")
    if me_ok:
        print(f"✅ /auth/me  {code}  user={body.get('email')}")
    else:
        print(f"❌ /auth/me  {code}  {body}")

    # 3. /tenants/me — returns a SINGLE tenant dict, NOT a list
    code, reason, body = http("GET", "/api/v1/tenants/me", token=token)
    if code != 200 or not isinstance(body, dict) or "id" not in body:
        print(f"❌ /tenants/me  {code}  {body}")
        return 2
    tenant_id = body["id"]
    tenant_slug = body.get("slug")
    print(f"✅ /tenants/me  {code}  id={tenant_id}  slug={tenant_slug}\n")
    # Also probe the WRONG endpoint the UI calls
    code_w, _, body_w = http("GET", "/api/v1/me/memberships", token=token)
    print(f"⚠ /me/memberships (URL rota en la UI) → {code_w}  {body_w}\n")

    # 4. Endpoints que la UI del dashboard podría llamar.
    # Formato: (etiqueta_UI, path, método)
    targets = [
        ("Resumen / KPIs",         f"/api/v1/tenants/{tenant_id}/stats/overview",                "GET"),
        ("Notificaciones",         f"/api/v1/tenants/{tenant_id}/notifications",                 "GET"),
        ("Notificaciones resumen", f"/api/v1/tenants/{tenant_id}/notifications/summary",         "GET"),
        ("Productos",              f"/api/v1/tenants/{tenant_id}/products?page=1&page_size=20",  "GET"),
        ("Categorías",             f"/api/v1/tenants/{tenant_id}/categories?page=1&page_size=20","GET"),
        ("Pedidos",                f"/api/v1/tenants/{tenant_id}/orders?page=1&page_size=20",    "GET"),
        ("Pipeline (kanban)",      f"/api/v1/tenants/{tenant_id}/orders?page=1&page_size=200",   "GET"),
        ("Clientes",               f"/api/v1/tenants/{tenant_id}/customers?page=1&page_size=20", "GET"),
        ("Promociones",            f"/api/v1/tenants/{tenant_id}/promotions?page=1&page_size=20","GET"),
        ("Códigos QR",             f"/api/v1/tenants/{tenant_id}/qrs?page=1&page_size=20",      "GET"),
        ("Sucursales",             f"/api/v1/tenants/{tenant_id}/branches?page=1&page_size=20",  "GET"),
        ("Inventario (branch-prod)",f"/api/v1/tenants/{tenant_id}/branch-products?page=1&page_size=20","GET"),
        ("Reservas",               f"/api/v1/tenants/{tenant_id}/bookings?page=1&page_size=20",  "GET"),
        ("Reservas stats",         f"/api/v1/tenants/{tenant_id}/bookings/stats",                "GET"),
        ("Cotizaciones",           f"/api/v1/tenants/{tenant_id}/quotes?page=1&page_size=20",   "GET"),
        ("Fidelidad",              f"/api/v1/tenants/{tenant_id}/loyalty/campaigns",             "GET"),
        ("Costos",                 f"/api/v1/tenants/{tenant_id}/costs",                         "GET"),
        ("Costos breakdown",       f"/api/v1/tenants/{tenant_id}/costs/breakdown",               "GET"),
        ("Audit log",              f"/api/v1/tenants/{tenant_id}/audit?page=1&page_size=20",     "GET"),
        ("Oportunidades",          f"/api/v1/tenants/{tenant_id}/opportunities",                 "GET"),
        ("Daily brief",            f"/api/v1/tenants/{tenant_id}/opportunities/daily-brief",     "GET"),
        ("Landing pública",        f"/api/v1/tenants/{tenant_id}/landing",                       "GET"),
        ("Members",                f"/api/v1/tenants/{tenant_id}/members",                       "GET"),
    ]

    ok = 0
    fail = 0
    print("─" * 100)
    print(f"{'Sección':<26} {'HTTP':<6} {'Resultado':<20} {'Endpoint'}")
    print("─" * 100)
    for label, path, method in targets:
        c, r, b = http(method, path, token=token)
        n = count(b)
        status = "✅" if c == 200 else "❌"
        if c == 200:
            ok += 1
        else:
            fail += 1
        print(f"{label:<26} {c:<6} {n:<20} {path}  {status}")
        if c not in (200, 401, 403):
            # Show first detail if any
            if isinstance(b, dict) and "detail" in b:
                print(f"   ↳ detail: {b['detail']}")
    print("─" * 100)
    print(f"OK: {ok}    FAIL: {fail}    TOTAL: {ok + fail}")
    return 0 if fail == 0 else 4


if __name__ == "__main__":
    sys.exit(main())
