"""HU_38 — Seed default RBAC policies.

Carga las policies defaults que mapean los 4 roles WowHub
(OWNER, ADMIN, STAFF, VIEWER) más SUPERADMIN al modelo Casbin.

Semántica legacy (matriz hard-coded anterior — ver ``_LEGACY_ROLE_MATRIX``
en ``app/core/security.py``):

    SUPERADMIN → todo (*, *, *, *)
    OWNER      → todo (read/write/delete sobre cualquier obj)
    ADMIN      → read/write sobre la mayoría; delete sólo orders/products
    STAFF      → read/write sobre pedidos y productos; NO delete
    VIEWER     → read-only sobre todo

Estas policies usan ``dom='*'`` (wildcard global) — el aislamiento por
tenant lo da el grouping ``(role:USER, role:OWNER, tenant-uuid)`` que
se crea por membresía en otra HU (HU_39 / fase 2). Aquí sembramos sólo
los templates globales.

Idempotencia:
  * ``seed_default_rbac_policies`` chequea ``count == 0`` antes de
    insertar. Si ya hay policies, NO duplica.
  * Para forzar un re-seed, usar ``seed_default_rbac_policies(reset=True)``.

Helpers:
  * ``seed_default_rbac_policies(reset=False)`` — idempotente.
  * ``rebuild_default_policies()`` — wipe + re-seed (para
    ``POST /rbac/seed?reset=true``).

NOTA sobre SUPERADMIN:
  * En el ``requires_permission`` decorator, si el usuario es
    ``is_superuser`` (User.is_superuser=True), el decorator hace bypass
    directo sin consultar Casbin. SUPERADMIN sólo aparece en policies
    como safety net / debug.
"""
from __future__ import annotations

import logging
from typing import List, Tuple

from sqlalchemy.orm import Session

from app.models.rbac import RBACPolicy

logger = logging.getLogger("wowhub.rbac.seed")


# ── Defaults ───────────────────────────────────────────────────────────
# Cada tupla es (sub, dom, obj, act).
# ``dom='*'`` significa que la policy aplica a todos los tenants.
DEFAULT_POLICIES: List[Tuple[str, str, str, str]] = [
    # ── SUPERADMIN: bypass total (decorator ya hace bypass, esto es debug)
    ("role:SUPERADMIN", "*", "*", "*"),

    # ── OWNER: control total del tenant ───────────────────────────────
    ("role:OWNER", "*", "*", "*"),

    # ── ADMIN: gestión operativa, sin delete global ──────────────────
    # Puede crear/editar productos, categorías, ver estadísticas, etc.
    ("role:ADMIN", "*", "product", "read"),
    ("role:ADMIN", "*", "product", "write"),
    ("role:ADMIN", "*", "product", "delete"),
    ("role:ADMIN", "*", "category", "read"),
    ("role:ADMIN", "*", "category", "write"),
    ("role:ADMIN", "*", "category", "delete"),
    ("role:ADMIN", "*", "order", "read"),
    ("role:ADMIN", "*", "order", "write"),
    ("role:ADMIN", "*", "order", "delete"),
    ("role:ADMIN", "*", "customer", "read"),
    ("role:ADMIN", "*", "customer", "write"),
    ("role:ADMIN", "*", "customer", "delete"),
    ("role:ADMIN", "*", "promotion", "read"),
    ("role:ADMIN", "*", "promotion", "write"),
    ("role:ADMIN", "*", "promotion", "delete"),
    ("role:ADMIN", "*", "branch", "read"),
    ("role:ADMIN", "*", "branch", "write"),
    ("role:ADMIN", "*", "branch", "delete"),
    ("role:ADMIN", "*", "stats", "read"),
    ("role:ADMIN", "*", "loyalty", "read"),
    ("role:ADMIN", "*", "loyalty", "write"),
    ("role:ADMIN", "*", "audit", "read"),
    ("role:ADMIN", "*", "settings", "read"),
    ("role:ADMIN", "*", "settings", "write"),

    # ── STAFF: operacional, sin deletes sensibles ─────────────────────
    ("role:STAFF", "*", "product", "read"),
    ("role:STAFF", "*", "product", "write"),  # puede crear/editar productos
    ("role:STAFF", "*", "category", "read"),
    ("role:STAFF", "*", "category", "write"),
    ("role:STAFF", "*", "order", "read"),
    ("role:STAFF", "*", "order", "write"),    # registrar pedidos
    # STAFF NO puede borrar órdenes/productos (verificar por ausencia).
    ("role:STAFF", "*", "customer", "read"),
    ("role:STAFF", "*", "customer", "write"),
    ("role:STAFF", "*", "promotion", "read"),
    ("role:STAFF", "*", "promotion", "write"),
    ("role:STAFF", "*", "branch", "read"),
    ("role:STAFF", "*", "stats", "read"),
    ("role:STAFF", "*", "loyalty", "read"),
    ("role:STAFF", "*", "loyalty", "write"),

    # ── VIEWER: solo lectura ─────────────────────────────────────────
    ("role:VIEWER", "*", "product", "read"),
    ("role:VIEWER", "*", "category", "read"),
    ("role:VIEWER", "*", "order", "read"),
    ("role:VIEWER", "*", "customer", "read"),
    ("role:VIEWER", "*", "promotion", "read"),
    ("role:VIEWER", "*", "branch", "read"),
    ("role:VIEWER", "*", "stats", "read"),
    ("role:VIEWER", "*", "loyalty", "read"),
    ("role:VIEWER", "*", "settings", "read"),

    # ── CASHIER (rol custom HU_19 / POS): subset de STAFF ────────────
    ("role:CASHIER", "*", "product", "read"),
    ("role:CASHIER", "*", "order", "read"),
    ("role:CASHIER", "*", "order", "write"),
    ("role:CASHIER", "*", "customer", "read"),
    ("role:CASHIER", "*", "customer", "write"),
    ("role:CASHIER", "*", "loyalty", "read"),
    ("role:CASHIER", "*", "loyalty", "write"),
]


# ── Funciones públicas ────────────────────────────────────────────────
def seed_default_rbac_policies(
    session_factory=None,
    reset: bool = False,
) -> int:
    """Inserta las policies default que falten.

    Idempotente y **reconciliador**: comprueba una por una las policies
    declaradas en ``DEFAULT_POLICIES`` y sólo inserta las que faltan. Antes
    el seed sólo corría cuando la tabla estaba COMPLETAMENTE vacía
    (``count() == 0``), así que una tabla a medias (o un seed que falló a
    medias) se quedaba así para siempre.

    FIX V2.012 — además, cada INSERT va en su propia transacción: si una
    policy concreta falla (p. ej. por drift de esquema), no se revierte
    el resto. Con un único ``commit()`` final, un solo INSERT inválido
    tumbaba las N filas y la tabla quedaba VACÍA: Casbin no tenía ninguna
    policy que cargar y denegaba TODAS las operaciones a TODOS los roles
    → HTTP 403 en 26 endpoints (clientes, productos, pedidos, RFM...).

    Retorna el número total de policies presentes tras la ejecución.
    """
    # Imports lazy para no acoplar seed <-> database en import time.
    if session_factory is None:
        from app.database import SessionLocal
        session_factory = SessionLocal

    # Imports de modelos también lazy pero ANTES del bloque session.query().
    from app.models.rbac import RBACPolicy, RBACGrouping

    with session_factory() as session:
        if reset:
            session.query(RBACPolicy).delete()
            session.query(RBACGrouping).delete()
            session.commit()
            logger.info("rbac_seed: reset=True — tablas vaciadas")

        # Qué hay ya: tupla (sub, dom, obj, act).
        existing_rows = {
            (row.sub, row.dom, row.obj, row.act)
            for row in session.query(
                RBACPolicy.sub, RBACPolicy.dom, RBACPolicy.obj, RBACPolicy.act
            ).all()
        }

        inserted = 0
        failed = 0
        for sub, dom, obj, act in DEFAULT_POLICIES:
            if (sub, dom, obj, act) in existing_rows:
                continue
            try:
                session.add(
                    RBACPolicy(
                        sub=sub,
                        dom=dom,
                        obj=obj,
                        act=act,
                        effect="allow",
                        priority=0,
                        note="default seed",
                    )
                )
                # Commit por policy: un fallo aislado no tumba el resto.
                session.commit()
                existing_rows.add((sub, dom, obj, act))
                inserted += 1
            except Exception as exc:  # noqa: BLE001
                failed += 1
                session.rollback()
                logger.error(
                    "rbac_seed: NO se pudo insertar la policy %s/%s/%s/%s: %s",
                    sub, dom, obj, act, exc,
                )

        total = session.query(RBACPolicy).count()
        if inserted:
            logger.info(
                "rbac_seed: insertadas %d policies faltantes (total %d)",
                inserted, total,
            )
        if failed:
            logger.error(
                "rbac_seed: %d policies NO se pudieron insertar — "
                "revisá el drift de esquema (rbac_policies.id / created_at)",
                failed,
            )
        if total == 0:
            logger.error(
                "rbac_seed: la tabla rbac_policies quedó VACÍA — Casbin va a "
                "denegar TODAS las operaciones hasta que se repueblen"
            )
        return total


def count_policies(session_factory=None) -> int:
    """Cuenta policies actuales (útil en health-check)."""
    if session_factory is None:
        from app.database import SessionLocal
        session_factory = SessionLocal
    with session_factory() as session:
        return session.query(RBACPolicy).count()


def rebuild_default_policies(session_factory=None) -> int:
    """Wipe + re-seed (endpoint ``POST /rbac/seed?reset=true``)."""
    return seed_default_rbac_policies(session_factory, reset=True)