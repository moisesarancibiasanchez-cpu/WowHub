"""HU_12 — Servicio de variantes y modificadores.

Encapsula:
  - CRUD de ProductVariant (multi-tenant)
  - CRUD de Modifier + ModifierOption (multi-tenant)
  - Validaciones: producto del tenant, SKU único, etc.

Nota: las queries son SIEMPRE filtradas por tenant_id. Las excepciones
son NotFoundError (modelo no encontrado o de otro tenant) — coherente
con el patrón del resto del proyecto.
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, ValidationError, ConflictError
from app.models.product import Product
from app.models.product_variant import (
    Modifier, ModifierOption, ModifierType, ProductVariant,
)
from app.schemas.product import (
    ModifierIn, ModifierOptionIn, ModifierOptionUpdate, ModifierUpdate,
    ProductVariantIn, ProductVariantUpdate,
)


class ProductVariantService:
    def __init__(self, db: Session, tenant_id: str):
        self.db = db
        self.tenant_id = tenant_id

    # ── helpers ────────────────────────────────────────────
    def _get_product(self, product_id: UUID) -> Product:
        p = self.db.get(Product, product_id)
        if not p or str(p.tenant_id) != str(self.tenant_id):
            raise NotFoundError("Producto")
        return p

    def _get_variant(self, variant_id: UUID) -> ProductVariant:
        v = self.db.get(ProductVariant, variant_id)
        if not v or str(v.tenant_id) != str(self.tenant_id):
            raise NotFoundError("Variante")
        return v

    def _get_modifier(self, modifier_id: UUID) -> Modifier:
        m = self.db.get(Modifier, modifier_id)
        if not m or str(m.tenant_id) != str(self.tenant_id):
            raise NotFoundError("Modifier")
        return m

    # ── Variants ───────────────────────────────────────────
    def list_variants(self, product_id: UUID) -> list[ProductVariant]:
        self._get_product(product_id)  # 404 si no existe
        return list(self.db.execute(
            select(ProductVariant)
            .where(
                ProductVariant.tenant_id == self.tenant_id,
                ProductVariant.product_id == str(product_id),
            )
            .order_by(ProductVariant.sort_order, ProductVariant.created_at)
        ).scalars())

    def create_variant(
        self, product_id: UUID, payload: ProductVariantIn,
    ) -> ProductVariant:
        self._get_product(product_id)
        # SKU único por tenant
        existing = self.db.execute(
            select(ProductVariant).where(
                ProductVariant.tenant_id == self.tenant_id,
                ProductVariant.sku == payload.sku,
            )
        ).scalar_one_or_none()
        if existing:
            raise ConflictError(f"Ya existe una variante con SKU {payload.sku} en este tenant")
        v = ProductVariant(
            tenant_id=self.tenant_id,
            product_id=str(product_id),
            sku=payload.sku,
            name=payload.name,
            price_cents=payload.price_cents,
            cost_cents=payload.cost_cents,
            stock=payload.stock,
            track_inventory=payload.track_inventory,
            image_url=payload.image_url,
            sort_order=payload.sort_order,
            is_active=payload.is_active,
            attributes=payload.attributes or {},
        )
        self.db.add(v)
        self.db.commit()
        self.db.refresh(v)
        return v

    def update_variant(
        self, variant_id: UUID, payload: ProductVariantUpdate,
    ) -> ProductVariant:
        v = self._get_variant(variant_id)
        data = payload.model_dump(exclude_unset=True)
        if "sku" in data and data["sku"] != v.sku:
            dup = self.db.execute(
                select(ProductVariant).where(
                    ProductVariant.tenant_id == self.tenant_id,
                    ProductVariant.sku == data["sku"],
                    ProductVariant.id != str(variant_id),
                )
            ).scalar_one_or_none()
            if dup:
                raise ConflictError(f"Ya existe una variante con SKU {data['sku']} en este tenant")
        for k, val in data.items():
            setattr(v, k, val)
        self.db.commit()
        self.db.refresh(v)
        return v

    def delete_variant(self, variant_id: UUID) -> bool:
        v = self._get_variant(variant_id)
        # Soft delete: NO borramos físicamente (puede estar referenciado
        # por order_items históricos). Sólo lo desactivamos.
        v.is_active = False
        self.db.commit()
        return True

    # ── Modifiers ──────────────────────────────────────────
    def list_modifiers(self, product_id: UUID) -> list[Modifier]:
        self._get_product(product_id)
        return list(self.db.execute(
            select(Modifier)
            .where(
                Modifier.tenant_id == self.tenant_id,
                Modifier.product_id == str(product_id),
            )
            .order_by(Modifier.sort_order, Modifier.created_at)
        ).scalars())

    def create_modifier(
        self, product_id: UUID, payload: ModifierIn,
    ) -> Modifier:
        self._get_product(product_id)
        if payload.type not in (ModifierType.SINGLE.value, ModifierType.MULTI.value):
            raise ValidationError("type debe ser 'single' o 'multi'")
        m = Modifier(
            tenant_id=self.tenant_id,
            product_id=str(product_id),
            name=payload.name,
            type=payload.type,
            required=payload.required,
            sort_order=payload.sort_order,
            is_active=payload.is_active,
            description=payload.description,
        )
        # Creamos las opciones en cascada
        for opt in (payload.options or []):
            m.options.append(ModifierOption(
                name=opt.name,
                price_delta_cents=opt.price_delta_cents,
                is_default=opt.is_default,
                sort_order=opt.sort_order,
                is_active=opt.is_active,
            ))
        self.db.add(m)
        try:
            self.db.commit()
        except Exception as e:
            self.db.rollback()
            raise ConflictError(f"No se pudo crear el modifier: {e}")
        self.db.refresh(m)
        return m

    def update_modifier(
        self, modifier_id: UUID, payload: ModifierUpdate,
    ) -> Modifier:
        m = self._get_modifier(modifier_id)
        data = payload.model_dump(exclude_unset=True)
        for k, val in data.items():
            setattr(m, k, val)
        self.db.commit()
        self.db.refresh(m)
        return m

    def delete_modifier(self, modifier_id: UUID) -> bool:
        m = self._get_modifier(modifier_id)
        self.db.delete(m)
        self.db.commit()
        return True

    # ── Modifier Options ───────────────────────────────────
    def add_option(
        self, modifier_id: UUID, payload: ModifierOptionIn,
    ) -> ModifierOption:
        m = self._get_modifier(modifier_id)
        opt = ModifierOption(
            modifier_id=str(m.id),
            name=payload.name,
            price_delta_cents=payload.price_delta_cents,
            is_default=payload.is_default,
            sort_order=payload.sort_order,
            is_active=payload.is_active,
        )
        self.db.add(opt)
        self.db.commit()
        self.db.refresh(opt)
        return opt

    def update_option(
        self, option_id: UUID, payload: ModifierOptionUpdate,
    ) -> ModifierOption:
        opt = self.db.get(ModifierOption, option_id)
        if not opt:
            raise NotFoundError("Opción de modifier")
        # pertenencia transitiva al tenant via modifier
        self._get_modifier(opt.modifier_id)
        for k, val in payload.model_dump(exclude_unset=True).items():
            setattr(opt, k, val)
        self.db.commit()
        self.db.refresh(opt)
        return opt

    def delete_option(self, option_id: UUID) -> bool:
        opt = self.db.get(ModifierOption, option_id)
        if not opt:
            raise NotFoundError("Opción de modifier")
        self._get_modifier(opt.modifier_id)
        self.db.delete(opt)
        self.db.commit()
        return True
