"""BranchProduct: stock multi-sucursal."""
from sqlalchemy import ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import GUID, BaseModel, TenantMixin


class BranchProduct(BaseModel, TenantMixin):
    """Inventario por sucursal. Si no existe, se usa Product.stock global."""
    __tablename__ = "branch_products"

    branch_id: Mapped[str] = mapped_column(
        GUID(),
        ForeignKey("branches.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_id: Mapped[str] = mapped_column(
        GUID(),
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    stock: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    low_stock_threshold: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
