"""
Compat layer para endpoints legacy que la UI llama pero el router no expone.

CASO CONCRETO:
  La UI hace `GET /api/v1/me/memberships` esperando una lista de membresías
  del usuario. Esa ruta NO existe en el router actual — la API tiene
  `GET /api/v1/tenants/me` (devuelve UN tenant con `.id`, NO una lista).

  Sin esta compat, TODA página que arranca llamando a `/me/memberships`
  queda pegada en "Cargando..." porque la promesa rechaza y el placeholder
  nunca se reemplaza.

  Esta capa agrega un endpoint compat que devuelve un array de UN elemento
  con la forma `{tenant_id, role, tenant: {...}}` que el JS espera.

USO:
  En `main.py`:
      from app.api_compat import compat_router
      app.include_router(compat_router)

  O ejecutar el servidor con `uvicorn app.main_compat:app` que ya hace el wiring.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models.tenant import Tenant, TenantMembership
from app.models.user import User

compat_router = APIRouter(prefix="/api/v1", tags=["compat"])


@compat_router.get("/me/memberships")
def get_my_memberships(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Lista de tenants a los que el usuario pertenece (compat legacy).

    Devuelve un array de `{tenant_id, role, tenant_slug, tenant_name}`
    ordenado por `created_at` ASC. La UI toma el primero como tenant activo.
    """
    rows = (
        db.query(TenantMembership, Tenant)
        .join(Tenant, Tenant.id == TenantMembership.tenant_id)
        .filter(TenantMembership.user_id == user.id)
        .order_by(TenantMembership.created_at.asc())
        .all()
    )
    out = []
    for m, t in rows:
        out.append(
            {
                "tenant_id": str(m.tenant_id),
                "role": m.role,
                "tenant_slug": t.slug,
                "tenant_name": t.display_name or t.legal_name,
                "is_active": True,
            }
        )
    return out
