"""Schemas Pydantic — capa de validación/serialización de la API."""
from app.schemas.auth import (  # noqa: F401
    UserCreate, UserLogin, UserOut, UserUpdate,
    TokenPair, TokenRefresh, MembershipOut,
)
from app.schemas.tenant import (  # noqa: F401
    TenantCreate, TenantOut, TenantUpdate,
    TenantMembershipCreate, TenantMembershipOut,
)
from app.schemas.branch import BranchCreate, BranchOut, BranchUpdate  # noqa: F401
from app.schemas.category import CategoryCreate, CategoryOut, CategoryUpdate  # noqa: F401
from app.schemas.product import (  # noqa: F401
    ProductCreate, ProductOut, ProductUpdate, ProductListItem,
)
from app.schemas.customer import CustomerCreate, CustomerOut, CustomerUpdate  # noqa: F401
from app.schemas.promotion import (  # noqa: F401
    PromotionCreate, PromotionOut, PromotionUpdate,
)
from app.schemas.qr import QrCodeCreate, QrCodeOut, QrCodeUpdate  # noqa: F401
from app.schemas.landing import LandingConfigOut, LandingConfigUpdate  # noqa: F401
from app.schemas.order import (  # noqa: F401
    OrderCreate, OrderOut, OrderItemOut,
)
from app.schemas.common import Page  # noqa: F401
from app.schemas.quote import (  # noqa: F401
    QuoteCreate, QuoteUpdate, QuoteOut, QuoteListItem, QuoteStats,
    QuoteItemCreate, QuoteItemOut,
)
