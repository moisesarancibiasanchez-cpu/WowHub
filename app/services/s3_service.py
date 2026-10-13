"""S3-compatible storage service with local fallback.

HU_37: Almacenamiento de archivos (imágenes, PDFs, adjuntos).
Supports: AWS S3, Cloudflare R2, MinIO.
Falls back to local filesystem in development.

Usage:
    from app.services.s3_service import s3_service
    url = s3_service.upload_file(tenant_id=1, file_path="logos/hero.png", content=bytes_data)
    s3_service.delete_file(tenant_id=1, file_path="logos/hero.png")
"""
import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger("wowhub.s3")


class S3Service:
    """Unified storage service: S3/R2 in production, local filesystem in dev."""

    def __init__(self) -> None:
        self.s3_enabled = bool(os.getenv("S3_BUCKET"))
        self._client: Optional[object] = None
        self._bucket: Optional[str] = None

        if self.s3_enabled:
            try:
                import boto3  # type: ignore
                self._client = boto3.client(
                    "s3",
                    endpoint_url=os.getenv("S3_ENDPOINT_URL"),
                    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
                    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
                    region_name=os.getenv("AWS_REGION", "us-east-1"),
                )
                self._bucket = os.getenv("S3_BUCKET")
                logger.info("S3 enabled — bucket=%s, endpoint=%s", self._bucket, os.getenv("S3_ENDPOINT_URL"))
            except ImportError:
                logger.warning("boto3 not installed — S3 disabled, falling back to local")
                self.s3_enabled = False
            except Exception as exc:
                logger.error("S3 init failed: %s — falling back to local", exc)
                self.s3_enabled = False
        else:
            logger.info("S3 disabled — using local filesystem at %s", self.storage_path)

    @property
    def storage_path(self) -> Path:
        return Path(os.getenv("STORAGE_PATH", "/workspace/storage"))

    def upload_file(
        self,
        tenant_id: int,
        file_path: str,
        content: bytes,
        content_type: str = "application/octet-stream",
    ) -> str:
        """Upload file to S3 or local storage. Returns URL."""
        if self.s3_enabled:
            return self._upload_s3(tenant_id, file_path, content, content_type)
        return self._upload_local(tenant_id, file_path, content)

    def _upload_s3(
        self,
        tenant_id: int,
        file_path: str,
        content: bytes,
        content_type: str,
    ) -> str:
        key = f"{tenant_id}/{file_path}"
        extra: dict = {"ContentType": content_type}
        if os.getenv("S3_CACHE_CONTROL"):
            extra["CacheControl"] = os.getenv("S3_CACHE_CONTROL")
        self._client.put_object(Bucket=self._bucket, Key=key, Body=content, **extra)
        expires_in = int(os.getenv("S3_PRESIGN_EXPIRES", 3600))
        url = self._client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket, "Key": key},
            ExpiresIn=expires_in,
        )
        logger.debug("S3 upload — key=%s, bytes=%d", key, len(content))
        return url

    def _upload_local(
        self,
        tenant_id: int,
        file_path: str,
        content: bytes,
    ) -> str:
        local_dir = self.storage_path / str(tenant_id) / file_path
        local_dir.parent.mkdir(parents=True, exist_ok=True)
        local_dir.write_bytes(content)
        logger.debug("Local upload — path=%s, bytes=%d", local_dir, len(content))
        return f"/storage/{tenant_id}/{file_path}"

    def delete_file(self, tenant_id: int, file_path: str) -> None:
        """Delete file from S3 or local storage."""
        if self.s3_enabled:
            key = f"{tenant_id}/{file_path}"
            self._client.delete_object(Bucket=self._bucket, Key=key)
        else:
            local_path = self.storage_path / str(tenant_id) / file_path
            if local_path.exists():
                local_path.unlink()

    def get_upload_url(
        self,
        tenant_id: int,
        file_path: str,
        content_type: str = "application/octet-stream",
        expires_in: int = 3600,
    ) -> str:
        """Generate a presigned PUT URL for direct browser uploads (S3) or local path."""
        if self.s3_enabled:
            key = f"{tenant_id}/{file_path}"
            return self._client.generate_presigned_url(
                "put_object",
                Params={"Bucket": self._bucket, "Key": key, "ContentType": content_type},
                ExpiresIn=expires_in,
            )
        return f"/storage/{tenant_id}/{file_path}"

    def file_exists(self, tenant_id: int, file_path: str) -> bool:
        """Check if a file exists."""
        if self.s3_enabled:
            try:
                self._client.head_object(Bucket=self._bucket, Key=f"{tenant_id}/{file_path}")
                return True
            except Exception:
                return False
        return (self.storage_path / str(tenant_id) / file_path).exists()


# ── Module-level singleton ────────────────────────────────────────────
_s3_service: Optional[S3Service] = None


def get_s3_service() -> S3Service:
    global _s3_service
    if _s3_service is None:
        _s3_service = S3Service()
    return _s3_service


# Convenient import alias
s3_service = get_s3_service()
