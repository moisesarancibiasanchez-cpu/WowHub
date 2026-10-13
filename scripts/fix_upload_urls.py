"""Arregla URLs de uploads que quedaron con el host equivocado.

Causa: versiones anteriores de UploadService.py usaban
    self.base_url = os.getenv("BASE_URL", "http://localhost:8000")
y en Railway BASE_URL no estaba seteada, así que los registros Upload
quedaron con URLs como  http://localhost:8000/storage/<tid>/<file>.jpg
que el browser en producción no puede cargar.

Este script reemplaza el prefijo equivocado por la URL pública real
(settings.public_base_url), sin tocar el path (que es el mismo).

Uso:
    python scripts/fix_upload_urls.py [--dry-run] [--old-prefix http://localhost:8000]

Por defecto el old-prefix es "http://localhost:8000" y el nuevo es
settings.public_base_url. Pasa --old-prefix explícito si tu problema es
otro (por ej. un dominio de Railway anterior).
"""
import argparse
import os
import sys
from pathlib import Path

# Permitir ejecutar desde la raíz del proyecto
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select, update  # noqa: E402

from app.config import settings  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.models.upload import Upload  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Solo muestra qué cambiaría, sin escribir")
    parser.add_argument(
        "--old-prefix",
        default="http://localhost:8000",
        help="Prefijo de URL a reemplazar (default: http://localhost:8000)",
    )
    parser.add_argument(
        "--new-prefix",
        default=None,
        help="Prefijo nuevo (default: settings.public_base_url)",
    )
    args = parser.parse_args()

    new_prefix = (args.new_prefix or settings.public_base_url).rstrip("/")
    old_prefix = args.old_prefix.rstrip("/")
    storage_marker = "/storage/"

    print(f"Buscando URLs con prefijo: {old_prefix}{storage_marker}...")
    print(f"Reemplazando por:           {new_prefix}{storage_marker}...")
    if args.dry_run:
        print("(modo dry-run: no se escriben cambios)")

    with SessionLocal() as db:
        rows = db.execute(
            select(Upload).where(Upload.url.like(f"{old_prefix}{storage_marker}%"))
        ).scalars().all()

        if not rows:
            print("No se encontraron uploads con ese prefijo. Nada que hacer.")
            return 0

        print(f"Encontrados: {len(rows)} uploads a actualizar")
        for u in rows:
            new_url = u.url.replace(f"{old_prefix}{storage_marker}", f"{new_prefix}{storage_marker}", 1)
            print(f"  - {u.id}  {u.url}  ->  {new_url}")
            if not args.dry_run:
                u.url = new_url
        if not args.dry_run:
            db.commit()
            print(f"✓ {len(rows)} uploads actualizados.")
        else:
            print(f"  (dry-run: {len(rows)} cambios NO aplicados)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
