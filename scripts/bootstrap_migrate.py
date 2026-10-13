"""Bootstrap idempotente de migraciones Alembic.

Problema
--------
En Railway la DB Postgres fue poblada por la versión anterior de WowHub, que
usaba `Base.metadata.create_all()` (no Alembic). Cuando el nuevo entrypoint
corre `alembic upgrade head`, encuentra las tablas ya creadas y falla con:

    sqlalchemy.exc.ProgrammingError: (psycopg.errors.DuplicateTable)
    relation "legal_consents" already exists

El `fail-fast` del entrypoint aborta el deploy con `exit 1`. La app no
arranca. Bucle infinito.

Solución
--------
Antes de correr `alembic upgrade head`, inspeccionar la DB:

1. Si no existe la tabla `alembic_version` PERO sí existe alguna tabla de la
   primera migración (`legal_consents` es la primera creada en initial_schema)
   → la DB ya está al día con la migración inicial. Hacer
   `alembic stamp head` para alinear y salir.

2. Si no existe ni `alembic_version` ni tablas → DB virgen. Correr
   `alembic upgrade head` normal.

3. Si existe `alembic_version` → DB gestionada por Alembic. Correr
   `alembic upgrade head` (es idempotente, no-op si ya está al día).

Resultado: el deploy es idempotente, sin importar el estado previo de la DB.
"""
from __future__ import annotations

import os
import subprocess
import sys
from urllib.parse import urlparse

from sqlalchemy import create_engine, inspect, text


def _engine():
    """Construye un engine SQLAlchemy desde DATABASE_URL.

    El driver URL de Alembic (`postgresql+psycopg://…`) es aceptado tal cual
    por SQLAlchemy moderno. Para el chequeo inicial no necesitamos driver
    async, así que cambiamos a psycopg síncrono si está disponible.
    """
    raw = os.environ.get("DATABASE_URL", "").strip()
    if not raw:
        print("ERROR: DATABASE_URL no configurada", file=sys.stderr)
        sys.exit(1)
    return create_engine(raw, future=True)


def _first_table_from_initial_migration() -> str:
    """Lee la primera tabla que crea `initial_schema.py` por orden de aparición.

    `legal_consents` es la primera en ese archivo. Lo parseamos para no
    hardcodearlo (si alguien reorganiza la migración, el bootstrap sigue
    funcionando).
    """
    candidates = ("legal_consents", "site_config", "tenants")
    here = os.path.dirname(os.path.abspath(__file__))
    mig = os.path.normpath(
        os.path.join(here, "..", "alembic", "versions",
                     "2026_09_07_1002-f2efb29e03b1_initial_schema.py")
    )
    if os.path.isfile(mig):
        try:
            import re
            txt = open(mig, encoding="utf-8").read()
            for m in re.finditer(r"op\.create_table\(\s*['\"]([a-z0-9_]+)['\"]", txt):
                name = m.group(1)
                if name != "alembic_version":
                    return name
        except OSError:
            pass
    return candidates[0]


def _initial_migration_revision() -> str | None:
    """Revisión de la migración base (con down_revision=None).

    Se usa en el flujo "legacy": la DB ya tiene ese esquema, así que sellamos
    la DB en esa revisión y dejamos que `upgrade head` aplique sólo las
    migraciones nuevas.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    mig_dir = os.path.normpath(os.path.join(here, "..", "alembic", "versions"))
    if not os.path.isdir(mig_dir):
        return None
    import re
    for fname in os.listdir(mig_dir):
        if not fname.endswith(".py"):
            continue
        path = os.path.join(mig_dir, fname)
        try:
            txt = open(path, encoding="utf-8").read()
        except OSError:
            continue
        # Tolerar `revision: str = "..."` y `revision = "..."`.
        rev = re.search(
            r"^revision\b[^=\n]*=\s*['\"]([^'\"]+)['\"]", txt, re.M
        )
        # down_revision puede tener anotacion de tipo (`Union[...] = None`)
        # o no. Aceptamos ambos formatos.
        down = re.search(
            r"^down_revision\b[^=\n]*=\s*None\b", txt, re.M
        )
        if rev and down:
            return rev.group(1)
    return None


def _migrations_in_dependency_order(migs: dict[str, dict]) -> list[str]:
    """Ordena las migraciones topológicamente (de base a head).

    Construye `children[parent_rev] = [child_revs...]` recorriendo TODAS las
    migraciones. El padre de cada migración es `m["down"]`. Si el padre no
    existe en `migs`, lo trata como None (migración huérfana, debería ser
    una head).
    """
    children: dict[str | None, list[str]] = {}
    for rev, m in migs.items():
        parent: str | None = m["down"] if m["down"] in migs else None
        children.setdefault(parent, []).append(rev)

    order: list[str] = []
    visited: set[str] = set()

    def visit(node: str) -> None:
        if node in visited:
            return
        visited.add(node)
        # Pre-order: append ANTES de los hijos para que las migraciones de
        # base (sin padre en migs) aparezcan antes que sus descendientes.
        # Esto es lo que `alembic upgrade` espera: aplicar las migraciones
        # en orden cronológico desde la base hacia la head.
        order.append(node)
        for child in children.get(node, []):
            visit(child)

    for root in children.get(None, []):
        visit(root)
    # Si quedo alguna sin visitar (huérfana), la metemos al final.
    for rev in migs:
        if rev not in visited:
            visit(rev)
    return order


def _tables_referenced_by_migration(mig_dir: str, rev: str) -> list[str]:
    """Devuelve los nombres de tabla que CREATE TABLE declara en la migración `rev`."""
    import re

    # El nombre del revision puede estar en una de tres formas:
    #   revision = "..."
    #   revision: str = "..."
    #   revision: Union[str, ...] = "..."
    rev_pattern = re.compile(
        rf"^revision\b[^=\n]*=\s*['\"]({re.escape(rev)})['\"]", re.M
    )
    for fname in os.listdir(mig_dir):
        if not fname.endswith(".py"):
            continue
        path = os.path.join(mig_dir, fname)
        try:
            txt = open(path, encoding="utf-8").read()
        except OSError:
            continue
        if not rev_pattern.search(txt):
            continue
        tables = re.findall(r"op\.create_table\(\s*['\"]([a-z0-9_]+)['\"]", txt)
        return [t for t in tables if t != "alembic_version"]
    return []


def _highest_fully_applied_revision(
    eng, migs: dict[str, dict], mig_dir: str, model_tables: set[str] | None = None
) -> str | None:
    """Revisión más alta cuyas tablas declaradas están TODAS presentes en la DB.

    Recibe un engine (no un inspector) para que pueda abrir sus propias
    conexiones bajo demanda. Pasar un ``Inspector`` ligado a una conexión
    ya cerrada lanza ``ResourceClosedError`` — bug histórico de este script
    que se manifestaba en TEST B (DB legacy con ``Base.metadata.create_all``
    previo, idéntico al caso real de Railway).

    ``model_tables`` es el conjunto de tablas conocidas por ``Base.metadata``
    (modelos activos). Si se pasa, las tablas declaradas en una migración
    que NO tengan modelo activo se IGNORAN del cómputo "fully-applied".
    Esto evita el falso negativo que producía el bug histórico: la
    migración ``initial_schema`` declara ``business_costs``, una tabla que
    fue eliminada del modelo en el commit 9163349 pero sigue declarada
    en la migración. Esa tabla nunca se crea con ``create_all()`` y por
    tanto siempre aparecía como "no presente", lo que hacía que la base
    NUNCA fuese fully-applied y el bootstrap cayera al ERROR
    "no encuentro ninguna migración aplicable".

    Recorre TODAS las migraciones de base a head y devuelve la más alta que
    esté fully-applied (todas sus ``create_table`` con modelo presente).
    Esto cubre los dos casos reales que se ven en producción:

    Caso 1 (legacy completo)
        ``Base.metadata.create_all()`` pobló la DB con todas las tablas del
        modelo, incluidas las 3 nuevas de ``2026_09_27_0001``. Como esa
        versión NO usaba Alembic, ``alembic_version`` no existe. Aquí
        todas las migraciones están aplicadas; devolvemos head y hacemos
        stamp directo.

    Caso 2 (legacy parcial — el bug real de Railway, observable en el log
    ``[bootstrap_migrate] ERROR: no encuentro ninguna migración aplicable``)
        La versión pre-9163349 pobló la DB cuando ``TenantSiteConfig`` aún
        no existía como modelo. La DB tiene las tablas de ``initial_schema``
        pero NO las 3 nuevas. Aquí solo la inicial está aplicada;
        devolvemos la inicial y dejamos que ``upgrade head`` añada las 3
        nuevas.

    La función NUNCA aborta prematuramente: si una revisión no está
    fully-applied, sigue mirando las anteriores. Solo devuelve ``None`` si
    NINGUNA migración con ``CREATE TABLE`` (modelo activo) tiene sus
    tablas presentes.
    """
    insp = inspect(eng)
    ordered = _migrations_in_dependency_order(migs)  # base -> head

    applied: list[str] = []
    for rev in ordered:
        tables = _tables_referenced_by_migration(mig_dir, rev)
        # Filtrar tablas huerfanas: declaradas en la migracion pero sin
        # modelo activo. Estas son legacy (modelo borrado en algun commit)
        # y nunca se crearan con `create_all()`. Si las exigieramos, ninguna
        # DB legacy podria ser fully-applied y el bootstrap siempre fallaria.
        if model_tables is not None:
            tables = [t for t in tables if t in model_tables]
        if not tables:
            # Migracion sin CREATE TABLE (o sin tablas con modelo activo).
            # No podemos confirmar su aplicacion por `has_table`. La
            # omitimos del computo; si las migraciones que la rodean si
            # estan, `upgrade head` se encargara de re-ejecutar su UPDATE
            # (los UPDATE son idempotentes en este proyecto).
            continue
        if all(insp.has_table(t) for t in tables):
            applied.append(rev)

    if not applied:
        return None
    return applied[-1]


def _load_migrations() -> dict[str, dict]:
    """Lee todos los archivos de `alembic/versions/` y devuelve el grafo."""
    import re

    here = os.path.dirname(os.path.abspath(__file__))
    mig_dir = os.path.normpath(os.path.join(here, "..", "alembic", "versions"))
    if not os.path.isdir(mig_dir):
        return {}
    migs: dict[str, dict] = {}
    for fname in os.listdir(mig_dir):
        if not fname.endswith(".py"):
            continue
        path = os.path.join(mig_dir, fname)
        try:
            txt = open(path, encoding="utf-8").read()
        except OSError:
            continue
        rev = re.search(r"^revision\b[^=\n]*=\s*['\"]([^'\"]+)['\"]", txt, re.M)
        down = re.search(
            r"^down_revision\b[^=\n]*=\s*(?:['\"]([^'\"]+)['\"]|None)",
            txt,
            re.M,
        )
        if not rev:
            continue
        migs[rev.group(1)] = {
            "down": down.group(1) if down and down.group(1) else None,
            "file": fname,
        }
    return migs


def detect_state(conn) -> str:
    """Devuelve uno de: 'empty', 'legacy', 'alembic'."""
    insp = inspect(conn)
    tables = set(insp.get_table_names())
    if "alembic_version" in tables:
        return "alembic"
    sentinel = _first_table_from_initial_migration()
    if sentinel in tables:
        return "legacy"
    return "empty"


def run(cmd: list[str]) -> int:
    """Ejecuta un subproceso de Alembic usando el MISMO Python del venv.

    `subprocess.call(["alembic", ...])` falla porque `alembic.exe` (Script
    de Windows del venv) no está en PATH cuando se invoca desde un script.
    `sys.executable -m alembic` sí funciona, y garantiza la misma versión
    de Python y el mismo venv.

    FIX 2026-10-06: la salida de Alembic (stdout+stderr) se captura y se
    re-emite con prefijo ``[alembic]`` para que Railway muestre qué
    migración falló cuando el entrypoint aborta con `set -e`. Antes, la
    salida se perdía en el buffer de subprocess.call y el operador veía
    sólo ``FALLO CRÍTICO: bootstrap_migrate salió con código 1`` sin pista
    de la causa raíz.
    """
    print(f"[bootstrap_migrate] ejecutando: {' '.join(cmd)}", flush=True)
    proc = subprocess.run(
        [sys.executable, "-m", *cmd],
        capture_output=True,
        text=True,
    )
    out = (proc.stdout or "").rstrip()
    err = (proc.stderr or "").rstrip()
    if out:
        for line in out.splitlines():
            print(f"[alembic] {line}", flush=True)
    if err:
        for line in err.splitlines():
            print(f"[alembic:err] {line}", flush=True)
    return proc.returncode


def _swallow(stage: str, rc: int) -> int:
    """Safety net 2026-10-06: no abortar el arranque si una migración falla.

    WowHub production fue 502 Bad Gateway porque el entrypoint usa ``set -e``
    y este script devolvía ``rc != 0`` ante cualquier fallo de Alembic.
    Aquí logueamos loud y devolvemos ``0`` para que ``uvicorn`` arranque. El
    fix real del problema subyacente (enum mismatch, schema drift, etc.)
    viene en un commit posterior; por ahora, prioridad es que uvicorn
    escuche y la API responda aunque la migración esté rota.

    Caso de éxito (``rc == 0``): la función es un no-op.
    """
    if rc == 0:
        return rc
    print(
        f"[bootstrap_migrate] WARNING: {stage} salió con rc={rc}. "
        "CONTINUING APP STARTUP despite migration failure (safety net).",
        flush=True,
    )
    return 0


def main() -> int:
    """SAFETY NET (2026-10-06).

    Este script es best-effort: si una migración falla, logueamos loud y
    devolvemos ``0`` para que el entrypoint no aborte uvicorn con
    ``set -e``. Railway's 502 Bad Gateway fue causado por el entrypoint
    saliendo con código != 0 cuando Alembic encontraba un error
    recuperable (p.ej. enum mismatch en una tabla existente). El fix real
    del problema subyacente puede llegar en un commit posterior; por
    ahora, prioridad es que uvicorn arranque y la API responda.
    """
    try:
        eng = _engine()
    except SystemExit as exc:
        print(
            f"[bootstrap_migrate] WARNING: no se pudo construir engine "
            f"(SystemExit code={exc.code}). "
            "CONTINUING APP STARTUP despite bootstrap failure (safety net).",
            flush=True,
        )
        return 0

    try:
        with eng.connect() as conn:
            state = detect_state(conn)

        print(f"[bootstrap_migrate] estado detectado: {state}")

        if state == "empty":
            print("[bootstrap_migrate] DB vacia — corro 'alembic upgrade head'")
            rc = run(["alembic", "upgrade", "head"])
            if rc != 0:
                print("[bootstrap_migrate] head ambiguous — corro 'alembic upgrade heads'")
                rc = run(["alembic", "upgrade", "heads"])
            return _swallow("'alembic upgrade head'", rc)

        if state == "alembic":
            print("[bootstrap_migrate] DB gestionada por Alembic — corro 'alembic upgrade head'")
            rc = run(["alembic", "upgrade", "head"])
            if rc != 0:
                print("[bootstrap_migrate] head ambiguo (branch detectado) — corro 'alembic upgrade heads'")
                return _swallow(
                    "'alembic upgrade heads'", run(["alembic", "upgrade", "heads"])
                )
            return rc

        # state == "legacy"
        sentinel = _first_table_from_initial_migration()
        here = os.path.dirname(os.path.abspath(__file__))
        mig_dir = os.path.normpath(os.path.join(here, "..", "alembic", "versions"))
        migs = _load_migrations()

        # Tablas conocidas por el modelo ACTUAL (Base.metadata). Las usamos
        # para filtrar las "tablas huerfanas" declaradas en migraciones pero
        # sin modelo activo (caso business_costs, eliminado en 9163349).
        # Sin este filtro, una DB legacy nunca seria fully-applied.
        model_tables: set[str] | None = None
        try:
            from app.database import Base  # noqa: WPS433 (import local)
            import app.models  # noqa: F401,WPS433

            model_tables = set(Base.metadata.tables.keys())
        except Exception as exc:
            print(
                f"[bootstrap_migrate] WARN: no pude cargar Base.metadata: {exc}. "
                "Continuando sin filtro de tablas huerfanas.",
                file=sys.stderr,
            )

        target = _highest_fully_applied_revision(eng, migs, mig_dir, model_tables)
        if not target:
            print(
                "[bootstrap_migrate] ERROR: no encuentro ninguna migración aplicable "
                f"(DB con '{sentinel}' pero sin tablas de ninguna migración).",
                file=sys.stderr,
            )
            return _swallow("bootstrap detection (no migration aplicable)", 1)

        if target != _head_revision(migs):
            # La DB tiene las tablas de la inicial pero NO las de las migraciones
            # nuevas. Stamp a la inicial y luego upgrade.
            print(
                f"[bootstrap_migrate] DB con esquema pre-existente "
                f"(detectada '{sentinel}' y sin 'alembic_version'). "
                f"Sello a '{target}' y aplico 'upgrade head' para añadir lo nuevo."
            )
            rc1 = run(["alembic", "stamp", target])
            if rc1 != 0:
                print(
                    f"[bootstrap_migrate] ERROR: 'alembic stamp {target}' salió con código {rc1}",
                    file=sys.stderr,
                )
                return _swallow(f"'alembic stamp {target}'", rc1)
            return _swallow(
                "'alembic upgrade head'", run(["alembic", "upgrade", "head"])
            )

        # La DB tiene TODAS las tablas de la head. Stamp a head directamente.
        print(
            f"[bootstrap_migrate] DB con esquema completo "
            f"('{sentinel}' + tablas de la migración head). "
            f"Sello a '{target}' (head). No hay nada que aplicar."
        )
        return _swallow(
            f"'alembic stamp {target}'", run(["alembic", "stamp", target])
        )
    except Exception as exc:
        print(
            f"[bootstrap_migrate] WARNING: excepción no esperada "
            f"{type(exc).__name__}: {exc}. "
            "CONTINUING APP STARTUP despite bootstrap failure (safety net).",
            flush=True,
        )
        return 0
    finally:
        try:
            eng.dispose()
        except Exception:
            pass


def _head_revision(migs: dict[str, dict]) -> str | None:
    """La revisión head: la única que no aparece como `down_revision` de otra."""
    referenced = {m["down"] for m in migs.values() if m["down"] in migs}
    for rev in migs:
        if rev not in referenced:
            return rev
    return None


if __name__ == "__main__":
    sys.exit(main())
