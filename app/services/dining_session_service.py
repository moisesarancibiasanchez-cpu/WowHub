"""HU_19 — Servicio de sesiones de mesa (DiningSession).

Reglas de negocio:
  - Una mesa no puede tener 2 sesiones OPEN simultáneas en la misma
    branch_id + table_label.
  - Al cerrar (close) se congela total_cents, paid_cents y tip_cents.
  - La división equitativa reparte total_cents entre customer_count
    comensales; las líneas con assigned_to se asignan a ese comensal.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.models.branch import Branch
from app.models.dining_session import (
    DiningSession, DiningSessionItem, DiningSessionStatus,
)
from app.models.order import OrderItem


def _now() -> datetime:
    return datetime.now(timezone.utc)


class DiningSessionService:
    def __init__(self, db: Session, tenant_id: str):
        self.db = db
        self.tenant_id = tenant_id

    # ── helpers ────────────────────────────────────────────
    def _get_session(self, session_id: UUID) -> DiningSession:
        s = self.db.get(DiningSession, session_id)
        if not s or str(s.tenant_id) != str(self.tenant_id):
            raise NotFoundError("Sesión de mesa")
        return s

    def _get_branch(self, branch_id: UUID) -> Branch:
        b = self.db.get(Branch, branch_id)
        if not b or str(b.tenant_id) != str(self.tenant_id):
            raise NotFoundError("Sucursal")
        return b

    # ── CRUD ───────────────────────────────────────────────
    def open(self, payload: dict) -> DiningSession:
        """Abre una mesa."""
        self._get_branch(payload["branch_id"])
        # Validar que no haya otra sesión OPEN con mismo label en la branch
        existing = self.db.execute(
            select(DiningSession).where(
                DiningSession.tenant_id == self.tenant_id,
                DiningSession.branch_id == str(payload["branch_id"]),
                DiningSession.table_label == payload["table_label"],
                DiningSession.status == DiningSessionStatus.OPEN.value,
            )
        ).scalar_one_or_none()
        if existing:
            raise ConflictError(
                f"Ya hay una sesión abierta en '{payload['table_label']}'"
            )
        s = DiningSession(
            tenant_id=self.tenant_id,
            branch_id=str(payload["branch_id"]),
            table_id=str(payload["table_id"]) if payload.get("table_id") else None,
            table_label=payload["table_label"],
            customer_count=int(payload.get("customer_count") or 1),
            server_user_id=str(payload["server_user_id"]) if payload.get("server_user_id") else None,
            notes=payload.get("notes"),
            status=DiningSessionStatus.OPEN.value,
            opened_at=_now(),
        )
        self.db.add(s)
        self.db.commit()
        self.db.refresh(s)
        return s

    def add_order_item(
        self, session_id: UUID, order_item_id: UUID,
        assigned_to: Optional[str] = None,
        share_cents: Optional[int] = None,
        notes: Optional[str] = None,
    ) -> DiningSessionItem:
        s = self._get_session(session_id)
        if s.status != DiningSessionStatus.OPEN.value:
            raise ConflictError("La mesa no está abierta")
        oi = self.db.get(OrderItem, order_item_id)
        if not oi:
            raise NotFoundError("Item de pedido")
        item = DiningSessionItem(
            session_id=str(s.id),
            order_item_id=str(order_item_id),
            assigned_to=assigned_to,
            share_cents=share_cents,
            notes=notes,
        )
        self.db.add(item)
        # Actualizar total de la sesión con el total del OrderItem.
        # Acumulamos para soportar varios items.
        s.total_cents = (s.total_cents or 0) + int(oi.total_cents or 0)
        self.db.commit()
        self.db.refresh(item)
        self.db.refresh(s)
        return item

    def list_items(self, session_id: UUID) -> list[DiningSessionItem]:
        self._get_session(session_id)
        return list(self.db.execute(
            select(DiningSessionItem)
            .where(DiningSessionItem.session_id == str(session_id))
            .order_by(DiningSessionItem.created_at)
        ).scalars())

    def split_equally(self, session_id: UUID) -> dict:
        """Calcula la división equitativa de la cuenta.

        Estrategia:
          1. Si hay items con assigned_to definido, esos se acumulan
             al monto de esa persona (share_cents si está definido, o
             el total_cents del OrderItem si no).
          2. El resto (items sin assigned_to) se reparte en partes
             iguales entre customer_count comensales etiquetados
             1..N.
          3. Si la división no es entera, el remanente va al primer
             comensal (1 centavo de diferencia es aceptable en LATAM).
        """
        s = self._get_session(session_id)
        items = self.list_items(session_id)

        # Shares por persona
        n = max(1, int(s.customer_count or 1))
        # Inicializar cada comensal con su label "Comensal 1..N"
        shares: dict[str, dict] = {
            f"Comensal {i+1}": {"amount_cents": 0, "items": []}
            for i in range(n)
        }

        def _item_amount(it) -> int:
            """Monto a imputar a este item: share_cents si está definido,
            sino el total_cents del OrderItem asociado."""
            if it.share_cents is not None:
                return int(it.share_cents)
            oi = self.db.get(OrderItem, it.order_item_id)
            return int(oi.total_cents or 0) if oi else 0

        # 1) Items con assigned_to van a su persona
        unassigned_total = 0
        for it in items:
            amount = _item_amount(it)
            target_label = it.assigned_to or None
            if target_label and target_label in shares:
                shares[target_label]["amount_cents"] += amount
                shares[target_label]["items"].append(it)
            else:
                unassigned_total += amount

        # 2) Repartir lo no-asignado entre los n comensales
        per_head, remainder = divmod(unassigned_total, n)
        for i in range(n):
            label = f"Comensal {i+1}"
            shares[label]["amount_cents"] += per_head
        # El remanente lo absorbe el primer comensal.
        if remainder and shares:
            first_label = next(iter(shares))
            shares[first_label]["amount_cents"] += remainder

        # 3) Agregar la propina proporcionalmente
        if s.tip_cents and s.total_cents:
            tip_per_head, tip_rem = divmod(int(s.tip_cents), n)
            for i in range(n):
                label = f"Comensal {i+1}"
                shares[label]["amount_cents"] += tip_per_head
            if tip_rem and shares:
                first_label = next(iter(shares))
                shares[first_label]["amount_cents"] += tip_rem

        return {
            "session_id": str(s.id),
            "customer_count": n,
            "total_cents": int(s.total_cents or 0),
            "paid_cents": int(s.paid_cents or 0),
            "tip_cents": int(s.tip_cents or 0),
            "shares": [
                {
                    "label": label,
                    "amount_cents": int(data["amount_cents"]),
                    "items": data["items"],
                }
                for label, data in shares.items()
            ],
            "remainder_cents": int(remainder),
        }

    def close(
        self, session_id: UUID,
        paid_cents: Optional[int] = None,
        notes: Optional[str] = None,
    ) -> DiningSession:
        s = self._get_session(session_id)
        if s.status != DiningSessionStatus.OPEN.value:
            raise ConflictError(f"La mesa ya está {s.status}")
        s.status = DiningSessionStatus.CLOSED.value
        s.closed_at = _now()
        if paid_cents is not None:
            s.paid_cents = paid_cents
        if notes is not None:
            s.notes = (s.notes + "\n" if s.notes else "") + notes
        self.db.commit()
        self.db.refresh(s)
        return s

    def add_tip(self, session_id: UUID, tip_cents: int) -> DiningSession:
        s = self._get_session(session_id)
        if s.status != DiningSessionStatus.OPEN.value:
            raise ConflictError("Sólo se puede agregar propina a una mesa abierta")
        if tip_cents < 0:
            raise ValidationError("tip_cents debe ser >= 0")
        s.tip_cents = (s.tip_cents or 0) + int(tip_cents)
        self.db.commit()
        self.db.refresh(s)
        return s

    def cancel(self, session_id: UUID) -> DiningSession:
        s = self._get_session(session_id)
        s.status = DiningSessionStatus.CANCELLED.value
        s.closed_at = _now()
        self.db.commit()
        self.db.refresh(s)
        return s
