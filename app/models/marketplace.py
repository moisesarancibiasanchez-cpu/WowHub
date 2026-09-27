"""Marketplace models for WowHub plugin ecosystem (HU_45)."""
import uuid
from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.database import Base


class MarketplacePlugin(Base):
    """Plugin published by the platform admin.

    Managed by platform admin (role=superadmin).
    Tenants subscribe to install in their tenant.
    """
    __tablename__ = "marketplace_plugins"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False)
    slug = Column(String(100), unique=True, nullable=False)
    description = Column(Text, nullable=True)
    version = Column(String(20), default="1.0.0")
    category = Column(String(50), nullable=False)  # notifications, analytics, crm, ai, operations, integrations

    # SDK / installation
    pip_package = Column(String(255), nullable=True)
    git_url = Column(String(500), nullable=True)
    install_script = Column(Text, nullable=True)
    config_schema = Column(Text, nullable=True)

    # Visibility
    is_active = Column(Boolean, default=True, nullable=False)
    is_featured = Column(Boolean, default=False, nullable=False)
    is_paid = Column(Boolean, default=False)
    price_monthly_usd = Column(Integer, default=0)  # price in USD cents

    # Ratings & stats
    installs = Column(Integer, default=0)
    rating = Column(Integer, default=0)  # 0-5 stars (stored as int)

    # Ownership
    published_by = Column(UUID(as_uuid=True), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<MarketplacePlugin {self.slug} v{self.version}>"


class PluginSubscription(Base):
    """Tenant subscription to a marketplace plugin."""
    __tablename__ = "plugin_subscriptions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    plugin_id = Column(UUID(as_uuid=True), ForeignKey("marketplace_plugins.id"), nullable=False, index=True)

    status = Column(String(20), default="active")  # active, suspended, canceled
    config = Column(Text, nullable=True)  # JSON config for this tenant

    installed_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    canceled_at = Column(DateTime, nullable=True)

    # Revenue share (for paid plugins): 70/30 platform/developer
    revenue_share_70_to_developer = Column(Boolean, default=True)

    __table_args__ = (
        UniqueConstraint("tenant_id", "plugin_id", name="uq_tenant_plugin"),
    )
