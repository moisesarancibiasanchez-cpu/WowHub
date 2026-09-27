# DEPRECATED: TenantSiteConfig merged into existing SiteConfig model.
# This schema file is kept for backwards compatibility (no-op).
# The existing site_configs table serves both platform admin and per-tenant configs.
from app.schemas.site_config import *  # noqa: F401,F403
