# syntax=docker/dockerfile:1.6
# ─── WowHub — Dockerfile multi-stage ──────────────────────
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Dependencias del sistema (para bcrypt, pillow, qrcode)
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copiamos primero la metadata para aprovechar la cache de Docker
COPY pyproject.toml README.md ./

# Instalar dependencias
RUN pip install --upgrade pip && \
    pip install "fastapi>=0.110.0" \
                "uvicorn[standard]>=0.27.0" \
                "sqlalchemy>=2.0.27" \
                "alembic>=1.13.1" \
                "pydantic>=2.6.0" \
                "pydantic-settings>=2.2.0" \
                "python-multipart>=0.0.9" \
                "python-jose[cryptography]>=3.3.0" \
                "passlib[bcrypt]>=1.7.4" \
                "bcrypt==4.0.1" \
                "email-validator>=2.1.0" \
                "jinja2>=3.1.3" \
                "itsdangerous>=2.1.2" \
                "qrcode[pil]>=7.4.2" \
                "python-slugify>=8.0.1" \
                "httpx>=0.27.0" \
                "tenacity>=8.2.3" \
                "psycopg[binary]>=3.1.0"

# Copiar el código
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./
COPY scripts ./scripts

# Crear usuario no-root por seguridad
RUN useradd --create-home --shell /bin/bash wowhub && \
    chown -R wowhub:wowhub /app
USER wowhub

EXPOSE 8000

# Healthcheck
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

# Copiar entrypoint (con permisos de ejecución)
COPY --chown=wowhub:wowhub scripts/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Comando de arranque
CMD ["/app/entrypoint.sh"]
