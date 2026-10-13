"""HU_32 — Router SII Chile (Libro de Ventas).

Endpoints:
  POST /api/v1/tenants/{tenant_id}/sii/export-ventas
        body: {year, month}
        → retorna CSV (text/csv; charset=utf-8) con BOM utf-8-sig

  POST /api/v1/tenants/{tenant_id}/sii/validate-rut
        body: {rut}
        → {valid: bool, formatted: str, clean: str}

  GET  /api/v1/tenants/{tenant_id}/sii/libro/{year}/{month}
        → CSV descargable (attachment) con el libro del mes pedido.

Todos los endpoints requieren membresía activa en el tenant
(``Depends(get_tenant_for_membership)``) por multi-tenancy.
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_tenant_for_membership
from app.models.tenant import Tenant
from app.services.sii_exporter import export_ventas as exporter_export_ventas
from app.services.sii_validator import clean_rut, format_rut, validate_rut

router = APIRouter(prefix="/tenants/{tenant_id}", tags=["sii"])


# ── Schemas ─────────────────────────────────────────────────────────
class ExportVentasRequest(BaseModel):
    year: int = Field(..., ge=2000, le=2100, description="Año del período")
    month: int = Field(..., ge=1, le=12, description="Mes 1-12")


class ValidateRutRequest(BaseModel):
    rut: str = Field(..., min_length=1, description="RUT a validar")


class ValidateRutResponse(BaseModel):
    valid: bool
    formatted: str
    clean: str


# ── Helpers ─────────────────────────────────────────────────────────
def _validate_period(year: int, month: int) -> None:
    """Lanza 400 si el período es inválido."""
    if year < 2000 or year > 2100:
        raise HTTPException(status_code=400, detail=f"Año fuera de rango: {year}")
    if month < 1 or month > 12:
        raise HTTPException(status_code=400, detail=f"Mes inválido: {month}")


def _csv_response(csv_str: str, year: int, month: int) -> Response:
    """Empaqueta el CSV como respuesta HTTP con content-type correcto."""
    body = csv_str.encode("utf-8-sig")
    filename = f"LV_{year}_{month:02d}.csv"
    return Response(
        content=body,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-SII-Period": f"{year}-{month:02d}",
            "X-SII-Bytes": str(len(body)),
            # Evitar que el navegador cachee respuestas contables.
            "Cache-Control": "no-store",
        },
    )


# ── Endpoints ───────────────────────────────────────────────────────
@router.post(
    "/sii/export-ventas",
    summary="Exportar Libro de Ventas del período (HU_32)",
    responses={
        200: {"content": {"text/csv": {}}},
        400: {"description": "Período inválido"},
        401: {"description": "Sin autenticación"},
        403: {"description": "Sin acceso a este tenant"},
    },
)
def export_ventas(
    tenant_id: UUID,
    payload: ExportVentasRequest,
    tenant: Tenant = Depends(get_tenant_for_membership),
    db: Session = Depends(get_db),
):
    """Genera el Libro de Ventas SII del período (year, month) del tenant.

    Devuelve el CSV con BOM UTF-8 (legible directamente por Excel Chile).
    """
    _validate_period(payload.year, payload.month)
    csv_str = exporter_export_ventas(tenant_id, payload.year, payload.month, db)
    return _csv_response(csv_str, payload.year, payload.month)


@router.post(
    "/sii/validate-rut",
    response_model=ValidateRutResponse,
    summary="Validar RUT chileno (HU_32)",
)
def validate_rut_endpoint(
    tenant_id: UUID,
    payload: ValidateRutRequest,
    tenant: Tenant = Depends(get_tenant_for_membership),
):
    """Valida el dígito verificador de un RUT chileno (módulo 11).

    Devuelve el RUT formateado (``12.345.678-9``) si es válido, o el input
    original si no lo es, junto con el ``clean`` (sin puntos ni guión).
    """
    is_valid = validate_rut(payload.rut)
    cleaned = clean_rut(payload.rut)
    formatted = format_rut(payload.rut) if is_valid else cleaned
    return ValidateRutResponse(
        valid=is_valid,
        formatted=formatted,
        clean=cleaned,
    )


@router.get(
    "/sii/libro/{year}/{month}",
    summary="Descargar Libro de Ventas (HU_32)",
    responses={
        200: {"content": {"text/csv": {}}},
        400: {"description": "Período inválido"},
    },
)
def get_libro(
    tenant_id: UUID,
    year: int,
    month: int,
    tenant: Tenant = Depends(get_tenant_for_membership),
    db: Session = Depends(get_db),
):
    """Atajo GET del export — útil para descargar directo desde el navegador."""
    _validate_period(year, month)
    csv_str = exporter_export_ventas(tenant_id, year, month, db)
    return _csv_response(csv_str, year, month)
