"""ReportsService — persistencia de ejecuciones del catálogo de reportes (HU_31).

Funciones exportadas:
- ``record_report_run``: persiste una ejecución de un reporte (1 fila en
  ``report_runs``). Usado por el endpoint ``GET /reports`` cada vez que
  un usuario consulta el catálogo.
- ``get_last_run_at``: devuelve el ``started_at`` de la última ejecución
  de un ``report_key`` para un tenant. Usado por el endpoint
  ``GET /reports`` para hidratar ``last_run_at``.

Decisiones de diseño:
- Funciones planas (no clase) — son helpers simples, no necesitan
  estado. Mismo estilo que ``audit_chain.py``.
- ``tenant_id`` se acepta como ``Optional[UUID]`` (puede ser ``None``
  para reportes cross-tenant de plataforma ejecutados por superadmin).
- ``started_at`` y ``finished_at`` se infieren de los args explícitos
  que pasa el caller — el endpoint ya tiene esos timestamps porque
  envuelve la ejecución.
- ``duration_ms`` se calcula aquí (``(finished_at - started_at) *
  1000``) para mantener la responsabilidad en un solo lugar.
- ``get_last_run_at`` filtra por ``tenant_id`` cuando se pasa (caso
  típico); con ``tenant_id=None`` devuelve la última ejecución
  cross-tenant de ese ``report_key`` (útil para reportes globales).
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Mapping, Optional
from uuid import UUID

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.models.report_run import ReportRun

logger = logging.getLogger("wowhub.reports")


def record_report_run(
    db: Session,
    tenant_id: Optional[UUID],
    user_id: Optional[UUID],
    report_key: str,
    params: Optional[Mapping[str, Any]],
    started_at: datetime,
    finished_at: datetime,
    status: str = "ok",
    error: Optional[str] = None,
    *,
    commit: bool = True,
) -> ReportRun:
    """Persiste una ejecución de reporte en ``report_runs``.

    Args:
        db: Sesión SQLAlchemy.
        tenant_id: Tenant dueño del reporte (``None`` para reportes de
            plataforma cross-tenant).
        user_id: Usuario que disparó la ejecución (``None`` para
            scheduler / system).
        report_key: Identificador lógico del reporte (``"sales"``,
            ``"customers"``, ``"inventory"``).
        params: Filtros / params del request. Se serializa como JSON.
            ``None`` → ``params_json=NULL``.
        started_at: Inicio de la ejecución (UTC).
        finished_at: Fin de la ejecución (UTC).
        status: ``"ok"`` (default) o ``"error"``.
        error: Mensaje de error si ``status="error"``.
        commit: Si ``True`` (default), hace ``db.commit()``. Si
            ``False``, deja la sesión sin commitear (útil en tests o
            cuando el caller ya gestiona la transacción).

    Returns:
        El ``ReportRun`` recién creado y persistido.
    """
    # Serializar params a JSON (o NULL si no hay)
    if params is None:
        params_json: Optional[str] = None
    else:
        # ``default=str`` para serializar datetimes/UUIDs sin errores.
        params_json = json.dumps(dict(params), default=str, ensure_ascii=False)

    # Calcular duration_ms desde los timestamps (precisión submicrosegundo
    # preservada — ``total_seconds()`` devuelve float).
    duration_ms_val: Optional[int] = None
    if started_at and finished_at:
        delta = finished_at - started_at
        # ``int(...)`` trunca; si el delta es < 1ms queda 0 (no negativo).
        duration_ms_val = max(int(delta.total_seconds() * 1000), 0)

    run = ReportRun(
        tenant_id=tenant_id,
        user_id=user_id,
        report_key=report_key,
        params_json=params_json,
        status=status,
        error=error,
        started_at=started_at,
        finished_at=finished_at,
        duration_ms=duration_ms_val,
    )
    db.add(run)
    if commit:
        db.commit()
        db.refresh(run)
    else:
        db.flush()
    logger.debug(
        "report_run registrado: tenant=%s user=%s report_key=%s status=%s duration_ms=%s",
        tenant_id,
        user_id,
        report_key,
        status,
        duration_ms_val,
    )
    return run


def get_last_run_at(
    db: Session,
    tenant_id: Optional[UUID],
    report_key: str,
) -> Optional[datetime]:
    """Devuelve el ``started_at`` de la última ejecución de un reporte.

    Args:
        db: Sesión SQLAlchemy.
        tenant_id: Tenant dueño del reporte. Si es ``None``, devuelve
            la última ejecución cross-tenant (reportes de plataforma).
        report_key: Identificador lógico del reporte.

    Returns:
        ``datetime`` UTC de la última ejecución, o ``None`` si nunca
        corrió. En SQLite el datetime NO trae tzinfo (sqlite default);
        en PG sí. El caller debe tratarlo como UTC.
    """
    stmt = select(ReportRun.started_at).where(ReportRun.report_key == report_key)
    if tenant_id is not None:
        stmt = stmt.where(ReportRun.tenant_id == tenant_id)
    stmt = stmt.order_by(desc(ReportRun.started_at)).limit(1)
    return db.execute(stmt).scalar_one_or_none()


def get_last_run_at_bulk(
    db: Session,
    tenant_id: Optional[UUID],
    report_keys: list[str],
) -> dict[str, Optional[datetime]]:
    """Variante bulk: devuelve ``{report_key: last_started_at}`` en una sola query.

    Más eficiente que llamar ``get_last_run_at`` en un loop cuando el
    endpoint tiene que hidratar N varios de los reportes (HU_31: 3).

    Args:
        db: Sesión SQLAlchemy.
        tenant_id: Tenant dueño de los reportes (``None`` para cross-tenant).
        report_keys: Lista de ``report_key`` a consultar.

    Returns:
        Dict ``{report_key: datetime-or-None}``. Los ``report_key``
        sin ejecuciones tienen ``None``.
    """
    if not report_keys:
        return {}
    stmt = select(
        ReportRun.report_key,
        func.max(ReportRun.started_at).label("last_started_at"),
    ).where(ReportRun.report_key.in_(report_keys))
    if tenant_id is not None:
        stmt = stmt.where(ReportRun.tenant_id == tenant_id)
    stmt = stmt.group_by(ReportRun.report_key)
    rows = db.execute(stmt).all()
    out: dict[str, Optional[datetime]] = {key: None for key in report_keys}
    for key, last in rows:
        out[key] = last
    return out