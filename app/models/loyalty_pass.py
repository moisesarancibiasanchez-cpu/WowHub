"""Loyalty Pass — sistema de fidelización con tarjetas digitales (Fase 1 y 2).

Tablas:
  - loyalty_campaigns: 1 por tenant (puede tener varias, una activa a la vez)
  - customer_passes: 1 por (cliente, campaña) — el "pase" del cliente
  - pass_stamps: cada estampilla/canje (auditoría)
  - qr_tokens: tokens QR del mostrador (rotativos, 1-shot)

Todas las tablas son multi-tenant. Aislamos por tenant_id en cada query.
"""
from __future__ import annotations

import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text,
    UniqueConstraint, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel, TenantMixin, GUID


# ── Enums ──────────────────────────────────────────────────
class PassSource(str, enum.Enum):
    WEB = "web"          # alta via landing, sin wallet nativa
    APPLE = "apple"      # reservado para Fase 3
    GOOGLE = "google"    # reservado para Fase 4
    MANUAL = "manual"    # creado por el owner en panel


class PassStatus(str, enum.Enum):
    ACTIVE = "active"
    REDEEMED = "redeemed"     # canjeó un premio (resetea a 0)
    EXPIRED = "expired"
    REPLACED = "replaced"     # reemplazado por uno nuevo
    REVOKED = "revoked"       # cancelado por el owner


class StampReason(str, enum.Enum):
    SCAN = "scan"                 # escaneado por garzón
    MANUAL_ADJUST = "manual_adjust"  # ajuste manual del owner
    REWARD_REDEEM = "reward_redeem"  # redención (delta = -stamps_required)
    REISSUE = "reissue"           # re-emisión tras recuperar cuenta


class QrTokenKind(str, enum.Enum):
    COUNTER = "counter"   # el QR del mostrador (suma 1 sello)
    SHOW = "show"         # solo muestra info (para debugging)


# ── Campaign ───────────────────────────────────────────────
class LoyaltyCampaign(BaseModel, TenantMixin):
    """Una campaña de sellos (1 por tenant por defecto, N permitidas)."""
    __tablename__ = "loyalty_campaigns"

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    reward_label: Mapped[str] = mapped_column(String(160), nullable=False)
    stamps_required: Mapped[int] = mapped_column(Integer, nullable=False, default=6)

    # Diseño
    primary_color: Mapped[str] = mapped_column(String(7), nullable=False, default="#1A73E8")
    text_color: Mapped[str] = mapped_column(String(7), nullable=False, default="#FFFFFF")
    logo_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    icon_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    strip_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    accent_color: Mapped[Optional[str]] = mapped_column(String(7), nullable=True)

    # Operación
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    starts_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    ends_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Anti-fraude: PIN de garzón (4-8 dígitos). Se valida al escanear.
    cashier_pin: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)
    pin_hint: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)

    # Métricas rápidas (desnormalizadas; la fuente de verdad es pass_stamps)
    total_passes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_stamps_issued: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_rewards_redeemed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    passes: Mapped[list["CustomerPass"]] = relationship(
        back_populates="campaign", cascade="all, delete-orphan",
    )

    __table_args__ = (
        CheckConstraint("stamps_required BETWEEN 2 AND 50", name="ck_stamps_range"),
        Index("ix_loyalty_campaigns_tenant_active", "tenant_id", "is_active"),
    )


# ── Customer Pass ─────────────────────────────────────────
class CustomerPass(BaseModel, TenantMixin):
    """La tarjeta digital de un cliente para una campaña."""
    __tablename__ = "customer_passes"

    campaign_id: Mapped[str] = mapped_column(
        GUID(), ForeignKey("loyalty_campaigns.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    customer_id: Mapped[str] = mapped_column(
        GUID(), ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )

    # Identificadores para wallets nativas
    serial_number: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    source: Mapped[str] = mapped_column(String(16), nullable=False, default=PassSource.WEB.value)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=PassStatus.ACTIVE.value)

    # Estado de sellos
    stamps_current: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rewards_earned: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Token QR firmado que se escanea (rotativo)
    qr_payload: Mapped[str] = mapped_column(Text, nullable=False)

    # Reservado para Fase 3/4
    apple_pass_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    google_pass_jwt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    installed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_stamp_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    redeemed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    campaign: Mapped["LoyaltyCampaign"] = relationship(back_populates="passes")

    __table_args__ = (
        UniqueConstraint("tenant_id", "campaign_id", "customer_id",
                         name="uq_pass_per_customer_campaign"),
        Index("ix_passes_tenant_status", "tenant_id", "status"),
        CheckConstraint("stamps_current >= 0", name="ck_stamps_nonneg"),
    )


# ── Stamp Audit ───────────────────────────────────────────
class PassStamp(BaseModel, TenantMixin):
    """Auditoría: cada estampilla, ajuste o redención."""
    __tablename__ = "pass_stamps"

    pass_id: Mapped[str] = mapped_column(
        GUID(), ForeignKey("customer_passes.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    campaign_id: Mapped[str] = mapped_column(
        GUID(), ForeignKey("loyalty_campaigns.id", ondelete="CASCADE"),
        nullable=False,
    )

    delta: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(String(32), nullable=False)

    # Quién lo hizo
    scanned_by: Mapped[Optional[str]] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )
    cashier_pin_validated: Mapped[bool] = mapped_column(default=False, nullable=False)
    device_fp: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # jti del QR usado (1-shot enforcement)
    qr_token_jti: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)

    # Resultado
    stamps_after: Mapped[int] = mapped_column(Integer, nullable=False)
    reward_unlocked: Mapped[bool] = mapped_column(default=False, nullable=False)

    __table_args__ = (
        Index("ix_pass_stamps_pass_when", "pass_id", "created_at"),
    )


# ── QR Token (rotativo, mostrador) ────────────────────────
class QrToken(BaseModel, TenantMixin):
    """Tokens QR del mostrador (rotativos). 1-shot enforced en scan."""
    __tablename__ = "qr_tokens"

    jti: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    campaign_id: Mapped[str] = mapped_column(
        GUID(), ForeignKey("loyalty_campaigns.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )

    created_by: Mapped[str] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False,
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default=QrTokenKind.COUNTER.value)

    # Ventana de validez (por defecto 60s)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # 1-shot: cuándo se consumió
    consumed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    consumed_by_pass: Mapped[Optional[str]] = mapped_column(
        GUID(), ForeignKey("customer_passes.id", ondelete="SET NULL"), nullable=True,
    )
    consumed_by_user: Mapped[Optional[str]] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )

    # Fingerprint del dispositivo que lo solicitó (opcional)
    device_fp: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        Index("ix_qr_tokens_expires", "expires_at"),
    )
