"""Schemas Pydantic v2 para Bookings / Reservas.

Diseño:
- BookingIn: payload de entrada para crear una reserva (admin o público).
- BookingOut: respuesta con todos los campos serializados.
- BookingUpdate: cambios parciales (status, notas, etc).
- AvailabilityQuery / AvailabilitySlot: para el endpoint check_availability.
- PublicBookingIn: lo que manda el cliente desde la landing pública.
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.booking import BookingStatus


# ── Input: crear reserva (admin) ─────────────────────────
class BookingIn(BaseModel):
    customer_name: str = Field(..., min_length=2, max_length=160)
    customer_phone: str = Field(..., min_length=8, max_length=40)
    customer_email: Optional[str] = Field(None, max_length=255)
    branch_id: Optional[UUID] = None
    product_id: Optional[UUID] = None
    customer_id: Optional[UUID] = None
    starts_at: datetime
    ends_at: datetime
    price_cents: int = Field(0, ge=0)
    currency: str = Field("CLP", min_length=3, max_length=3)
    notes: Optional[str] = Field(None, max_length=2000)
    staff_name: Optional[str] = Field(None, max_length=120)
    # Status opcional al crear (default = PENDING). Útil para migrar reservas ya confirmadas.
    status: BookingStatus = BookingStatus.PENDING
    # Permite guardar metadata arbitraria (origen, referral, etc).
    extra: dict = Field(default_factory=dict)

    @field_validator("currency")
    @classmethod
    def _up_currency(cls, v: str) -> str:
        return v.upper()

    @model_validator(mode="after")
    def _validate_window(self):
        if self.ends_at <= self.starts_at:
            raise ValueError("ends_at debe ser mayor que starts_at")
        if (self.ends_at - self.starts_at).total_seconds() < 60:
            raise ValueError("La reserva debe durar al menos 1 minuto")
        if (self.ends_at - self.starts_at).total_seconds() > 24 * 3600:
            raise ValueError("La reserva no puede durar más de 24 horas")
        return self


# ── Input: reserva pública (cliente final) ───────────────
class PublicBookingIn(BaseModel):
    """Payload que manda el cliente desde la landing pública.
    No incluye customer_id (se crea o se reutiliza por email/phone).
    """
    customer_name: str = Field(..., min_length=2, max_length=160)
    customer_phone: str = Field(..., min_length=8, max_length=40)
    customer_email: Optional[str] = Field(None, max_length=255)
    branch_id: Optional[UUID] = None
    product_id: Optional[UUID] = None
    starts_at: datetime
    ends_at: datetime
    notes: Optional[str] = Field(None, max_length=2000)
    staff_name: Optional[str] = Field(None, max_length=120)
    accepts_terms: bool = Field(..., description="Debe ser True para crear la reserva")

    @field_validator("accepts_terms")
    @classmethod
    def _must_accept(cls, v: bool) -> bool:
        if not v:
            raise ValueError("El cliente debe aceptar los términos para reservar")
        return v

    @model_validator(mode="after")
    def _validate_window(self):
        if self.ends_at <= self.starts_at:
            raise ValueError("ends_at debe ser mayor que starts_at")
        if (self.ends_at - self.starts_at).total_seconds() < 60:
            raise ValueError("La reserva debe durar al menos 1 minuto")
        return self


# ── Update: cambios parciales ─────────────────────────────
class BookingUpdate(BaseModel):
    status: Optional[BookingStatus] = None
    notes: Optional[str] = Field(None, max_length=2000)
    staff_name: Optional[str] = Field(None, max_length=120)
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None

    @model_validator(mode="after")
    def _validate_window_if_changed(self):
        if self.starts_at and self.ends_at and self.ends_at <= self.starts_at:
            raise ValueError("ends_at debe ser mayor que starts_at")
        return self


# ── Output: reserva serializada ──────────────────────────
class BookingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    branch_id: Optional[UUID] = None
    customer_id: Optional[UUID] = None
    product_id: Optional[UUID] = None

    status: BookingStatus
    starts_at: datetime
    ends_at: datetime

    customer_name: str
    customer_phone: str
    customer_email: Optional[str] = None

    price_cents: int
    currency: str
    notes: Optional[str] = None
    staff_name: Optional[str] = None
    extra: dict = Field(default_factory=dict)
    created_at: datetime


# ── Output: vista pública (cliente) ───────────────────────
class PublicBookingOut(BaseModel):
    """Lo que ve el cliente cuando reserva o consulta su reserva.
    NO expone price_cents ni staff_name (privado del owner)."""
    id: UUID
    status: BookingStatus
    starts_at: datetime
    ends_at: datetime
    branch_id: Optional[UUID] = None
    product_id: Optional[UUID] = None
    customer_name: str
    # Email enmascarado para que el cliente confirme su registro
    customer_email_masked: Optional[str] = None
    notes: Optional[str] = None
    cancel_token: Optional[str] = None  # permite cancelar sin auth


# ── Availability ──────────────────────────────────────────
class AvailabilityQuery(BaseModel):
    """Parámetros de consulta de disponibilidad."""
    branch_id: Optional[UUID] = None
    date_from: datetime
    date_to: datetime
    duration_minutes: int = Field(60, ge=15, le=480)
    # Intervalo entre slots a evaluar (default 30 min)
    slot_step_minutes: int = Field(30, ge=5, le=120)


class AvailabilitySlot(BaseModel):
    """Un slot libre para reservar."""
    starts_at: datetime
    ends_at: datetime
    available: bool = True
    # Razones por las que NO está disponible (debug / UX)
    conflicts_with: List[UUID] = Field(default_factory=list)


class AvailabilityResponse(BaseModel):
    branch_id: Optional[UUID] = None
    branch_name: Optional[str] = None
    date_from: datetime
    date_to: datetime
    slot_step_minutes: int
    duration_minutes: int
    slots: List[AvailabilitySlot]
    total_slots: int
    available_slots: int


# ── Bulk: confirmar / cancelar múltiples ──────────────────
class BookingBulkUpdate(BaseModel):
    booking_ids: List[UUID] = Field(..., min_length=1, max_length=100)
    status: BookingStatus


# ── Métricas de agenda ───────────────────────────────────
class BookingStats(BaseModel):
    total: int
    pending: int
    confirmed: int
    completed: int
    canceled: int
    no_show: int
    today_count: int
    upcoming_count: int
    revenue_cents: int
    currency: str
