# syntax=docker/dockerfile:1.6
# ─── WowHub — Dockerfile (Render / Railway) ──────────────────
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
COPY requirements.txt ./

# 2) Instalar dependencias Python desde requirements.txt (fuente única de verdad).
#    FIX 2026-09-27: la lista estaba hardcodeada acá y NO incluía `alembic`,
#    por lo que el entrypoint ejecutaba `alembic upgrade head`, fallaba con
#    "command not found" y caía silenciosamente a `create_all()`.
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir \
        "gunicorn>=21.2.0" \
        "psycopg[binary]>=3.1.0" \
        "prometheus-fastapi-instrumentator>=7.0.0"

# 3) Copiar el código de la app
#    FIX 2026-09-27: faltaban `alembic/` y `alembic.ini`, sin los cuales el
#    control de esquema no existe dentro del contenedor.
COPY app ./app
COPY scripts ./scripts
COPY alembic ./alembic
COPY alembic.ini ./
# NOTA: NO copiar `templates` aquí — las plantillas viven en `app/templates`
# (51 archivos) y ya vienen incluidas por `COPY app ./app`. Una línea
# `COPY templates ./templates` rompe el build con
# "failed to calculate checksum ... /templates: not found".
# Los .json de i18n también viven en `app/i18n` y llegan por la misma vía.

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

# Healthcheck (Render y Railway usan healthCheckPath / healthcheckPath)
HEALTHCHECK --interval=30s --timeout=5s --retries=3 --start-period=40s \
    CMD curl -fsS http://localhost:${PORT}/health || exit 1

# Arranque
CMD ["/app/entrypoint.sh"]
