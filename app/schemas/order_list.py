"""Schemas de Order para vistas Customer 360 (HU_25).

Schema dedicado para el endpoint ``GET /tenants/{tid}/customers/{cid}/orders``.
Tiene campos distintos al ``OrderListItem`` de ``app.schemas.order`` (que se usa
en la vista general de Pedidos). Mantenerlos separados evita acoplar el contrato
del dashboard de cliente al de gestión de pedidos — si cambian los requisitos de
uno, no se rompe el otro.
"""
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class CustomerOrderListItem(BaseModel):
    """Línea de pedido en el contexto del perfil 360° del cliente.

    Diseñado para una vista condensada: incluye resumen de productos (primeros 3)
    y el nombre de la sucursal (denormalizado para evitar N+1 en el front).
    """

    id: UUID
    # Identificador corto legible (ej. "ORD-20261006-AC12"). Es la columna ``number``
    # del modelo Order; la exponemos como ``short_id`` para que el front lo use
    # directamente sin saber del esquema interno.
    short_id: str
    status: str
    total_cents: int
    created_at: datetime
    # Canal/origen del pedido ("web", "whatsapp", "pos", etc.). String para
    # tolerar valores legacy que no estén en el Enum OrderSource.
    source: Optional[str] = None
    branch_name: Optional[str] = None
    items_count: int = 0
    items_summary: list[str] = []


class CustomerTimelineEvent(BaseModel):
    """Evento en la línea de tiempo cronológica del cliente (HU_25).

    Tipos:
      - ``order``     → pedido creado/cambió de estado
      - ``payment``   → pago confirmado (de payments.order_id)
      - ``rfm``       → recálculo RFM (cliente.rfm_updated_at)
      - ``customer``  → alta del cliente (cliente.created_at)
    """

    type: str
    date: datetime
    title: str
    detail: str
    amount_cents: Optional[int] = None