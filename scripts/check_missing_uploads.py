"""Diagnóstico de uploads cuyo archivo NO está en el servidor.

Contexto (V2.014, 2026-10-24)
----------------------------
En producción (Railway) el almacenamiento es **local y efímero**: el
directorio ``storage/`` vive dentro del contenedor y NO está montado en un
volumen persistente. Cada despliegue reconstruye el contenedor, así que los
archivos subidos se pierden aunque la fila de la tabla ``uploads`` siga
viva en la base de datos.

El síntoma es que el registro existe (``GET /uploads`` lo lista) pero el
archivo no: ``GET /tenants/{tid}/uploads/{uid}/content`` responde 404
"Archivo no encontrado en disco" y la landing pública tampoco muestra la
imagen.

Este script es **de sólo lectura**: lista los uploads cuyo archivo falta,
para saber exactamente qué imágenes hay que volver a subir. No borra ni
modifica nada.

Uso::

    # Dentro del contenedor de Railway (disco real del volumen):
    DATABASE_URL=postgresql://... python -m scripts.check_missing_uploads

    # Sólo la lista de la base de datos (desde tu máquina): sirve para
    # saber QUÉ imágenes hay que volver a subir.
    DATABASE_URL=postgresql://... python -m scripts.check_missing_uploads --db-only

    # Filtrar por un tenant:
    DATABASE_URL=postgresql://... python -m scripts.check_missing_uploads --tenant-id <uuid>
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlalchemy import select

# La consola de Windows usa cp1252 y revienta con los caracteres del aviso
# (UnicodeEncodeError). Se fuerza UTF-8 con reemplazo, como el resto de los
# scripts del repo.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass

from app.config import get_settings  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.models.upload import Upload  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Lista uploads sin archivo en disco.")
    ap.add_argument("--tenant-id", default=None, help="Filtrar por un tenant_id.")
    ap.add_argument(
        "--db-only",
        action="store_true",
        help=(
            "No comparar con el disco: listar todos los uploads de la base "
            "de datos (útil desde tu máquina, donde el disco de producción "
            "no está)."
        ),
    )
    args = ap.parse_args()

    settings = get_settings()
    storage_dir = Path(settings.storage_dir)
    print(f"storage_dir: {storage_dir}  (existe: {storage_dir.is_dir()})")

    with SessionLocal() as db:
        q = select(Upload).order_by(Upload.created_at.desc())
        if args.tenant_id:
            q = q.where(Upload.tenant_id == str(args.tenant_id))
        uploads = list(db.execute(q).scalars())

    if args.db_only:
        print(f"uploads totales en la base: {len(uploads)}")
        print()
        print(f"{'tenant_id':<38} {'id':<38} {'purpose':<22} archivo")
        print("-" * 120)
        for u in uploads:
            print(f"{str(u.tenant_id):<38} {str(u.id):<38} {str(u.purpose or '-'):<22} {u.filename}")
        print()
        print("Éstos son los archivos que la plataforma tiene registrados.")
        print("Las imágenes que ya no se ven en el dashboard son las que hay")
        print("que volver a subir (el archivo no está en el volumen).")
        return 0

    faltan: list[tuple[Upload, Path]] = []
    for u in uploads:
        if not u.stored_filename:
            faltan.append((u, storage_dir / str(u.tenant_id) / "(sin stored_filename)"))
            continue
        path = storage_dir / str(u.tenant_id) / u.stored_filename
        if not path.is_file():
            faltan.append((u, path))

    print(f"uploads totales: {len(uploads)}")
    print(f"sin archivo en disco: {len(faltan)}")

    if faltan and not storage_dir.is_dir():
        print()
        print("⚠ ATENCIÓN: el directorio de storage no existe en esta máquina.")
        print("  Este resultado NO describe el disco de producción: el volumen")
        print("  vive dentro del contenedor de Railway. Corré el script DENTRO")
        print("  del servicio (railway ssh / railway run) para el diagnóstico")
        print("  real, o usá --db-only para listar sólo la base de datos.")
        return 1

    if not faltan:
        print("OK: todos los archivos están presentes.")
        return 0

    print()
    print(f"{'tenant_id':<38} {'id':<38} {'purpose':<22} archivo")
    print("-" * 140)
    for u, path in faltan:
        print(f"{str(u.tenant_id):<38} {str(u.id):<38} {str(u.purpose or '-'):<22} {path.name}")

    print()
    print("ACCIÓN: volver a subir esas imágenes desde el dashboard.")
    print("        Para que no se vuelvan a perder, hay que montar un volumen")
    print("        persistente en /app/storage (Railway: Volume -> Mount Path).")
    return 1


if __name__ == "__main__":
    sys.exit(main())
