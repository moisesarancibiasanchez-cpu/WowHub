"""Schemas Pydantic v2 del Automation Manager™ (Cap. 19.3).

Orquesta las acciones que el Growth Coach (Cap. 19.2) recomienda:
- create_promotion   → crea una promo en el tenant
- create_booking     → agenda una reserva en nombre de un cliente
- send_campaign      → envía una campaña de email a un segmento

Diseño:
- `ActionType` es una `Literal` cerrada. Cualquier valor fuera de la lista
  es rechazado por FastAPI antes de llegar al handler. Esto evita la
  inyección de acciones no registradas.
- `AutomationRequest` lleva los `params` crudos. Cada handler los valida
  con un Pydantic schema específico (PromotionCreate | BookingIn |
  CampaignCreate) antes de ejecutar.
- `dry_run=true`  → resuelve todo, devuelve preview, NO toca la DB.
- `dry_run=false` + `confirmed=true` → ejecuta + escribe audit log.
- `preview_id` permite vincular un preview previo con su execute (anti-CSRF
  / anti doble-click). Es opcional para llamadas one-shot.

Reglas de oro (§20 CANONICAL):
1. NUNCA ejecuta una acción de escritura sin `confirmed=true` y
   `dry_run=false` simultáneos.
2. NUNCA acepta una `ActionType` que no esté en el ActionRegistry.
3. SIEMPRE escribe un `AutomationExecution` (audit log) al ejecutar.
4. SIEMPRE chequea `ai_daily_automation_limit` antes de aceptar /execute.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ── Tipos de acciones soportadas (MVP v1) ────────────────────────
ActionType = Literal[
    "create_promotion",
    "create_booking",
    "send_campaign",
]


# ── Estados de una ejecución (alineado con §16.4 CANONICAL) ───────
ExecutionStatus = Literal[
    "draft",                  # request recibida pero NO validada aún
    "preview_ready",          # dry_run=true completado, listo para confirmar
    "awaiting_confirmation",  # request ejecutable pero sin confirmed=true
    "executing",              # en curso
    "succeeded",              # OK
    "failed",                 # excepción no-recuperable
    "cancelled",              # usuario canceló (no implementado en MVP)
    "expired",                # preview > TTL
]


# ── Catálogo (para listar acciones disponibles al cliente) ────────
class ActionSpec(BaseModel):
    """Describe una acción registrada en el ActionRegistry.

    Sirve para que el frontend pueda renderizar:
    - Nombre legible
    - Descripción / qué hace
    - Roles requeridos (OWNER | ADMIN | STAFF | VIEWER)
    - Lista de campos esperados en `params`
    - Si requiere preview obligatorio
    """
    key: ActionType
    label: str = Field(..., description="Nombre visible para el usuario.")
    description: str = Field(..., description="Qué hace la acción en 1 línea.")
    required_role: Literal["owner", "admin", "staff", "viewer"] = "admin"
    requires_preview: bool = True
    params_schema: dict[str, Any] = Field(
        default_factory=dict,
        description="Esquema JSON de los params esperados (orientativo).",
    )
    example: dict[str, Any] = Field(
        default_factory=dict,
        description="Ejemplo de `params` válidos para esta acción.",
    )


# ── Resultado de una acción (output del handler) ─────────────────
class ActionResult(BaseModel):
    """Resultado devuelto por un handler del ActionRegistry."""
    success: bool = True
    status: ExecutionStatus = "succeeded"
    message: str = Field(..., description="Mensaje humano, listo para mostrar.")
    # ID del recurso creado (promotion_id | booking_id | campaign_id)
    resource_id: Optional[str] = None
    # Tipo de recurso creado (para que el frontend decida a dónde navegar)
    resource_type: Optional[Literal["promotion", "booking", "campaign"]] = None
    # URL del dashboard del recurso (relativa, ej. /dashboard/promotions/{id})
    resource_url: Optional[str] = None
    # Metadata adicional (counts, ids secundarios, etc)
    meta: dict[str, Any] = Field(default_factory=dict)
    # Si dry_run, esto trae un preview human-friendly
    preview: Optional[str] = None
    # Si falló, esto trae el detalle del error
    error: Optional[str] = None


# ── Request: una sola acción ─────────────────────────────────────
class AutomationRequest(BaseModel):
    """Payload de /api/v1/automation/preview y /api/v1/automation/execute.

    `params` debe cumplir con el schema de la `action_type` elegida. El
    servicio valida con el Pydantic schema específico (PromotionCreate,
    BookingIn, CampaignCreate) antes de cualquier ejecución.
    """
    action_type: ActionType
    params: dict[str, Any] = Field(
        default_factory=dict,
        description="Parámetros específicos de la acción. Validados server-side.",
    )
    # ── Confirmación (críticos) ───────────────────────────────
    dry_run: bool = Field(
        True,
        description="Si true: solo resuelve y devuelve preview. NO toca la DB.",
    )
    confirmed: bool = Field(
        False,
        description=(
            "Si true: el usuario confirma que quiere ejecutar. "
            "Requerido cuando dry_run=false. Sin esto → 400."
        ),
    )
    # ── Vínculo con preview previo (opcional pero recomendado) ─
    preview_id: Optional[str] = Field(
        None,
        description=(
            "ID del preview generado por /preview. Si viene, el execute "
            "lo valida contra un cache server-side (anti-CSRF / drift)."
        ),
    )
    # ── Contexto opcional (de Growth Coach / Marketing Studio) ─
    source: Optional[Literal["growth_coach", "marketing_studio", "chat", "manual"]] = None
    source_insight_id: Optional[str] = Field(
        None,
        description="ID de la insight que originó esta acción (audit).",
    )
    notes: Optional[str] = Field(
        None,
        max_length=500,
        description="Nota libre que el usuario puede agregar antes de ejecutar.",
    )


# ── Response: preview o execute ────────────────────────────────
class AutomationResponse(BaseModel):
    """Respuesta del endpoint /preview o /execute."""
    action_type: ActionType
    dry_run: bool
    confirmed: bool
    # ID del preview (para que /execute lo referencie)
    preview_id: Optional[str] = None
    # Resultado completo
    result: ActionResult
    # Auditoría
    execution_id: Optional[UUID] = Field(
        None,
        description="ID del AutomationExecution (solo en /execute confirmado).",
    )
    created_at: datetime


# ── Listado de ejecuciones (audit) ──────────────────────────────
class AutomationExecutionOut(BaseModel):
    """Output de GET /automation/history."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    user_id: UUID
    action_type: ActionType
    status: ExecutionStatus
    dry_run: bool
    confirmed: bool
    source: Optional[str] = None
    source_insight_id: Optional[str] = None
    notes: Optional[str] = None
    resource_id: Optional[str] = None
    resource_type: Optional[str] = None
    resource_url: Optional[str] = None
    error: Optional[str] = None
    created_at: datetime


class AutomationHistoryResponse(BaseModel):
    """Respuesta paginada de GET /automation/history."""
    items: list[AutomationExecutionOut]
    total: int
    limit: int
    offset: int
