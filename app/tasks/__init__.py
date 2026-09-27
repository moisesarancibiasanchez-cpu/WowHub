"""WowHub background tasks (Celery).

Register this package in celery_app.py with:
    celery_app.include(["app.tasks.emails", "app.tasks.pdfs", "app.tasks.ocr", "app.tasks.rfm"])

Each module exposes typed Celery tasks used by the API and automation engine.
"""
from app.celery_app import celery_app  # noqa: F401  (exports the configured app)
