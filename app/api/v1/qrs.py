"""QR endpoints."""
from uuid import UUID
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.database import get_db
from app.deps import get_tenant_for_membership
from app.models.qr import QrCode
from app.models.tenant import Tenant
from app.schemas.qr import QrCodeCreate, QrCodeOut, QrCodeUpdate
from app.services.qr_service import QrService

router = APIRouter(prefix="/tenants/{tenant_id}/qrs", tags=["qrs"])


@router.get("", response_model=list[QrCodeOut])
def list_qrs(tenant: Tenant = Depends(get_tenant_for_membership), db: Session = Depends(get_db)):
    svc = QrService(db)
    return [svc.to_out(q) for q in svc.list(tenant.id)]


@router.post("", response_model=QrCodeOut, status_code=201)
def create_qr(
    payload: QrCodeCreate,
    tenant: Tenant = Depends(get_tenant_for_membership),
    db: Session = Depends(get_db),
):
    svc = QrService(db)
    q = svc.create(tenant.id, payload)
    return svc.to_out(q)


@router.get("/{qr_id}", response_model=QrCodeOut)
def get_qr(qr_id: UUID, tenant: Tenant = Depends(get_tenant_for_membership), db: Session = Depends(get_db)):
    svc = QrService(db)
    q = svc.get(tenant.id, qr_id)
    return svc.to_out(q)


@router.patch("/{qr_id}", response_model=QrCodeOut)
def update_qr(
    qr_id: UUID,
    payload: QrCodeUpdate,
    tenant: Tenant = Depends(get_tenant_for_membership),
    db: Session = Depends(get_db),
):
    svc = QrService(db)
    q = svc.get(tenant.id, qr_id)
    q = svc.update(q, payload)
    return svc.to_out(q)


@router.delete("/{qr_id}", status_code=204)
def delete_qr(qr_id: UUID, tenant: Tenant = Depends(get_tenant_for_membership), db: Session = Depends(get_db)):
    svc = QrService(db)
    q = svc.get(tenant.id, qr_id)
    svc.delete(q)
