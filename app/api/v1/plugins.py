"""Plugin Sandbox API — endpoint de prueba (HU_45).

POST /api/v1/tenants/{tenant_id}/plugins/test
Body: {"code": "print('hello')", "test_payload": {...}, "timeout_sec": 10}
Response: {"output": ..., "error": ..., "timed_out": false}

Este endpoint NO requiere que el plugin esté publicado en el marketplace:
recibe código arbitrario y lo ejecuta en sandbox. Pensado para que el
desarrollador pruebe su plugin antes de publicarlo.

La autorización es la misma que el resto de endpoints tenant-scoped:
  - JWT válido con membresía activa en el tenant.
"""
from typing import Any, Dict, Optional
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_tenant_for_membership
from app.models.tenant import Tenant
from app.services.plugin_sandbox import run_plugin as run_plugin_sandbox

router = APIRouter(prefix="/tenants/{tenant_id}/plugins", tags=["plugins"])


class PluginTestRequest(BaseModel):
    """Body del POST /plugins/test."""

    code: str = Field(
        ...,
        min_length=1,
        max_length=100_000,
        description="Código fuente Python del plugin a ejecutar.",
    )
    test_payload: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Payload de prueba accesible dentro del plugin como `payload`.",
    )
    timeout_sec: int = Field(
        default=10,
        ge=1,
        le=30,
        description="Tiempo máximo de wall-clock en segundos (1-30).",
    )


class PluginTestResponse(BaseModel):
    """Respuesta del POST /plugins/test."""

    output: str = ""
    error: Optional[str] = None
    timed_out: bool = False
    duration_ms: int = 0


@router.post("/test", response_model=PluginTestResponse)
def test_plugin(
    payload: PluginTestRequest,
    tenant: Tenant = Depends(get_tenant_for_membership),
    db: Session = Depends(get_db),  # noqa: ARG001 - reservado para HU_40 audit
) -> PluginTestResponse:
    """Ejecuta código de plugin en sandbox (HU_45).

    No requiere que el plugin esté registrado en el marketplace. Es un
    endpoint de "playground" para que el desarrollador valide su código.
    """
    context: Dict[str, Any] = {
        "tenant_id": str(tenant.id),
        "tenant_name": tenant.name if hasattr(tenant, "name") else None,
        "plugin_slug": "test",
        "payload": payload.test_payload or {},
    }
    result = run_plugin_sandbox(
        plugin_code=payload.code,
        context=context,
        timeout_sec=payload.timeout_sec,
    )
    return PluginTestResponse(**result)