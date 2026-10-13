"""Bootstrap: promover / revocar el flag `is_superuser` de un usuario.

Uso:
    # Promover
    python -m scripts.promote_superuser --email admin@wowhub.app --grant

    # Revocar
    python -m scripts.promote_superuser --email admin@wowhub.app --revoke

    # Listar todos los superusers
    python -m scripts.promote_superuser --list

Notas:
- Edita la base de datos directamente. Solo usar en bootstrap inicial o
  recuperación de emergencia.
- Si no hay NINGÚN superuser, se permite promover sin restricción.
- Si vas a revocar al ÚNICO superuser, primero promueve a otro.
"""
from __future__ import annotations

import argparse
import sys

from sqlalchemy import select

from app.database import SessionLocal
from app.models.user import User


def cmd_list() -> int:
    with SessionLocal() as db:
        rows = db.execute(
            select(User).where(User.is_superuser == True).order_by(User.email)  # noqa
        ).scalars().all()
        if not rows:
            print("No hay superusers aún.")
            return 0
        print(f"{len(rows)} superuser(s):")
        for u in rows:
            print(f"  - {u.email}  ({u.full_name})  active={u.is_active}  id={u.id}")
        return 0


def cmd_grant(email: str) -> int:
    email_norm = (email or "").strip().lower()
    if not email_norm:
        print("ERROR: email requerido", file=sys.stderr)
        return 2
    with SessionLocal() as db:
        u = db.execute(
            select(User).where(User.email == email_norm)
        ).scalar_one_or_none()
        if not u:
            print(f"ERROR: usuario '{email_norm}' no existe", file=sys.stderr)
            return 3
        if u.is_superuser:
            print(f"'{email_norm}' ya es superuser.")
            return 0
        u.is_superuser = True
        db.commit()
        print(f"OK: '{email_norm}' ahora es superuser (id={u.id}).")
        return 0


def cmd_revoke(email: str) -> int:
    email_norm = (email or "").strip().lower()
    if not email_norm:
        print("ERROR: email requerido", file=sys.stderr)
        return 2
    with SessionLocal() as db:
        u = db.execute(
            select(User).where(User.email == email_norm)
        ).scalar_one_or_none()
        if not u:
            print(f"ERROR: usuario '{email_norm}' no existe", file=sys.stderr)
            return 3
        if not u.is_superuser:
            print(f"'{email_norm}' NO es superuser, nada que revocar.")
            return 0
        # Bloqueo: no revocar al único superuser
        others = int(
            db.execute(
                select(User).where(
                    User.is_superuser == True,  # noqa
                    User.id != u.id,
                    User.is_active == True,  # noqa
                )
            ).all().__len__()
        )
        if others == 0:
            print("ERROR: no puedes revocar al ÚNICO superuser activo. Promueve a otro primero.", file=sys.stderr)
            return 4
        u.is_superuser = False
        db.commit()
        print(f"OK: '{email_norm}' ya no es superuser.")
        return 0


def main() -> int:
    p = argparse.ArgumentParser(description="Bootstrap de SUPERADMIN de WowHub")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--list", action="store_true", help="Listar todos los superusers")
    g.add_argument("--email", help="Email del usuario a modificar")
    p.add_argument("--grant", action="store_true", help="Promover a superuser")
    p.add_argument("--revoke", action="store_true", help="Revocar superuser")
    args = p.parse_args()

    if args.list:
        return cmd_list()
    if not (args.grant or args.revoke):
        p.error("Especifica --grant o --revoke (o usa --list)")
    if args.grant:
        return cmd_grant(args.email)
    return cmd_revoke(args.email)


if __name__ == "__main__":
    raise SystemExit(main())
