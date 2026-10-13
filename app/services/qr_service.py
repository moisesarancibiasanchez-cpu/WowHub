"""QRService — generación de short_code, QR PNG data-URL, escaneo."""
import base64
import io
import secrets
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

import qrcode
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.models.qr import QrCode, QrTarget
from app.schemas.qr import QrCodeCreate, QrCodeUpdate
from app.config import settings


def _to_uuid(v) -> Optional[UUID]:
    """Coerce str|UUID|None a UUID|None."""
    if v is None or isinstance(v, UUID):
        return v
    return UUID(str(v))


class QrService:
    def __init__(self, db: Session):
        self.db = db

    def _new_short_code(self, length: int = 8) -> str:
        # Alfanum sin ambigüedades (sin 0/O, 1/I/l)
        alphabet = "23456789abcdefghjkmnpqrstuvwxyz"
        while True:
            code = "".join(secrets.choice(alphabet) for _ in range(length))
            exists = self.db.execute(
                select(QrCode).where(QrCode.short_code == code)
            ).scalar_one_or_none()
            if not exists:
                return code

    def _build_qr_data_url(self, payload: str) -> str:
        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=8,
            border=2,
        )
        qr.add_data(payload)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()

    def list(self, tenant_id: UUID) -> list[QrCode]:
        return list(self.db.execute(
            select(QrCode).where(QrCode.tenant_id == str(tenant_id))
            .order_by(QrCode.created_at.desc())
        ).scalars())

    def get(self, tenant_id: UUID, qr_id: UUID) -> QrCode:
        q = self.db.get(QrCode, qr_id)
        if not q or q.tenant_id != tenant_id:
            raise NotFoundError("QR")
        return q

    def get_by_code(self, short_code: str) -> QrCode:
        q = self.db.execute(
            select(QrCode).where(QrCode.short_code == short_code)
        ).scalar_one_or_none()
        if not q:
            raise NotFoundError("QR")
        return q

    def create(self, tenant_id: UUID, payload: QrCodeCreate) -> QrCode:
        short_code = self._new_short_code()
        data = payload.model_dump()
        data["tenant_id"] = str(tenant_id)
        data["short_code"] = short_code
        for f in ("target_id", "branch_id"):
            if data.get(f):
                data[f] = str(data[f])
        q = QrCode(**data)
        self.db.add(q)
        self.db.commit()
        self.db.refresh(q)
        return q

    def update(self, qr: QrCode, payload: QrCodeUpdate) -> QrCode:
        data = payload.model_dump(exclude_unset=True)
        for k, v in data.items():
            if k in ("target_id", "branch_id") and v is not None:
                v = str(v)
            setattr(qr, k, v)
        self.db.commit()
        self.db.refresh(qr)
        return qr

    def delete(self, qr: QrCode) -> None:
        self.db.delete(qr)
        self.db.commit()

    def record_scan(self, qr: QrCode, unique: bool = False) -> QrCode:
        qr.scan_count += 1
        if unique:
            qr.unique_scans += 1
        self.db.commit()
        self.db.refresh(qr)
        return qr

    # ── DTO helpers ────────────────────────────────────
    def to_out(self, qr: QrCode):
        from app.schemas.qr import QrCodeOut
        full_url = f"{settings.base_url}/r/{qr.short_code}"
        data_url = self._build_qr_data_url(full_url)
        return QrCodeOut(
            id=qr.id,
            tenant_id=_to_uuid(qr.tenant_id),
            label=qr.label,
            short_code=qr.short_code,
            target_type=qr.target_type,
            target_id=_to_uuid(qr.target_id),
            external_url=qr.external_url,
            branch_id=_to_uuid(qr.branch_id),
            scan_count=qr.scan_count,
            unique_scans=qr.unique_scans,
            conversion_count=qr.conversion_count,
            is_active=qr.is_active,
            expires_at=qr.expires_at,
            created_at=qr.created_at,
            full_url=full_url,
            qr_image_data_url=data_url,
        )
