"""FIX — ``orders.status`` migrar de ENUM a VARCHAR(40) + traducir valores.

Revision ID: 2026_10_06_0003
Revises: 2026_10_06_0002
Create Date: 2026-10-06

Contexto
--------
La migración inicial creó el ENUM de PostgreSQL::

  sa.Column('status', sa.Enum('PENDING', 'CONFIRMED', 'PREPARING',
                              'READY', 'DELIVERED', 'CANCELED',
                              name='order_status'), nullable=False)

Pero ``app/models/order.py`` declara::

  class OrderStatus(str, enum.Enum):
      RECIBIDO       = "recibido"
      CONFIRMADO     = "confirmado"
      EN_PREPARACION = "en_preparacion"
      LISTO          = "listo"
      ENTREGADO      = "entregado"
      CANCELADO      = "cancelado"
      PAGADO         = "pagado"

Los valores en el modelo (lowercase en español) NO existen en el ENUM de PG.
Cada ``Order.status != OrderStatus.CANCELADO`` en ``stats_service`` /
``customers`` / ``opportunity_engine`` / ``analytics`` / etc. hace que
SQLAlchemy emita ``ORDER BY status != 'cancelado'`` → PG rechaza con
``invalid input value for enum order_status: 'cancelado'`` (HTTP 500).

Endpoints afectados en producción:
  /tenants/{id}/stats/overview
  /tenants/{id}/opportunities
  /tenants/{id}/opportunities/daily-brief
  /tenants/{id}/analytics/sales-trend
  /tenants/{id}/analytics/sales-7d
  /tenants/{id}/analytics/customer-segments

Fix (alineado con el patrón HU_45 — columnas string en lugar de ENUM para
flexibilidad):
1. Traducir valores viejos a los nuevos (PENDING → recibido, etc.).
2. ``ALTER COLUMN ... TYPE VARCHAR(40) USING status::text``.
3. ``DROP TYPE IF EXISTS order_status`` (libera el tipo).

SQLite: el modelo sigue usando ``Enum`` localmente pero el tipo es portable;
no-op en SQLite (la columna ya es TEXT).
"""
from __future__ import annotations

import logging

from alembic import op
from sqlalchemy import text

revision = "2026_10_06_0003"
down_revision = "2026_10_06_0002"
branch_labels = None
depends_on = None


logger = logging.getLogger("alembic.runtime.migration")


# Mapa de valores viejos (PG ENUM) → valores nuevos (modelo de código).
_STATUS_TRANSLATIONS = (
    ("PENDING", "recibido"),
    ("CONFIRMED", "confirmado"),
    ("PREPARING", "en_preparacion"),
    ("READY", "listo"),
    ("DELIVERED", "entregado"),
    ("CANCELED", "cancelado"),
)


def upgrade() -> None:
    """Migra ``orders.status`` de ENUM a VARCHAR(40) con valores traducidos."""
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        logger.info("SQLite: orders.status ya es portable; no-op")
        return

    # 1) Traducir valores existentes del ENUM viejo → valores del modelo.
    for old, new in _STATUS_TRANSLATIONS:
        op.execute(text(f"UPDATE orders SET status = '{new}' WHERE status = '{old}'"))
    # (PAGADO es valor nuevo; cualquier status NULL defensivo → recibido).
    op.execute(
        text(
            "UPDATE orders SET status = 'recibido' "
            "WHERE status IS NULL OR status NOT IN "
            "  ('recibido','confirmado','en_preparacion',"
            "   'listo','entregado','cancelado','pagado')"
        )
    )

    # 2) Cambiar el tipo de columna: ENUM → VARCHAR(40).
    op.execute(
        text(
            "ALTER TABLE orders "
            "ALTER COLUMN status TYPE VARCHAR(40) USING status::text"
        )
    )

    # 3) Eliminar el tipo ENUM (ya no se usa).
    op.execute(text("DROP TYPE IF EXISTS order_status"))

    logger.info("orders.status: ENUM→VARCHAR(40) + traducción OK")


def downgrade() -> None:
    """Revierte (best-effort) recreando el ENUM y traduciendo de vuelta."""
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    # Re-crear el ENUM con los valores viejos.
    op.execute(
        text(
            "CREATE TYPE order_status AS ENUM "
            "('PENDING','CONFIRMED','PREPARING','READY','DELIVERED','CANCELED')"
        )
    )

    # Traducir de vuelta (best-effort).
    reverse_map = {n: o for o, n in _STATUS_TRANSLATIONS}
    for new, old in reverse_map.items():
        op.execute(text(f"UPDATE orders SET status = '{old}' WHERE status = '{new}'"))

    # Cambiar el tipo de vuelta a ENUM. Si el estado actual no calza en el ENUM
    # (p.ej. 'pagado'), falla — eso es esperado.
    op.execute(
        text(
            "ALTER TABLE orders "
            "ALTER COLUMN status TYPE order_status USING status::order_status"
        )
    )