"""HU_34 — API REST para el layout personalizable del dashboard (GridStack).

Endpoints:
- GET  /api/v1/dashboard/layout — devuelve el layout del tenant.
- PUT  /api/v1/dashboard/layout — guarda (upsert) el layout del tenant.

Ambos requieren ``get_tenant_for_membership`` (multi-tenant).

Default layout
--------------
Si el tenant no tiene layout guardado, ``GET`` devuelve un default de 4
widgets (12 columnas GridStack):

- ``stats``    (x=0, y=0, w=4, h=2)
- ``orders``   (x=4, y=0, w=4, h=4)
- ``products`` (x=0, y=2, w=4, h=4)
- ``ai``       (x=8, y=0, w=4, h=2)

El layout default NO se persiste en la tabla — se devuelve en línea
para que el frontend pueda decidir cuándo guardar (típicamente después
del primer drag&drop).
"""
from __future__ import annotations

import logging
from typing import Any, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_tenant_for_membership
from app.models.dashboard import DashboardLayout
from app.models.tenant import Tenant

logger = logging.getLogger("wowhub.dashboard.api")

router = APIRouter(prefix="/dashboard", tags=["dashboard-layout"])


# ── Schemas ────────────────────────────────────────────────────────────
class Widget(BaseModel):
    """Un widget del GridStack (id + posición + tamaño + tipo)."""
    id: str = Field(..., min_length=1, max_length=60, description="Identificador único del widget (e.g. 'stats', 'orders').")
    x: int = Field(..., ge=0, le=11, description="Columna (0-11, GridStack usa 12 columnas).")
    y: int = Field(..., ge=0, description="Fila.")
    w: int = Field(..., ge=1, le=12, description="Ancho en columnas (1-12).")
    h: int = Field(..., ge=1, le=24, description="Alto en filas.")
    type: str = Field(..., min_length=1, max_length=40, description="Tipo de widget (stats|orders|products|ai|custom).")


class LayoutIn(BaseModel):
    """Body de PUT /api/v1/dashboard/layout."""
    widgets: List[Widget] = Field(..., min_length=1, max_length=24, description="Lista de widgets (1-24).")


class LayoutOut(BaseModel):
    """Response de GET/PUT /api/v1/dashboard/layout."""
    tenant_id: str
    widgets: List[dict[str, Any]]
    updated_at: Optional[str] = None
    is_default: bool = Field(..., description="True si se devolvió el layout default (no había fila guardada).")


# ── Helpers ────────────────────────────────────────────────────────────
def _default_widgets() -> List[dict[str, Any]]:
    """Layout default de 4 widgets (12 columnas GridStack, 1 grid row).

    Geometría:
        +----+----+----+
        |stats     | ai |
        +----+----+----+
        |orders    |products|
        |          |        |
        +----+----+----+
    Concretamente:
      - stats    : (0,0,4,2) — KPIs (ventas, margen, etc.)
      - orders   : (4,0,4,4) — Pedidos en vivo (alto)
      - products : (0,2,4,4) — Top productos (alto)
      - ai       : (8,0,4,2) — Resumen IA (compacto)
    """
    return [
        {"id": "stats",    "x": 0, "y": 0, "w": 4, "h": 2, "type": "stats"},
        {"id": "orders",   "x": 4, "y": 0, "w": 4, "h": 4, "type": "orders"},
        {"id": "products", "x": 0, "y": 2, "w": 4, "h": 4, "type": "products"},
        {"id": "ai",       "x": 8, "y": 0, "w": 4, "h": 2, "type": "ai"},
    ]


def _load_or_default(db: Session, tenant_id) -> tuple[List[dict[str, Any]], Optional[DashboardLayout]]:
    """Devuelve (widgets, fila_layout). Si no hay fila, widgets=default, fila=None."""
    layout = (
        db.query(DashboardLayout)
        .filter(DashboardLayout.tenant_id == str(tenant_id))
        .one_or_none()
    )
    if layout is None:
        return _default_widgets(), None
    widgets = layout.widgets
    # Defensive: si la fila existe pero la lista está vacía, devolvemos default.
    if not widgets:
        return _default_widgets(), layout
    return widgets, layout


# ── GET /api/v1/dashboard/layout ───────────────────────────────────────
@router.get("/layout", response_model=LayoutOut)
def get_layout(
    tenant: Tenant = Depends(get_tenant_for_membership),
    db: Session = Depends(get_db),
):
    """Devuelve el layout guardado del tenant.

    Si no hay layout guardado, devuelve el layout default (4 widgets) y
    ``is_default=True``. La fila NO se persiste aquí — el frontend debe
    hacer PUT explícito para guardarlo.
    """
    widgets, layout = _load_or_default(db, tenant.id)
    return LayoutOut(
        tenant_id=str(tenant.id),
        widgets=widgets,
        updated_at=layout.updated_at.isoformat() if layout and layout.updated_at else None,
        is_default=layout is None,
    )


# ── PUT /api/v1/dashboard/layout ───────────────────────────────────────
@router.put("/layout", response_model=LayoutOut)
def put_layout(
    payload: LayoutIn = Body(...),
    tenant: Tenant = Depends(get_tenant_for_membership),
    db: Session = Depends(get_db),
):
    """Guarda (upsert) el layout del tenant.

    - Si ya existe fila → actualiza ``layout_json``.
    - Si no existe → crea nueva fila con ``tenant_id``.

    La validación Pydantic asegura que cada widget tiene x/y/w/h dentro
    de los rangos GridStack razonables (12 columnas, ≤24 filas).
    """
    widgets_dict = [w.model_dump() for w in payload.widgets]
    # Verificar ids únicos dentro del layout (GridStack lo requiere).
    seen = set()
    for w in widgets_dict:
        if w["id"] in seen:
            raise HTTPException(
                status_code=422,
                detail=f"id de widget duplicado: {w['id']!r}",
            )
        seen.add(w["id"])

    layout = (
        db.query(DashboardLayout)
        .filter(DashboardLayout.tenant_id == str(tenant.id))
        .one_or_none()
    )

    if layout is None:
        layout = DashboardLayout(
            tenant_id=str(tenant.id),
            layout_json=widgets_dict,
        )
        db.add(layout)
    else:
        layout.layout_json = widgets_dict

    db.commit()
    db.refresh(layout)

    return LayoutOut(
        tenant_id=str(tenant.id),
        widgets=layout.widgets,
        updated_at=layout.updated_at.isoformat() if layout.updated_at else None,
        is_default=False,
    )