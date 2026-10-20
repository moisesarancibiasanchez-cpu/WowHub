"""InsumoMovement — tracking de movimientos de stock de insumos.
HU_55 — Épica E8 (S5) — TOBE v134.2-Producción-v2.

Replica WowPrint db.consumptions + db.wasteRecords.
Extiende Insumo (V8 P0.1) sin modificarlo.
"""
import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import GUID, BaseModel, TenantMixin


class InsumoMovementType(str, enum.Enum):
    ENTRADA = "entrada"      # Compra / reposición
    SALIDA = "salida"        # Consumo en producción
    AJUSTE = "ajuste"        # Corrección manual
    MERMA = "merma"          # Desperdicio


class InsumoMovement(BaseModel, TenantMixin):
    """Movimiento de stock de un Insumo.

    Para HU_55: se crea automáticamente un InsumoMovement de tipo SALIDA
    por cada Receta del producto cuando un ProductionJob se mueve a TERMINACION.
    """
    __tablename__ = "insumo_movements"

    insumo_id: Mapped[str] = mapped_column(
        GUID(),
        ForeignKey("insumos.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tenant_id: Mapped[str] = mapped_column(GUID(), nullable=False, index=True)

    type: Mapped[InsumoMovementType] = mapped_column(
        Enum(InsumoMovementType, name="insumo_movement_type"),
        nullable=False,
        index=True,
    )
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    # positivo = entrada; negativo = salida/ajuste/merma
    balance_after: Mapped[float] = mapped_column(Float, nullable=False)

    # Contexto
    production_job_id: Mapped[Optional[str]] = mapped_column(
        GUID(),
        ForeignKey("production_jobs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    order_id: Mapped[Optional[str]] = mapped_column(
        GUID(),
        ForeignKey("orders.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Costo al momento del movimiento
    unit_cost_cents_at_move: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_cost_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Auditoría
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False, index=True
    )

    insumo = relationship("Insumo", lazy="select")
