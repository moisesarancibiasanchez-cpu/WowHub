"""Test HU_36 — Configuración anti-thundering-herd de Celery.

Valida que el worker tenga prefetch=1 (no acapara tareas) y que
ack_late=True (no pierde tareas en crash).
"""
import pytest


def test_worker_prefetch_is_one():
    """El worker debe tener prefetch=1 para evitar thundering herd."""
    from app.celery_app import celery_app
    assert celery_app.conf.worker_prefetch_multiplier == 1


def test_task_acks_late_enabled():
    """Tasks deben confirmarse DESPUÉS de completarse (no antes)."""
    from app.celery_app import celery_app
    assert celery_app.conf.task_acks_late is True


def test_task_reject_on_worker_lost():
    """Tasks perdidas por crash deben reencolarse."""
    from app.celery_app import celery_app
    assert celery_app.conf.task_reject_on_worker_lost is True


def test_task_time_limit_set():
    """Tasks tienen un límite duro de 5 min (300s)."""
    from app.celery_app import celery_app
    assert celery_app.conf.task_time_limit == 300


def test_all_queues_routed():
    """Las 4 colas (emails, pdfs, ocr, rfm) deben tener su task_route."""
    from app.celery_app import celery_app
    routes = celery_app.conf.task_routes
    assert "app.tasks.emails.*" in routes
    assert "app.tasks.pdfs.*" in routes
    assert "app.tasks.ocr.*" in routes
    assert "app.tasks.rfm.*" in routes


def test_serializer_is_json():
    """Las tareas deben serializarse en JSON (no pickle — RCE prevention)."""
    from app.celery_app import celery_app
    assert celery_app.conf.task_serializer == "json"
    assert "json" in celery_app.conf.accept_content
