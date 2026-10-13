"""HU_38 — API REST para gestión de RBAC (superadmin only).

5 endpoints:

  GET    /api/v1/rbac/policies       — lista policies (filtro opcional ?dom=)
  POST   /api/v1/rbac/policies       — agrega una policy (idempotente)
  DELETE /api/v1/rbac/policies/{id}  — borra por id
  POST   /api/v1/rbac/check          — debug: enforce(sub, dom, obj, act)
  POST   /api/v1/rbac/seed?reset=true — (re-)inserta defaults

Todos requieren ``require_superuser``. El bypass de Casbin para
``is_superuser`` ya está en el decorator ``@requires_permission``, pero
acá usamos el guard directo (más rápido, no necesita BD hit extra).
"""
from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.errors import ForbiddenError, ValidationError
from app.core.security import _get_rbac_enforcer  # type: ignore[attr-defined]
from app.database import SessionLocal, get_db
from app.deps import require_superuser
from app.models.user import User
from app.core.rbac_seed import rebuild_default_policies

logger = logging.getLogger("wowhub.rbac.api")

router = APIRouter(prefix="/rbac", tags=["rbac"])


# ── Schemas ────────────────────────────────────────────────────────────
class PolicyIn(BaseModel):
    """Schema para POST /rbac/policies."""
    sub: str = Field(..., min_length=1, max_length=120, description="e.g. role:CASHIER")
    dom: str = Field(..., min_length=1, max_length=120, description="tenant-uuid o '*'")
    obj: str = Field(..., min_length=1, max_length=120, description="e.g. product, order")
    act: str = Field(..., min_length=1, max_length=60, description="read|write|delete|*")
    note: Optional[str] = Field(default="", max_length=255)


class PolicyOut(BaseModel):
    id: str
    sub: str
    dom: str
    obj: str
    act: str
    effect: str
    priority: int
    note: str


class CheckIn(BaseModel):
    """Schema para POST /rbac/check (debug)."""
    subject: str = Field(..., min_length=1, description="e.g. role:STAFF")
    domain: str = Field(..., min_length=1, description="tenant-uuid o '*'")
    obj: str = Field(..., min_length=1, description="product, order, etc.")
    act: str = Field(..., min_length=1, description="read|write|delete")


class CheckOut(BaseModel):
    allowed: bool
    source: str  # 'casbin' | 'legacy' | 'error'


class SeedOut(BaseModel):
    inserted: int
    reset: bool


# ── Endpoints ──────────────────────────────────────────────────────────
@router.get("/policies", response_model=List[PolicyOut])
def list_policies(
    dom: Optional[str] = Query(default=None, max_length=120),
    db: Session = Depends(get_db),
    _admin: User = Depends(require_superuser),
):
    """Lista todas las policies (filtro opcional por domain)."""
    from app.core.rbac_adapter import SQLAlchemyAdapter
    adapter = SQLAlchemyAdapter(lambda: SessionLocal())
    return adapter.list_policies(dom=dom)


@router.post("/policies", response_model=PolicyOut, status_code=201)
def add_policy(
    payload: PolicyIn,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_superuser),
):
    """Agrega una policy (idempotente vía UNIQUE index).

    Si ya existe, devuelve la existente con su id.
    """
    from app.core.rbac_adapter import SQLAlchemyAdapter
    from app.models.rbac import RBACPolicy

    adapter = SQLAlchemyAdapter(lambda: SessionLocal())

    # Validar formato del subject (debe empezar con 'role:' por convención).
    if not payload.sub.startswith("role:"):
        raise ValidationError(
            "subject debe empezar con 'role:' (e.g. role:CASHIER)"
        )

    # Buscar existente primero (idempotencia a nivel API).
    existing = (
        db.query(RBACPolicy)
        .filter(
            RBACPolicy.sub == payload.sub,
            RBACPolicy.dom == payload.dom,
            RBACPolicy.obj == payload.obj,
            RBACPolicy.act == payload.act,
        )
        .one_or_none()
    )
    if existing:
        return PolicyOut(
            id=str(existing.id),
            sub=existing.sub,
            dom=existing.dom,
            obj=existing.obj,
            act=existing.act,
            effect=existing.effect,
            priority=existing.priority,
            note=existing.note,
        )

    adapter.add_policy(
        "p",
        "p",
        [payload.sub, payload.dom, payload.obj, payload.act],
    )

    # Releer para devolver el id generado.
    db.expire_all()
    new = (
        db.query(RBACPolicy)
        .filter(
            RBACPolicy.sub == payload.sub,
            RBACPolicy.dom == payload.dom,
            RBACPolicy.obj == payload.obj,
            RBACPolicy.act == payload.act,
        )
        .one_or_none()
    )
    if not new:
        # No debería pasar — el UNIQUE index garantiza unicidad.
        raise HTTPException(
            status_code=500,
            detail="Policy creada pero no encontrada al releer",
        )

    # Invalidar cache de Casbin (la próxima enforce() re-load).
    from app.core import security
    if hasattr(security, "_invalidate_rbac_enforcer"):
        security._invalidate_rbac_enforcer()

    return PolicyOut(
        id=str(new.id),
        sub=new.sub,
        dom=new.dom,
        obj=new.obj,
        act=new.act,
        effect=new.effect,
        priority=new.priority,
        note=new.note,
    )


@router.delete("/policies/{policy_id}", status_code=200)
def delete_policy(
    policy_id: str,
    _admin: User = Depends(require_superuser),
):
    """Borra una policy por UUID."""
    from app.core.rbac_adapter import SQLAlchemyAdapter
    adapter = SQLAlchemyAdapter(lambda: SessionLocal())
    ok = adapter.delete_policy_by_id(policy_id)
    if not ok:
        raise HTTPException(
            status_code=404,
            detail=f"Policy {policy_id} no encontrada",
        )

    # Invalidar cache de Casbin.
    from app.core import security
    if hasattr(security, "_invalidate_rbac_enforcer"):
        security._invalidate_rbac_enforcer()

    return {"deleted": True, "id": policy_id}


@router.post("/check", response_model=CheckOut)
def check_permission(
    payload: CheckIn,
    _admin: User = Depends(require_superuser),
):
    """Debug: evalúa ``enforce(subject, dom, obj, act)`` y devuelve el resultado.

    NO requiere membership/role — es un endpoint de inspección.
    """
    enforcer = _get_rbac_enforcer()
    try:
        allowed = enforcer.enforce(
            payload.subject, payload.domain, payload.obj, payload.act
        )
        return CheckOut(allowed=bool(allowed), source="casbin")
    except Exception as exc:  # noqa: BLE001
        logger.warning("rbac.check: enforce falló (%s) — fallback legacy", exc)
        # Fallback legacy si Casbin no está inicializado.
        allowed = _legacy_check(payload.subject, payload.obj, payload.act)
        return CheckOut(allowed=bool(allowed), source="legacy")


@router.post("/seed", response_model=SeedOut)
def seed(
    reset: bool = Query(default=False, description="Borrar antes de re-seedear"),
    _admin: User = Depends(require_superuser),
):
    """(Re-)inicializa las policies default.

    Con ``reset=true`` borra todas las policies y re-inserta las
    defaults — útil después de un migration manual o para resetear
    cambios ad-hoc hechos vía POST /policies.
    """
    inserted = rebuild_default_policies()

    # Invalidar cache de Casbin para que la próxima enforce() re-load.
    from app.core import security
    if hasattr(security, "_invalidate_rbac_enforcer"):
        security._invalidate_rbac_enforcer()

    return SeedOut(inserted=inserted, reset=reset)


# ── Legacy fallback (idéntica a la de app/core/security.py) ─────────
def _legacy_check(subject: str, obj: str, act: str) -> bool:
    """Matriz legacy hard-coded (réplica de ``_LEGACY_ROLE_MATRIX``).

    Se usa como fallback cuando Casbin no está inicializado o falla.
    La fuente de verdad es ``app.core.security._LEGACY_ROLE_MATRIX``;
    esta función es defensiva para no romper el endpoint si la
    refactor borra esa constante en el futuro.
    """
    # Extracción robusta del role del subject.
    role = subject.replace("role:", "", 1).upper() if subject else ""

    # SUPERADMIN / OWNER → todo.
    if role in ("SUPERADMIN", "OWNER"):
        return True

    # ADMIN → casi todo menos delete sensible.
    if role == "ADMIN":
        if act == "delete" and obj in ("tenant", "user", "settings"):
            return False
        return True

    # STAFF → read/write, NO delete sensible.
    if role == "STAFF":
        if act == "delete" and obj in ("product", "customer", "order", "promotion"):
            return False
        if act in ("read", "write"):
            return True
        return False

    # CASHIER → read/write operacional, no delete.
    if role == "CASHIER":
        if act == "delete":
            return False
        if act in ("read", "write") and obj in (
            "product", "order", "customer", "loyalty"
        ):
            return True
        return False

    # VIEWER → solo read.
    if role == "VIEWER":
        return act == "read"

    # Custom role unknown → deny.
    return False