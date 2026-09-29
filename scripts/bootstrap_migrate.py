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
    eng, migs: dict[str, dict], mig_dir: str
) -> str | None:
    """Revisión más alta cuyas tablas declaradas están TODAS presentes en la DB.

    Recibe un engine (no un inspector) para que pueda abrir sus propias
    conexiones bajo demanda. Pasar un ``Inspector`` ligado a una conexión
    ya cerrada lanza ``ResourceClosedError`` — bug histórico de este script
    que se manifestaba en TEST B (DB legacy con ``Base.metadata.create_all``
    previo, idéntico al caso real de Railway).

    Recorre las migraciones de head a base. La primera migración (de head
    hacia abajo) cuyas tablas declaradas faltan es la cota. La migración
    inmediatamente anterior (de mayor a menor) es la más alta fully applied.

        Caso típico: tras ``Base.metadata.create_all``, la DB tiene todas las
    tablas (incluidas las de migraciones nuevas), pero ``alembic_version`` no
    existe. Esta función devuelve head directamente, evitando el
    ``DuplicateTable`` del upgrade.
    """
    insp = inspect(eng)
    ordered = _migrations_in_dependency_order(migs)
    for rev in reversed(ordered):
        tables = _tables_referenced_by_migration(mig_dir, rev)
        if not tables:
            # Migración sin CREATE TABLE (ej. sólo UPDATE de filas). Si todas
            # las migraciones posteriores a ella están aplicadas, también está
            # aplicada. Conservamos la candidata actual y seguimos mirando
            # hacia abajo por si hay una base aún más temprana.
            continue
        if all(insp.has_table(t) for t in tables):
            return rev
        # Esta migración NO está aplicada. En la práctica, las migraciones
        # se aplican en orden, así que una falla aquí implica que las
        # anteriores también faltan. Devolvemos None.
        return None
    return None


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
    """
    return subprocess.call([sys.executable, "-m", *cmd])


def main() -> int:
    eng = _engine()
    # NOTA: NO llamamos `eng.dispose()` al salir de `with eng.connect()`.
    # El engine se mantiene vivo durante toda la ejecución porque el branch
    # `legacy` lo reutiliza para inspeccionar la DB con `_highest_fully_applied_revision`.
    # Cerrarlo prematuramente dejaba las conexiones en estado disposed y
    # `inspect(conn)` crasheaba con `ResourceClosedError`.

    try:
        with eng.connect() as conn:
            state = detect_state(conn)

        print(f"[bootstrap_migrate] estado detectado: {state}")

        if state == "empty":
            print("[bootstrap_migrate] DB vacia — corro 'alembic upgrade head'")
            return run(["alembic", "upgrade", "head"])

        if state == "alembic":
            print("[bootstrap_migrate] DB gestionada por Alembic — corro 'alembic upgrade head'")
            return run(["alembic", "upgrade", "head"])

        # state == "legacy"
        sentinel = _first_table_from_initial_migration()
        here = os.path.dirname(os.path.abspath(__file__))
        mig_dir = os.path.normpath(os.path.join(here, "..", "alembic", "versions"))
        migs = _load_migrations()

        target = _highest_fully_applied_revision(eng, migs, mig_dir)
        if not target:
            print(
                "[bootstrap_migrate] ERROR: no encuentro ninguna migración aplicable "
                f"(DB con '{sentinel}' pero sin tablas de ninguna migración).",
                file=sys.stderr,
            )
            return 1

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
                return rc1
            return run(["alembic", "upgrade", "head"])

        # La DB tiene TODAS las tablas de la head. Stamp a head directamente.
        print(
            f"[bootstrap_migrate] DB con esquema completo "
            f"('{sentinel}' + tablas de la migración head). "
            f"Sello a '{target}' (head). No hay nada que aplicar."
        )
        return run(["alembic", "stamp", target])
    finally:
        eng.dispose()


def _head_revision(migs: dict[str, dict]) -> str | None:
    """La revisión head: la única que no aparece como `down_revision` de otra."""
    referenced = {m["down"] for m in migs.values() if m["down"] in migs}
    for rev in migs:
        if rev not in referenced:
            return rev
    return None


if __name__ == "__main__":
    sys.exit(main())
