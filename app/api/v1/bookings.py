"""Bookings API — reservas (para industries services/beauty/health/education).

Fase 2:
- Endpoints admin (owner) con auth de membresía.
- Validación de conflictos y horarios de sucursal vía BookingService.
- Envío de confirmaciones por email vía NotificationService.
- Endpoint público para que clientes reserven.
- Endpoint de métricas de agenda.
"""
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.database import get_db
from app.deps import get_current_membership
from app.models.booking import Booking, BookingStatus
from app.models.tenant import Tenant, TenantMembership
from app.schemas.booking import (
    AvailabilityQuery, AvailabilityResponse, BookingIn, BookingOut,
    BookingStats, BookingUpdate, PublicBookingIn,
)
from app.services.booking_service import BookingService

router = APIRouter(prefix="/tenants/{tenant_id}/bookings", tags=["bookings"])
# Router público (cliente final) — sin auth, resuelto por tenant slug
public_router = APIRouter(prefix="/bookings", tags=["bookings-public"])


# ── Listar (admin) ───────────────────────────────────────
@router.get("", response_model=list[BookingOut])
def list_bookings(
    tenant_id: UUID,
    status: Optional[BookingStatus] = Query(None),
    branch_id: Optional[UUID] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    customer_id: Optional[UUID] = Query(None),
    limit: int = Query(200, ge=1, le=1000),
    membership: TenantMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    """Lista reservas del tenant con filtros opcionales."""
    svc = BookingService(db, str(tenant_id))
    bookings = svc.list(
        status=status,
        branch_id=branch_id,
        date_from=date_from,
        date_to=date_to,
        customer_id=customer_id,
        limit=limit,
    )
    return bookings


# ── Crear (admin) ─────────────────────────────────────────
@router.post("", response_model=BookingOut, status_code=201)
def create_booking(
    tenant_id: UUID,
    payload: BookingIn,
    send_confirmation: bool = Query(True, description="Enviar email de confirmación"),
    membership: TenantMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    """Crea una reserva en nombre del cliente (uso admin / call-center)."""
    svc = BookingService(db, str(tenant_id))
    return svc.create(payload, send_confirmation=send_confirmation)


# ── Stats de la agenda ────────────────────────────────────
@router.get("/stats", response_model=BookingStats)
def get_booking_stats(
    tenant_id: UUID,
    membership: TenantMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    """Métricas rápidas para el dashboard de agenda."""
    svc = BookingService(db, str(tenant_id))
    return svc.stats()


# ── Toggle web-booking (P2 #3) ────────────────────────────
class WebBookingToggle(BaseModel):
    enabled: bool = Field(..., description="True para permitir reservas desde el sitio público")


@router.get("/web-booking")
def get_web_booking(
    tenant_id: UUID,
    membership: TenantMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    """Lee el estado actual del toggle de web-booking del tenant.

    El estado se guarda en `tenant.settings["web_booking_enabled"]`.
    Default: True (siempre activo para no romper tenants existentes).
    """
    from app.models.tenant import Tenant
    tenant = db.get(Tenant, tenant_id)
    if not tenant:
        raise NotFoundError("Tenant")
    settings = tenant.settings or {}
    enabled = bool(settings.get("web_booking_enabled", True))
    return {
        "tenant_id": str(tenant.id),
        "web_booking_enabled": enabled,
        "public_url": f"/u/{tenant.slug}#reservar" if enabled else None,
    }


@router.post("/web-booking")
def set_web_booking(
    tenant_id: UUID,
    payload: WebBookingToggle,
    membership: TenantMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    """Activa o desactiva las reservas online (P2 #3).

    Cuando está desactivado, el sitio público NO muestra el botón
    "Reservar" y el endpoint público POST /bookings devuelve 403.
    El estado se persiste en `tenant.settings["web_booking_enabled"]`.
    """
    from app.models.tenant import Tenant
    tenant = db.get(Tenant, tenant_id)
    if not tenant:
        raise NotFoundError("Tenant")
    settings = dict(tenant.settings or {})
    settings["web_booking_enabled"] = bool(payload.enabled)
    tenant.settings = settings
    db.add(tenant)
    db.commit()
    db.refresh(tenant)
    return {
        "tenant_id": str(tenant.id),
        "web_booking_enabled": bool(payload.enabled),
        "public_url": f"/u/{tenant.slug}#reservar" if payload.enabled else None,
    }


# ── Availability ────────────────────────────────────────
@router.post("/availability", response_model=AvailabilityResponse)
def check_availability(
    tenant_id: UUID,
    payload: AvailabilityQuery,
    membership: TenantMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    """Devuelve los slots disponibles en el rango pedido."""
    svc = BookingService(db, str(tenant_id))
    return svc.get_availability(payload)


# ── Detalle de una reserva ──────────────────────────────
@router.get("/{booking_id}", response_model=BookingOut)
def get_booking(
    tenant_id: UUID,
    booking_id: UUID,
    membership: TenantMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    svc = BookingService(db, str(tenant_id))
    return svc.get_or_404(booking_id)


# ── Actualizar (admin) ──────────────────────────────────
@router.patch("/{booking_id}", response_model=BookingOut)
def update_booking(
    tenant_id: UUID,
    booking_id: UUID,
    payload: BookingUpdate,
    membership: TenantMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    """Actualiza estado, notas, staff, o reagenda."""
    svc = BookingService(db, str(tenant_id))
    return svc.update(
        booking_id,
        status=payload.status,
        notes=payload.notes,
        staff_name=payload.staff_name,
        starts_at=payload.starts_at,
        ends_at=payload.ends_at,
    )


# ── Acciones de estado (atajos) ─────────────────────────
@router.post("/{booking_id}/confirm", response_model=BookingOut)
def confirm_booking(
    tenant_id: UUID,
    booking_id: UUID,
    membership: TenantMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    svc = BookingService(db, str(tenant_id))
    return svc.confirm(booking_id)


@router.post("/{booking_id}/complete", response_model=BookingOut)
def complete_booking(
    tenant_id: UUID,
    booking_id: UUID,
    membership: TenantMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    svc = BookingService(db, str(tenant_id))
    return svc.complete(booking_id)


@router.post("/{booking_id}/no-show", response_model=BookingOut)
def mark_no_show(
    tenant_id: UUID,
    booking_id: UUID,
    membership: TenantMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    svc = BookingService(db, str(tenant_id))
    return svc.mark_no_show(booking_id)


class CancelIn(BaseModel):
    reason: Optional[str] = Field(None, max_length=500)


@router.post("/{booking_id}/cancel", response_model=BookingOut)
def cancel_booking(
    tenant_id: UUID,
    booking_id: UUID,
    payload: CancelIn = CancelIn(),
    membership: TenantMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    svc = BookingService(db, str(tenant_id))
    return svc.cancel(booking_id, reason=payload.reason)


@router.delete("/{booking_id}", status_code=204)
def delete_booking(
    tenant_id: UUID,
    booking_id: UUID,
    membership: TenantMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    """Elimina definitivamente una reserva (sólo admin)."""
    svc = BookingService(db, str(tenant_id))
    svc.delete(booking_id)
    return None


# ════════════════════════════════════════════════════════════
# PUBLIC endpoints (cliente final) — sin auth, resuelto por slug
# ════════════════════════════════════════════════════════════

def _resolve_tenant_by_slug(slug: str, db: Session) -> Tenant:
    t = db.query(Tenant).filter(Tenant.slug == slug).first()
    if not t or not t.is_active:
        raise NotFoundError("Tenant")
    return t


@public_router.get("/t/{slug}/status")
def public_booking_status(
    slug: str,
    db: Session = Depends(get_db),
):
    """Indica al sitio público si las reservas online están activas.

    Usado por /u/{slug} para mostrar u ocultar el botón "Reservar".
    No expone datos sensibles; sólo el flag `enabled` y la URL de
    contacto como fallback.
    """
    t = _resolve_tenant_by_slug(slug, db)
    enabled = bool((t.settings or {}).get("web_booking_enabled", True))
    return {
        "slug": slug,
        "web_booking_enabled": enabled,
        "contact_url": f"/u/{slug}#contacto",
    }


@public_router.post("/t/{slug}/public-check")
def public_check_availability(
    slug: str,
    payload: AvailabilityQuery,
    db: Session = Depends(get_db),
):
    """Consulta slots disponibles para que el cliente elija cuándo reservar."""
    t = _resolve_tenant_by_slug(slug, db)
    if not (t.settings or {}).get("web_booking_enabled", True):
        from app.core.errors import ForbiddenError
        raise ForbiddenError("Las reservas online están desactivadas para este negocio.")
    svc = BookingService(db, str(t.id))
    return svc.get_availability(payload)


class PublicBookingOutResp(BaseModel):
    """Lo que devolvemos al cliente tras reservar (sin datos sensibles)."""
    id: str
    status: str
    starts_at: datetime
    ends_at: datetime
    customer_name: str
    customer_email_masked: Optional[str] = None
    branch_name: Optional[str] = None
    cancel_token: Optional[str] = None
    message: str = "Reserva creada. Recibirás un email de confirmación."


def _mask_email(email: Optional[str]) -> Optional[str]:
    if not email or "@" not in email:
        return email
    name, domain = email.split("@", 1)
    if len(name) <= 2:
        masked = "*" * len(name)
    else:
        masked = name[0] + "*" * (len(name) - 2) + name[-1]
    return f"{masked}@{domain}"


@public_router.post(
    "/t/{slug}/public-create",
    response_model=PublicBookingOutResp,
    status_code=201,
)
def public_create_booking(
    slug: str,
    payload: PublicBookingIn,
    db: Session = Depends(get_db),
):
    """Crea una reserva pública. El cliente debe aceptar términos.
    Devuelve datos enmascarados (sin staff, sin precio)."""
    t = _resolve_tenant_by_slug(slug, db)
    if not (t.settings or {}).get("web_booking_enabled", True):
        from app.core.errors import ForbiddenError
        raise ForbiddenError("Las reservas online están desactivadas para este negocio.")
    svc = BookingService(db, str(t.id))
    b = svc.create(payload, send_confirmation=True)
    branch_name = None
    if b.branch_id:
        from app.models.branch import Branch
        br = db.get(Branch, b.branch_id)
        if br:
            branch_name = br.name
    return PublicBookingOutResp(
        id=str(b.id),
        status=b.status.value,
        starts_at=b.starts_at,
        ends_at=b.ends_at,
        customer_name=b.customer_name,
        customer_email_masked=_mask_email(b.customer_email),
        branch_name=branch_name,
        cancel_token=str(b.id)[:12],  # opaco al cliente
        message="Reserva creada. Recibirás un email de confirmación.",
    )


@public_router.post("/t/{slug}/public-cancel")
def public_cancel_booking(
    slug: str,
    booking_id: UUID,
    cancel_token: str = Query(...),
    db: Session = Depends(get_db),
):
    """Cancela una reserva por ID + token opaco (sin auth).
    El token es los primeros 12 chars del UUID; mitigación mínima.
    Para producción real añadiríamos un JWT firmado por reserva."""
    t = _resolve_tenant_by_slug(slug, db)
    expected = str(booking_id)[:12]
    if cancel_token != expected:
        from app.core.errors import ForbiddenError
        raise ForbiddenError("Token inválido")
    svc = BookingService(db, str(t.id))
    b = svc.cancel(booking_id, reason="Cancelada por el cliente desde la web")
    return {
        "id": str(b.id),
        "status": b.status.value,
        "message": "Reserva cancelada.",
    }
