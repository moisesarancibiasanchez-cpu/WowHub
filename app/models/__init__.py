"""Modelos del dominio. Importar aquí para que SQLAlchemy los registre."""
from app.models.base import BaseModel, TimestampMixin, TenantMixin  # noqa: F401
from app.models.user import User, UserRole  # noqa: F401
from app.models.tenant import Tenant, TenantMembership, TenantPlan, TenantStatus, Industry  # noqa: F401
from app.models.branch import Branch  # noqa: F401
from app.models.category import Category  # noqa: F401
from app.models.product import Product, ProductStatus  # noqa: F401
from app.models.customer import Customer  # noqa: F401
from app.models.promotion import Promotion, PromotionType, DiscountType  # noqa: F401
from app.models.qr import QrCode, QrTarget  # noqa: F401
from app.models.landing import LandingConfig  # noqa: F401
from app.models.order import Order, OrderItem, OrderStatus  # noqa: F401
