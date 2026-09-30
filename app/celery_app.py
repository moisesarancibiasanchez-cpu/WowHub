"""Celery app configuration for WowHub background jobs.

HU_36: Cola de tareas asíncronas para:
  - Email campaigns
  - Generación de PDFs (cotizaciones, reportes)
  - OCR de tickets/facturas
  - Cálculo RFM de clientes

Usa Redis como broker y result backend.
En desarrollo puede ejecutarse con `celery -A app.celery_app worker`.
"""
import os
import logging

from celery import Celery

logger = logging.getLogger("wowhub.celery")

celery_app = Celery(
    "wowhub",
    broker=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
    backend=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
    include=[
        "app.tasks.emails",
        "app.tasks.pdfs",
        "app.tasks.ocr",
        "app.tasks.rfm",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=300,          # 5 min max per job
    # HU_36 — Anti thundering-herd:
    #   prefetch=1 evita que un worker acapare N tareas en memoria y cause
    #   spikes de CPU cuando una tarea pesada bloquea el evento loop.
    #   Combinado con task_acks_late=True garantiza que la tarea solo se
    #   elimina del broker DESPUÉS de completarse (no al recibirla).
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    # HU_36 — Visibilidad de la cola:
    broker_transport_options={"visibility_timeout": 3600},  # 1 h
    task_routes={
        "app.tasks.emails.*": {"queue": "emails"},
        "app.tasks.pdfs.*":  {"queue": "pdfs"},
        "app.tasks.ocr.*":   {"queue": "ocr"},
        "app.tasks.rfm.*":   {"queue": "rfm"},
    },
)

# Auto-discover tasks from installed apps (Celery standard behaviour)
celery_app.autodiscover_tasks(["app.tasks"], related_name="*", force=True)

logger.info(
    "Celery initialised — broker=%s",
    os.getenv("REDIS_URL", "redis://localhost:6379/0"),
)
