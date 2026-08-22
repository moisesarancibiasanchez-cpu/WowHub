"""Configuración central via Pydantic Settings."""
from functools import lru_cache
from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Variables de entorno de WowHub."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # App
    app_name: str = "WowHub"
    app_env: str = "development"
    debug: bool = True
    log_level: str = "INFO"
    secret_key: str = "change-me-in-production-min-32-chars-please-ok"
    base_url: str = "http://localhost:8000"
    # v1.9.1-r2: el dominio PÚBLICO de la plataforma es wowhub.app.
    # Este valor se usa para armar las URLs ABSOLUTAS que devuelve la tool
    # `get_tenant_dashboard_urls` y `get_tenant_public_urls`. Si está vacío,
    # la tool devuelve paths relativos + warning (modo defensivo).
    #
    # v1.9.1-r3: si está vacío en runtime (no seteado en .env ni en Railway),
    # se hace fallback automático a `base_url` (útil para dev local: si dejás
    # el default de `base_url=http://localhost:8000` y no tocás nada, la IA
    # sugiere links `http://localhost:8000/dashboard/products` en vez del
    # `https://wowhub.app` que rompería en dev). El método `effective_public_base_url`
    # es la propiedad canónica que las tools deben usar.
    #
    # v1.9.1-r4: el dominio público REAL es el backend desplegado en Railway
    # (https://wowhub-api-production.up.railway.app/), NO wowhub.app.
    # Razón: la única URL que el sistema puede GARANTIZAR como "existe y
    # responde hoy" es la del backend en producción (lo confirma su OpenAPI
    # en /openapi.json). Cualquier otro dominio que la IA entregue como
    # "tu link público" sería una URL FALSA → 404 → usuario con la impresión
    # de que WowHub no funciona. La IA NO debe hardcodear wowhub.app.
    public_base_url: str = "https://wowhub-api-production.up.railway.app"

    @property
    def effective_public_base_url(self) -> str:
        """Devuelve `public_base_url` si está seteado, si no `base_url`.

        Esto evita que en dev local (donde nadie setea PUBLIC_BASE_URL en .env)
        la IA recomiende links `https://wowhub.app/...` que NO funcionan
        en localhost. Si en producción tampoco se setea, el default
        `https://wowhub.app` aplica igual (porque `public_base_url` ya tiene
        ese default, no queda vacío).
        """
        return (self.public_base_url or "").strip() or self.base_url

    # DB
    database_url: str = "sqlite:///./wowhub.db"

    # Auth
    jwt_secret: str = "change-me-jwt-secret-min-32-chars-random-ok"
    jwt_algorithm: str = "HS256"
    jwt_access_ttl_minutes: int = 60
    jwt_refresh_ttl_days: int = 14

    # CORS
    # Incluye localhost (dev) + el dominio de producción de Railway.
    # Si necesitás más orígenes, set CORS_ORIGINS en el .env o en Railway.
    cors_origins: str = (
        "http://localhost:3000,http://localhost:8000,"
        "https://wowhub-api-production.up.railway.app,"
        "https://wowhub.app,https://www.wowhub.app"
    )

    # Storage
    storage_backend: str = "local"
    storage_path: str = "./storage"

    # ── Nuevas settings (v0.2.0) ──────────────────────────
    # Email
    email_backend: str = "log"  # log | console | smtp | resend
    email_from: str = "no-reply@wowhub.app"
    email_from_name: str = "WowHub"

    # SMTP
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_use_tls: bool = True

    # Resend
    resend_api_key: str = ""

    # MercadoPago
    mercadopago_access_token: str = ""
    mercadopago_public_key: str = ""
    mercadopago_enabled: bool = False
    payment_default_provider: str = "mock"  # mock | mercadopago

    # Webhooks
    webhook_secret: str = "change-me-webhook-secret-min-32-chars-ok"
    webhook_max_retries: int = 5
    webhook_timeout_seconds: int = 10

    # Rate limit
    rate_limit_enabled: bool = True
    rate_limit_auth_per_min: int = 20
    rate_limit_orders_per_min: int = 60
    rate_limit_default_per_min: int = 200

    # Audit
    audit_enabled: bool = True
    audit_retention_days: int = 365

    # Password policy
    password_min_length: int = 8
    password_require_letter: bool = True
    password_require_digit: bool = True

    # Loyalty defaults (se puede override por tenant)
    loyalty_points_per_currency_unit: int = 1  # 1 punto por cada unidad de moneda gastada
    loyalty_currency_unit: int = 100  # cada 100 unidades (ej. $1) = N puntos
    loyalty_redeem_rate: int = 100  # 100 puntos = 100 unidades (1:1)
    loyalty_min_redeem: int = 100  # mínimo 100 puntos para canjear

    # Uploads
    upload_max_bytes: int = 5 * 1024 * 1024  # 5 MB
    upload_allowed_types: str = "image/jpeg,image/png,image/webp,application/pdf"

    # Búsqueda
    search_max_results: int = 50

    # ── AI Core (WowHub) ─────────────────────────────
    # Proveedor LLM. openai_compatible = /v1 (MiniMax) | anthropic = /anthropic
    llm_provider: str = "openai_compatible"
    llm_api_key: str = ""
    llm_base_url: str = "https://api.minimax.io/v1"
    llm_model: str = "MiniMax-M3"
    llm_timeout_seconds: int = 30
    llm_max_retries: int = 2
    # Circuit breaker
    llm_cb_fail_threshold: int = 5
    llm_cb_reset_seconds: int = 60
    # Chat por usuario
    ai_context_messages: int = 20
    ai_daily_message_limit: int = 100
    # Automation Manager (Cap. 19.3) — ejecuciones por usuario/día
    # Cuenta solo /execute confirmados (NO los previews).
    ai_daily_automation_limit: int = 50
    # Fallback cuando el LLM está caído
    ai_fallback_enabled: bool = True

    @property
    def llm_enabled(self) -> bool:
        """El LLM está operativo si hay API key, base URL y modelo configurados."""
        return bool(self.llm_api_key and self.llm_base_url and self.llm_model)

    @field_validator("cors_origins")
    @classmethod
    def _strip_origins(cls, v: str) -> str:
        return v.strip()

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def allowed_upload_mime_types(self) -> List[str]:
        return [m.strip() for m in self.upload_allowed_types.split(",") if m.strip()]

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
