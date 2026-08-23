"""Schemas para `BusinessCosts` (Costos fijos mensuales por tenant).

Decisiones de diseño:
  - Todos los campos monetarios se exponen en **cents** (entero) — coherente
    con el resto del proyecto (`Product.price_cents`, `Order.total_cents`).
  - `productive_hours_per_month` y `target_margin_pct` y `waste_pct` son
    enteros simples.
  - `is_na` es un `dict[str, bool]` (mismo shape que se persiste).
  - Hay un `Breakdown` derivado que entrega los valores ya calculados
    (`total_fixed_cents`, `cost_hour_cents`, `cost_real_*`).
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ── Inputs ──────────────────────────────────────────────
class BusinessCostsBase(BaseModel):
    """Campos editables (los 14 + 2 auxiliares)."""

    # Personal
    owner_salary_cents: int = Field(0, ge=0, description="Sueldo asignado al dueño.")
    workers_salary_cents: int = Field(0, ge=0, description="Sueldo de trabajadores.")

    # Operación
    productive_hours_per_month: int = Field(
        160, ge=1, le=720,
        description="Horas reales disponibles para producir o prestar servicios.",
    )
    target_margin_pct: int = Field(
        30, ge=0, le=99,
        description="Rentabilidad mínima objetivo (%). Usada en precio sugerido.",
    )

    # Básicos
    rent_cents: int = Field(0, ge=0)
    electricity_cents: int = Field(0, ge=0)
    water_cents: int = Field(0, ge=0)
    gas_cents: int = Field(0, ge=0)

    # Otros fijos
    software_cents: int = Field(0, ge=0)
    advertising_cents: int = Field(0, ge=0)
    payment_commission_cents: int = Field(0, ge=0)
    packaging_cents: int = Field(0, ge=0)
    maintenance_cents: int = Field(0, ge=0)
    depreciation_cents: int = Field(0, ge=0)

    # Merma promedio — informativo
    waste_pct: int = Field(0, ge=0, le=100)

    # Flags "No aplica"
    is_na: dict[str, bool] = Field(default_factory=dict)

    notes: Optional[str] = Field(None, max_length=500)

    @field_validator("is_na")
    @classmethod
    def _clean_is_na(cls, v: dict) -> dict:
        """Filtra is_na para que solo contenga keys válidas y values bool."""
        allowed = {
            "owner_salary_cents",
            "workers_salary_cents",
            "rent_cents",
            "electricity_cents",
            "water_cents",
            "gas_cents",
            "software_cents",
            "advertising_cents",
            "payment_commission_cents",
            "packaging_cents",
            "maintenance_cents",
            "depreciation_cents",
        }
        return {k: bool(val) for k, val in (v or {}).items() if k in allowed}


class BusinessCostsUpdate(BusinessCostsBase):
    """PUT: el tenant actualiza su config de costos. Todos los campos son opcionales
    en la práctica — el front puede enviar subsets parciales si lo desea, pero
    en esta primera versión enviamos todo (atomic update)."""


# ── Output ─────────────────────────────────────────────
class BusinessCostsRead(BusinessCostsBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    # Campos derivados (re-calculados en cada PUT)
    total_fixed_cents: int
    cost_hour_cents: int
    version: int
    created_at: datetime
    updated_at: datetime


class BusinessCostsBreakdown(BaseModel):
    """Lectura derivada: totales por sección + costo hora + métricas auxiliares.

    Pensado para alimentar widgets del dashboard y el panel de
    `costos.html` sin obligar al front a recalcular.
    """

    model_config = ConfigDict(from_attributes=True)

    tenant_id: UUID
    currency: str

    # Totales por sección (excluyendo NA)
    personal_total_cents: int
    basics_total_cents: int      # electricidad + agua + gas + arriendo
    other_fixed_total_cents: int # software + publicidad + comisiones + packaging + mantenimiento + depreciación

    total_fixed_cents: int
    cost_hour_cents: int
    productive_hours_per_month: int
    target_margin_pct: int

    # Última actualización
    version: int
    updated_at: datetime
    is_configured: bool = Field(
        ...,
        description="True si el tenant ya completó al menos un PUT inicial.",
    )


# ── Cálculo de precio sugerido (usado por productos) ──
class PricingSuggestionRequest(BaseModel):
    """Body para `POST /tenants/{id}/costs/pricing-suggestion` (o similar).

    Calcula precio sugerido y margen dado:
      - material_cost_cents (insumos directos)
      - production_time_min (minutos)
      - target_margin_pct_override (opcional, si quiere simular con otro margen)
    """
    material_cost_cents: int = Field(0, ge=0)
    production_time_min: int = Field(0, ge=0)
    target_margin_pct: Optional[int] = Field(None, ge=0, le=99)


class PricingSuggestionResponse(BaseModel):
    cost_real_cents: int           # insumos + tiempo * costo_hora
    suggested_price_cents: int     # cost_real / (1 - margen/100)
    current_price_cents: Optional[int] = None
    current_margin_pct: Optional[float] = None
    target_margin_pct: int
    cost_hour_used_cents: int
    currency: str
