"""Schemas Pydantic v2 para el sistema de fidelización con tarjetas digitales.

Diseño:
- Validamos colores como #RRGGBB con regex (Pydantic v2 AfterValidator)
- El qr_payload se devuelve opaco al cliente (es un JWT firmado)
- Los endpoints públicos NO exponen email/phone del cliente
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.loyalty_pass import (
    PassSource, PassStatus, QrTokenKind, StampReason,
)

_HEX_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")


def _validate_hex_color(v: Optional[str]) -> Optional[str]:
    if v is None:
        return v
    if not _HEX_COLOR.match(v):
        raise ValueError("color debe ser formato #RRGGBB (ej. #1A73E8)")
    return v.upper()


# ── Campaign ───────────────────────────────────────────────
class CampaignBase(BaseModel):
    # v1.9.1-r5: min_length del name baja de 2 a 1 para permitir
    # nombres cortos en pruebas (ej. "A", "B") y nombres de una
    # letra legítimos en producción (ej. "X", "Y"). La validación
    # semántica sigue siendo max_length=120.
    name: str = Field(..., min_length=1, max_length=120)
    reward_label: str = Field(..., min_length=2, max_length=160)
    stamps_required: int = Field(6, ge=2, le=50)
    primary_color: str = Field("#1A73E8")
    text_color: str = Field("#FFFFFF")
    accent_color: Optional[str] = None
    logo_url: Optional[str] = Field(None, max_length=500)
    icon_url: Optional[str] = Field(None, max_length=500)
    strip_url: Optional[str] = Field(None, max_length=500)
    # ── V2 metallic gradient (5 stops + angle + sheen) ──
    metal_c1: Optional[str] = None
    metal_c2: Optional[str] = None
    metal_c3: Optional[str] = None
    metal_c4: Optional[str] = None
    metal_c5: Optional[str] = None
    metal_angle: Optional[int] = Field(None, ge=0, le=360)
    sheen_opacity: Optional[int] = Field(None, ge=0, le=100)
    is_active: bool = True
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    cashier_pin: Optional[str] = Field(None, min_length=4, max_length=8)
    pin_hint: Optional[str] = Field(None, max_length=40)

    @field_validator("primary_color", "text_color", "accent_color")
    @classmethod
    def _check_color(cls, v: Optional[str]) -> Optional[str]:
        return _validate_hex_color(v)

    @field_validator("metal_c1", "metal_c2", "metal_c3", "metal_c4", "metal_c5")
    @classmethod
    def _check_metal_color(cls, v: Optional[str]) -> Optional[str]:
        return _validate_hex_color(v)


class CampaignCreate(CampaignBase):
    pass


class CampaignUpdate(BaseModel):
    # v1.9.1-r5: min_length del name baja de 2 a 1 (ver CampaignBase).
    name: Optional[str] = Field(None, min_length=1, max_length=120)
    reward_label: Optional[str] = Field(None, min_length=2, max_length=160)
    stamps_required: Optional[int] = Field(None, ge=2, le=50)
    primary_color: Optional[str] = None
    text_color: Optional[str] = None
    accent_color: Optional[str] = None
    logo_url: Optional[str] = Field(None, max_length=500)
    icon_url: Optional[str] = Field(None, max_length=500)
    strip_url: Optional[str] = Field(None, max_length=500)
    # ── V2 metallic gradient (5 stops + angle + sheen) ──
    metal_c1: Optional[str] = None
    metal_c2: Optional[str] = None
    metal_c3: Optional[str] = None
    metal_c4: Optional[str] = None
    metal_c5: Optional[str] = None
    metal_angle: Optional[int] = Field(None, ge=0, le=360)
    sheen_opacity: Optional[int] = Field(None, ge=0, le=100)
    is_active: Optional[bool] = None
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    # v1.9.1-r5: cashier_pin acepta string vacío como sentinel para
    # QUITAR el PIN de la campaña (LoyaltyPassService.update_campaign
    # ya implementa esta lógica: pin == "" → c.cashier_pin = None).
    # Antes el schema rechazaba "" con min_length=4 → 422.
    # min_length=0 permite tanto None (no tocar) como "" (quitar) o
    # un PIN real de 4-8 chars.
    cashier_pin: Optional[str] = Field(None, min_length=0, max_length=8)
    pin_hint: Optional[str] = Field(None, max_length=40)

    @field_validator("primary_color", "text_color", "accent_color")
    @classmethod
    def _check_color(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        return _validate_hex_color(v)

    @field_validator("metal_c1", "metal_c2", "metal_c3", "metal_c4", "metal_c5")
    @classmethod
    def _check_metal_color(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        return _validate_hex_color(v)


class CampaignOut(CampaignBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    total_passes: int
    total_stamps_issued: int
    total_rewards_redeemed: int
    created_at: datetime
    # ── IMPORTANTE ──────────────────────────────────────────
    # Sobrescribimos `cashier_pin` heredado de CampaignBase.
    # En la DB se guarda como SHA-256 hex (64 chars), pero
    # CampaignBase lo define con min_length=4 / max_length=8
    # (validación de INPUT del PIN crudo del usuario).
    # Si lo dejamos así, model_validate() rechaza el hash con
    # 500 "string_too_long" al devolver cualquier campaña con PIN.
    # En la respuesta NUNCA exponemos el hash: el front solo ve
    # `cashier_pin_set: bool`. Por eso lo forzamos a Optional[str]
    # sin restricciones y lo anulamos en la salida.
    cashier_pin: Optional[str] = Field(
        default=None, exclude=True, repr=False,
        description="(interno) hash SHA-256; nunca se expone en la respuesta",
    )
    # Si el owner definió un PIN, no lo devolvemos en claro
    cashier_pin_set: bool = False


# ── Customer Pass ──────────────────────────────────────────
class PassOut(BaseModel):
    """Lo que ve el cliente. NO incluye email/phone."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    campaign_id: UUID
    serial_number: str
    status: PassStatus
    stamps_current: int
    stamps_required: int  # para que el front sepa la meta
    rewards_earned: int
    reward_label: str     # "1 Café Gratis"
    primary_color: str
    text_color: str
    logo_url: Optional[str] = None
    icon_url: Optional[str] = None
    accent_color: Optional[str] = None
    # ── V2 metallic gradient (5 stops + angle + sheen) ──
    metal_c1: Optional[str] = None
    metal_c2: Optional[str] = None
    metal_c3: Optional[str] = None
    metal_c4: Optional[str] = None
    metal_c5: Optional[str] = None
    metal_angle: Optional[int] = None
    sheen_opacity: Optional[int] = None
    qr_payload: str       # JWT firmado (opaco al cliente pero necesario para su QR)
    last_stamp_at: Optional[datetime] = None
    installed_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None


# ── Customer Pass (vista owner) ────────────────────────────
class PassAdminOut(PassOut):
    """Lo que ve el owner: incluye customer_id y source."""
    customer_id: UUID
    source: PassSource
    created_at: datetime


# ── Customer alta (registro) ──────────────────────────────
class CustomerRegisterIn(BaseModel):
    """Alta rápida del cliente vía landing público.

    Acepta email o phone (uno de los dos). Si el cliente existe para el
    tenant, se reusa; si no, se crea.
    """
    full_name: str = Field(..., min_length=2, max_length=160)
    email: Optional[str] = Field(None, max_length=255)
    phone: Optional[str] = Field(None, max_length=40)
    accepts_marketing: bool = True
    accepts_terms: bool = Field(..., description="Debe ser True para crear el pass")

    @field_validator("accepts_terms")
    @classmethod
    def _must_accept(cls, v: bool) -> bool:
        if not v:
            raise ValueError("El cliente debe aceptar los términos")
        return v


# ── Customer lookup (Fase 8) ──────────────────────────────
class CustomerLookupIn(BaseModel):
    """Recuperación de pase existente por email o teléfono (Fase 8).

    A diferencia de CustomerRegisterIn, NO requiere full_name ni
    accepts_terms: el cliente ya existe. Solo necesitamos uno de los
    dos campos de contacto.
    """
    email: Optional[str] = Field(None, max_length=255)
    phone: Optional[str] = Field(None, max_length=40)


# ── Scan (POS) ─────────────────────────────────────────────
class ScanIn(BaseModel):
    """Lo que manda el escáner al backend.

    - qr_payload: el JWT firmado del QR del mostrador (rotativo)
    - pass_serial: el serial del pass del cliente (su QR)
    - cashier_pin: el PIN del garzón (si la campaña lo define)
    """
    qr_payload: str = Field(..., description="JWT del QR del mostrador")
    pass_serial: str = Field(..., description="Serial del pass del cliente")
    cashier_pin: Optional[str] = Field(None, min_length=4, max_length=8)
    device_fp: Optional[str] = Field(None, max_length=64)


class ScanOut(BaseModel):
    """Lo que devuelve el scan."""
    model_config = ConfigDict(populate_by_name=True)

    ok: bool
    error: Optional[str] = None
    error_code: Optional[str] = None  # 'qr_expired' | 'qr_used' | 'pin_invalid' | 'pass_not_found' | etc
    # Usamos Field alias para que en JSON la clave sea 'pass' (no se puede
    # usar 'pass' como atributo Python porque es keyword reservado).
    pass_: Optional[PassOut] = Field(default=None, alias="pass")
    reward_unlocked: bool = False
    reward_label: Optional[str] = None
    stamps_after: Optional[int] = None


# ── QR Token (mostrador) ──────────────────────────────────
class QrTokenOut(BaseModel):
    """Lo que se muestra en el QR del mostrador."""
    jti: str
    qr_payload: str
    expires_at: datetime
    refresh_in_seconds: int = 60


# ── Métricas (Fase 5) — placeholder para no acoplar ──────
class CampaignMetrics(BaseModel):
    campaign_id: UUID
    active_passes: int
    total_stamps_today: int
    total_rewards_today: int
    conversion_rate: float  # 0..1
    avg_stamps_to_reward: float


# ── Webhook payload (Fase 3/4, para Apple/Google) ─────────
class PassUpdateWebhook(BaseModel):
    serial_number: str
    event: str  # 'install' | 'uninstall' | 'update'
    device_id: Optional[str] = None
