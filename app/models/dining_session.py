"""HU_19 — Mesero virtual con cuenta dividida (DiningSession).

Una DiningSession representa una mesa abierta en un local. Los pedidos
(Order) que pertenecen a la mesa se asocian vía DiningSessionItem.

Estados:
  - OPEN       : los comensales siguen pidiendo
  - CLOSED     : la mesa cerró (cuenta saldada o no, snapshot final)
  - CANCELLED  : se anuló (ej. mesa era de prueba)

Casos de uso soportados:
  - Cuenta dividida equitativa (split equally): GET /split
  - Snapshot al cerrar: total_cents, paid_cents, tip_cents
  - Propinas: PATCH /tip

Multi-tenant: todos los modelos heredan TenantMixin.
"""
from __future__ import annotations

import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean, DateTime, ForeignKey, Index, Integer, String, Text, JSON,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import GUID, BaseModel, TenantMixin


class DiningSessionStatus(str, enum.Enum):
    OPEN = "open"
    CLOSED = "closed"
    CANCELLED = "cancelled"


# ── DiningSession ─────────────────────────────────────────
class DiningSession(BaseModel, TenantMixin):
    """Mesa / sesión abierta en una sucursal.

    El snapshot final (CLOSED) congela total_cents, paid_cents y
    tip_cents para que la división no varíe si después se editan los
    pedidos históricos.
    """
    __tablename__ = "dining_sessions"

    branch_id: Mapped[str] = mapped_column(
        GUID(), ForeignKey("branches.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    # Tabla física opcional (la mayoría de los locales identifican
    # la mesa por nombre/libre, pero si hay un módulo de FloorPlan
    # podemos enlazar a una entidad Table).
    table_id: Mapped[Optional[str]] = mapped_column(
        GUID(), nullable=True, index=True,
    )

    # Identificador humano: "Mesa 7", "Barra 2", "Terraza A"
    table_label: Mapped[str] = mapped_column(String(60), nullable=False)

    status: Mapped[str] = mapped_column(
        String(16),
        default=DiningSessionStatus.OPEN.value,
        nullable=False,
        index=True,
    )

    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
    )
    closed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    # Snapshot de cuenta
    total_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    paid_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tip_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    customer_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    # Garzón / mesero asignado (opcional)
    server_user_id: Mapped[Optional[str]] = mapped_column(
        GUID(), nullable=True, index=True,
    )

    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    extra: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    items: Mapped[list["DiningSessionItem"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_dining_sessions_branch_status", "tenant_id", "branch_id", "status"),
        Index("ix_dining_sessions_opened", "branch_id", "opened_at"),
    )


# ── DiningSessionItem ─────────────────────────────────────
class DiningSessionItem(BaseModel):
    """Línea de pedido agregada a una mesa.

    Enlaza un OrderItem (que es donde vive el monto) con la sesión.
    `share_cents` se usa para división desigual (opcional). Si es NULL
    y la sesión se cierra con split equitativo, el sistema divide
    total_cents / customer_count.
    """
    __tablename__ = "dining_session_items"

    session_id: Mapped[str] = mapped_column(
        GUID(), ForeignKey("dining_sessions.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    order_item_id: Mapped[str] = mapped_column(
        GUID(), ForeignKey("order_items.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )

    # Si el cliente pidió que esta línea la pague una persona específica
    # (None = entra en la división equitativa).
    assigned_to: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)

    # Override manual del monto que paga esta línea en particular
    # (None = tomar total_cents del OrderItem).
    share_cents: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    notes: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)

    session: Mapped["DiningSession"] = relationship(back_populates="items")

    __table_args__ = (
        Index("ix_dsi_session", "session_id"),
    )
