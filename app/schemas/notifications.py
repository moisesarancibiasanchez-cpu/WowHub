"""Schemas Pydantic para la API de notificaciones (Fase 5).

El motor `NotificationsEngine` (en `app/services/notifications.py`) ya
devuelve dicts; estos schemas son el contrato público que la API
expone a la UI (Fase 6) y a integraciones externas.

Reglas de validación:
- `severity`: una de info | warning | critical
- `category`: una de pricing | inventory | orders | costs | system
- `limit`: 1..100 (cap defensivo para evitar respuestas enormes)
"""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


# ── Listas cerradas (alineadas con notifications.py) ─────────────
Severity = Literal["info", "warning", "critical"]
Category = Literal["pricing", "inventory", "orders", "costs", "system"]


# ── Una notificación individual ──────────────────────────────────
class NotificationOut(BaseModel):
    """Una notificación accionable para el dueño del tenant."""
    id: str = Field(..., description="ID estable (sha1 de rule:entity) — cacheable")
    severity: Severity
    category: Category
    title: str
    body: str
    action_label: str
    action_url: str
    entity_type: str
    entity_id: str
    detected_at: str = Field(..., description="ISO 8601 UTC")
    metric: dict[str, Any] = Field(default_factory=dict)


# ── Lista paginada (para la página /dashboard/notifications) ─────
class NotificationListOut(BaseModel):
    """Respuesta de GET /notifications."""
    count: int
    total_by_severity: dict[Severity, int]
    total_by_category: dict[Category, int]
    items: list[NotificationOut]


# ── Summary (para el bell badge del header) ──────────────────────
class NotificationSummaryOut(BaseModel):
    """Resumen compacto para el badge del header.

    - `total`: total de notificaciones activas
    - `by_severity`: {info, warning, critical} → conteo
    - `by_category`: {pricing, inventory, orders, costs, system} → conteo
    - `top_3`: las 3 más urgentes (critical primero, luego warning, info)
    """
    generated_at: str
    total: int
    by_severity: dict[Severity, int]
    by_category: dict[Category, int]
    top_3: list[NotificationOut]
