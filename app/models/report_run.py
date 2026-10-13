"""ReportRun: historial de ejecuciones de los reportes programables (HU_31 follow-up).

Cada vez que un usuario consulta el catálogo de reportes en
``GET /api/v1/tenants/{tid}/reports`` se persiste una fila en esta tabla
para hidratar ``last_run_at`` desde la BD (en vez de devolver siempre
``null``).

Decisiones de diseño:
- ``tenant_id`` es NULLABLE para soportar reportes de plataforma (futuro:
  reportes cross-tenant ejecutados por superadmin). El patrón es
  idéntico a ``AuditLog.tenant_id`` (HU_40 v1.1). Por eso heredamos de
  ``TenantMixin`` y ANULAMOS la columna para permitir NULL.
- ``user_id`` es NULLABLE para permitir ejecuciones anónimas / system
  (cuando el scheduler Celery beat corra los reportes sin usuario).
- ``report_key`` está restringido al set del HU_31 (``sales``, ``customers``,
  ``inventory``); la validación fuerte se hace en la API, no en BD
  (la columna es ``str(64)`` para dar margen a futuros report_keys).
- ``started_at`` / ``finished_at`` son ``DateTime(timezone=True)`` y se
  llenan explícitamente desde Python (``datetime.now(timezone.utc)``)
  para tener precisión de microsegundo tanto en PG como en SQLite
  (igual que ``AuditLog.created_at``).
- ``params_json`` guarda los filtros del request (``{"since": "...",
  "until": "...", "branch_id": "..."}``) como JSON serializado para
  reproducir o debuggear ejecuciones.
- ``duration_ms`` se calcula en el servicio (``record_report_run``) como
  ``(finished_at - started_at).total_seconds() * 1000``.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import GUID, BaseModel, TenantMixin


class ReportRun(BaseModel, TenantMixin):
    """Una ejecución histórica de un reporte del catálogo HU_31.

    Inheritamos de ``BaseModel`` (id UUID + timestamps) y ``TenantMixin``
    (FK a ``tenants.id`` + index). El ``tenant_id`` se redefine abajo
    para permitir ``NULL`` (igual que ``AuditLog.tenant_id``).
    """

    __tablename__ = "report_runs"
    __table_args__ = (
        # Queries típicas: "última ejecución del reporte X del tenant Y"
        # y "todas las ejecuciones en orden cronológico".
        # ``tenant_id`` y ``report_key`` ya tienen ``index=True`` en sus
        # columnas → SQLAlchemy crea los índices simples automáticamente.
        # Aquí declaramos solo los compuestos que NO están cubiertos.
        Index("ix_report_runs_tenant_key_started", "tenant_id", "report_key", "started_at"),
        Index("ix_report_runs_started_at", "started_at"),
        Index("ix_report_runs_created_at", "created_at"),
    )

    # ── HU_31 follow-up: tenant_id NULLABLE (override del TenantMixin) ───
    # Mantenemos la FK a ``tenants.id`` y el index. El superadmin list
    # query puede usar ``tenant_id IS NULL OR tenant_id = X`` para incluir
    # ejecuciones globales de reportes de plataforma (futuro). Patrón idéntico
    # a ``AuditLog.tenant_id`` en ``app/models/audit.py``.
    tenant_id: Mapped[Optional[UUID]] = mapped_column(
        GUID(),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    # ── Usuario que disparó la ejecución (NULLABLE) ───────────────────────
    # NULL para ejecuciones del scheduler / system (sin usuario humano).
    # ``ON DELETE SET NULL`` para no perder historial si el user se borra.
    user_id: Mapped[Optional[UUID]] = mapped_column(
        GUID(),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # ── Identificador lógico del reporte (catálogo HU_31) ─────────────────
    # Set válido hoy: ``"sales"``, ``"customers"``, ``"inventory"``.
    # La columna acepta hasta 64 chars para futuros report_keys.
    report_key: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )

    # ── Filtros / params del request (JSON serializado) ───────────────────
    # ``None`` cuando el request no trae params (caso típico de HU_31).
    params_json: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    # ── Estado de la ejecución ────────────────────────────────────────────
    # ``"ok"`` si terminó bien; ``"error"`` si falló (ver ``error``).
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="ok",
        server_default="ok",
    )

    # ── Mensaje de error (sólo cuando status="error") ─────────────────────
    error: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    # ── Tiempos de ejecución (con TZ; precisión microsegundo desde Python) ─
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    finished_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    # ── Duración calculada en ms (NULLABLE — el cálculo se hace en el service)
    duration_ms: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )

    def __repr__(self) -> str:
        return (
            f"<ReportRun id={self.id} report_key={self.report_key!r} "
            f"status={self.status!r}>"
        )