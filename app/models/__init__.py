"""Modelos del dominio. Importar aquí para que SQLAlchemy los registre."""
from app.models.base import BaseModel, TimestampMixin, TenantMixin, GUID  # noqa: F401
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
from app.models.payment import Payment, PaymentMethod, PaymentStatus  # noqa: F401
from app.models.webhook import Webhook, WebhookEvent, WebhookDelivery  # noqa: F401
from app.models.audit import AuditLog  # noqa: F401
from app.models.branch_product import BranchProduct  # noqa: F401
from app.models.token import AuthToken, TokenType  # noqa: F401
from app.models.cart import Cart, CartItem  # noqa: F401
from app.models.invoice import Invoice, InvoiceStatus  # noqa: F401
from app.models.booking import Booking, BookingStatus  # noqa: F401
from app.models.legal import LegalConsent  # noqa: F401
from app.models.onboarding import OnboardingState  # noqa: F401
from app.models.upload import Upload  # noqa: F401
from app.models.site_config import SiteConfig  # noqa: F401
from app.models.ai import (  # noqa: F401
    AIConversation, AIMessage, AILog, AITrace, AIMetricDaily,
    AgentKind, MessageRole, ConversationStatus, LogStatus,
)
from app.models.loyalty_pass import (  # noqa: F401
    LoyaltyCampaign, CustomerPass, PassStamp, QrToken,
    PassSource, PassStatus, StampReason, QrTokenKind,
)
from app.models.quote import Quote, QuoteItem, QuoteStatus  # noqa: F401
# Automation Manager™ (Cap. 19.3) — audit log de ejecuciones
from app.models.automation import AutomationExecution, AutomationStatus  # noqa: F401
# V8 P0.1 — Insumos (materia prima) + Recetas (BOM)
from app.models.insumo import Insumo, Receta  # noqa: F401
