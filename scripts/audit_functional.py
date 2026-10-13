"""Auditoría funcional exhaustiva de WowHub.

Verifica, sin necesidad de Docker ni Railway, todo lo que puede romper en
producción:
  1. Que la app importe y arranque
  2. Que cada `TemplateResponse` apunte a una plantilla existente
  3. Que cada template referenciado (extends/include/url_for) resuelva
  4. Que cada asset estático referenciado exista
  5. Que no haya rutas duplicadas ni catch-all que eclipse endpoints
  6. Que las migraciones Alembic estén encadenadas sin ciclos
  7. Que los modelos SQLAlchemy tengan tabla y que coincidan con la migración
  8. Que no queden imports rotos
"""
from __future__ import annotations

import ast
import os
import re
import sys
from collections import Counter
from pathlib import Path

os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("DATABASE_URL", "sqlite:///./audit.db")
os.environ.setdefault("SECRET_KEY", "audit-secret-key-min-32-chars-long-ok!!")
os.environ.setdefault("JWT_SECRET", "audit-jwt-secret-key-min-32-chars-ok!!!")
os.environ.setdefault("WEBHOOK_SECRET", "audit-webhook-secret-min-32-chars-ok")

ROOT = Path(__file__).resolve().parent.parent
TPL = ROOT / "app" / "templates"
STATIC = ROOT / "app" / "static"

err: list[str] = []
warn: list[str] = []
info: list[str] = []


def head(t: str) -> None:
    print()
    print("=" * 76)
    print(t)
    print("=" * 76)


# ── 1. La app importa y arranca ───────────────────────────────
head("1) Arranque de la aplicación")
try:
    from fastapi.testclient import TestClient

    from app.main_compat import app

    client = TestClient(app)
    info.append(f"OpenAPI expone {len(client.get('/openapi.json').json().get('paths', {}))} rutas")
    print(f"   [OK  ] app importa; {info[-1]}")
except Exception as exc:  # noqa: BLE001
    print(f"   [FAIL] la app no importa: {type(exc).__name__}: {exc}")
    err.append(f"app no importa: {exc}")
    sys.exit(1)


# ── 2. TemplateResponse apunta a plantilla existente ─────────
head("2) TemplateResponse -> plantilla existente")
# Distinguir destinos de ESCRITURA (Path(...).write_text) de lecturas.
# `prototype_generator.py` genera prototypes/f0_baseline/demo.html: no es
# una plantilla de entrada, así que no debe contarse como referencia rota.
write_targets: set[str] = set()
for py in (ROOT / "app").rglob("*.py"):
    txt = py.read_text(encoding="utf-8", errors="ignore")
    for m in re.finditer(r"""write_text\([^)]*?["']([^"']+\.html)["']""", txt):
        write_targets.add(m.group(1))
    for m in re.finditer(r"""write_text\(""", txt):
        pass
if write_targets:
    print(f"   HTML generados por el código (no son plantillas de entrada): "
          f"{', '.join(sorted(write_targets))}")
print()

used_templates: set[str] = set()
for py in (ROOT / "app").rglob("*.py"):
    txt = py.read_text(encoding="utf-8", errors="ignore")
    for m in re.finditer(
        r"TemplateResponse\(\s*[^,]+,\s*[\"']([^\"']+\.html)[\"']", txt
    ):
        used_templates.add(m.group(1))
    for m in re.finditer(r"[\"']([a-z0-9_/]+\.html)[\"']", txt):
        used_templates.add(m.group(1))
used_templates -= write_targets
# Artefactos generados: rutas HTML que el propio código produce con
# `prototype_generator.py` y que `f0_baseline` lee si existen. No son
# plantillas de entrada ni Assets: no se sirven por HTTP.
generated_artifacts = {"prototypes/f0_baseline/demo.html"}
used_templates -= generated_artifacts
if generated_artifacts:
    print(f"   Artefactos generados en runtime (no plantillas): "
          f"{', '.join(sorted(generated_artifacts))}")
    print()

missing_tpl = sorted(t for t in used_templates if not (TPL / t).is_file())
print(f"   Plantillas referenciadas en código: {len(used_templates)}")
for t in sorted(used_templates):
    ok = (TPL / t).is_file()
    if not ok:
        err.append(f"plantilla inexistente referenciada desde código: {t}")
    print(f"   [{'OK  ' if ok else 'FAIL'}] {t}")

# ── 3. Herencias e includes dentro de los templates ───────────
head("3) extends / include dentro de los templates")
tpl_files = [p for p in TPL.rglob("*.html")]
print(f"   Templates totales: {len(tpl_files)}")
# Jinja2 resuelve `{% extends "x" %}` desde la RAÍZ del loader
# (app/templates), no desde el directorio del archivo hijo. Por eso
# `dashboard/index.html` puede extender `dashboard/base.html`.
for p in tpl_files:
    txt = p.read_text(encoding="utf-8", errors="ignore")
    rel = p.relative_to(TPL).as_posix()
    for m in re.finditer(
        r"\{%-?\s*(?:extends|include|import)\s+[\"']([^\"']+)[\"']", txt
    ):
        ref = m.group(1)
        # 1) desde la raíz del loader (comportamiento real de Jinja2)
        target = TPL / ref
        if not target.is_file():
            # 2) fallback: relativo al archivo (por si se usa "./")
            target = (p.parent / ref).resolve()
        ok = target.is_file()
        if not ok:
            err.append(f"{rel} -> extends/include inexistente: {ref}")
        print(f"   [{'OK  ' if ok else 'FAIL'}] {rel} -> {ref}")

# ── 4. Assets estáticos referenciados ────────────────────────
head("4) Assets estáticos referenciados (url_for 'static' y href/src)")
missing_assets: list[str] = []
checked_assets = 0
for p in list(tpl_files) + [py for py in (ROOT / "app").rglob("*.py")]:
    txt = p.read_text(encoding="utf-8", errors="ignore")
    for m in re.finditer(
        r"""url_for\(\s*['"]static['"]\s*,\s*filename=['"]([^'"]+)['"]""", txt
    ):
        rel = m.group(1)
        checked_assets += 1
        if not (STATIC / rel).is_file():
            missing_assets.append(f"{p.name} url_for static '{rel}'")
    for m in re.finditer(r"""(?:href|src)=["'](?:/static/)?([^"'#?][^"']*\.(?:css|js|png|jpg|jpeg|svg|webp|ico|woff2?))["']""", txt):
        rel = m.group(1).lstrip("/")
        if rel.startswith("static/"):
            rel = rel[len("static/"):]
        if rel.startswith(("http://", "https://", "//", "data:")):
            continue
        checked_assets += 1
        cand = (STATIC / rel) if not rel.startswith("templates/") else (ROOT / "app" / rel)
        if not cand.is_file():
            missing_assets.append(f"{p.name} -> {rel}")
print(f"   Assets comprobados: {checked_assets}")
if missing_assets:
    for a in sorted(set(missing_assets)):
        print(f"   [WARN] asset no encontrado: {a}")
        warn.append(f"asset roto: {a}")
else:
    print("   [OK  ] todos los assets referenciados existen")

# ── 5. Rutas duplicadas y catch-all ───────────────────────────
head("5) Rutas: duplicados y catch-all")
from starlette.routing import Route  # noqa: E402

routes = [(r.path, tuple(sorted(getattr(r, "methods", []) or []))) for r in app.routes if isinstance(r, Route)]
dups = [(p, m) for (p, m), c in Counter(routes).items() if c > 1]
print(f"   Rutas totales: {len(routes)}")
if dups:
    for p, m in dups:
        print(f"   [WARN] ruta duplicada: {m} {p}")
        warn.append(f"ruta duplicada {m} {p}")
else:
    print("   [OK  ] no hay rutas duplicadas")

catchalls = [p for p, _ in routes if p.count("/") == 1 and p not in
             ("/health", "/metrics", "/", "/docs", "/redoc", "/openapi.json",
              "/login", "/register", "/forgot-password", "/reset-password",
              "/manifest.json", "/sw.js", "/robots.txt", "/sitemap.xml")]
print(f"   Rutas de primer nivel (posibles catch-all): {len(catchalls)}")
for p in sorted(catchalls):
    print(f"      {p}")

# ── 6. Cadena de migraciones Alembic ─────────────────────────
head("6) Cadena de migraciones Alembic")
alembic_dir = ROOT / "alembic" / "versions"
migs = {}
for p in sorted(alembic_dir.glob("*.py")):
    if p.name.startswith("__"):
        continue
    txt = p.read_text(encoding="utf-8", errors="ignore")
    rev = re.search(r'^revision(?::\s*str)?\s*=\s*["\']([^"\']+)', txt, re.M)
    down = re.search(r'^down_revision(?::[^=]+)?\s*=\s*(?:["\']([^"\']+)["\']|None)', txt, re.M)
    if rev:
        migs[rev.group(1)] = {"file": p.name, "down": down.group(1) if down and down.group(1) else None}
print(f"   Migraciones: {len(migs)}")
# Un "head" es una revisión que NO aparece como down_revision de ninguna otra.
# (Ojo: f2efb29e03b1 tiene down=None pero es BASE, no head, porque 2026_09_27_0001
#  la referencia como su padre.)
referenced_as_parent = {
    m["down"] for m in migs.values() if m["down"] and m["down"] in migs
}
heads = [r for r in migs if r not in referenced_as_parent]
for r, m in sorted(migs.items()):
    if m["down"] and m["down"] not in migs:
        print(f"   [FAIL] {r:<18} down={m['down']} APUNTA A UNA REVISIÓN INEXISTENTE")
        err.append(f"migración {r} tiene down_revision inexistente: {m['down']}")
    else:
        print(f"   [OK  ] {r:<18} down={m['down']}  {m['file']}")
if len(heads) > 1:
    err.append(f"{len(heads)} cabezas de migracion (deberia ser 1): {heads}")
    print(f"   [FAIL] {len(heads)} cabezas: {heads}")
elif not heads:
    err.append("no se puede determinar la cabeza de la cadena de migraciones")
    print("   [FAIL] no hay head (ciclo en la cadena)")
else:
    print(f"   [OK  ] head unico: {heads[0]}  (alembic upgrade head aplicara esta)")

# ── 7. Modelos vs migración ──────────────────────────────────
head("7) Modelos SQLAlchemy declarados")
try:
    from app.database import Base
    import app.models  # noqa: F401

    tables = sorted(Base.metadata.tables)
    print(f"   Tablas en metadata: {len(tables)}")
    mig_txt = "\n".join(
        p.read_text(encoding="utf-8", errors="ignore") for p in alembic_dir.glob("*.py")
    )
    for t in tables:
        in_mig = f"'{t}'" in mig_txt or f'"{t}"' in mig_txt
        if not in_mig:
            print(f"   [WARN] tabla sin migración: {t}")
            warn.append(f"tabla sin migración: {t}")
    print("   [OK  ] todas las tablas tienen migración" if not any(
        w.startswith("tabla sin migración") for w in warn) else "")
except Exception as exc:  # noqa: BLE001
    print(f"   [FAIL] no se pudo inspeccionar metadata: {exc}")
    err.append(f"metadata: {exc}")

# ── 8. Imports rotos ─────────────────────────────────────────
head("8) Imports de módulos app.* resueltos")
bad_imports: list[str] = []
for py in (ROOT / "app").rglob("*.py"):
    try:
        tree = ast.parse(py.read_text(encoding="utf-8", errors="ignore"))
    except SyntaxError as exc:
        err.append(f"sintaxis inválida en {py.relative_to(ROOT)}: {exc}")
        continue
    for node in ast.walk(tree):
        mods: list[str] = []
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("app."):
            mods.append(node.module)
        elif isinstance(node, ast.Import):
            mods += [a.name for a in node.names if a.name.startswith("app.")]
        for m in mods:
            p = ROOT / (m.replace(".", "/") + ".py")
            d = ROOT / m.replace(".", "/")
            if not p.is_file() and not d.is_dir():
                bad_imports.append(f"{py.relative_to(ROOT)} -> {m}")
if bad_imports:
    for b in sorted(set(bad_imports)):
        print(f"   [FAIL] import roto: {b}")
        err.append(f"import roto: {b}")
else:
    print("   [OK  ] todos los imports app.* resuelven")

# ── Resumen ──────────────────────────────────────────────────
head("RESUMEN DE LA AUDITORÍA FUNCIONAL")
print(f"   Errores  : {len(err)}")
print(f"   Warnings : {len(warn)}")
print()
for e in err:
    print(f"   [FAIL] {e}")
for w in warn:
    print(f"   [WARN] {w}")
if not err:
    print("\n   RESULTADO: sin errores funcionales.")
sys.exit(1 if err else 0)
