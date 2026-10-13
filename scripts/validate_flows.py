"""Validación de enlaces de UI y flujos funcionales con base de datos real.

A diferencia del resto, esto EJERCITA la aplicación: crea un tenant, se
registra un usuario, hace login y recorre los endpoints principales
comprobando que no devuelven 5xx.
"""
from __future__ import annotations

import os
import re
import sys
import uuid
from pathlib import Path

os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("SECRET_KEY", "flow-secret-key-min-32-chars-long-ok!!")
os.environ.setdefault("JWT_SECRET", "flow-jwt-secret-key-min-32-chars-ok!!!")
os.environ.setdefault("WEBHOOK_SECRET", "flow-webhook-secret-min-32-chars-ok")
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")
os.environ.setdefault("AUDIT_ENABLED", "false")
os.environ.setdefault("STORAGE_PUBLIC", "true")


DB = Path("flowcheck.db").resolve()
if DB.exists():
    DB.unlink()
os.environ["DATABASE_URL"] = f"sqlite:///{DB}"
os.environ["LOG_LEVEL"] = "ERROR"

import logging  # noqa: E402

logging.getLogger("sqlalchemy.engine").setLevel(logging.ERROR)
logging.getLogger("sqlalchemy").setLevel(logging.ERROR)
logging.getLogger("wowhub").setLevel(logging.ERROR)

from fastapi.testclient import TestClient  # noqa: E402

import app.models  # noqa: E402,F401
from app.database import Base, engine  # noqa: E402
from app.main_compat import app  # noqa: E402

TPL = Path(__file__).resolve().parent.parent / "app" / "templates"

err: list[str] = []
warn: list[str] = []


def to_regex(path: str) -> str:
    """Convierte una ruta de FastAPI (con {param}) en regex."""
    return "^" + "".join(
        ("[^/]+" if part.startswith("{") else re.escape(part))
        for part in re.split(r"(\{[^}]+\})", path)
    ) + "$"


print("=" * 76)
print("A) Enlaces internos de la UI -> rutas registradas")
print("=" * 76)

Base.metadata.create_all(bind=engine)
client = TestClient(app)

registered = [r.path for r in app.routes if getattr(r, "path", None)]
compiled = [to_regex(r) for r in registered]

links: set[str] = set()
for tpl in TPL.rglob("*.html"):
    txt = tpl.read_text(encoding="utf-8", errors="ignore")
    for m in re.finditer(r"""href=["'](/[^"'#?]*)["']""", txt):
        link = m.group(1)
        # Excluir estaticos y anchors puros: no son rutas a validar.
        if link.startswith(("/static/", "/assets/", "/favicon")):
            continue
        links.add(link)

broken = sorted(li for li in links if not any(re.match(p, li) for p in compiled))
print(f"   Enlaces internos unicos en templates : {len(links)}")
print(f"   Rutas registradas en la app         : {len(registered)}")
for li in sorted(links):
    ok = li not in broken
    if not ok:
        err.append(f"enlace roto: {li} (no coincide con ninguna ruta registrada)")
    print(f"   [{'OK  ' if ok else 'FAIL'}] {li}")

print()
print("=" * 76)
print("B) Flujo funcional extremo a extremo con SQLite")
print("=" * 76)

slug = f"tenant{uuid.uuid4().hex[:8]}"
# `email-validator` rechaza dominios special-use (.local, .test, .invalid),
# por lo que se usa example.com, que es el dominio reservado para documentación.
email = f"owner{uuid.uuid4().hex[:8]}@example.com"
password = "Prueba1234!"
print(f"   Tenant slug     : {slug}")
print(f"   Usuario          : {email}")

r = client.post(
    "/api/v1/auth/register",
    json={
        "email": email,
        "password": password,
        "full_name": "Dueno Prueba",
        "create_tenant": True,
        "tenant_slug": slug,
        "tenant_legal_name": "Negocio de Prueba",
    },
)
if not ok:
    err.append(f"register devolvio {r.status_code}")
    print(f"        {r.text[:300]}")
else:
    body = r.json()
    tenant_id = (
        (body.get("current_tenant") or {}).get("tenant_id")
        or body.get("tenant_id")
        or (body.get("tenant") or {}).get("id")
        or body.get("id")
    )
    print(f"        tenant_id (UUID) = {tenant_id}")
    if not tenant_id:
        err.append("register no devolvio tenant_id")

r = client.post("/api/v1/auth/login", json={"email": email, "password": password})
ok = r.status_code < 400
print(f"   [{'OK  ' if ok else 'FAIL'}] POST /api/v1/auth/login -> {r.status_code}")
token = None
if ok:
    token = r.json().get("access_token") or r.json().get("accessToken")
    print(f"        access_token: {'obtenido' if token else 'AUSENTE'}")
    if not token:
        err.append("login no devolvio access_token")
else:
    err.append(f"login devolvio {r.status_code}")
    print(f"        {r.text[:300]}")

auth = {"Authorization": f"Bearer {token}"} if token else {}

# Las rutas usan el UUID del tenant, no el slug.
TID = tenant_id or ""

resource_checks = [
    ("get", f"/api/v1/tenants/{TID}/products", None),
    ("post", f"/api/v1/tenants/{TID}/products",
     {"name": "Cafe", "price_cents": 1500, "sku": "CAF-001"}),
    ("get", f"/api/v1/tenants/{TID}/orders", None),
    ("get", f"/api/v1/tenants/{TID}/customers", None),
    ("get", f"/api/v1/tenants/{TID}/bookings", None),
    ("get", f"/api/v1/tenants/{TID}/categories", None),
    ("get", f"/api/v1/tenants/{TID}/insumos", None),
    ("get", f"/api/v1/tenants/{TID}/costs", None),
    ("get", f"/api/v1/tenants/{TID}/site-config", None),
    ("patch", f"/api/v1/tenants/{TID}/site-config", {"nombre_sitio": "Mi Negocio"}),
    ("get", f"/api/v1/tenants/{TID}/search/products?q=caf", None),
    ("get", f"/api/v1/tenants/{TID}/qrs", None),
    ("get", f"/api/v1/tenants/{TID}/webhooks", None),
    ("get", f"/api/v1/tenants/{TID}/quotes", None),
    ("get", f"/api/v1/tenants/{TID}/payments", None),
    ("get", f"/api/v1/tenants/{TID}/branches", None),
    ("get", f"/api/v1/tenants/{TID}/members", None),
    ("get", f"/api/v1/tenants/{TID}/uploads", None),
]
print()
for method, path, payload in resource_checks:
    fn = getattr(client, method)
    try:
        rr = fn(path, json=payload, headers=auth) if payload else fn(path, headers=auth)
    except Exception as exc:  # noqa: BLE001
        print(f"   [FAIL] {method.upper():<5} {path} -> {type(exc).__name__}: {exc}")
        err.append(f"{method.upper()} {path} lanzo {type(exc).__name__}")
        continue
    ok = rr.status_code < 500
    if not ok:
        err.append(f"{method.upper()} {path} devolvio {rr.status_code}")
    print(f"   [{'OK  ' if ok else 'FAIL'}] {method.upper():<5} {path[:58]:<58} -> {rr.status_code}")

print()
print("   Paginas HTML autenticadas:")
for p in [
    "/dashboard", "/dashboard/products", "/dashboard/orders",
    "/dashboard/customers", "/dashboard/bookings", "/dashboard/costs",
    "/dashboard/qrs", "/dashboard/marketplace", "/dashboard/site",
]:
    try:
        rr = client.get(p, headers=auth, follow_redirects=False)
    except Exception as exc:  # noqa: BLE001
        print(f"   [FAIL] GET {p:<38} -> {type(exc).__name__}: {exc}")
        err.append(f"pagina {p} lanzo {type(exc).__name__}")
        continue
    ok = rr.status_code < 500
    if not ok:
        err.append(f"pagina {p} devolvio {rr.status_code}")
    note = f" -> {rr.headers.get('location', '?')}" if 300 <= rr.status_code < 400 else ""
    print(f"   [{'OK  ' if ok else 'FAIL'}] GET {p:<38} -> {rr.status_code}{note}")

print()
print("   Paginas publicas:")
for p in ["/", "/login", "/register", "/health", "/docs", f"/u/{slug}", f"/loyalty/{slug}"]:
    try:
        rr = client.get(p, follow_redirects=False)
    except Exception as exc:  # noqa: BLE001
        print(f"   [FAIL] GET {p:<38} -> {type(exc).__name__}: {exc}")
        err.append(f"pagina publica {p} lanzo {type(exc).__name__}")
        continue
    ok = rr.status_code < 500
    if not ok:
        err.append(f"pagina publica {p} devolvio {rr.status_code}")
    print(f"   [{'OK  ' if ok else 'FAIL'}] GET {p:<38} -> {rr.status_code}")

print()
print("=" * 76)
print("RESUMEN")
print("=" * 76)
print(f"   Errores  : {len(err)}")
print(f"   Warnings : {len(warn)}")
for e in err:
    print(f"   [FAIL] {e}")
if not err:
    print("\n   RESULTADO: todos los flujos y enlaces responden sin 5xx.")
sys.exit(1 if err else 0)
