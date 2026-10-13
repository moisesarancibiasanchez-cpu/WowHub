"""BusinessCosts: estructura de costos fijos mensuales por tenant.

Es la **fuente de verdad** para el cálculo de `costo_hora` y, en consecuencia,
para el costo real de los productos y la sugerencia de precio por IA.

Diseño (alineado con `WowHub_V8_Costos_Onboarding.html`):
  - 14 campos en cents (excepto `productive_hours_per_month` y `waste_pct`
    que son enteros / porcentaje respectivamente).
  - Cada campo admite "No aplica" via la columna JSON `is_na`. Cuando un
    campo está marcado como NA, queda EXCLUIDO del cálculo del costo fijo
    mensual (pero sigue apareciendo en la UI para que el usuario lo vea).
  - `cost_hour_cents` y `total_fixed_cents` se persisten pre-calculados en
    cada `PUT` para evitar recalcular en cada lectura (defensivo: defensivo
    para el usuario → costo_hora se redondea hacia arriba).
  - `target_margin_pct` se persiste aparte (no se usa en costo_hora; se
    usa en el cálculo de precio sugerido).

El modelo se conecta al Tenant por FK CASCADE. Hay 1 sola fila por tenant
(siempre upsert en `update_for_tenant`).
"""
from __future__ import annotations

import math
from typing import Optional

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import GUID, BaseModel, TenantMixin


class BusinessCosts(BaseModel, TenantMixin):
    __tablename__ = "business_costs"

    # ── Personal ────────────────────────────────────────────
    owner_salary_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    workers_salary_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # ── Operación ───────────────────────────────────────────
    # Horas reales disponibles para producir / prestar servicios.
    productive_hours_per_month: Mapped[int] = mapped_column(Integer, default=160, nullable=False)
    # Margen objetivo (%). 0–100. Se usa en el cálculo de precio sugerido.
    target_margin_pct: Mapped[int] = mapped_column(Integer, default=30, nullable=False)

    # ── Gastos básicos ──────────────────────────────────────
    rent_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    electricity_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    water_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    gas_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # ── Otros costos fijos ──────────────────────────────────
    software_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    advertising_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    payment_commission_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    packaging_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    maintenance_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    depreciation_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # ── Merma promedio (%) — informativo, no entra al costo_hora
    waste_pct: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # ── Flags "No aplica" por campo (JSON map nombre_campo → bool) ──
    # Ej: {"electricity_cents": true, "rent_cents": false}
    is_na: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    # ── Valores cacheados (re-calculados en cada PUT) ───────
    total_fixed_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cost_hour_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # ── Metadata ────────────────────────────────────────────
    notes: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    # version optimista (incrementa en cada update) — útil para auditoría
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    # ── Helpers de cálculo (puros, no tocan DB) ─────────────
    # Lista canónica de campos monetarios que entran al costo fijo.
    # El orden es importante: el frontend itera sobre esta misma lista
    # para renderizar el form (ver `costs_service.MONEY_FIELDS`).
    MONEY_FIELDS: tuple[str, ...] = (
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
    )

    def total_fixed_excluding_na(self) -> int:
        """Suma de todos los MONEY_FIELDS cuyo `is_na` no esté en True."""
        total = 0
        is_na = self.is_na or {}
        for f in self.MONEY_FIELDS:
            if is_na.get(f):
                continue
            total += int(getattr(self, f) or 0)
        return total

    def compute_cost_hour_cents(self) -> int:
        """costo_hora = total_fijo / horas_productivas.

        Redondeo defensivo (math.ceil en unidades de cent): si el
        costo real es 7999.4, devolvemos 8000. Esto hace que el
        cálculo sea ligeramente favorable para el usuario cuando hay
        residuos (cobra de más en el redondeo, no de menos).
        """
        hours = max(1, int(self.productive_hours_per_month or 0))
        total = self.total_fixed_excluding_na()
        if total <= 0:
            return 0
        # 1 cent = 1 unidad de la moneda. (Asumimos currency sin
        # decimales como CLP. Para currency con decimales habría que
        # usar `cents_per_unit` — fuera de scope por ahora.)
        cost_hour = total / hours
        return int(math.ceil(cost_hour))

    def compute_total_fixed_cents(self) -> int:
        return self.total_fixed_excluding_na()

    def recompute_derived(self) -> None:
        """Recalcula `total_fixed_cents` y `cost_hour_cents` en el objeto.

        Llamado por el service después de un update. NO hace commit.
        """
        self.total_fixed_cents = self.compute_total_fixed_cents()
        self.cost_hour_cents = self.compute_cost_hour_cents()
        self.version = (self.version or 0) + 1
