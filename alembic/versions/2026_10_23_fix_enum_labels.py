"""FIX — alinear los ENUM ``product_status`` y ``quote_status`` con el modelo.

Revision ID: 2026_10_23_fix_enum_labels
Revises: 2026_10_21_fix_drift
Create Date: 2026-10-23

Contexto
--------
El ENUM ``product_status`` se creó en la migración inicial
``2026_09_07_1002-f2efb29e03b1_initial_schema.py`` con valores en INGLÉS y
MAYÚSCULAS::

    sa.Enum('DRAFT', 'ACTIVE', 'OUT_OF_STOCK', 'ARCHIVED', name='product_status')

Pero el modelo ``app/models/product.py`` declara ``ProductStatus`` con valores
en minúsculas y fuerza el uso del ``.value``::

    Enum(ProductStatus, name="product_status",
         values_callable=lambda obj: [e.value for e in obj])
    # DRAFT="draft", ACTIVE="active", OUT_OF_STOCK="out_of_stock",
    # ARCHIVED="archived"

Cada filtro ``WHERE status = 'active'`` genera ``'active'::product_status`` y
PostgreSQL valida el cast contra los miembros del ENUM. Como ``active`` no
existe en el TYPE, la consulta falla::

    DataError: (psycopg.errors.InvalidTextRepresentation)
    invalid input value for enum product_status: "active"

Esto provoca HTTP 500 en los endpoints que consultan o filtran productos:

    GET /api/v1/public/t/{slug}/catalog
    GET /api/v1/public/t/{slug}/products/{product_slug}
    GET /api/v1/tenants/{tenant_id}/products
    GET /api/v1/tenants/{tenant_id}/search/products

El mismo desfase existe en ``quote_status`` (creado en mayúsculas:
DRAFT/SENT/VIEWED/ACCEPTED/REJECTED/EXPIRED; el modelo usa minúsculas),
lo que rompe los endpoints de cotizaciones.

Este error estaba ENMASCARADO por el de ``products.product_type`` (Bug 1): el
``SELECT`` fallaba antes por la columna inexistente. Al reparar el esquema,
el desfase del ENUM quedó expuesto.

Por qué NO se corrigió en ``order_status``
-------------------------------------------
``2026_10_06_0004_order_status_add_lowercase_values.py`` ya resolvió ese caso
con el patrón que se replica aquí: ``ALTER TYPE ... ADD VALUE IF NOT EXISTS``.
No existe migración equivalente para ``product_status`` ni ``quote_status``:
ahí está el hueco.

Fix (patrón HU_26 / order_status, ADITIVO y NO destructivo)
-------------------------------------------------------------
- ``ALTER TYPE <tipo> ADD VALUE IF NOT EXISTS '<label>'`` para cada label que
  el modelo declara. Idempotente (PG 9.6+).
- NO se recrea el TYPE, NO se DROP, NO se tocan filas, NO se bloquea la tabla.
- Los labels en mayúsculas (legacy) se conservan: pueden quedar filas viejas
  con esos valores y siguen siendo legibles.

Idempotencia
------------
Si el TYPE no existe (base recién creada donde ``create_all`` corrió después
de la migración), el bloque DO lo crea con TODOS los labels (legacy +
lowercase), igual que hace la migración de ``order_status``.

Reversible
----------
PG no permite ``DROP VALUE`` de un ENUM. El ``downgrade`` es un no-op
documentado: revertirlo exigiría recrear el TYPE y migrar la columna, lo
que no es seguro en producción.
"""
from __future__ import annotations

import logging

from alembic import op
from sqlalchemy import text

revision = "2026_10_23_fix_enum_labels"
down_revision = "2026_10_21_fix_drift"
branch_labels = None
depends_on = None


logger = logging.getLogger("alembic.runtime.migration")


# ── Tipos a corregir: (nombre del TYPE, labels legacy, labels del modelo) ──
ENUMS: list[tuple[str, tuple[str, ...], tuple[str, ...]]] = [
    (
        "product_status",
        ("DRAFT", "ACTIVE", "OUT_OF_STOCK", "ARCHIVED"),
        ("draft", "active", "out_of_stock", "archived"),
    ),
    (
        "quote_status",
        ("DRAFT", "SENT", "VIEWED", "ACCEPTED", "REJECTED", "EXPIRED"),
        ("draft", "sent", "viewed", "accepted", "rejected", "expired"),
    ),
]


def _ensure_type(type_name: str, labels: tuple[str, ...]) -> None:
    """Crea el TYPE si no existe (por si ``create_all`` corrió después)."""
    values_literal = ", ".join(f"'{v}'" for v in labels)
    op.execute(
        text(
            f"""
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = '{type_name}') THEN
                    CREATE TYPE {type_name} AS ENUM ({values_literal});
                END IF;
            END
            $$;
            """
        )
    )


def upgrade() -> None:
    """Agrega a cada TYPE los labels que el modelo declara en minúsculas."""
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        logger.info("SQLite: no hay ENUM; no-op")
        return

    for type_name, legacy_values, model_values in ENUMS:
        # 1) El TYPE debe existir (o se crea con todos los labels).
        _ensure_type(type_name, tuple(legacy_values) + tuple(model_values))
        logger.info("%s: tipo verificado/asegurado", type_name)

        # 2) Agregar los labels del modelo. Idempotente (PG 9.6+).
        for value in model_values:
            op.execute(text(f"ALTER TYPE {type_name} ADD VALUE IF NOT EXISTS '{value}'"))
            logger.info("%s: +'%s' OK", type_name, value)

        logger.info(
            "%s: el TYPE contiene %d labels del modelo",
            type_name,
            len(model_values),
        )


def downgrade() -> None:
    """No-op: PostgreSQL no permite ``DROP VALUE`` de un ENUM.

    Revertir de verdad exigiría recrear el TYPE sin los labels nuevos y
    migrar la columna, lo que no es seguro en producción con datos.
    """
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    logger.warning(
        "downgrade no implementado (PG no permite DROP VALUE en un ENUM). "
        "Los labels agregados se conservan; son inofensivos."
    )
