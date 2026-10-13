"""HU_29 — Servicio de tiers de fidelidad + auto-asignación.

CRUD de LoyaltyTier + helper ``recompute_tier_for_pass`` que se llama
desde ``LoyaltyPassService.scan`` (hook al sumar sellos).
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.models.loyalty_pass import CustomerPass, LoyaltyCampaign
from app.models.loyalty_tier import LoyaltyTier
from app.schemas.loyalty import (
    LoyaltyTierCreate, LoyaltyTierUpdate,
)


class LoyaltyTierService:
    def __init__(self, db: Session, tenant_id: str):
        self.db = db
        self.tenant_id = tenant_id

    # ── helpers ────────────────────────────────────────────
    def _get_campaign(self, campaign_id: UUID) -> LoyaltyCampaign:
        c = self.db.get(LoyaltyCampaign, campaign_id)
        if not c or str(c.tenant_id) != str(self.tenant_id):
            raise NotFoundError("Campaña")
        return c

    def _get_tier(self, tier_id: UUID) -> LoyaltyTier:
        t = self.db.get(LoyaltyTier, tier_id)
        if not t or str(t.tenant_id) != str(self.tenant_id):
            raise NotFoundError("Tier")
        return t

    # ── CRUD ───────────────────────────────────────────────
    def list_tiers(self, campaign_id: UUID) -> list[LoyaltyTier]:
        self._get_campaign(campaign_id)
        return list(self.db.execute(
            select(LoyaltyTier)
            .where(
                LoyaltyTier.tenant_id == self.tenant_id,
                LoyaltyTier.campaign_id == str(campaign_id),
            )
            .order_by(LoyaltyTier.sort_order, LoyaltyTier.min_stamps)
        ).scalars())

    def create_tier(self, payload: LoyaltyTierCreate) -> LoyaltyTier:
        self._get_campaign(payload.campaign_id)
        if payload.min_stamps < 0:
            raise ValidationError("min_stamps debe ser >= 0")
        if not (0 <= payload.discount_pct <= 100):
            raise ValidationError("discount_pct debe estar entre 0 y 100")

        # Validar unicidad: (campaign_id, name) y (campaign_id, min_stamps)
        existing = self.db.execute(
            select(LoyaltyTier).where(
                LoyaltyTier.tenant_id == self.tenant_id,
                LoyaltyTier.campaign_id == str(payload.campaign_id),
                (LoyaltyTier.name == payload.name) | (LoyaltyTier.min_stamps == payload.min_stamps),
            )
        ).scalars().all()
        for e in existing:
            if e.name == payload.name:
                raise ConflictError(f"Ya existe un tier '{payload.name}' en esta campaña")
            if e.min_stamps == payload.min_stamps:
                raise ConflictError(f"Ya existe un tier con min_stamps={payload.min_stamps}")

        t = LoyaltyTier(
            tenant_id=self.tenant_id,
            campaign_id=str(payload.campaign_id),
            name=payload.name,
            min_stamps=payload.min_stamps,
            discount_pct=payload.discount_pct,
            perks=payload.perks or {},
            sort_order=payload.sort_order,
            is_active=payload.is_active,
            color=payload.color,
            icon=payload.icon,
        )
        self.db.add(t)
        try:
            self.db.commit()
        except Exception as e:
            self.db.rollback()
            raise ConflictError(f"No se pudo crear el tier: {e}")
        self.db.refresh(t)
        return t

    def update_tier(self, tier_id: UUID, payload: LoyaltyTierUpdate) -> LoyaltyTier:
        t = self._get_tier(tier_id)
        data = payload.model_dump(exclude_unset=True)
        for k, val in data.items():
            setattr(t, k, val)
        self.db.commit()
        self.db.refresh(t)
        return t

    def delete_tier(self, tier_id: UUID) -> bool:
        t = self._get_tier(tier_id)
        # Antes de borrar, limpiar las referencias en customer_passes.
        self.db.execute(
            CustomerPass.__table__.update()
            .where(CustomerPass.current_tier_id == str(t.id))
            .values(current_tier_id=None)
        )
        self.db.delete(t)
        self.db.commit()
        return True

    # ── Auto-asignación (HU_29 hook) ───────────────────────
    def recompute_tier_for_pass(self, customer_pass: CustomerPass) -> Optional[UUID]:
        """Recalcula y asigna el tier correspondiente al pass.

        Estrategia: elegir el tier de mayor min_stamps tal que
        ``min_stamps <= stamps_current``. Si ninguno cumple, deja
        current_tier_id en NULL.

        Retorna el tier_id asignado (o None si quedó sin tier).
        """
        campaign_id = str(customer_pass.campaign_id)
        tiers = self.db.execute(
            select(LoyaltyTier).where(
                LoyaltyTier.tenant_id == str(customer_pass.tenant_id),
                LoyaltyTier.campaign_id == campaign_id,
                LoyaltyTier.is_active.is_(True),
            ).order_by(LoyaltyTier.min_stamps.desc())
        ).scalars().all()

        if not tiers:
            customer_pass.current_tier_id = None
            return None

        best = None
        for t in tiers:
            if (customer_pass.stamps_current or 0) >= t.min_stamps:
                best = t
                break

        new_id = str(best.id) if best else None
        if str(customer_pass.current_tier_id or "") != (new_id or ""):
            customer_pass.current_tier_id = new_id
        return best.id if best else None
