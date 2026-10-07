"""HU_19 — Mesero virtual: tablas (mesas físicas) con su sesión activa.

Combina la definición de mesas del FloorMap (Branch.floor_layout.tables)
con las sesiones activas (DiningSession abiertas) para entregar al
frontend una lista unificada lista para renderizar:

  GET /tenants/{tid}/tables?branch_id=...&status_filter=active|all

Respuesta por mesa:
  {
    "table_id":      "<uuid o null>",
    "label":          "Mesa 7",      # table_label humano
    "capacity":       4,
    "branch_id":      "<uuid>",
    "branch_name":    "Local Centro",
    "shape":          "round",
    "status":         "free" | "occupied" | "needs_attention" | "reserved",
    "session_id":     "<uuid o null>",
    "session_opened_at": "<iso o null>",
    "party_size":     3,
    "server_name":    "Juan Pérez",   # nombre full del User
    "items_count":    5,
    "total_cents":    12500,
  }

Estrategia de merge:
  1. Cargar Branch[].floor_layout.tables (mesas "físicas" del floor map).
  2. Cargar DiningSession activas (status == open) para el tenant.
  3. Match por (branch_id, table_label):
     - match    → mesa del floor map enriquecida con datos de la sesión
     - sin mesa → igualmente devolvemos la mesa derivada de la sesión,
                  con shape=null y capacity=0, status="occupied".
  4. status:
     - "occupied" si hay sesión abierta
     - "needs_attention" si opened_at > 90 min (límite duro configurable)
     - "free" en caso contrario
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.database import get_db
from app.deps import get_tenant_for_membership
from app.models.branch import Branch
from app.models.dining_session import DiningSession, DiningSessionStatus
from app.models.tenant import Tenant
from app.models.user import User

router = APIRouter(prefix="/tenants/{tenant_id}/tables", tags=["tables"])


# ── Helpers ────────────────────────────────────────────────
ATTENTION_THRESHOLD_MIN = 90  # > 90 min abierta ⇒ requiere atención


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _user_display_name(db: Session, user_id: Optional[str]) -> Optional[str]:
    """Lookup rápido del nombre del mesero (User.full_name)."""
    if not user_id:
        return None
    u = db.get(User, user_id)
    return u.full_name if u else None


def _branch_floor_tables(branch: Branch) -> list[dict]:
    """Extrae las mesas del floor_layout de una branch.

    El layout es un dict JSON ``{"tables": [...]}``. Cada entry trae
    campos como id, name, shape, capacity, status.
    """
    layout = getattr(branch, "floor_layout", None)
    if not layout or not isinstance(layout, dict):
        return []
    raw = layout.get("tables") or []
    return [t for t in raw if isinstance(t, dict)]


# ── Endpoint principal ─────────────────────────────────────
@router.get("")
def list_tables(
    tenant_id: UUID,
    branch_id: Optional[UUID] = Query(None, description="Filtrar por sucursal"),
    status_filter: str = Query(
        "all",
        pattern="^(active|all)$",
        description="active = sólo con sesión abierta; all = todas",
    ),
    tenant: Tenant = Depends(get_tenant_for_membership),
    db: Session = Depends(get_db),
):
    """Lista mesas del tenant con el estado actual de su sesión.

    - Mantiene aislamiento por tenant (TenantMixin + tenant_id check).
    - Si el tenant no tiene FloorMap configurado aún, igual devuelve
      mesas derivadas de las sesiones activas para no romper el flujo
      del mesero virtual.
    """
    # 1) Sucursales del tenant (filtradas por branch_id si viene)
    branches_q = select(Branch).where(Branch.tenant_id == str(tenant.id))
    if branch_id:
        branches_q = branches_q.where(Branch.id == str(branch_id))
    branches = list(db.execute(branches_q).scalars())

    if not branches and not branch_id:
        # tenant sin sucursales → lista vacía
        return []

    branch_ids = [str(b.id) for b in branches]

    # 2) Sesiones activas (open) para esas sucursales
    active_q = (
        select(DiningSession)
        .where(
            DiningSession.tenant_id == str(tenant.id),
            DiningSession.status == DiningSessionStatus.OPEN.value,
        )
        .order_by(DiningSession.opened_at.desc())
    )
    if branch_ids:
        active_q = active_q.where(DiningSession.branch_id.in_(branch_ids))
    active_sessions = list(db.execute(active_q).scalars())

    # Indexar sesiones por (branch_id, table_label) para lookup O(1)
    session_index: dict[tuple[str, str], DiningSession] = {}
    for s in active_sessions:
        key = (str(s.branch_id), s.table_label)
        session_index[key] = s

    # 3) Construir respuesta: una entry por mesa del floor map + por sesión
    out: list[dict] = []
    seen_keys: set[tuple[str, str]] = set()

    # 3a) Mesas "físicas" del floor_layout
    for branch in branches:
        for raw in _branch_floor_tables(branch):
            label = str(raw.get("name") or raw.get("label") or "").strip()
            if not label:
                continue
            key = (str(branch.id), label)
            seen_keys.add(key)
            session = session_index.get(key)
            entry = _build_entry(
                branch=branch,
                label=label,
                capacity=int(raw.get("capacity") or 0),
                shape=raw.get("shape"),
                floor_table_id=raw.get("id"),
                session=session,
                db=db,
            )
            out.append(entry)

    # 3b) Sesiones activas sin mesa en floor_layout (mesero abrió mesa ad-hoc)
    for s in active_sessions:
        key = (str(s.branch_id), s.table_label)
        if key in seen_keys:
            continue
        branch = next((b for b in branches if str(b.id) == str(s.branch_id)), None)
        if not branch:
            continue
        entry = _build_entry(
            branch=branch,
            label=s.table_label,
            capacity=0,
            shape=None,
            floor_table_id=None,
            session=s,
            db=db,
        )
        out.append(entry)

    # 4) Filtrar por status_filter
    if status_filter == "active":
        out = [t for t in out if t["session_id"]]

    # Ordenar: sucursal → status (attention/occupied primero) → label
    priority = {"needs_attention": 0, "occupied": 1, "reserved": 2, "free": 3}
    out.sort(
        key=lambda t: (
            t["branch_name"] or "",
            priority.get(t["status"], 9),
            t["label"] or "",
        )
    )

    return out


# ── Builder ─────────────────────────────────────────────────
def _build_entry(
    *,
    branch: Branch,
    label: str,
    capacity: int,
    shape: Optional[str],
    floor_table_id,
    session: Optional[DiningSession],
    db: Session,
) -> dict:
    """Arma el dict de respuesta combinando la mesa física + sesión abierta."""
    items_count = 0
    total_cents = 0
    status = "free"
    party_size = None
    server_name = None
    session_opened_at = None
    session_id = None
    needs_attention = False

    if session is not None:
        session_id = str(session.id)
        session_opened_at = session.opened_at.isoformat() if session.opened_at else None
        party_size = int(session.customer_count or 1)
        server_name = _user_display_name(db, session.server_user_id)
        items_count = len(session.items or [])
        total_cents = int(session.total_cents or 0)
        # Calcular si necesita atención (> 90 min)
        if session.opened_at:
            opened = session.opened_at
            # Si viene naive, asumimos UTC
            if opened.tzinfo is None:
                opened = opened.replace(tzinfo=timezone.utc)
            elapsed_min = (_now() - opened).total_seconds() / 60
            needs_attention = elapsed_min > ATTENTION_THRESHOLD_MIN
        status = "needs_attention" if needs_attention else "occupied"

    return {
        "table_id": str(floor_table_id) if floor_table_id else None,
        "label": label,
        "capacity": capacity,
        "branch_id": str(branch.id),
        "branch_name": branch.name,
        "shape": shape,
        "status": status,
        "session_id": session_id,
        "session_opened_at": session_opened_at,
        "party_size": party_size,
        "server_name": server_name,
        "items_count": items_count,
        "total_cents": total_cents,
    }