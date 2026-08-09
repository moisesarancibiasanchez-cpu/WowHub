"""Uploads API — gestión de archivos subidos."""
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session

from app.core.errors import ValidationError
from app.database import get_db
from app.deps import get_current_membership
from app.models.tenant import TenantMembership
from app.schemas.upload import UploadOut
from app.services.upload_service import UploadService

router = APIRouter(prefix="/tenants/{tenant_id}/uploads", tags=["uploads"])


@router.post("", response_model=UploadOut, status_code=201)
async def upload_file(
    tenant_id: UUID,
    file: UploadFile = File(...),
    purpose: Optional[str] = Form(None),
    entity_type: Optional[str] = Form(None),
    entity_id: Optional[UUID] = Form(None),
    membership: TenantMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    """Sube un archivo (imagen)."""
    content = await file.read()
    svc = UploadService(db)
    upload = svc.save_image(
        tenant_id,
        content=content,
        filename=file.filename or "upload",
        content_type=file.content_type or "application/octet-stream",
        purpose=purpose,
        entity_type=entity_type,
        entity_id=entity_id,
    )
    return UploadOut.model_validate(upload)


@router.get("", response_model=list[UploadOut])
def list_uploads(
    tenant_id: UUID,
    entity_type: Optional[str] = None,
    entity_id: Optional[UUID] = None,
    membership: TenantMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    svc = UploadService(db)
    if entity_type and entity_id:
        return [UploadOut.model_validate(u) for u in svc.list_for_entity(tenant_id, entity_type=entity_type, entity_id=entity_id)]
    from app.models.upload import Upload
    from sqlalchemy import select
    q = select(Upload).where(Upload.tenant_id == str(tenant_id))
    if entity_type:
        q = q.where(Upload.entity_type == entity_type)
    q = q.order_by(Upload.created_at.desc()).limit(100)
    return [UploadOut.model_validate(u) for u in db.execute(q).scalars()]


@router.delete("/{upload_id}", status_code=204)
def delete_upload(
    tenant_id: UUID,
    upload_id: UUID,
    membership: TenantMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    UploadService(db).delete(tenant_id, upload_id)
