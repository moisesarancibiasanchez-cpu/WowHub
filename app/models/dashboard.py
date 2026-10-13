"""HU_34 — DashboardLayout: layout personalizable del dashboard por tenant.

Cada tenant tiene UN solo layout (relación 1:1) que define cómo se
distribuyen los widgets (stats, orders, products, ai, ...) en el
GridStack del frontend.

Diseño
------
- Hereda ``BaseModel`` (id UUID + created_at + updated_at).
- Hereda ``TenantMixin`` para la FK a ``tenants.id``.
- ``UniqueConstraint("tenant_id")`` refuerza el 1:1 — un tenant no puede
  tener dos layouts distintos. Esto cumple el spec ("unique=True") sin
  re-declarar ``tenant_id`` (lo que sí entraría en conflicto con
  ``TenantMixin`` según ``tenant_site_config.py``).
- ``layout_json`` es un ``JSON`` que almacena el array de widgets
  serializado por GridStack (id, x, y, w, h, type).

Sin seed inicial: cuando un tenant abre su dashboard por primera vez y
no hay layout guardado, el endpoint ``GET /api/v1/dashboard/layout``
devuelve un layout default de 4 widgets (ver ``api/v1/dashboard.py``).
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import JSON, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel, TenantMixin


class DashboardLayout(BaseModel, TenantMixin):
    """Layout personalizable del dashboard para un tenant (1:1).

    Attributes:
        tenant_id: FK a ``tenants.id``. Unique (constraint a nivel tabla).
        layout_json: Array de widgets serializado. Estructura:
            ``[{"id": "stats", "x": 0, "y": 0, "w": 4, "h": 2, "type": "stats"}, ...]``
        created_at / updated_at: heredados de ``BaseModel``/``TimestampMixin``.
    """

    __tablename__ = "dashboard_layouts"
    __table_args__ = (
        UniqueConstraint("tenant_id", name="uq_dashboard_layouts_tenant"),
    )

    # Array de widgets serializado. Default: lista vacía. El endpoint
    # GET /api/v1/dashboard/layout sustituye esta lista por el default
    # de 4 widgets cuando no hay fila guardada.
    layout_json: Mapped[list] = mapped_column(JSON, default=list, nullable=False)

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        n = len(self.layout_json) if isinstance(self.layout_json, list) else 0
        return f"<DashboardLayout tenant_id={self.tenant_id} widgets={n}>"

    @property
    def widgets(self) -> list[dict[str, Any]]:
        """Helper: devuelve ``layout_json`` como lista de dicts."""
        if isinstance(self.layout_json, list):
            return self.layout_json
        return []