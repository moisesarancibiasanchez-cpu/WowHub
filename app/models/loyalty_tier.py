"""HU_29 — Dashboard de lealtad con tiers (LoyaltyTier).

Una LoyaltyTier es un nivel dentro de una LoyaltyCampaign:
Bronce → Plata → Oro → Platino (los nombres son sugeridos; el owner
puede definirlos).

Cada tier declara:
  - min_stamps       : umbral de ingreso (inclusive)
  - discount_pct     : % de descuento automático (0..100) sobre consumo
  - perks            : JSON libre (freebies, beneficios, copy del front)
  - sort_order       : orden de presentación en el dashboard

Auto-asignación: cuando un CustomerPass cambia stamps_current, el
servicio LoyaltyPassService.add_stamp (HU_29) recalcula el tier
correspondiente según min_stamps y lo asigna a customer_pass.current_tier_id.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import ForeignKey, Index, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import GUID, BaseModel, TenantMixin


class LoyaltyTier(BaseModel, TenantMixin):
    """Nivel de fidelidad dentro de una LoyaltyCampaign.

    Hereda TenantMixin (multi-tenant). El ``tenant_id`` coincide con
    el de la campaña — ambos viven en el mismo tenant.
    """
    __tablename__ = "loyalty_tiers"

    campaign_id: Mapped[str] = mapped_column(
        GUID(),
        ForeignKey("loyalty_campaigns.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(String(60), nullable=False)
    # Umbral de ingreso (inclusive). Por ej. Bronce=0, Plata=6, Oro=12
    min_stamps: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Descuento sobre consumo. 0..100. Se interpreta como % (12.5 = 12,5%).
    discount_pct: Mapped[float] = mapped_column(default=0.0, nullable=False)
    # Beneficios libres: freebies, prioridad, copy para la UI, etc.
    perks: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    color: Mapped[Optional[str]] = mapped_column(String(7), nullable=True)
    icon: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)

    __table_args__ = (
        # Nombre único por campaña (no pueden haber dos tiers "Bronce"
        # en la misma campaña).
        UniqueConstraint(
            "campaign_id", "name", name="uq_loyalty_tier_per_campaign",
        ),
        # Un umbral único por campaña — evita ambigüedad al asignar.
        UniqueConstraint(
            "campaign_id", "min_stamps", name="uq_loyalty_tier_min_stamps",
        ),
        Index("ix_loyalty_tiers_campaign_sort", "campaign_id", "sort_order"),
    )
