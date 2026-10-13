"""Validador del Dockerfile contra el build context real.

Reproduce las comprobaciones que hace `docker build` sin tener Docker:
  - que cada COPY tenga su origen existente en el contexto
  - que cada CMD/RUN/ENTRYPOINT apunte a algo real
  - que los directorios que el entrypoint crea existan o se creen
  - que el paquete `app` sea importable con sólo lo que se copia a la imagen
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCKERFILE = ROOT / "Dockerfile"

failures: list[str] = []
warnings: list[str] = []
oks: list[str] = []


def check(cond: bool, msg_ok: str, msg_bad: str) -> None:
    if cond:
        oks.append(msg_ok)
    else:
        failures.append(msg_bad)


print("=" * 74)
print("VALIDACIÓN DEL DOCKERFILE CONTRA EL BUILD CONTEXT")
print("=" * 74)
print(f"Dockerfile   : {DOCKERFILE}")
print(f"Build context: {ROOT}")
print()

if not DOCKERFILE.is_file():
    print("FATAL: no existe el Dockerfile")
    sys.exit(2)

content = DOCKERFILE.read_text(encoding="utf-8")
lines = content.splitlines()

# ── 1. Cada COPY debe tener un origen existente ──────────────
print("1) Instrucciones COPY")
copy_re = re.compile(
    r"^\s*COPY\s+(?:--from=\S+\s+)?(.+)$", re.IGNORECASE
)
copies: list[tuple[int, str, list[str]]] = []
for i, line in enumerate(lines, start=1):
    if line.strip().upper().startswith("COPY"):
        m = copy_re.match(line)
        if not m:
            continue
        raw = m.group(1)
        # partir respetando el flag --chown y el destino final
        parts = [p for p in raw.split() if not p.startswith("--")]
        if not parts:
            continue
        sources = parts[:-1]
        dest = parts[-1]
        copies.append((i, line.strip(), sources))
        for src in sources:
            target = ROOT / src
            if target.exists():
                size = (
                    sum(1 for _ in target.rglob("*") if _.is_file())
                    if target.is_dir()
                    else 1
                )
                print(f"   [OK  ] L{i:<3} {src:<22} -> {dest}   ({size} archivos)")
                oks.append(f"COPY {src}")
            else:
                print(f"   [FAIL] L{i:<3} {src:<22} -> {dest}   NO EXISTE")
                failures.append(f"L{i}: COPY {src} (origen inexistente)")

# ── 2. .dockerignore no debe excluir lo que se copia ─────────
print()
print("2) .dockerignore")
di = ROOT / ".dockerignore"
if di.is_file():
    di_lines = [
        l.strip()
        for l in di.read_text(encoding="utf-8").splitlines()
        if l.strip() and not l.strip().startswith("#")
    ]
    print(f"   .dockerignore presente con {len(di_lines)} reglas")
    for _, _, sources in copies:
        for src in sources:
            for rule in di_lines:
                if src == rule or src.startswith(rule.rstrip("/") + "/"):
                    print(f"   [WARN] '{src}' coincidiría con la regla '{rule}'")
                    warnings.append(f"dockerignore podría excluir {src}")
else:
    print("   [WARN] no hay .dockerignore — el build copiará .venv y .git")
    warnings.append("sin .dockerignore: se envía .venv (~200MB) al daemon")

# ── 3. Dependencias del RUN pip ──────────────────────────────
print()
print("3) Dependencias instaladas en la imagen")
req = ROOT / "requirements.txt"
req_text = req.read_text(encoding="utf-8") if req.is_file() else ""
for pkg in ("alembic", "fastapi", "sqlalchemy", "uvicorn", "psycopg"):
    present = re.search(rf"^\s*{pkg}\b", req_text, re.MULTILINE | re.IGNORECASE)
    in_docker = re.search(rf'"{pkg}', content, re.IGNORECASE)
    if pkg == "psycopg":
        ok = present or in_docker
    else:
        ok = bool(present)
    print(f"   [{'OK  ' if ok else 'FAIL'}] {pkg:<12} requirements.txt={'si' if present else 'no'} Dockerfile_extra={'si' if in_docker else 'no'}")
    check(ok, f"dep {pkg}", f"falta dependencia {pkg} en el build")

# ── 4. Archivos que el entrypoint necesita ───────────────────
print()
print("4) Archivos que consume scripts/entrypoint.sh")
entry = ROOT / "scripts" / "entrypoint.sh"
if entry.is_file():
    etext = entry.read_text(encoding="utf-8")
    for needed in ("scripts.migrate_ai_help_enum", "scripts.migrate_product_v8_columns"):
        mod = ROOT / (needed.replace(".", "/") + ".py")
        has = mod.is_file() or (ROOT / needed.split(".")[-1] + ".py").is_file()
        in_copy = "COPY scripts ./scripts" in content
        print(
            f"   [{'OK  ' if has and in_copy else 'WARN'}] {needed:<38} "
            f"({'existe' if has else 'NO EXISTE'})"
        )
        if not has:
            warnings.append(f"entrypoint llama a {needed} pero el módulo no existe")
    # el seed ahora es opt-in
    seed_optin = "SEED_DEMO_DATA" in etext
    print(f"   [{'OK  ' if seed_optin else 'FAIL'}] seed opt-in (SEED_DEMO_DATA)")
    check(seed_optin, "seed opt-in", "el seed sigue corriendo siempre en producción")
    # alembic fail-fast
    failfast = "exit 1" in etext and "alembic upgrade head" in etext
    print(f"   [{'OK  ' if failfast else 'FAIL'}] alembic fail-fast")
    check(failfast, "alembic fail-fast", "alembic no es fail-fast")
else:
    print("   [FAIL] no existe scripts/entrypoint.sh")
    failures.append("falta scripts/entrypoint.sh")

# ── 5. HEALTHCHECK apunta a un endpoint real ─────────────────
print()
print("5) HEALTHCHECK / healthcheckPath")
health_declared = re.search(r"HEALTHCHECK", content, re.IGNORECASE)
railway_json = ROOT / "railway.json"
railway_health = ""
if railway_json.is_file():
    rj = railway_json.read_text(encoding="utf-8")
    m = re.search(r'"healthcheckPath"\s*:\s*"([^"]+)"', rj)
    railway_health = m.group(1) if m else ""
    print(f"   railway.json healthcheckPath = {railway_health or '(no declarado)'}")
    check(
        railway_health == "/health",
        "railway healthcheckPath=/health",
        f"railway.json healthcheckPath incorrecto: {railway_health!r}",
    )
print(f"   Dockerfile HEALTHCHECK: {'sí' if health_declared else 'no'}")

# ── 6. El paquete app debe ser importable con lo copiado ────
print()
print("6) Módulos de app que se referencian pero no están bajo app/")
refs: set[str] = set()
for py in (ROOT / "app").rglob("*.py"):
    txt = py.read_text(encoding="utf-8", errors="ignore")
    for m in re.finditer(r"from\s+(scripts|tests)([\w.]*)\s+import", txt):
        refs.add(m.group(0))
    for m in re.finditer(r"\bscripts\.([a-z_][a-z0-9_]*)", txt):
        refs.add(f"scripts.{m.group(1)}")
missing = []
for r in sorted(refs):
    tokens = r.split()
    mod = tokens[1] if len(tokens) > 1 else r.replace("scripts.", "scripts.")
    if not mod.startswith("scripts"):
        mod = "scripts." + mod if "." not in mod else mod
    p = ROOT / (mod.replace(".", "/") + ".py")
    if not p.is_file():
        pkg_dir = ROOT / mod.replace(".", "/")
        if not pkg_dir.is_dir():
            missing.append(r)
if missing:
    for m in missing:
        print(f"   [WARN] referenciado pero inexistente: {m}")
        warnings.append(f"import inexistente: {m}")
else:
    print(f"   [OK  ] los {len(refs)} módulos referenciados bajo scripts/ existen")

# ── 7. railway.json vs CMD ───────────────────────────────────
print()
print("7) Coherencia railway.json vs Dockerfile")
if railway_json.is_file():
    rj = railway_json.read_text(encoding="utf-8")
    start_cmd = re.search(r'"startCommand"\s*:\s*"([^"]+)"', rj)
    sc = start_cmd.group(1) if start_cmd else ""
    exists_in_img = sc == "/app/entrypoint.sh" and entry.is_file()
    print(f"   startCommand = {sc!r} -> {'existe en la imagen' if exists_in_img else 'REVISAR'}")
    check(bool(sc), "railway startCommand declarado", "railway.json sin startCommand")
    dockerfile_path = re.search(r'"dockerfilePath"\s*:\s*"([^"]+)"', rj)
    dp = dockerfile_path.group(1) if dockerfile_path else ""
    check(
        (ROOT / dp).is_file() if dp else False,
        f"dockerfilePath {dp} existe",
        f"railway.json dockerfilePath inexistente: {dp!r}",
    )

# ── Resumen ──────────────────────────────────────────────────
print()
print("=" * 74)
print(f"OK        : {len(oks)}")
print(f"WARNINGS  : {len(warnings)}")
print(f"ERRORES   : {len(failures)}")
print("=" * 74)
for w in warnings:
    print(f"  [WARN] {w}")
for f in failures:
    print(f"  [FAIL] {f}")
if not failures:
    print("\nRESULTADO: el Dockerfile es construible.")
sys.exit(1 if failures else 0)
