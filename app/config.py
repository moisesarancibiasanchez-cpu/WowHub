"""Configuración central via Pydantic Settings."""
from functools import lru_cache
from typing import List

from pydantic import Field, field_validator, model_validator
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
    # Access token de corta duración (HU_03): reducido de 60 → 15 min para
    # acotar ventana de exposición ante robo de token. Rotación de refresh
    # token queda fuera de scope de esta HU.
    jwt_access_ttl_minutes: int = 15
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
    # FIX 2026-09-27: en producción `/storage` NO debe servirse como
    # `StaticFiles` público. El endpoint autenticado
    # `GET /tenants/{tid}/uploads/{id}/content` valida pertenencia al tenant.
    # Poner en True sólo en desarrollo local.
    storage_public: bool = True

    # ── HU_39 — Encriptación de campos sensibles (Fernet / AES-128-CBC + HMAC) ──
    # Clave Fernet (32 bytes) codificada en base64 url-safe (44 chars). Se aplica
    # a columnas con datos personales (teléfono, dirección, email secundario, etc.)
    # mediante ``app.core.encryption.encrypt_value`` / ``decrypt_value``.
    #
    # En DESARROLLO / TESTING: si está vacía se deriva determinísticamente de
    # ``SECRET_KEY`` vía HKDF-SHA256, así no hace falta configurar nada extra
    # para que los tests pasen. Los datos cifrados en dev NO se pueden descifrar
    # en producción (claves distintas) — eso es intencional.
    #
    # En PRODUCCIÓN: REQUERIDA y ABORTA el arranque si está vacía o es
    # placeholder (mismo fail-fast que SECRET_KEY/JWT_SECRET/WEBHOOK_SECRET).
    # Generar con: ``python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"``
    field_encryption_key: str = ""

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

    # ── HU_23 — Stripe (pasarela unificada) ────────────────────────
    # Fail-open: si `stripe_secret_key` está vacío, `get_provider("stripe")`
    # sigue funcionando pero `create_payment_intent` / `confirm_payment` /
    # `refund` caen transparentes a `MockProvider` (mensaje warning en logs).
    # El webhook handler NO es fail-open: si falta `stripe_webhook_secret`,
    # devuelve 503 explícito para no aceptar eventos sin verificar firma.
    stripe_secret_key: str | None = None
    stripe_webhook_secret: str | None = None
    stripe_publishable_key: str | None = None

    # ── HU_16 — WhatsApp Business (pedidos multi-canal) ───────────────
    # App secret del webhook de WhatsApp Cloud API. Si está vacío, el endpoint
    # `POST /api/v1/webhooks/whatsapp` devuelve 503 explícito (fail-closed,
    # igual que Stripe): aceptar 200 sin verificar firma sería fail-open.
    whatsapp_business_token: str | None = None
    # HU_16 — Secret alternativo para webhook Twilio-compatible (form-encoded,
    # X-Twilio-Signature HMAC-SHA1). Si está vacío + APP_ENV=production → 503.
    # Lección CVSS 9.1: NUNCA fail-open en producción. Si ambos están
    # configurados, este gana para el path Twilio y ``whatsapp_business_token``
    # sigue aplicando para el path WhatsApp Cloud API (JSON body).
    whatsapp_webhook_secret: str | None = None

    # Webhooks
    webhook_secret: str = "change-me-webhook-secret-min-32-chars-ok"
    webhook_max_retries: int = 5
    webhook_timeout_seconds: int = 10

    # Rate limit
    rate_limit_enabled: bool = True
    rate_limit_auth_per_min: int = 20
    rate_limit_orders_per_min: int = 60
    rate_limit_default_per_min: int = 200

    # ── HU_41: Redis-backed rate limit (sliding window) ────────────
    # ``redis_url`` re-usa la variable de entorno ``REDIS_URL`` que
    # ya existe en .env.example para Celery. Si está vacía o el
    # cliente Redis no responde, ``app.services.redis_client`` cae
    # transparente a in-memory. NO es necesario tocar nada de lo
    # existente para activar HU_41: basta con setear ``REDIS_URL``
    # en producción.
    #
    # ``redis_enabled`` es un kill-switch explícito: si se setea
    # ``REDIS_ENABLED=false``, ``get_redis()`` devuelve ``None``
    # sin intentar conectar. Útil para tests y para apagar el rate
    # limit distribuido en caso de incidente operativo.
    redis_url: str | None = None
    redis_enabled: bool = True

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
    def storage_dir(self) -> str:
        """Directorio raíz de archivos subidos (alias de `storage_path`)."""
        return self.storage_path

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    # ── FIX 2026-09-27: fail-fast de secretos en producción ──────────
    # Antes no existía ninguna defensa: si `JWT_SECRET` no llegaba al
    # contenedor, la app firmaba tokens con una clave pública del repo y
    # aceptaba `is_superuser: true` forjado → escalada a SUPERADMIN.
    # Ahora la app NO ARRANCA con secretos por defecto en producción.
    @model_validator(mode="after")
    def _reject_placeholder_secrets_in_production(self) -> "Settings":
        if self.app_env != "production":
            return self

        offenders: list[str] = []

        def _is_placeholder(name: str, value: str, *, required: bool = True) -> None:
            v = (value or "").strip()
            if not v:
                if required:
                    offenders.append(f"{name} (vacío)")
                return
            low = v.lower()
            if low.startswith("change-me") or "change-me" in low or low.startswith("tu-") or low == "changeme":
                offenders.append(name)

        _is_placeholder("SECRET_KEY", self.secret_key)
        _is_placeholder("JWT_SECRET", self.jwt_secret)
        _is_placeholder("WEBHOOK_SECRET", self.webhook_secret)
        # HU_39 — helper Fernet disponible (encrypt_value/decrypt_value) pero
        # el cifrado NO se aplica a ninguna columna todavía (scope MÍNIMO de
        # esta HU). Por eso NO exigimos FIELD_ENCRYPTION_KEY en producción:
        # si lo exigiéramos con código sin usar, abortaríamos el arranque de
        # instancias que no necesitan encryption. Se exigirá cuando algún
        # modelo use el helper como columna PII cifrada.
        # Ver `app/core/encryption.py::decrypt_value` para cuando esté wired.

        # En producción el modo debug tampoco es aceptable.
        if offenders:
            raise ValueError(
                "ABORTANDO ARRANQUE: secretos placeholder detectados en producción "
                f"({', '.join(offenders)}). Configúralos como variables de entorno "
                "reales antes de desplegar. Si es un entorno de pruebas, usá "
                "APP_ENV=staging o APP_ENV=development."
            )
        if self.debug:
            raise ValueError(
                "ABORTANDO ARRANQUE: DEBUG=True no es permitido en producción. "
                "Seteá DEBUG=false."
            )
        # `/storage` público expone los archivos de todos los tenants.
        if self.storage_public:
            raise ValueError(
                "ABORTANDO ARRANQUE: STORAGE_PUBLIC=true no es permitido en "
                "producción (expondría los archivos de todos los tenants sin "
                "autenticación). Seteá STORAGE_PUBLIC=false; el endpoint "
                "autenticado /tenants/{tid}/uploads/{id}/content los sirve."
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
