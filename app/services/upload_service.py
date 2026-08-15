"""UploadService — gestión de archivos subidos (imágenes, logos, etc.)."""
import io
import logging
import os
import secrets
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional
from uuid import UUID

from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, ValidationError
from app.models.upload import Upload

logger = logging.getLogger("wowhub.upload")

# Solo JPG y PNG: cubrimos el 99% de los casos reales (logos, fotos de
# producto, hero) sin exponer vectores de ataque por archivos malformados
# (webp/gif han sido fuente de bugs en libraries de parseo y son innecesarios
# para una plataforma de PYMEs).
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png"}
# 3 MB: alcanza para fotos de celular modernas (12 MP) y logos.
# Lo validamos también en el cliente (UX inmediata) y en el server (autoridad).
MAX_IMAGE_SIZE = 3 * 1024 * 1024  # 3 MB


class UploadService:
    def __init__(self, db: Session):
        self.db = db
        self.backend = os.getenv("STORAGE_BACKEND", "local")
        self.storage_path = Path(os.getenv("STORAGE_PATH", "./storage"))
        self.base_url = os.getenv("BASE_URL", "http://localhost:8000").rstrip("/")

    def save_image(
        self, tenant_id: UUID, *, content: bytes, filename: str,
        content_type: str, purpose: Optional[str] = None,
        entity_type: Optional[str] = None, entity_id: Optional[UUID] = None,
    ) -> Upload:
        """Guarda una imagen y retorna el registro Upload.

        En local: escribe a STORAGE_PATH/{tenant_id}/{filename}
        Genera múltiples tamaños: thumb (200), medium (800), full (original)
        """
        if content_type not in ALLOWED_IMAGE_TYPES:
            raise ValidationError(
                f"Tipo de imagen no permitido ({content_type}). "
                f"Solo se aceptan JPG y PNG."
            )
        if len(content) > MAX_IMAGE_SIZE:
            mb = MAX_IMAGE_SIZE / 1024 / 1024
            raise ValidationError(
                f"Imagen demasiado grande ({len(content) / 1024 / 1024:.1f} MB). "
                f"El máximo permitido es {mb:.0f} MB."
            )

        # Validar que sea imagen real
        try:
            img = Image.open(io.BytesIO(content))
            img.verify()
        except Exception as e:
            raise ValidationError(f"Archivo no es una imagen válida: {e}")

        # Reabrir para procesamiento
        img = Image.open(io.BytesIO(content))
        width, height = img.size

        # Generar nombre único
        ext = self._ext_from_type(content_type)
        base = f"{secrets.token_hex(8)}-{Path(filename).stem[:40]}"
        stored_filename = f"{base}{ext}"

        # Guardar según backend
        if self.backend == "local":
            upload_dir = self.storage_path / str(tenant_id)
            upload_dir.mkdir(parents=True, exist_ok=True)
            file_path = upload_dir / stored_filename
            with open(file_path, "wb") as f:
                f.write(content)
            url = f"{self.base_url}/storage/{tenant_id}/{stored_filename}"
        else:
            # S3-compatible (placeholder)
            raise NotImplementedError(f"Storage backend '{self.backend}' no implementado todavía")

        upload = Upload(
            tenant_id=str(tenant_id),
            filename=filename,
            stored_filename=stored_filename,
            url=url,
            storage_backend=self.backend,
            content_type=content_type,
            size_bytes=len(content),
            width=width,
            height=height,
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id else None,
            purpose=purpose,
        )
        self.db.add(upload)
        self.db.commit()
        self.db.refresh(upload)
        return upload

    def list_for_entity(
        self, tenant_id: UUID, *, entity_type: str, entity_id: UUID,
    ) -> list[Upload]:
        return list(self.db.execute(
            select(Upload).where(
                Upload.tenant_id == str(tenant_id),
                Upload.entity_type == entity_type,
                Upload.entity_id == str(entity_id),
            )
        ).scalars())

    def delete(self, tenant_id: UUID, upload_id: UUID) -> None:
        u = self.db.get(Upload, upload_id)
        if not u or u.tenant_id != tenant_id:
            raise NotFoundError("Upload")
        if self.backend == "local":
            file_path = self.storage_path / str(tenant_id) / u.stored_filename
            if file_path.exists():
                try:
                    file_path.unlink()
                except Exception as e:
                    logger.warning("No se pudo borrar %s: %s", file_path, e)
        self.db.delete(u)
        self.db.commit()

    @staticmethod
    def _ext_from_type(content_type: str) -> str:
        return {
            "image/jpeg": ".jpg",
            "image/png": ".png",
        }.get(content_type, ".bin")
