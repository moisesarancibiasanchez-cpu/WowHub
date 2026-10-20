"""PaymentRecord y DebtAdjustment API (HU_56, HU_57)."""
from __future__ import annotations
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.security import requires_permission
from app.database import get_db
from app.deps import get_current_membership, get_current_user
from app.models.tenant import TenantMembership
from app.models.user import User
from app.schemas.payment_record import (
    PaymentRecordCreate, PaymentRecordOut, CustomerDebtSummary,
    DebtAdjustmentCreate, DebtAdjustmentOut,
)
from app.services.payment_record_service import PaymentRecordService, DebtAdjustmentService


router = APIRouter(prefix="/tenants/{tenant_id}", tags=["payment-records"])


@router.post("/payment-records", response_model=PaymentRecordOut, status_code=201)
@requires_permission("payment", "write")
def create_payment_record(
    tenant_id: UUID,
    payload: PaymentRecordCreate,
    membership: TenantMembership = Depends(get_current_membership),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """HU_56 — registrar pago manual (efectivo/transfer)."""
    return PaymentRecordService(db).create(tenant_id, payload, current_user.id)


@router.get("/payment-records", response_model=list[PaymentRecordOut])
def list_payment_records(
    tenant_id: UUID,
    customer_id: Optional[UUID] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    membership: TenantMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    """HU_56 — listar pagos (opcionalmente por cliente)."""
    if customer_id:
        return PaymentRecordService(db).list_for_customer(tenant_id, customer_id, limit)
    from app.models.payment_record import PaymentRecord
    from sqlalchemy import select
    return list(db.execute(
        select(PaymentRecord)
        .where(PaymentRecord.tenant_id == str(tenant_id))
        .order_by(PaymentRecord.created_at.desc())
        .limit(limit)
    ).scalars())


@router.get("/customers/{customer_id}/debt-summary", response_model=CustomerDebtSummary)
def get_debt_summary(
    tenant_id: UUID,
    customer_id: UUID,
    membership: TenantMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    """HU_56 — resumen de deuda del cliente."""
    return PaymentRecordService(db).debt_summary(tenant_id, customer_id)


@router.post("/debt-adjustments", response_model=DebtAdjustmentOut, status_code=201)
@requires_permission("payment", "write")
def create_debt_adjustment(
    tenant_id: UUID,
    payload: DebtAdjustmentCreate,
    membership: TenantMembership = Depends(get_current_membership),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """HU_57 — crear ajuste de deuda (condonación). Solo OWNER/ADMIN."""
    if membership.role.value not in ("owner", "admin"):
        from app.core.errors import PermissionDeniedError
        raise PermissionDeniedError("Solo OWNER/ADMIN pueden crear ajustes de deuda")
    return DebtAdjustmentService(db).create(tenant_id, payload, current_user.id)
