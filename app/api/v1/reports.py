# -*- coding: utf-8 -*-
"""HU_31 — Reportes PDF/Excel programables.

Endpoints:
- GET /api/v1/tenants/{tid}/reports
    Lista los reportes disponibles/programados del tenant.
    HU_31 alcance mínimo: respuesta fija (3 reportes).
    El endpoint valida la membresía del usuario contra el tenant y devuelve
    la metadata (id, type, format, last_run_at, schedule).

HU_31 follow-up (2026-10-03): persistencia de ejecuciones.
- Cada ``GET /reports`` registra 3 filas en ``report_runs`` (una por
  reporte del catálogo) con ``status="ok"`` y ``duration_ms`` calculado.
- El ``last_run_at`` de la respuesta se hidrata con ``MAX(started_at)``
  agrupado por ``report_key`` para el tenant actual — en una sola query
  (``get_last_run_at_bulk``). Antes siempre era ``null``.
- Si el usuario quiere disparar la generación real del PDF lo hace via
  ``app.tasks.pdfs.generate_report_pdf`` (HU_36) — este endpoint sólo
  registra la "consulta al catálogo" como una ejecución de referencia
  para alimentar el historial.

Notas de diseño:
- HU_31 NO introduce un catálogo persistente: los 3 reportes se siguen
  describiendo en código (``_REPORTS_CATALOG``). Lo que se persiste es
  el HISTORIAL de ejecuciones (``report_runs``).
- Una evolución自然会 crear ``reports`` catalog (modelo) + Celery beat
  para scheduling real (HU_36 / V134.3).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user_optional, get_tenant_for_membership
from app.models.tenant import Tenant
from app.models.user import User
from app.services.reports_service import (
    get_last_run_at_bulk,
    record_report_run,
)


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
                "last_run_at": "2026-10-03T12:00:00+00:00",
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
    request: Request,
    tenant: Tenant = Depends(get_tenant_for_membership),
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
) -> List[ReportOut]:
    """Devuelve el catálogo de reportes programables del tenant.

    HU_31 follow-up: cada GET persiste una fila en ``report_runs`` por
    cada reporte del catálogo (``status="ok"``, ``duration_ms`` calculado).
    El ``last_run_at`` de la respuesta se hidrata con
    ``MAX(started_at)`` agrupado por ``report_key`` para el tenant
    actual en una sola query (evita N+1).

    La membresía del usuario se valida contra el tenant vía
    ``get_tenant_for_membership`` (401 si no hay Authorization, 403 si
    el usuario no pertenece al tenant).
    """
    tenant_uuid: Optional[UUID] = (
        tenant.id if isinstance(tenant.id, UUID) else UUID(str(tenant.id))
    )
    user_uuid: Optional[UUID] = None
    if current_user is not None:
        uid = current_user.id
        user_uuid = uid if isinstance(uid, UUID) else UUID(str(uid))

    # ── 1) Persistir 3 runs (uno por reporte del catálogo) ────────────
    now_start = datetime.now(timezone.utc)
    # ``now_end`` es el mismo timestamp para mantener ``duration_ms``
    # consistente (la "ejecución" es atómica — sólo estamos marcando que
    # el catálogo fue consultado). El cálculo de duración real se hace
    # cuando el reporte PDF se genere de verdad (HU_36).
    now_end = datetime.now(timezone.utc)
    for item in _REPORTS_CATALOG:
        try:
            record_report_run(
                db=db,
                tenant_id=tenant_uuid,
                user_id=user_uuid,
                report_key=item["type"],
                params=None,  # HU_31: el endpoint no acepta params (alcance mínimo)
                started_at=now_start,
                finished_at=now_end,
                status="ok",
                error=None,
                commit=False,  # commit bulk al final para no hacer 3 round-trips
            )
        except Exception as exc:  # noqa: BLE001
            # Loguear pero no romper el endpoint: si la persistencia falla,
            # igual devolvemos el catálogo (degradación graciosa). El
            # ``last_run_at`` quedará desactualizado, pero el endpoint sigue
            # cumpliendo su contrato principal (devolver el catálogo).
            import logging
            logging.getLogger("wowhub.reports").warning(
                "report_run registro falló (tenant=%s, report_key=%s): %s",
                tenant_uuid,
                item["type"],
                exc,
            )
            db.rollback()
            continue
    db.commit()

    # ── 2) Hidratar last_run_at en una sola query (bulk) ───────────────
    report_keys = [item["type"] for item in _REPORTS_CATALOG]
    last_runs = get_last_run_at_bulk(db, tenant_uuid, report_keys)

    # ── 3) Construir la respuesta con last_run_at real ────────────────
    return [
        ReportOut(
            id=item["id"],
            type=item["type"],
            format=item["format"],
            last_run_at=last_runs.get(item["type"]),
            schedule=item["schedule"],
        )
        for item in _REPORTS_CATALOG
    ]