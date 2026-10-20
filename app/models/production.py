"""ProductionJob: jobs derivados de Order para el Kanban de producción.
HU_52, HU_53 — Épica E8 (S5) — TOBE v134.2-Producción-v2.

Replica el Kanban de 7 etapas de WowPrint V1354_R2:
  nuevo → archivo_aprobado → preparando → imprimiendo → terminacion → listo → entregado
  + cancelado (terminal)

Es INDEPENDIENTE de Order.status (que es comercial).
Relación 1-N: una Order puede tener N ProductionJob (uno por OrderItem que requiere producción).
"""
import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import GUID, BaseModel, TenantMixin


class ProductionJobStatus(str, enum.Enum):
    """Pipeline de producción — replica WowPrint línea 134."""
    NUEVO = "nuevo"
    ARCHIVO_APROBADO = "archivo_aprobado"
    PREPARANDO = "preparando"
    IMPRIMIENDO = "imprimiendo"
    TERMINACION = "terminacion"
    LISTO = "listo"
    ENTREGADO = "entregado"
    CANCELADO = "cancelado"


# State machine de transiciones (HU_53)
PRODUCTION_JOB_TRANSITIONS = {
    ProductionJobStatus.NUEVO: {
        ProductionJobStatus.ARCHIVO_APROBADO, ProductionJobStatus.CANCELADO
    },
    ProductionJobStatus.ARCHIVO_APROBADO: {
        ProductionJobStatus.PREPARANDO, ProductionJobStatus.CANCELADO
    },
    ProductionJobStatus.PREPARANDO: {
        ProductionJobStatus.IMPRIMIENDO, ProductionJobStatus.CANCELADO
    },
    ProductionJobStatus.IMPRIMIENDO: {
        ProductionJobStatus.TERMINACION, ProductionJobStatus.CANCELADO
    },
    ProductionJobStatus.TERMINACION: {
        ProductionJobStatus.LISTO, ProductionJobStatus.CANCELADO
    },
    ProductionJobStatus.LISTO: {
        ProductionJobStatus.ENTREGADO, ProductionJobStatus.CANCELADO
    },
    ProductionJobStatus.ENTREGADO: set(),  # terminal
    ProductionJobStatus.CANCELADO: set(),  # terminal
}


class ProductionJob(BaseModel, TenantMixin):
    """Job de producción derivado de un OrderItem.
    
    Se crea automáticamente cuando Order.transition(CONFIRMADO) y
    OrderItem.product.product_type ∈ (PRINT, M2, PRODUCTION_ONLY).
    """
    __tablename__ = "production_jobs"

    # Vínculo al pedido comercial
    order_id: Mapped[str] = mapped_column(
        GUID(),
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    order_item_id: Mapped[Optional[str]] = mapped_column(
        GUID(),
        ForeignKey("order_items.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Producto (snapshot FK + JSON)
    product_id: Mapped[Optional[str]] = mapped_column(
        GUID(),
        ForeignKey("products.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    product_snapshot: Mapped[dict] = mapped_column(
        JSON, default=dict, nullable=False,
        comment="Snapshot del producto al crear el job: id, name, sku, template_type, etc."
    )

    # Cliente (denormalizado para el Kanban)
    customer_id: Mapped[Optional[str]] = mapped_column(
        GUID(),
        ForeignKey("customers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    customer_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    # Cantidades
    quantity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    completed_qty: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Medidas (para productos print/m2)
    width_cm: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    height_cm: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Pipeline
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="nuevo", index=True,
        comment="nuevo | archivo_aprobado | preparando | imprimiendo | "
                "terminacion | listo | entregado | cancelado — "
                "ver ProductionJobStatus",
    )

    # Prioridad (heredada del pedido)
    priority: Mapped[str] = mapped_column(String(20), default="normal", nullable=False)
    # Valores: "normal" | "alta" | "urgente"

    # Fechas
    due_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, index=True)
    delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Archivo/diseño
    file_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    file_status: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False,
        comment="pending | approved | rejected"
    )

    # Notas
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Costeo
    estimated_cost_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    actual_cost_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Optimistic locking
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    # Relación con Order (lazy='select' para no cargar siempre)
    order = relationship("Order", back_populates="production_jobs", lazy="select")
