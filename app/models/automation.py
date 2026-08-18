"""Automation Manager™ — modelos para audit log (§20 CANONICAL).

`AutomationExecution` es la única tabla nueva. NO persiste los recursos
creados (eso lo hace cada handler vía su modelo de dominio). Solo guarda
QUIÉN ejecutó QUÉ acción, CUÁNDO, y con qué resultado — para auditoría,
debugging, y para que el frontend pueda mostrar un historial.
"""
from __future__ import annotations

import enum
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    JSON,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel, GUID


class AutomationStatus(str, enum.Enum):
    """Estados posibles de una ejecución (alineado con §16.4 CANONICAL)."""
    DRAFT = "draft"
    PREVIEW_READY = "preview_ready"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    EXECUTING = "executing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class AutomationExecution(BaseModel):
    """Audit log de UNA ejecución de una acción del Automation Manager.

    - `tenant_id` + `user_id` permiten filtrar por membership / superuser.
    - `action_type` es string (no enum) para forward-compat: si agregamos
      una nueva acción, no necesitamos migración.
    - `params` se guarda como JSON para reproducir / debuggear.
    - `status` es enum para reportes / filtros.
    - `resource_id` + `resource_type` permiten linkear al recurso creado.
    """
    __tablename__ = "automation_executions"
    __table_args__ = (
        Index("ix_auto_exec_tenant_created", "tenant_id", "created_at"),
        Index("ix_auto_exec_user_created", "user_id", "created_at"),
        Index("ix_auto_exec_action", "action_type"),
    )

    tenant_id: Mapped[UUID] = mapped_column(
        GUID(),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[UUID] = mapped_column(
        GUID(),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    action_type: Mapped[str] = mapped_column(
        String(60),
        nullable=False,
        index=True,
    )
    status: Mapped[AutomationStatus] = mapped_column(
        Enum(AutomationStatus, name="automation_status"),
        default=AutomationStatus.SUCCEEDED,
        nullable=False,
        index=True,
    )
    # Flags
    dry_run: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    confirmed: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    # Origen (Growth Coach insight, Marketing Studio, chat, manual)
    source: Mapped[Optional[str]] = mapped_column(
        String(40),
        nullable=True,
    )
    source_insight_id: Mapped[Optional[str]] = mapped_column(
        String(60),
        nullable=True,
        index=True,
    )
    # Notas del usuario
    notes: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    # Recurso creado
    resource_id: Mapped[Optional[str]] = mapped_column(
        String(60),
        nullable=True,
    )
    resource_type: Mapped[Optional[str]] = mapped_column(
        String(40),
        nullable=True,
    )
    resource_url: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    # Error si falló
    error: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    # Params originales (JSON, para debug / re-run)
    params: Mapped[dict] = mapped_column(
        JSON,
        default=dict,
        nullable=False,
    )
    # Meta del resultado (counts, etc)
    result_meta: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
    )

    def __repr__(self) -> str:
        return (
            f"<AutomationExecution {self.action_type} "
            f"status={self.status.value} tenant={self.tenant_id}>"
        )
