"""Contexto de tenant — un ContextVar que la sesión/queries puede consultar
para auto-filtrar por tenant_id. Esto se setea por middleware o dependencia
una vez que el usuario se autentica y su membresía activa es conocida.

En SQLite/Postgres sin RLS, lo aplicamos manualmente en las queries (ver
services) y/o con `with_loader_criteria`. Para producción con Postgres
se puede complementar con Row-Level Security policies (ver spec sección 6).
"""
from contextvars import ContextVar
from typing import Optional
from uuid import UUID

# Tenant activo en el request actual
current_tenant_id: ContextVar[Optional[UUID]] = ContextVar(
    "current_tenant_id", default=None
)


def set_tenant(tenant_id: Optional[UUID]) -> None:
    current_tenant_id.set(tenant_id)


def get_tenant() -> Optional[UUID]:
    return current_tenant_id.get()


def clear_tenant() -> None:
    current_tenant_id.set(None)
