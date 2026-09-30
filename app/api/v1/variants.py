"""HU_12 — Router de variantes y modificadores.

Endpoints:
  POST   /tenants/{tid}/products/{pid}/variants          crear variante
  GET    /tenants/{tid}/products/{pid}/variants          listar variantes
  PATCH  /tenants/{tid}/variants/{vid}                   actualizar variante
  DELETE /tenants/{tid}/variants/{vid}                   soft delete (is_active=False)
  POST   /tenants/{tid}/products/{pid}/modifiers         crear modifier group
  GET    /tenants/{tid}/products/{pid}/modifiers         listar modifiers con opciones
  PATCH  /tenants/{tid}/modifiers/{mid}                  actualizar modifier
  DELETE /tenants/{tid}/modifiers/{mid}                  eliminar modifier
  POST   /tenants/{tid}/modifiers/{mid}/options          agregar opción
  PATCH  /tenants/{tid}/modifier-options/{oid}           actualizar opción
  DELETE /tenants/{tid}/modifier-options/{oid}           eliminar opción
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_membership, get_current_user, get_tenant_for_membership
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.product import (
    ModifierIn, ModifierOptionIn, ModifierOptionOut, ModifierOptionUpdate,
    ModifierOut, ModifierUpdate, ProductVariantIn, ProductVariantOut,
    ProductVariantUpdate,
)
from app.services.product_variant_service import ProductVariantService

router = APIRouter(prefix="/tenants/{tenant_id}", tags=["product-variants"])


def _svc(db: Session, tenant_id: UUID) -> ProductVariantService:
    return ProductVariantService(db, tenant_id=str(tenant_id))


# ── Variants ──────────────────────────────────────────────
@router.post(
    "/products/{product_id}/variants",
    response_model=ProductVariantOut,
    status_code=status.HTTP_201_CREATED,
)
def create_variant(
    tenant_id: UUID,
    product_id: UUID,
    payload: ProductVariantIn,
    user: User = Depends(get_current_user),
    membership=Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    """Crea una variante del producto (talla, color, sabor...)."""
    return _svc(db, tenant_id).create_variant(product_id, payload)


@router.get(
    "/products/{product_id}/variants",
    response_model=list[ProductVariantOut],
)
def list_variants(
    tenant_id: UUID,
    product_id: UUID,
    user: User = Depends(get_current_user),
    membership=Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    """Lista las variantes activas (y no activas) de un producto."""
    return _svc(db, tenant_id).list_variants(product_id)


@router.patch(
    "/variants/{variant_id}",
    response_model=ProductVariantOut,
)
def update_variant(
    tenant_id: UUID,
    variant_id: UUID,
    payload: ProductVariantUpdate,
    user: User = Depends(get_current_user),
    membership=Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    return _svc(db, tenant_id).update_variant(variant_id, payload)


@router.delete(
    "/variants/{variant_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_variant(
    tenant_id: UUID,
    variant_id: UUID,
    user: User = Depends(get_current_user),
    membership=Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    """Soft-delete: marca is_active=False (preserva historial de ventas)."""
    _svc(db, tenant_id).delete_variant(variant_id)
    return None


# ── Modifiers ─────────────────────────────────────────────
@router.post(
    "/products/{product_id}/modifiers",
    response_model=ModifierOut,
    status_code=status.HTTP_201_CREATED,
)
def create_modifier(
    tenant_id: UUID,
    product_id: UUID,
    payload: ModifierIn,
    user: User = Depends(get_current_user),
    membership=Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    """Crea un grupo de modificadores con sus opciones."""
    return _svc(db, tenant_id).create_modifier(product_id, payload)


@router.get(
    "/products/{product_id}/modifiers",
    response_model=list[ModifierOut],
)
def list_modifiers(
    tenant_id: UUID,
    product_id: UUID,
    user: User = Depends(get_current_user),
    membership=Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    """Lista los grupos de modificadores (con sus opciones anidadas)."""
    return _svc(db, tenant_id).list_modifiers(product_id)


@router.patch(
    "/modifiers/{modifier_id}",
    response_model=ModifierOut,
)
def update_modifier(
    tenant_id: UUID,
    modifier_id: UUID,
    payload: ModifierUpdate,
    user: User = Depends(get_current_user),
    membership=Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    return _svc(db, tenant_id).update_modifier(modifier_id, payload)


@router.delete(
    "/modifiers/{modifier_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_modifier(
    tenant_id: UUID,
    modifier_id: UUID,
    user: User = Depends(get_current_user),
    membership=Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    _svc(db, tenant_id).delete_modifier(modifier_id)
    return None


# ── Modifier Options ──────────────────────────────────────
@router.post(
    "/modifiers/{modifier_id}/options",
    response_model=ModifierOptionOut,
    status_code=status.HTTP_201_CREATED,
)
def add_modifier_option(
    tenant_id: UUID,
    modifier_id: UUID,
    payload: ModifierOptionIn,
    user: User = Depends(get_current_user),
    membership=Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    return _svc(db, tenant_id).add_option(modifier_id, payload)


@router.patch(
    "/modifier-options/{option_id}",
    response_model=ModifierOptionOut,
)
def update_modifier_option(
    tenant_id: UUID,
    option_id: UUID,
    payload: ModifierOptionUpdate,
    user: User = Depends(get_current_user),
    membership=Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    return _svc(db, tenant_id).update_option(option_id, payload)


@router.delete(
    "/modifier-options/{option_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_modifier_option(
    tenant_id: UUID,
    option_id: UUID,
    user: User = Depends(get_current_user),
    membership=Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    _svc(db, tenant_id).delete_option(option_id)
    return None
