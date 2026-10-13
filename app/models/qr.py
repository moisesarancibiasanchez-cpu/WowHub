"""QrCode: códigos QR generados por tenant con su destino."""
import enum
from typing import Optional

from sqlalchemy import Boolean, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import GUID, BaseModel, TenantMixin


class QrTarget(str, enum.Enum):
    CATALOG = "catalog"          # → catálogo completo
    PRODUCT = "product"          # → producto individual
    CATEGORY = "category"        # → categoría
    PROMOTION = "promotion"      # → promo
    LANDING = "landing"          # → landing config
    EXTERNAL_URL = "external"    # → URL externa
    TABLE = "table"              # → mesa de restaurant


class QrCode(BaseModel, TenantMixin):
    __tablename__ = "qr_codes"

    label: Mapped[str] = mapped_column(String(120), nullable=False)
    short_code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    target_type: Mapped[QrTarget] = mapped_column(
        Enum(QrTarget, name="qr_target"),
        default=QrTarget.CATALOG,
        nullable=False,
    )
    # ID del recurso destino (producto, categoría, etc). Opcional si es URL externa.
    target_id: Mapped[Optional[str]] = mapped_column(GUID(), nullable=True, index=True)
    external_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Branch asociado (ej: mesa de un local)
    branch_id: Mapped[Optional[str]] = mapped_column(
        GUID(),
        ForeignKey("branches.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Métricas
    scan_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    unique_scans: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    conversion_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    expires_at: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
