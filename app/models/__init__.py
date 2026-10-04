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
from app.models.marketplace import MarketplacePlugin, PluginSubscription  # noqa: F401
# TenantSiteConfig: config por tenant en tabla `tenant_site_configs` (distinta del
# singleton global `site_config`). Ver app/models/tenant_site_config.py
from app.models.tenant_site_config import TenantSiteConfig  # noqa: F401
# HU_12 — Variantes y modificadores de productos
from app.models.product_variant import (  # noqa: F401
    ProductVariant, Modifier, ModifierOption, ModifierType, ProductModifierGroup,
)
# HU_17 — Línea de tiempo del pedido (OrderEvent)
from app.models.order_event import OrderEvent, OrderEventType  # noqa: F401
# HU_19 — Mesero virtual / cuenta dividida (DiningSession)
from app.models.dining_session import (  # noqa: F401
    DiningSession, DiningSessionItem, DiningSessionStatus,
)
# HU_29 — Tiers de fidelidad (Bronce / Plata / Oro / Platino)
from app.models.loyalty_tier import LoyaltyTier  # noqa: F401
# HU_38 — RBAC Granular con Casbin (rbac_policies + rbac_groupings)
from app.models.rbac import RBACPolicy, RBACGrouping  # noqa: F401
# HU_34 — Dashboard personalizable (GridStack widgets) — 1 fila por tenant (1:1)
from app.models.dashboard import DashboardLayout  # noqa: F401
# HU_33 — Receipt OCR (comprobantes/tickets) — 1 fila por imagen procesada
from app.models.receipt import Receipt, ReceiptStatus  # noqa: F401
# HU_31 follow-up — Historial de ejecuciones de reportes (last_run_at real)
from app.models.report_run import ReportRun  # noqa: F401
