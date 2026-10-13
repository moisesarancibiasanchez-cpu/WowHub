"""Insumos endpoints (V8 P0.1).

CRUD de Insumo (materia prima) + Receta (BOM). Permite llevar el
inventario de "lo que entra" (harina, azúcar, tela, etc) por separado
del stock-por-sucursal de productos terminados.

Endpoints:
  GET    /tenants/{tid}/insumos
  POST   /tenants/{tid}/insumos
  GET    /tenants/{tid}/insumos/stats
  GET    /tenants/{tid}/insumos/{id}
  PATCH  /tenants/{tid}/insumos/{id}
  DELETE /tenants/{tid}/insumos/{id}
  POST   /tenants/{tid}/recetas
  GET    /tenants/{tid}/recetas?product_id=...
  PATCH  /tenants/{tid}/recetas/{id}
  DELETE /tenants/{tid}/recetas/{id}
  GET    /tenants/{tid}/products/{product_id}/cost-breakdown
"""
from uuid import UUID
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select, func
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.database import get_db
from app.deps import get_tenant_for_membership
from app.models.insumo import Insumo, Receta
from app.models.tenant import Tenant
from app.schemas.common import Page
from app.schemas.insumo import (
    InsumoCreate,
    InsumoOut,
    InsumoStats,
    InsumoUpdate,
    RecetaCreate,
    RecetaOut,
    RecetaUpdate,
)

router = APIRouter(prefix="/tenants/{tenant_id}", tags=["insumos"])


# ── Helpers ─────────────────────────────────────────────────
def to_insumo_out(i: Insumo) -> InsumoOut:
    """Calcula campos derivados del Insumo."""
    available = max(0.0, float(i.stock or 0) - float(i.reserved or 0))
    stock_value = int(available * float(i.avg_cost_cents or 0))
    low_stock = (
        i.min_stock is not None
        and float(i.stock or 0) <= float(i.min_stock)
    )
    return InsumoOut(
        id=i.id,
        tenant_id=i.tenant_id,
        sku=i.sku,
        name=i.name,
        description=i.description,
        unit=i.unit,
        stock=float(i.stock or 0),
        reserved=float(i.reserved or 0),
        available=available,
        min_stock=i.min_stock,
        reorder_point=i.reorder_point,
        reorder_lead_time_days=i.reorder_lead_time_days,
        waste_pct=float(i.waste_pct or 0),
        last_cost_cents=i.last_cost_cents or 0,
        avg_cost_cents=i.avg_cost_cents or 0,
        stock_value_cents=stock_value,
        low_stock_alert=low_stock,
        supplier=i.supplier,
        location=i.location,
        lot=i.lot,
        expires_at=i.expires_at,
        image_url=i.image_url,
        tags=i.tags or [],
        is_active=i.is_active,
        is_na=i.is_na or [],
        created_at=i.created_at,
        updated_at=i.updated_at,
    )


# ── Insumo CRUD ─────────────────────────────────────────────
@router.get("/insumos", response_model=Page[InsumoOut])
def list_insumos(
    tenant: Tenant = Depends(get_tenant_for_membership),
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    search: str | None = None,
    low_stock: bool | None = None,
):
    """Lista los Insumos (materias primas) del tenant."""
    offset = (page - 1) * page_size
    q = select(Insumo).where(Insumo.tenant_id == str(tenant.id))
    if search:
        like = f"%{search.lower()}%"
        q = q.where(or_(
            func.lower(Insumo.name).like(like),
            func.lower(Insumo.sku).like(like),
        ))
    items_raw = list(db.execute(q.order_by(Insumo.name.asc())).scalars())
    # Filtro low_stock se aplica en Python (depende de min_stock)
    if low_stock is True:
        items_raw = [i for i in items_raw if i.min_stock is not None and float(i.stock or 0) <= float(i.min_stock)]
    elif low_stock is False:
        items_raw = [i for i in items_raw if not (i.min_stock is not None and float(i.stock or 0) <= float(i.min_stock))]
    total = len(items_raw)
    items_paged = items_raw[offset:offset + page_size]
    items = [to_insumo_out(i).model_dump(mode="json") for i in items_paged]
    return Page.build(items, total, page, page_size)


@router.post("/insumos", response_model=InsumoOut, status_code=201)
def create_insumo(
    payload: InsumoCreate,
    tenant: Tenant = Depends(get_tenant_for_membership),
    db: Session = Depends(get_db),
):
    """Crea un nuevo Insumo (materia prima)."""
    i = Insumo(**payload.model_dump(), tenant_id=str(tenant.id))
    db.add(i)
    db.commit()
    db.refresh(i)
    return to_insumo_out(i)


@router.get("/insumos/stats", response_model=InsumoStats)
def insumos_stats(
    tenant: Tenant = Depends(get_tenant_for_membership),
    db: Session = Depends(get_db),
):
    """Estadísticas globales del inventario de Insumos."""
    rows = list(db.execute(select(Insumo).where(Insumo.tenant_id == str(tenant.id))).scalars())
    total_value = 0
    low_stock_count = 0
    out_of_stock_count = 0
    active_count = 0
    for i in rows:
        if not i.is_active:
            continue
        active_count += 1
        available = max(0.0, float(i.stock or 0) - float(i.reserved or 0))
        total_value += int(available * float(i.avg_cost_cents or 0))
        if i.min_stock is not None and float(i.stock or 0) <= float(i.min_stock):
            low_stock_count += 1
        if float(i.stock or 0) <= 0:
            out_of_stock_count += 1
    return InsumoStats(
        total_insumos=len(rows),
        total_stock_value_cents=total_value,
        low_stock_count=low_stock_count,
        out_of_stock_count=out_of_stock_count,
        active_insumos=active_count,
    )


@router.get("/insumos/{insumo_id}", response_model=InsumoOut)
def get_insumo(insumo_id: UUID, tenant: Tenant = Depends(get_tenant_for_membership), db: Session = Depends(get_db)):
    i = db.get(Insumo, insumo_id)
    if not i or i.tenant_id != tenant.id:
        raise NotFoundError("Insumo")
    return to_insumo_out(i)


@router.patch("/insumos/{insumo_id}", response_model=InsumoOut)
def update_insumo(
    insumo_id: UUID,
    payload: InsumoUpdate,
    tenant: Tenant = Depends(get_tenant_for_membership),
    db: Session = Depends(get_db),
):
    i = db.get(Insumo, insumo_id)
    if not i or i.tenant_id != tenant.id:
        raise NotFoundError("Insumo")
    data = payload.model_dump(exclude_unset=True)
    # Si actualiza `last_cost_cents`, refrescar `avg_cost_cents` con una
    # media móvil simple (90% del promedio anterior + 10% del nuevo).
    if "last_cost_cents" in data:
        new_last = int(data["last_cost_cents"] or 0)
        old_avg = int(i.avg_cost_cents or 0)
        # Si no había promedio aún, lo inicializamos al nuevo valor.
        if old_avg == 0:
            data["avg_cost_cents"] = new_last
        else:
            data["avg_cost_cents"] = int(old_avg * 0.9 + new_last * 0.1)
        i.last_cost_cents = new_last
    for k, v in data.items():
        if k == "last_cost_cents":
            continue
        setattr(i, k, v)
    db.commit()
    db.refresh(i)
    return to_insumo_out(i)


@router.delete("/insumos/{insumo_id}", status_code=204)
def delete_insumo(insumo_id: UUID, tenant: Tenant = Depends(get_tenant_for_membership), db: Session = Depends(get_db)):
    i = db.get(Insumo, insumo_id)
    if not i or i.tenant_id != tenant.id:
        raise NotFoundError("Insumo")
    db.delete(i)
    db.commit()


# ── Receta (BOM) CRUD ───────────────────────────────────────
@router.get("/recetas", response_model=Page[RecetaOut])
def list_recetas(
    tenant: Tenant = Depends(get_tenant_for_membership),
    db: Session = Depends(get_db),
    product_id: UUID | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    """Lista las recetas. Si se pasa `product_id`, filtra por producto."""
    offset = (page - 1) * page_size
    q = select(Receta).where(Receta.tenant_id == str(tenant.id))
    if product_id:
        q = q.where(Receta.product_id == str(product_id))
    total = db.execute(select(func.count()).select_from(q.subquery())).scalar() or 0
    rows = list(db.execute(q.offset(offset).limit(page_size)).scalars())
    out: list[RecetaOut] = []
    for r in rows:
        line_cost = int((r.insumo.avg_cost_cents if r.insumo else 0) * float(r.quantity or 0))
        out.append(RecetaOut(
            id=r.id, tenant_id=r.tenant_id, product_id=r.product_id, insumo_id=r.insumo_id,
            quantity=float(r.quantity or 0), notes=r.notes, line_cost_cents=line_cost,
            insumo_name=(r.insumo.name if r.insumo else None),
            insumo_unit=(r.insumo.unit if r.insumo else None),
            insumo_sku=(r.insumo.sku if r.insumo else None),
        ))
    items = [o.model_dump(mode="json") for o in out]
    return Page.build(items, total, page, page_size)


@router.post("/recetas", response_model=RecetaOut, status_code=201)
def create_receta(
    payload: RecetaCreate,
    tenant: Tenant = Depends(get_tenant_for_membership),
    db: Session = Depends(get_db),
):
    """Crea una línea de receta: `quantity` de insumo para 1 producto."""
    r = Receta(**payload.model_dump(), tenant_id=str(tenant.id))
    db.add(r)
    db.commit()
    db.refresh(r)
    line_cost = int((r.insumo.avg_cost_cents if r.insumo else 0) * float(r.quantity or 0))
    return RecetaOut(
        id=r.id, tenant_id=r.tenant_id, product_id=r.product_id, insumo_id=r.insumo_id,
        quantity=float(r.quantity or 0), notes=r.notes, line_cost_cents=line_cost,
        insumo_name=(r.insumo.name if r.insumo else None),
        insumo_unit=(r.insumo.unit if r.insumo else None),
        insumo_sku=(r.insumo.sku if r.insumo else None),
    )


@router.patch("/recetas/{receta_id}", response_model=RecetaOut)
def update_receta(
    receta_id: UUID,
    payload: RecetaUpdate,
    tenant: Tenant = Depends(get_tenant_for_membership),
    db: Session = Depends(get_db),
):
    r = db.get(Receta, receta_id)
    if not r or r.tenant_id != tenant.id:
        raise NotFoundError("Receta")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(r, k, v)
    db.commit()
    db.refresh(r)
    line_cost = int((r.insumo.avg_cost_cents if r.insumo else 0) * float(r.quantity or 0))
    return RecetaOut(
        id=r.id, tenant_id=r.tenant_id, product_id=r.product_id, insumo_id=r.insumo_id,
        quantity=float(r.quantity or 0), notes=r.notes, line_cost_cents=line_cost,
        insumo_name=(r.insumo.name if r.insumo else None),
        insumo_unit=(r.insumo.unit if r.insumo else None),
        insumo_sku=(r.insumo.sku if r.insumo else None),
    )


@router.delete("/recetas/{receta_id}", status_code=204)
def delete_receta(receta_id: UUID, tenant: Tenant = Depends(get_tenant_for_membership), db: Session = Depends(get_db)):
    r = db.get(Receta, receta_id)
    if not r or r.tenant_id != tenant.id:
        raise NotFoundError("Receta")
    db.delete(r)
    db.commit()


@router.get("/products/{product_id}/cost-breakdown")
def product_cost_breakdown(
    product_id: UUID,
    tenant: Tenant = Depends(get_tenant_for_membership),
    db: Session = Depends(get_db),
):
    """Devuelve el desglose del costo de un producto a partir de sus
    recetas (BOM). Cada línea muestra el insumo, cantidad, costo unitario
    y subtotal. El total es lo que se setea como `cost_cents` sugerido.
    """
    rows = db.execute(
        select(Receta).where(
            Receta.tenant_id == str(tenant.id),
            Receta.product_id == str(product_id),
        )
    ).scalars().all()
    lines = []
    total = 0
    for r in rows:
        unit_cost = int(r.insumo.avg_cost_cents if r.insumo else 0)
        qty = float(r.quantity or 0)
        line_total = int(unit_cost * qty)
        total += line_total
        lines.append({
            "insumo_id": str(r.insumo_id),
            "insumo_name": r.insumo.name if r.insumo else None,
            "insumo_unit": r.insumo.unit if r.insumo else None,
            "quantity": qty,
            "unit_cost_cents": unit_cost,
            "line_total_cents": line_total,
        })
    return {
        "product_id": str(product_id),
        "lines": lines,
        "total_cost_cents": total,
        "recipe_count": len(lines),
    }
