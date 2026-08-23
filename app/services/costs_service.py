"""CostsService — CRUD + cálculo de costo_hora y precio sugerido.

Reglas de cálculo (alineadas con `WowHub_V8_Costos_Onboarding.html`):

  total_fijo_mensual = Σ campos monetarios (no NA)
  costo_hora         = total_fijo_mensual / horas_productivas
  costo_real         = costo_insumos + (tiempo_min / 60) * costo_hora
  precio_sugerido    = costo_real / (1 - margen_objetivo/100)
  margen             = (precio - costo_real) / precio * 100

Donde "costo_insumos" es el `cost_cents` que ya tiene el producto
(insumos directos). El tiempo de producción (`production_time_min`)
es un campo que **vamos a agregar en Fase 3** al `Product`; mientras
tanto el endpoint de pricing suggestion acepta ambos parámetros en
el body y los usa directamente.
"""
from __future__ import annotations

import math
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.models.business_costs import BusinessCosts
from app.models.tenant import Tenant
from app.schemas.business_costs import (
    BusinessCostsBreakdown,
    BusinessCostsUpdate,
    PricingSuggestionRequest,
    PricingSuggestionResponse,
)


# ── Constantes para el frontend ────────────────────────
# Lista canónica con metadatos de presentación. El front itera sobre
# esta lista para renderizar las cards y el modal (3 secciones).
COST_FIELDS_META: list[dict] = [
    # Personal
    {"key": "owner_salary_cents", "label": "Sueldo dueño", "section": "personal", "currency_kind": "money", "required": True, "default": 700_000},
    {"key": "workers_salary_cents", "label": "Sueldos trabajadores", "section": "personal", "currency_kind": "money", "required": True, "default": 1_200_000},
    # Operación
    {"key": "productive_hours_per_month", "label": "Horas productivas/mes", "section": "operacion", "currency_kind": "int", "required": True, "default": 160},
    {"key": "target_margin_pct", "label": "Margen objetivo (%)", "section": "operacion", "currency_kind": "pct", "required": True, "default": 30},
    # Básicos
    {"key": "rent_cents", "label": "Arriendo", "section": "basicos", "currency_kind": "money", "required": True, "default": 450_000},
    {"key": "electricity_cents", "label": "Luz", "section": "basicos", "currency_kind": "money", "required": True, "default": 180_000},
    {"key": "water_cents", "label": "Agua", "section": "basicos", "currency_kind": "money", "required": True, "default": 35_000},
    {"key": "gas_cents", "label": "Gas", "section": "basicos", "currency_kind": "money", "required": False, "default": 40_000},
    # Otros fijos
    {"key": "software_cents", "label": "Software / suscripciones", "section": "otros", "currency_kind": "money", "required": True, "default": 80_000},
    {"key": "advertising_cents", "label": "Publicidad", "section": "otros", "currency_kind": "money", "required": False, "default": 120_000},
    {"key": "payment_commission_cents", "label": "Comisiones de pago", "section": "otros", "currency_kind": "money", "required": False, "default": 60_000},
    {"key": "packaging_cents", "label": "Packaging", "section": "otros", "currency_kind": "money", "required": False, "default": 90_000},
    {"key": "maintenance_cents", "label": "Mantenimiento", "section": "otros", "currency_kind": "money", "required": False, "default": 70_000},
    {"key": "depreciation_cents", "label": "Depreciación", "section": "otros", "currency_kind": "money", "required": False, "default": 100_000},
    # Merma
    {"key": "waste_pct", "label": "Merma promedio (%)", "section": "otros", "currency_kind": "pct", "required": False, "default": 3},
]


class CostsService:
    def __init__(self, db: Session):
        self.db = db

    # ── Helpers ────────────────────────────────────────────
    def _get_tenant(self, tenant_id: UUID) -> Tenant:
        t = self.db.get(Tenant, tenant_id)
        if not t:
            raise NotFoundError("Tenant")
        return t

    def _get_or_create(self, tenant_id: UUID) -> BusinessCosts:
        existing = self.db.execute(
            select(BusinessCosts).where(BusinessCosts.tenant_id == str(tenant_id))
        ).scalar_one_or_none()
        if existing:
            return existing
        # Bootstrap con defaults razonables (los de la maqueta V8)
        bc = BusinessCosts(tenant_id=str(tenant_id))
        # Aplica defaults de la maqueta
        for f in COST_FIELDS_META:
            if f["currency_kind"] in ("money", "int", "pct"):
                setattr(bc, f["key"], int(f["default"]))
        bc.is_na = {}
        bc.recompute_derived()
        self.db.add(bc)
        self.db.commit()
        self.db.refresh(bc)
        return bc

    # ── Public API ─────────────────────────────────────────
    def get_for_tenant(self, tenant_id: UUID) -> BusinessCosts:
        """Devuelve la config del tenant (crea defaults si no existe)."""
        return self._get_or_create(tenant_id)

    def update_for_tenant(self, tenant_id: UUID, payload: BusinessCostsUpdate) -> BusinessCosts:
        bc = self._get_or_create(tenant_id)
        data = payload.model_dump(exclude_unset=False)
        for key, val in data.items():
            if hasattr(bc, key) and key not in ("id", "tenant_id", "created_at"):
                setattr(bc, key, val)
        bc.recompute_derived()
        self.db.commit()
        self.db.refresh(bc)
        return bc

    # ── Derivados ──────────────────────────────────────────
    def breakdown(self, tenant_id: UUID) -> BusinessCostsBreakdown:
        bc = self._get_or_create(tenant_id)
        t = self._get_tenant(tenant_id)
        is_na = bc.is_na or {}

        def _sum(*keys: str) -> int:
            return sum(
                int(getattr(bc, k) or 0)
                for k in keys
                if not is_na.get(k)
            )

        personal_total = _sum("owner_salary_cents", "workers_salary_cents")
        basics_total = _sum("rent_cents", "electricity_cents", "water_cents", "gas_cents")
        other_total = _sum(
            "software_cents", "advertising_cents", "payment_commission_cents",
            "packaging_cents", "maintenance_cents", "depreciation_cents",
        )

        return BusinessCostsBreakdown(
            tenant_id=bc.tenant_id,
            currency=t.currency or "CLP",
            personal_total_cents=personal_total,
            basics_total_cents=basics_total,
            other_fixed_total_cents=other_total,
            total_fixed_cents=bc.total_fixed_cents,
            cost_hour_cents=bc.cost_hour_cents,
            productive_hours_per_month=bc.productive_hours_per_month,
            target_margin_pct=bc.target_margin_pct,
            version=bc.version,
            updated_at=bc.updated_at,
            is_configured=bc.version > 1,  # versión 1 = defaults; >1 = editó
        )

    # ── Pricing suggestion (usado por productos / AI) ─────
    def pricing_suggestion(
        self,
        tenant_id: UUID,
        req: PricingSuggestionRequest,
        current_price_cents: Optional[int] = None,
    ) -> PricingSuggestionResponse:
        bc = self._get_or_create(tenant_id)
        t = self._get_tenant(tenant_id)

        margin_pct = req.target_margin_pct if req.target_margin_pct is not None else bc.target_margin_pct
        margin_pct = max(0, min(99, int(margin_pct)))

        # tiempo puede ser 0 → no hay componente de mano de obra
        labor_cents = math.ceil((req.production_time_min / 60.0) * bc.cost_hour_cents) if bc.cost_hour_cents else 0
        cost_real = int(req.material_cost_cents or 0) + labor_cents

        if margin_pct >= 99:
            suggested = cost_real * 100  # caso degenerado
        else:
            suggested = math.ceil(cost_real / (1 - margin_pct / 100.0))

        current_margin_pct = None
        if current_price_cents and current_price_cents > 0 and cost_real > 0:
            current_margin_pct = round((current_price_cents - cost_real) / current_price_cents * 100, 2)

        return PricingSuggestionResponse(
            cost_real_cents=cost_real,
            suggested_price_cents=suggested,
            current_price_cents=current_price_cents,
            current_margin_pct=current_margin_pct,
            target_margin_pct=margin_pct,
            cost_hour_used_cents=bc.cost_hour_cents,
            currency=t.currency or "CLP",
        )
