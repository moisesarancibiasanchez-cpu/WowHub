"""FIX — alinear los valores del ENUM ``order_status`` entre modelo y PG.

Revision ID: 2026_10_06_0004
Revises: 2026_10_06_0003
Create Date: 2026-10-06

Contexto
--------
El ENUM ``order_status`` se creó en la migración inicial
``2026_09_07_1002-f2efb29e03b1_initial_schema.py`` con valores en INGLÉS::

    sa.Enum('PENDING', 'CONFIRMED', 'PREPARING', 'READY',
            'DELIVERED', 'CANCELED', name='order_status')

Pero el modelo ``app/models/order.py`` define ``OrderStatus`` con valores en
ESPAÑOL (lowercase)::

    RECIBIDO       = "recibido"
    CONFIRMADO     = "confirmado"
    EN_PREPARACION = "en_preparacion"
    LISTO          = "listo"
    ENTREGADO      = "entregado"
    CANCELADO      = "cancelado"
    PAGADO         = "pagado"

Cada comparación ``Order.status == OrderStatus.X`` o ``Order.status != 'X'``
genera SQL del estilo ``WHERE status = 'recibido'::order_status``. PG
valida el cast contra los miembros del ENUM; como ``recibido`` no existe
en el ENUM original, devuelve::

    invalid input value for enum order_status: "recibido"

Esto provoca HTTP 500 en los endpoints que consultan órdenes:
  /tenants/{id}/stats/overview
  /tenants/{id}/opportunities
  /tenants/{id}/opportunities/daily-brief
  /tenants/{id}/analytics/sales-trend
  /tenants/{id}/analytics/sales-7d
  /tenants/{id}/analytics/customer-segments
  /tenants/{id}/customers

Fix (alineado con el patrón HU_45 — añadir valores sin DROP):
- ``ALTER TYPE order_status ADD VALUE IF NOT EXISTS 'recibido'`` etc.
- Idempotente (PG 9.6+): si el valor ya existe, no falla.
- NO modifica la columna (sigue siendo ``order_status`` ENUM).
- NO toca filas (no hay traducción de datos — los valores previos del ENUM
  viejo siguen ahí, simplemente ampliados con los nuevos).
- Compatible con SQLite (no-op, no hay ENUM en SQLite).

Notas técnicas
--------------
PG ≥ 12 permite ejecutar múltiples ``ALTER TYPE ... ADD VALUE`` dentro de
una transacción siempre que el valor no se use en la misma. Esta migración
solo añade valores y no los usa en la misma TX, así que funciona. Railway usa
PG 15+, por lo tanto compatible.

Robustez ante estado corrupto
-----------------------------
Si la migración rota ``567fc8f`` alcanzó a ejecutar ``DROP TYPE
order_status``, este archivo lo recrea (pues ``ALTER TYPE`` requiere que
el tipo exista). El bloque DO recrea el tipo con TODOS los valores
(viejos en inglés + nuevos en español) si y solo si no existe; en caso
contrario el ALTER TYPE ADD VALUE agrega los nuevos sin tocar los viejos.

Si necesitas revertir esta migración, PG no permite DROP VALUE en un
ENUM; tendrías que recrear el tipo y migrar la columna manualmente.
"""
from __future__ import annotations

import logging

from alembic import op
from sqlalchemy import text


revision = "2026_10_06_0004"
down_revision = "2026_10_06_0003"
branch_labels = None
depends_on = None


logger = logging.getLogger("alembic.runtime.migration")


# Valores que el modelo ``OrderStatus`` declara como lowercase en español.
# Se usan en (a) el DO block de CREATE TYPE condicional y (b) los ALTER
# TYPE ADD VALUE.
_LOWERCASE_VALUES = (
    "recibido",
    "confirmado",
    "en_preparacion",
    "listo",
    "entregado",
    "cancelado",
    "pagado",
)

# Valores originales del ENUM (creado en initial_schema). Se mantienen
# por si la migración rota 567fc8f dejó el tipo eliminado y necesitamos
# recrearlo completo (con viejos + nuevos para no perder semántica).
_UPPERCASE_VALUES = (
    "PENDING",
    "CONFIRMED",
    "PREPARING",
    "READY",
    "DELIVERED",
    "CANCELED",
)


def upgrade() -> None:
    """Asegura que el ENUM ``order_status`` exista con todos los valores."""
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        logger.info("SQLite: no hay ENUM; no-op")
        return

    # 1) Si el tipo fue eliminado por una migración rota previa, recrearlo
    #    con TODOS los valores (viejos + nuevos). DO block condicional.
    all_values = list(_UPPERCASE_VALUES) + list(_LOWERCASE_VALUES)
    values_literal = ", ".join(f"'{v}'" for v in all_values)
    op.execute(
        text(
            f"""
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'order_status') THEN
                    CREATE TYPE order_status AS ENUM ({values_literal});
                END IF;
            END
            $$;
            """
        )
    )
    logger.info("order_status: tipo verificado/asegurado")

    # 2) Añadir los valores nuevos (lowercase español). Idempotente:
    #    IF NOT EXISTS (PG 9.6+) evita error si el valor ya está.
    for value in _LOWERCASE_VALUES:
        op.execute(
            text(f"ALTER TYPE order_status ADD VALUE IF NOT EXISTS '{value}'")
        )
        logger.info("order_status: +'%s' OK", value)

    logger.info("orders.status ENUM contiene %d valores", len(all_values))


def downgrade() -> None:
    """No-op: PG no permite DROP VALUE de un ENUM.

    Para revertir realmente sería necesario recrear el ENUM sin los valores
    nuevos y migrar la columna, lo cual no es seguro en producción.
    """
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    logger.warning(
        "downgrade no implementado (PG no permite DROP VALUE en ENUM). "
        "Migración no se revierte automáticamente."
    )