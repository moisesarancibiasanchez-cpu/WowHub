"""Celery app configuration for WowHub background jobs.

HU_36: Cola de tareas asíncronas para:
  - Email campaigns
  - Generación de PDFs (cotizaciones, reportes)
  - OCR de tickets/facturas
  - Cálculo RFM de clientes

Usa Redis como broker y result backend.
En desarrollo puede ejecutarse con `celery -A app.celery_app worker`.

Modos de operación
------------------
- **Producción** (``APP_ENV=production``): broker y backend Redis reales.
- **Tests** (``APP_ENV=testing`` o ``CELERY_TASK_ALWAYS_EAGER=true``):
  ``task_always_eager=True`` + ``task_eager_propagates=True`` +
  ``task_store_eager_result=False`` y backend ``cache+memory://``
  para evitar conexiones a Redis. Permite que ``pytest`` corra sin broker.
- **Desarrollo local** (``APP_ENV=development``): mismo eager mode por
  defecto (no requiere Redis local). Para usar un worker real, exportar
  ``CELERY_TASK_ALWAYS_EAGER=false`` explícitamente.
"""
import os
import logging

from celery import Celery

logger = logging.getLogger("wowhub.celery")

# FIX HU_33 — Tests sin Redis: en modo dev/staging o cuando se setea
# CELERY_TASK_ALWAYS_EAGER=true, ejecutar tasks en línea (sin broker).
# Esto permite que ``task.delay()`` corra sincrónicamente sin Redis.
_eager_env = os.getenv("CELERY_TASK_ALWAYS_EAGER", "false").lower() == "true"
_app_env = os.getenv("APP_ENV", "production").lower()
_eager_for_env = _app_env in ("development", "dev", "test", "testing", "staging")
EAGER_MODE = _eager_env or _eager_for_env

# En eager mode: usar backend "cache+memory://" para evitar conexiones a Redis
# al persistir el AsyncResult local. El broker NO se usa en eager mode, pero
# Celery igual instancia el backend al ejecutar ``.delay()``.
_redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
_backend = "cache+memory://" if EAGER_MODE else _redis_url

celery_app = Celery(
    "wowhub",
    broker=_redis_url,
    backend=_backend,
    include=[
        "app.tasks.emails",
        "app.tasks.pdfs",
        "app.tasks.ocr",
        "app.tasks.rfm",
    ],
)

_celery_config = {
    "task_serializer": "json",
    "accept_content": ["json"],
    "result_serializer": "json",
    "timezone": "UTC",
    "enable_utc": True,
    "task_track_started": True,
    "task_time_limit": 300,          # 5 min max per job
    # HU_36 — Anti thundering-herd:
    #   prefetch=1 evita que un worker acapare N tareas en memoria y cause
    #   spikes de CPU cuando una tarea pesada bloquea el evento loop.
    #   Combinado con task_acks_late=True garantiza que la tarea solo se
    #   elimina del broker DESPUÉS de completarse (no al recibirla).
    "worker_prefetch_multiplier": 1,
    "task_acks_late": True,
    "task_reject_on_worker_lost": True,
    # HU_36 — Visibilidad de la cola:
    "broker_transport_options": {"visibility_timeout": 3600},  # 1 h
    "task_routes": {
        "app.tasks.emails.*": {"queue": "emails"},
        "app.tasks.pdfs.*":  {"queue": "pdfs"},
        "app.tasks.ocr.*":   {"queue": "ocr"},
        "app.tasks.rfm.*":   {"queue": "rfm"},
    },
}

if EAGER_MODE:
    # Eager mode: las tareas se ejecutan inline (sin broker).
    # task_eager_propagates=True hace que las excepciones se propaguen
    # al caller en lugar de quedar como AsyncResult.failed.
    # task_store_eager_result=False evita que el backend intente persistir
    # el resultado en Redis (innecesario en tests porque el EagerResult ya
    # tiene el retorno en memoria).
    _celery_config.update({
        "task_always_eager": True,
        "task_eager_propagates": True,
        "task_store_eager_result": False,
    })
    logger.warning(
        "Celery en EAGER mode (APP_ENV=%s, CELERY_TASK_ALWAYS_EAGER=%s) — "
        "tasks se ejecutan sincrónicamente, sin broker.",
        _app_env, _eager_env,
    )

celery_app.conf.update(_celery_config)

# Auto-discover tasks from installed apps (Celery standard behaviour)
celery_app.autodiscover_tasks(["app.tasks"], related_name="*", force=True)

logger.info(
    "Celery initialised — broker=%s, eager_mode=%s",
    os.getenv("REDIS_URL", "redis://localhost:6379/0"),
    EAGER_MODE,
)
