"""ProductionService — Kanban de producción (HU_52, HU_53, HU_55).

Replica el Kanban de 7 etapas de WowPrint V1354_R2.
Pipeline: nuevo → archivo_aprobado → preparando → imprimiendo → terminacion → listo → entregado
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select, and_, func
from sqlalchemy.orm import Session, selectinload

from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.models.customer import Customer
from app.models.insumo_movement import InsumoMovement, InsumoMovementType
from app.models.order import Order, OrderItem, OrderStatus
from app.models.production import (
    ProductionJob, ProductionJobStatus, PRODUCTION_JOB_TRANSITIONS
)
from app.models.product import Product


# Tipos de producto que requieren producción
PRODUCTION_PRODUCT_TYPES = {"print", "m2", "production_only"}


class ProductionService:
    def __init__(self, db: Session):
        self.db = db

    def get(self, tenant_id: UUID, job_id: UUID) -> ProductionJob:
        job = self.db.get(ProductionJob, job_id)
        if not job or str(job.tenant_id) != str(tenant_id):
            raise NotFoundError("ProductionJob")
        return job

    def list_for_kanban(
        self, tenant_id: UUID,
        statuses: Optional[list[ProductionJobStatus]] = None,
        limit_per_col: int = 50,
    ) -> dict:
        """HU_52 — devuelve el Kanban agrupado por status.
        
        Paginación: max 50 jobs por columna (NFR performance).
        """
        if statuses is None:
            statuses = list(ProductionJobStatus)

        # Una sola query agrupada por status
        q = (
            select(ProductionJob)
            .where(ProductionJob.tenant_id == str(tenant_id))
            .where(ProductionJob.status.in_([s.value for s in statuses]))
            .order_by(ProductionJob.priority.desc(), ProductionJob.due_date.asc())
        )
        all_jobs = list(self.db.execute(q).scalars())

        # Agrupar por status
        by_status: dict[str, list] = {s.value: [] for s in statuses}
        for job in all_jobs:
            by_status[job.status.value].append(job)

        # Construir columnas con paginación
        columns = []
        total = 0
        for status in statuses:
            jobs_in_col = by_status[status.value]
            total += len(jobs_in_col)
            columns.append({
                "status": status.value,
                "count": len(jobs_in_col),
                "jobs": jobs_in_col[:limit_per_col],  # cap
            })

        # Métricas globales
        urgent_count = sum(1 for j in all_jobs if j.priority == "urgente")
        late_count = sum(
            1 for j in all_jobs
            if j.due_date and j.due_date < datetime.now(timezone.utc)
            and j.status not in (ProductionJobStatus.ENTREGADO, ProductionJobStatus.CANCELADO)
        )

        return {
            "columns": columns,
            "total_jobs": total,
            "total_urgent": urgent_count,
            "total_late": late_count,
        }

    def move(self, tenant_id: UUID, job_id: UUID, new_status: ProductionJobStatus,
             notes: Optional[str] = None) -> ProductionJob:
        """HU_53 — transicionar job a nuevo estado con validación de state machine.
        
        Raises ConflictError si la transición no es válida.
        """
        job = self.get(tenant_id, job_id)
        allowed = PRODUCTION_JOB_TRANSITIONS.get(job.status, set())
        if new_status not in allowed:
            raise ConflictError(
                f"Transición inválida: {job.status.value} → {new_status.value}. "
                f"Estados permitidos: {[s.value for s in allowed]}"
            )

        from_status = job.status
        job.status = new_status
        if notes:
            job.notes = (job.notes or "") + f"\n[{from_status.value}→{new_status.value}] {notes}"

        if new_status == ProductionJobStatus.ENTREGADO:
            job.delivered_at = datetime.now(timezone.utc)

        # HU_55 — al transicionar a TERMINACION, consumir insumos según receta
        if new_status == ProductionJobStatus.TERMINACION:
            self._consume_insumos(job)

        self.db.commit()
        self.db.refresh(job)
        return job

    def _consume_insumos(self, job: ProductionJob):
        """HU_55 — al completar producción, consumir insumos según receta.
        
        Mueve a un método protegido para testeo.
        """
        from app.models.insumo import Receta

        if not job.product_id:
            return

        recetas = list(self.db.execute(
            select(Receta).where(Receta.product_id == str(job.product_id))
        ).scalars())

        for receta in recetas:
            # Calcular cantidad: receta.quantity × job.quantity × (1 + waste_pct)
            from app.models.insumo import Insumo
            insumo = self.db.get(Insumo, receta.insumo_id)
            if not insumo:
                continue

            qty_needed = receta.quantity * job.quantity * (1 + (insumo.waste_pct or 0) / 100)

            # Verificar stock disponible
            if insumo.stock < qty_needed:
                raise ConflictError(
                    f"Stock insuficiente de insumo '{insumo.name}': "
                    f"necesario {qty_needed:.2f} {insumo.unit}, disponible {insumo.stock:.2f} {insumo.unit}"
                )

            # Crear movimiento de salida
            unit_cost = insumo.avg_cost_cents or insumo.last_cost_cents
            movement = InsumoMovement(
                tenant_id=str(job.tenant_id),
                insumo_id=str(insumo.id),
                type=InsumoMovementType.SALIDA,
                quantity=-qty_needed,
                balance_after=insumo.stock - qty_needed,
                production_job_id=str(job.id),
                order_id=str(job.order_id),
                unit_cost_cents_at_move=unit_cost,
                total_cost_cents=int(qty_needed * unit_cost),
                notes=f"Consumo automático job {job.id}",
            )
            self.db.add(movement)
            insumo.stock -= qty_needed

    def create_for_order(self, order: Order) -> list[ProductionJob]:
        """HU_52 — auto-crear jobs al confirmar pedido.
        
        Se llama desde OrderService.transition(CONFIRMADO).
        Solo crea jobs para items con product_type ∈ (print, m2, production_only).
        """
        created = []
        for item in order.items:
            if not item.product_id:
                continue
            product = self.db.get(Product, UUID(item.product_id) if not isinstance(item.product_id, UUID) else item.product_id)
            if not product or product.product_type not in PRODUCTION_PRODUCT_TYPES:
                continue

            # Evitar duplicados: si ya existe job activo para este line, skip
            existing = self.db.execute(
                select(ProductionJob).where(
                    and_(
                        ProductionJob.order_id == str(order.id),
                        ProductionJob.order_item_id == str(item.id),
                        ProductionJob.status != ProductionJobStatus.CANCELADO.value,
                    )
                )
            ).scalar_one_or_none()
            if existing:
                continue

            customer = None
            if order.customer_id:
                customer = self.db.get(Customer, UUID(order.customer_id) if not isinstance(order.customer_id, UUID) else order.customer_id)

            job = ProductionJob(
                tenant_id=str(order.tenant_id),
                order_id=str(order.id),
                order_item_id=str(item.id),
                product_id=str(product.id),
                product_snapshot={
                    "id": str(product.id),
                    "name": product.name,
                    "sku": product.sku,
                    "product_type": product.product_type,
                    "template_type": product.template_type,
                    "production_time_min": product.production_time_min,
                },
                customer_id=str(order.customer_id) if order.customer_id else None,
                customer_name=order.customer_name or (customer.full_name if customer else None),
                quantity=item.quantity,
                status=ProductionJobStatus.NUEVO,
                priority="normal",
            )
            self.db.add(job)
            created.append(job)

        if created:
            self.db.commit()
            for j in created:
                self.db.refresh(j)
        return created
