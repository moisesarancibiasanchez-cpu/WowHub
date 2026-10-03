# -*- coding: utf-8 -*-
"""HU_31 — Reportes PDF/Excel programables.

Endpoints:
- GET /api/v1/tenants/{tid}/reports
    Lista los reportes disponibles/programados del tenant.
    HU_31 alcance mínimo: respuesta fija (3 reportes) sin persistencia.
    El endpoint valida la membresía del usuario contra el tenant y devuelve
    la metadata (id, type, format, last_run_at, schedule). La generación
    real del PDF se delega a ``app.tasks.pdfs.generate_report_pdf`` (HU_36).

Notas de diseño:
- HU_31 no introduce nuevas tablas: los reportes se describen en código.
  Esto mantiene el alcance mínimo. Una evolución自然会 crear ``reports``
  catalog (modelo) + ``report_runs`` (historial) + worker de Celery beat
  para scheduling.
- ``last_run_at`` se devuelve como ``null`` porque todavía no hay un historial
  persistido. Cuando se agregue el scheduler, este campo se hidrata desde la
  tabla ``report_runs``.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_tenant_for_membership
from app.models.tenant import Tenant


# ── Router ────────────────────────────────────────────────────────────
router = APIRouter(
    prefix="/tenants/{tenant_id}/reports",
    tags=["reports"],
)


# ── Schemas ────────────────────────────────────────────────────────────
ReportType = Literal["sales", "customers", "inventory"]
ReportFormat = Literal["pdf", "csv"]
ReportSchedule = Literal["daily", "weekly", "monthly"]


class ReportOut(BaseModel):
    """Schema público de un reporte disponible para el tenant."""

    id: str = Field(..., description="Identificador estable del reporte.")
    type: ReportType = Field(..., description="Categoría del reporte.")
    format: ReportFormat = Field(..., description="Formato de salida por defecto.")
    last_run_at: Optional[datetime] = Field(
        None,
        description="Última ejecución efectiva (UTC). null si aún no corre.",
    )
    schedule: ReportSchedule = Field(
        ...,
        description="Cadencia de generación automática.",
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "id": "sales-monthly",
                "type": "sales",
                "format": "pdf",
                "last_run_at": None,
                "schedule": "monthly",
            }
        }
    }


# ── Catálogo hardcoded (alcance mínimo HU_31) ─────────────────────────
# Estos 3 reportes describen el set mínimo viable de un tenant.
# La generación real del archivo la dispara ``app.tasks.pdfs.generate_report_pdf``.
_REPORTS_CATALOG: List[dict] = [
    {
        "id": "sales-monthly",
        "type": "sales",
        "format": "pdf",
        "schedule": "monthly",
    },
    {
        "id": "customers-weekly",
        "type": "customers",
        "format": "csv",
        "schedule": "weekly",
    },
    {
        "id": "inventory-daily",
        "type": "inventory",
        "format": "pdf",
        "schedule": "daily",
    },
]


# ── Endpoint ───────────────────────────────────────────────────────────
@router.get(
    "",
    response_model=List[ReportOut],
    summary="Lista los reportes disponibles del tenant (HU_31)",
)
def list_reports(
    tenant: Tenant = Depends(get_tenant_for_membership),
    db: Session = Depends(get_db),
) -> List[ReportOut]:
    """Devuelve el catálogo de reportes programables del tenant.

    HU_31 alcance mínimo: respuesta fija (3 reportes). La membresía del
    usuario se valida contra el tenant vía ``get_tenant_for_membership``
    (401 si no hay Authorization, 403 si el usuario no pertenece al tenant).

    TODO follow-up:
      - Persistir ejecuciones en tabla ``report_runs`` para hidratar
        ``last_run_at`` desde la BD.
      - Conectar con ``app.tasks.pdfs.generate_report_pdf`` mediante
        Celery beat para ejecutar la cadencia real (daily/weekly/monthly).
    """
    # ``db`` queda en la firma para que, cuando se conecte el historial, no
    # haya que cambiar la firma del endpoint. Hoy no se usa.
    _ = db

    now = datetime.now(timezone.utc)
    return [
        ReportOut(
            id=item["id"],
            type=item["type"],
            format=item["format"],
            last_run_at=None,  # Sin historial persistido todavía (HU_31 mínimo)
            schedule=item["schedule"],
        )
        for item in _REPORTS_CATALOG
    ]