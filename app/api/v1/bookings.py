"""Bookings API — reservas (para industries services/beauty/health/education)."""
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.database import get_db
from app.deps import get_current_membership
from app.models.booking import Booking, BookingStatus
from app.models.tenant import TenantMembership
from app.services.notification_service import NotificationService

router = APIRouter(prefix="/tenants/{tenant_id}/bookings", tags=["bookings"])


class BookingCreate(BaseModel):
    customer_name: str = Field(min_length=2, max_length=160)
    customer_phone: str = Field(min_length=8, max_length=40)
    customer_email: Optional[str] = None
    branch_id: Optional[UUID] = None
    product_id: Optional[UUID] = None
    customer_id: Optional[UUID] = None
    starts_at: datetime
    ends_at: datetime
    price_cents: int = 0
    notes: Optional[str] = None
    staff_name: Optional[str] = None


class BookingUpdate(BaseModel):
    status: Optional[BookingStatus] = None
    notes: Optional[str] = None


@router.get("")
def list_bookings(
    tenant_id: UUID,
    status: Optional[BookingStatus] = Query(None),
    from_date: Optional[datetime] = Query(None),
    membership: TenantMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    q = select(Booking).where(Booking.tenant_id == str(tenant_id))
    if status:
        q = q.where(Booking.status == status)
    if from_date:
        q = q.where(Booking.starts_at >= from_date)
    q = q.order_by(Booking.starts_at.asc())
    bookings = list(db.execute(q).scalars())
    return [_to_dict(b) for b in bookings]


@router.post("", status_code=201)
def create_booking(
    tenant_id: UUID,
    payload: BookingCreate,
    membership: TenantMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    b = Booking(
        tenant_id=str(tenant_id),
        customer_name=payload.customer_name,
        customer_phone=payload.customer_phone,
        customer_email=payload.customer_email,
        branch_id=str(payload.branch_id) if payload.branch_id else None,
        product_id=str(payload.product_id) if payload.product_id else None,
        customer_id=str(payload.customer_id) if payload.customer_id else None,
        starts_at=payload.starts_at,
        ends_at=payload.ends_at,
        price_cents=payload.price_cents,
        notes=payload.notes,
        staff_name=payload.staff_name,
        status=BookingStatus.PENDING,
    )
    db.add(b)
    db.commit()
    db.refresh(b)
    return _to_dict(b)


@router.patch("/{booking_id}")
def update_booking(
    tenant_id: UUID,
    booking_id: UUID,
    payload: BookingUpdate,
    membership: TenantMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    b = db.get(Booking, booking_id)
    if not b or b.tenant_id != tenant_id:
        raise NotFoundError("Reserva")
    if payload.status:
        b.status = payload.status
    if payload.notes:
        b.notes = payload.notes
    db.commit()
    db.refresh(b)
    return _to_dict(b)


def _to_dict(b: Booking) -> dict:
    return {
        "id": str(b.id),
        "tenant_id": b.tenant_id,
        "customer_name": b.customer_name,
        "customer_phone": b.customer_phone,
        "customer_email": b.customer_email,
        "branch_id": b.branch_id,
        "product_id": b.product_id,
        "customer_id": b.customer_id,
        "starts_at": b.starts_at.isoformat() if b.starts_at else None,
        "ends_at": b.ends_at.isoformat() if b.ends_at else None,
        "status": b.status.value,
        "price_cents": b.price_cents,
        "notes": b.notes,
        "staff_name": b.staff_name,
        "created_at": b.created_at.isoformat() if b.created_at else None,
    }
