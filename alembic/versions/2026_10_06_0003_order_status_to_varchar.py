"""DISABLED — ``orders.status`` ya no migra a VARCHAR(40).

Revision ID: 2026_10_06_0003
Revises: 2026_10_06_0002
Create Date: 2026-10-06

Contexto
--------
La versión original de este archivo intentaba convertir ``orders.status``
de ENUM (PG) a VARCHAR(40) + traducir valores + DROP TYPE. Esa migración
provocó un 502 Bad Gateway en producción el 2026-10-06 (commit ``567fc8f``)
porque el ``set -e`` del entrypoint de Railway abortó el arranque al fallar
el ``bootstrap_migrate``.

Recuperación (commit de rollback):
   - ``app/models/order.py`` revierte ``String(40)`` → ``Enum(OrderStatus,
     name="order_status")`` (mismo estado que el commit ``089910c``).
   - Este archivo conserva su revision_id y down_revision (no se borra del
     grafo de Alembic para no dejar referencias colgantes en
     ``alembic_version``), pero su ``upgrade()`` y ``downgrade()`` son
     no-ops. Resultado: en cualquier DB gestionada por Alembic, esta
     revision ya figura como aplicada y no ejecuta DDL.

El fix real del bug de queries (``status='cancelado'`` rechazado por PG,
HTTP 500 en /stats/overview, /opportunities, /analytics/...) se aborda en
un PR separado, con pruebas contra PG real antes del push.

Para borrar este archivo en una limpieza posterior:
  rm alembic/versions/2026_10_06_0003_order_status_to_varchar.py
(requiere bajar alembic_version a 2026_10_06_0002 en la DB correspondiente).
"""
from __future__ import annotations

revision = "2026_10_06_0003"
down_revision = "2026_10_06_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """No-op. Véanse los comentarios del módulo."""
    return


def downgrade() -> None:
    """No-op. Véanse los comentarios del módulo."""
    return