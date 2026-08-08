# syntax=docker/dockerfile:1.6
# ─── WowHub — Dockerfile para Render ──────────────────────
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PORT=8000

# Dependencias del sistema (para bcrypt, pillow, qrcode, postgres client)
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 1) Metadata primero (aprovecha cache de Docker layer)
COPY pyproject.toml ./

# 2) Instalar dependencias Python
RUN pip install --upgrade pip && \
    pip install --no-cache-dir \
        "fastapi>=0.110.0" \
        "uvicorn[standard]>=0.27.0" \
        "sqlalchemy>=2.0.27" \
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
        "psycopg2-binary>=2.9.0" \
        "gunicorn>=21.2.0"
        
# 3) Copiar el código de la app
COPY app ./app
COPY scripts ./scripts

# 4) Copiar y dar permisos al entrypoint (AÚN como root)
COPY scripts/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh && \
    mkdir -p /app/data /app/storage && \
    chown -R root:root /app

# 5) AHORA cambiar a usuario no-root
RUN useradd --create-home --shell /bin/bash wowhub && \
    chown -R wowhub:wowhub /app/data /app/storage
USER wowhub

EXPOSE 8000

# Healthcheck (Render también usa healthCheckPath del yaml)
HEALTHCHECK --interval=30s --timeout=5s --retries=3 --start-period=20s \
    CMD curl -fsS http://localhost:${PORT}/health || exit 1

# Arranque
CMD ["/app/entrypoint.sh"]
