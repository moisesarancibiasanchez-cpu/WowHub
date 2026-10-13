"""Insumo (raw material / input) y Receta (Bill of Materials).

V8 P0.1 — El spec WowHub_V8 pide un modelo de "Inventario de Insumos"
(materia prima), distinto del stock-por-sucursal que ya teníamos. Este
módulo añade:
- Insumo: una materia prima (harina, azúcar, huevos, tela, etc) con su
  stock físico, costo, unidades, alertas y campos N/A configurables.
- Receta: la relación "1 producto del catálogo usa N unidades de M insumo"
  que permite calcular el costo_real_cents de un producto a partir del
  costo promedio de sus insumos. Esto es lo que faltaba para que
  product.cost_cents deje de ser un input manual y se calcule en cascada.
"""
from typing import Optional
from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import GUID, BaseModel, TenantMixin


class Insumo(BaseModel, TenantMixin):
    """Materia prima / insumo de un tenant (V8 P0.1).

    Columnas que el spec pidió explícitamente:
      Insumo, Stock, Reservado, Disponible, Unidad, Último costo,
      Promedio, Valor stock, Alerta.

    El flag `is_na` (JSON) guarda qué campos opcionales están N/A para
    este insumo específico, según la lista del spec:
      ["proveedor", "stock_minimo", "punto_reposicion",
       "tiempo_reposicion", "merma", "ubicacion",
       "lote_vencimiento", "stock_reservado"]
    """
    __tablename__ = "insumos"

    # Identidad
    sku: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    unit: Mapped[str] = mapped_column(String(20), default="unidad", nullable=False)
    # unidad: kg, lt, unidad, m, m2, pack, etc

    # Stock (campos del spec)
    stock: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    reserved: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    # `available` es derivado (stock - reserved), se calcula en el schema.
    # Stock mínimo → alerta
    min_stock: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # Punto de reposición: cuando stock <= reorder_point, sugerir pedido
    reorder_point: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # Tiempo de reposición (días) desde el proveedor
    reorder_lead_time_days: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # Merma esperada (%)
    waste_pct: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    # Costos (centavos de la moneda del tenant)
    last_cost_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    avg_cost_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Valor stock = stock * avg_cost_cents (derivado, se calcula en schema)
    # Alerta: si stock <= min_stock → True (calculado en schema)

    # Metadata
    supplier: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    location: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    lot: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    expires_at: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    image_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    tags: Mapped[list] = mapped_column(JSON, default=list, nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # `is_na` (JSON): lista de campos que el tenant marcó como N/A para
    # este insumo en particular (los 8 N/A checkboxes del spec).
    is_na: Mapped[list] = mapped_column(JSON, default=list, nullable=False)

    # Relación con recetas
    recipes: Mapped[list["Receta"]] = relationship(  # noqa: F821
        back_populates="insumo",
        cascade="all, delete-orphan",
    )


class Receta(BaseModel, TenantMixin):
    """Bill of Materials: cuántos `quantity` de un `Insumo` se necesitan
    para hacer 1 unidad de un `Product` del catálogo.

    Esto permite que `Product.cost_real_cents` se calcule automáticamente:
        cost_real = sum(insumo.avg_cost_cents * receta.quantity)
    """
    __tablename__ = "recetas"

    product_id: Mapped[str] = mapped_column(
        GUID(),
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    insumo_id: Mapped[str] = mapped_column(
        GUID(),
        ForeignKey("insumos.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Cantidad de insumo necesaria para 1 unidad del producto.
    quantity: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    insumo: Mapped["Insumo"] = relationship(back_populates="recipes")
