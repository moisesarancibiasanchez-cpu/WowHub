"""API de Cotizaciones (Quotes) — owner y rutas públicas."""
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_membership
from app.models.quote import QuoteStatus
from app.models.tenant import TenantMembership
from app.schemas.common import Page
from app.schemas.quote import (
    QuoteCreate, QuoteUpdate, QuoteOut, QuoteListItem, QuoteStats,
)
from app.services.quote_service import QuoteService

router = APIRouter(prefix="/tenants/{tenant_id}/quotes", tags=["quotes"])


def _to_out(q) -> dict:
    return {
        "id": q.id,
        "number": q.number,
        "title": q.title,
        "status": q.status,
        "customer_id": q.customer_id,
        "branch_id": q.branch_id,
        "recipient_name": q.recipient_name,
        "recipient_email": q.recipient_email,
        "recipient_phone": q.recipient_phone,
        "subtotal_cents": q.subtotal_cents,
        "discount_cents": q.discount_cents,
        "tax_cents": q.tax_cents,
        "total_cents": q.total_cents,
        "currency": q.currency,
        "notes": q.notes,
        "terms": q.terms,
        "valid_until": q.valid_until,
        "public_token": q.public_token,
        "sent_at": q.sent_at,
        "viewed_at": q.viewed_at,
        "accepted_at": q.accepted_at,
        "rejected_at": q.rejected_at,
        "converted_order_id": q.converted_order_id,
        "created_at": q.created_at,
        "updated_at": q.updated_at,
        "items": [
            {
                "id": it.id,
                "product_id": it.product_id,
                "product_name": it.product_name,
                "product_sku": it.product_sku,
                "description": it.description,
                "quantity": it.quantity,
                "unit_price_cents": it.unit_price_cents,
                "discount_cents": it.discount_cents,
                "total_cents": it.total_cents,
            }
            for it in q.items
        ],
    }


@router.get("", response_model=Page[QuoteListItem])
def list_quotes(
    tenant_id: UUID,
    status: Optional[QuoteStatus] = Query(None),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    membership: TenantMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    return QuoteService(db).list(tenant_id, status=status, search=search, page=page, page_size=page_size)


@router.get("/stats", response_model=QuoteStats)
def quote_stats(
    tenant_id: UUID,
    membership: TenantMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    return QuoteService(db).stats(tenant_id)


@router.get("/{quote_id}", response_model=QuoteOut)
def get_quote(
    tenant_id: UUID,
    quote_id: UUID,
    membership: TenantMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    q = QuoteService(db).get(tenant_id, quote_id)
    return _to_out(q)


@router.post("", response_model=QuoteOut, status_code=201)
def create_quote(
    tenant_id: UUID,
    payload: QuoteCreate,
    membership: TenantMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    data = payload.model_dump(exclude={"items"})
    items = [it.model_dump() for it in payload.items]
    q = QuoteService(db).create(tenant_id, {**data, "items": items})
    return _to_out(q)


@router.patch("/{quote_id}", response_model=QuoteOut)
def update_quote(
    tenant_id: UUID,
    quote_id: UUID,
    payload: QuoteUpdate,
    membership: TenantMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    data = payload.model_dump(mode="json", exclude_none=True)
    if "items" in data:
        data["items"] = data["items"]
    q = QuoteService(db).update(tenant_id, quote_id, data)
    return _to_out(q)


@router.delete("/{quote_id}", status_code=204)
def delete_quote(
    tenant_id: UUID,
    quote_id: UUID,
    membership: TenantMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    QuoteService(db).delete(tenant_id, quote_id)
    return None


@router.post("/{quote_id}/send", response_model=QuoteOut)
def send_quote(
    tenant_id: UUID,
    quote_id: UUID,
    membership: TenantMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    q = QuoteService(db).mark_sent(tenant_id, quote_id)
    return _to_out(q)


@router.post("/{quote_id}/accept", response_model=QuoteOut)
def accept_quote(
    tenant_id: UUID,
    quote_id: UUID,
    membership: TenantMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    q = QuoteService(db).accept(tenant_id, quote_id)
    return _to_out(q)


@router.post("/{quote_id}/reject", response_model=QuoteOut)
def reject_quote(
    tenant_id: UUID,
    quote_id: UUID,
    membership: TenantMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    q = QuoteService(db).reject(tenant_id, quote_id)
    return _to_out(q)


@router.post("/{quote_id}/convert", status_code=201)
def convert_quote_to_order(
    tenant_id: UUID,
    quote_id: UUID,
    branch_id: Optional[UUID] = Query(None),
    membership: TenantMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    order = QuoteService(db).convert_to_order(tenant_id, quote_id, branch_id=branch_id)
    return {"order_id": str(order.id), "number": order.number}


# ── Rutas públicas ─────────────────────────────────────────
public_router = APIRouter(prefix="/public/quotes", tags=["public-quotes"])


@public_router.get("/{token}")
def public_get_quote(token: str, db: Session = Depends(get_db)):
    """El cliente abre la cotización por su token único."""
    q = QuoteService(db).mark_viewed(token)
    return _to_out(q)


@public_router.post("/{token}/accept", response_model=QuoteOut)
def public_accept_quote(token: str, db: Session = Depends(get_db)):
    from app.core.errors import ConflictError
    quote = QuoteService(db).get_by_token(token)
    if quote.status not in (QuoteStatus.SENT, QuoteStatus.VIEWED, QuoteStatus.DRAFT):
        raise ConflictError(f"No se puede aceptar en estado '{quote.status.value}'")
    q = QuoteService(db).accept(quote.tenant_id, quote.id)
    return _to_out(q)


@public_router.post("/{token}/reject", response_model=QuoteOut)
def public_reject_quote(token: str, db: Session = Depends(get_db)):
    quote = QuoteService(db).get_by_token(token)
    q = QuoteService(db).reject(quote.tenant_id, quote.id)
    return _to_out(q)
