"""Uploads API — gestión de archivos subidos."""
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
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
    request: Request,
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
    # Pasamos request.base_url para que la URL pública retornada siempre
    # apunte al host desde el que el browser está hablando (sea localhost
    # en dev o el dominio público en Railway). Esto es lo que se guarda en
    # la DB y se renderiza después en <img src> en landing/catálogo.
    svc = UploadService(db, base_url=str(request.base_url))
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
    request: Request,
    tenant_id: UUID,
    entity_type: Optional[str] = None,
    entity_id: Optional[UUID] = None,
    membership: TenantMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    svc = UploadService(db, base_url=str(request.base_url))
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
    request: Request,
    tenant_id: UUID,
    upload_id: UUID,
    membership: TenantMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    UploadService(db, base_url=str(request.base_url)).delete(tenant_id, upload_id)
