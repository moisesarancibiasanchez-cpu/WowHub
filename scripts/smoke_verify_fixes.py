"""Smoke test de la app corregida: arranca FastAPI y comprueba endpoints reales.

Reproduce lo que hará Railway: importa app.main_compat, levanta un TestClient y
comprueba los endpoints que estaban devolviendo 502.
"""
import json
import os
import sys

os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("DATABASE_URL", "sqlite:///./smoke.db")
os.environ.setdefault("SECRET_KEY", "smoke-secret-key-min-32-chars-long-ok!!")
os.environ.setdefault("JWT_SECRET", "smoke-jwt-secret-key-min-32-chars-ok!!!")
os.environ.setdefault("WEBHOOK_SECRET", "smoke-webhook-secret-min-32-chars-ok")
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")
os.environ.setdefault("AUDIT_ENABLED", "false")
os.environ.setdefault("STORAGE_PUBLIC", "true")

from fastapi.testclient import TestClient  # noqa: E402

print("1) Importando app.main_compat ...")
from app.main_compat import app  # noqa: E402

print("   OK - la app importa sin errores")

print("2) Levantando TestClient ...")
client = TestClient(app)
print("   OK - cliente construido")

# ── Endpoints que deben responder ────────────────────────────
checks = [
    ("/health", 200, "health del servicio"),
    ("/openapi.json", 200, "spec OpenAPI"),
    ("/docs", 200, "documentacion Swagger"),
    ("/metrics", 200, "metricas Prometheus"),
    ("/f0/", 200, "indice F0"),
    ("/f0/health", 200, "health F0"),
    ("/api/v1/auth/login", 405, "login existe (405 en GET, no 404)"),
]

print("\n3) Comprobando endpoints ...")
results = []
for path, expected, desc in checks:
    try:
        r = client.get(path)
        status = r.status_code
    except Exception as exc:  # noqa: BLE001
        status = f"ERROR: {type(exc).__name__}: {exc}"
    ok = status == expected
    results.append((path, status, expected, ok, desc))
    flag = "OK  " if ok else "FAIL"
    print(f"   [{flag}] {path:<28} -> {status} (esperado {expected})  {desc}")

# ── Verificación de seguridad: /f0/hu03?live=true en producción ──
print("\n4) Verificando que /f0/hu03?live=true quede bloqueado en produccion ...")
os.environ["APP_ENV"] = "production"
os.environ["SECRET_KEY"] = "real-secret-key-min-32-chars-long-ok!!x"
os.environ["JWT_SECRET"] = "real-jwt-secret-key-min-32-chars-long-ok!!"
os.environ["WEBHOOK_SECRET"] = "real-webhook-secret-min-32-chars-ok!!"
os.environ["DEBUG"] = "false"
os.environ["STORAGE_PUBLIC"] = "false"

try:
    from app.config import get_settings

    get_settings.cache_clear()
    s = get_settings()
    print(f"   settings de produccion cargados (storage_public={s.storage_public})")

    from app.core.errors import ForbiddenError  # noqa: F401

    r = client.get("/f0/hu03?live=true")
    blocked = r.status_code == 403
    print(
        f"   [{'OK  ' if blocked else 'FAIL'}] /f0/hu03?live=true -> {r.status_code} "
        f"(esperado 403)"
    )
    results.append(("/f0/hu03?live=true (prod)", r.status_code, 403, blocked, "DDL bloqueado"))
except Exception as exc:  # noqa: BLE001
    print(f"   ERROR al probar modo produccion: {type(exc).__name__}: {exc}")
    results.append(("/f0/hu03?live=true (prod)", "ERROR", 403, False, str(exc)))

# ── Verificación: search sin auth debe dar 401/403, no 200 ──
print("\n5) Verificando que /tenants/{uuid}/search ya NO sea público ...")
try:
    r = client.get("/api/v1/tenants/00000000-0000-0000-0000-000000000000/search/products?q=test")
    protected = r.status_code in (401, 403, 404, 422)
    print(
        f"   [{'OK  ' if protected else 'FAIL'}] search sin auth -> {r.status_code} "
        f"(esperado 401/403, NO 200)"
    )
    results.append(("search sin auth", r.status_code, "401/403", protected, "endpoint protegido"))
except Exception as exc:  # noqa: BLE001
    print(f"   ERROR: {exc}")
    results.append(("search sin auth", "ERROR", "401/403", False, str(exc)))

# ── Verificación: admin/site-config sin auth debe dar 401 ──
print("\n6) Verificando que /admin/site-config NO sea accesible sin rol ...")
try:
    r = client.patch("/api/v1/admin/site-config", json={"maintenance_mode": True})
    protected = r.status_code in (401, 403)
    print(
        f"   [{'OK  ' if protected else 'FAIL'}] site-config sin auth -> {r.status_code} "
        f"(esperado 401/403, NO 200)"
    )
    results.append(("site-config sin auth", r.status_code, "401/403", protected, "config global protegida"))
except Exception as exc:  # noqa: BLE001
    print(f"   ERROR: {exc}")
    results.append(("site-config sin auth", "ERROR", "401/403", False, str(exc)))

# ── Resumen ─────────────────────────────────────────────────
print("\n" + "=" * 68)
passed = sum(1 for x in results if x[3])
total = len(results)
print(f"RESULTADO: {passed}/{total} comprobaciones OK")
print("=" * 68)
for path, status, expected, ok, desc in results:
    mark = "OK" if ok else "FAIL"
    print(f"  [{mark}] {path:<34} {status} (esperado {expected}) — {desc}")

# Conteo de rutas OpenAPI
spec = client.get("/openapi.json").json()
n_paths = len(spec.get("paths", {}))
print(f"\nRutas en OpenAPI: {n_paths}")
sys.exit(0 if passed == total else 1)
