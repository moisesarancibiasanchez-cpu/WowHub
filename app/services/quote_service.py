"""QuoteService — lógica de negocio para cotizaciones.

Cubre: numeración, cálculo de totales, transiciones de estado, conversión
a Order, generación de token público y estadísticas agregadas.
"""
import logging
import secrets
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.errors import ConflictError, NotFoundError
from app.models.order import Order, OrderItem, OrderStatus
from app.models.quote import Quote, QuoteItem, QuoteStatus
from app.schemas.common import Page
from app.schemas.quote import QuoteListItem

logger = logging.getLogger("wowhub.quote")


class QuoteService:
    def __init__(self, db: Session):
        self.db = db

    # ── Listado & stats ──────────────────────────────────
    def list(
        self,
        tenant_id: UUID,
        status: Optional[QuoteStatus] = None,
        search: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Page[QuoteListItem]:
        stmt = select(Quote).where(Quote.tenant_id == tenant_id)
        if status:
            stmt = stmt.where(Quote.status == status)
        if search:
            like = f"%{search}%"
            stmt = stmt.where(
                (Quote.title.ilike(like))
                | (Quote.recipient_name.ilike(like))
                | (Quote.number.ilike(like))
            )
        total = self.db.execute(
            select(func.count()).select_from(stmt.subquery())
        ).scalar_one()
        rows = self.db.execute(
            stmt.order_by(Quote.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).scalars().all()
        items = [QuoteListItem.model_validate(r) for r in rows]
        return Page.build(items, int(total), page, page_size)

    def stats(self, tenant_id: UUID) -> dict:
        rows = self.db.execute(
            select(Quote.status, func.count(Quote.id), func.coalesce(func.sum(Quote.total_cents), 0))
            .where(Quote.tenant_id == tenant_id)
            .group_by(Quote.status)
        ).all()
        by_status: dict[str, int] = {s.value: 0 for s in QuoteStatus}
        value_by_status: dict[str, int] = {s.value: 0 for s in QuoteStatus}
        total = 0
        total_value = 0
        for st, count, value in rows:
            by_status[st] = int(count)
            value_by_status[st] = int(value)
            total += int(count)
            total_value += int(value)
        decided = by_status["accepted"] + by_status["rejected"]
        acceptance = (
            by_status["accepted"] / decided if decided > 0 else 0.0
        )
        return {
            "total": total,
            "by_status": by_status,
            "total_value_cents": total_value,
            "acceptance_rate": round(acceptance, 3),
            "draft_value_cents": value_by_status["draft"] + value_by_status["sent"] + value_by_status["viewed"],
            "accepted_value_cents": value_by_status["accepted"],
        }

    # ── CRUD ─────────────────────────────────────────────
    def get(self, tenant_id: UUID, quote_id: UUID) -> Quote:
        q = self.db.execute(
            select(Quote)
            .options(selectinload(Quote.items))
            .where(Quote.tenant_id == tenant_id, Quote.id == quote_id)
        ).scalar_one_or_none()
        if not q:
            raise NotFoundError("Cotización")
        return q

    def get_by_token(self, token: str) -> Quote:
        q = self.db.execute(
            select(Quote)
            .options(selectinload(Quote.items))
            .where(Quote.public_token == token)
        ).scalar_one_or_none()
        if not q:
            raise NotFoundError("Cotización")
        return q

    def create(self, tenant_id: UUID, data: dict) -> Quote:
        items = data.pop("items", [])
        number = self._next_number(tenant_id)
        token = self._unique_token()
        quote = Quote(
            tenant_id=tenant_id,
            number=number,
            public_token=token,
            currency=data.get("currency", "CLP"),
            **data,
        )
        self._recalc_totals(quote, items)
        self.db.add(quote)
        self.db.commit()
        self.db.refresh(quote)
        return quote

    def update(self, tenant_id: UUID, quote_id: UUID, data: dict) -> Quote:
        quote = self.get(tenant_id, quote_id)
        if quote.status not in (QuoteStatus.DRAFT, QuoteStatus.SENT, QuoteStatus.VIEWED):
            raise ConflictError(
                f"No se puede editar una cotización en estado '{quote.status.value}'"
            )
        items_in = data.pop("items", None)
        for k, v in data.items():
            if v is not None:
                setattr(quote, k, v)
        if items_in is not None:
            # Reemplazar items
            for old in list(quote.items):
                self.db.delete(old)
            self.db.flush()
            self._recalc_totals(quote, items_in)
        else:
            self._recalc_totals(quote, list(quote.items))
        self.db.commit()
        self.db.refresh(quote)
        return quote

    def delete(self, tenant_id: UUID, quote_id: UUID) -> None:
        quote = self.get(tenant_id, quote_id)
        if quote.status == QuoteStatus.ACCEPTED:
            raise ConflictError("No se puede eliminar una cotización ya aceptada")
        self.db.delete(quote)
        self.db.commit()

    # ── Acciones de estado ───────────────────────────────
    def mark_sent(self, tenant_id: UUID, quote_id: UUID) -> Quote:
        quote = self.get(tenant_id, quote_id)
        if quote.status == QuoteStatus.DRAFT:
            quote.status = QuoteStatus.SENT
            quote.sent_at = datetime.now(timezone.utc)
            self.db.commit()
            self.db.refresh(quote)
        return quote

    def mark_viewed(self, token: str) -> Quote:
        """Marca como vista cuando el cliente abre el link público."""
        quote = self.get_by_token(token)
        if quote.status in (QuoteStatus.SENT,):
            quote.status = QuoteStatus.VIEWED
            quote.viewed_at = datetime.now(timezone.utc)
            self.db.commit()
            self.db.refresh(quote)
        elif quote.status == QuoteStatus.DRAFT and quote.viewed_at is None:
            # permitir vista si es DRAFT para vista previa interna
            quote.viewed_at = datetime.now(timezone.utc)
            self.db.commit()
            self.db.refresh(quote)
        return quote

    def accept(self, tenant_id: UUID, quote_id: UUID) -> Quote:
        quote = self.get(tenant_id, quote_id)
        if quote.status in (QuoteStatus.ACCEPTED,):
            return quote
        if quote.status in (QuoteStatus.REJECTED, QuoteStatus.EXPIRED):
            raise ConflictError(
                f"No se puede aceptar una cotización en estado '{quote.status.value}'"
            )
        quote.status = QuoteStatus.ACCEPTED
        quote.accepted_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(quote)
        return quote

    def reject(self, tenant_id: UUID, quote_id: UUID) -> Quote:
        quote = self.get(tenant_id, quote_id)
        if quote.status in (QuoteStatus.REJECTED,):
            return quote
        if quote.status == QuoteStatus.ACCEPTED:
            raise ConflictError("No se puede rechazar una cotización ya aceptada")
        quote.status = QuoteStatus.REJECTED
        quote.rejected_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(quote)
        return quote

    # ── Conversión a Order ───────────────────────────────
    def convert_to_order(
        self,
        tenant_id: UUID,
        quote_id: UUID,
        *,
        branch_id: Optional[UUID] = None,
    ) -> Order:
        quote = self.get(tenant_id, quote_id)
        if quote.status == QuoteStatus.ACCEPTED and quote.converted_order_id:
            raise ConflictError("Esta cotización ya fue convertida a pedido")
        if quote.status not in (QuoteStatus.ACCEPTED, QuoteStatus.SENT, QuoteStatus.VIEWED, QuoteStatus.DRAFT):
            raise ConflictError(
                f"No se puede convertir una cotización en estado '{quote.status.value}'"
            )
        order = Order(
            tenant_id=tenant_id,
            number=self._next_order_number(tenant_id),
            status=OrderStatus.PENDING,
            customer_id=quote.customer_id,
            branch_id=branch_id or quote.branch_id,
            subtotal_cents=quote.subtotal_cents,
            discount_cents=quote.discount_cents,
            tax_cents=quote.tax_cents,
            total_cents=quote.total_cents,
            currency=quote.currency,
            customer_name=quote.recipient_name,
            customer_phone=quote.recipient_phone,
            customer_email=quote.recipient_email,
            source="quote",
            notes=quote.notes,
        )
        for qi in quote.items:
            order.items.append(
                OrderItem(
                    product_id=qi.product_id,
                    product_name=qi.product_name,
                    product_sku=qi.product_sku,
                    quantity=qi.quantity,
                    unit_price_cents=qi.unit_price_cents,
                    total_cents=qi.total_cents,
                    options={"discount_cents": qi.discount_cents},
                )
            )
        self.db.add(order)
        self.db.flush()
        quote.status = QuoteStatus.ACCEPTED
        quote.accepted_at = quote.accepted_at or datetime.now(timezone.utc)
        quote.converted_order_id = order.id
        self.db.commit()
        self.db.refresh(order)
        return order

    # ── Helpers ──────────────────────────────────────────
    def _recalc_totals(self, quote: Quote, items_data: list) -> None:
        """Calcula subtotal y total a partir de items (lista de dicts o QuoteItem)."""
        subtotal = 0
        items_to_persist = []
        for raw in items_data:
            if isinstance(raw, QuoteItem):
                # ya existente, recalcular su total
                line_total = (raw.unit_price_cents * raw.quantity) - raw.discount_cents
                raw.total_cents = max(0, line_total)
                subtotal += raw.total_cents
                items_to_persist.append(raw)
                continue
            qty = int(raw.get("quantity", 1))
            unit = int(raw["unit_price_cents"])
            disc = int(raw.get("discount_cents", 0))
            line_total = max(0, (unit * qty) - disc)
            subtotal += line_total
            qi = QuoteItem(
                product_id=raw.get("product_id"),
                product_name=raw["product_name"],
                product_sku=raw.get("product_sku"),
                description=raw.get("description"),
                quantity=qty,
                unit_price_cents=unit,
                discount_cents=disc,
                total_cents=line_total,
            )
            items_to_persist.append(qi)
        # purgar y reemplazar
        if not isinstance(items_data[0] if items_data else None, QuoteItem):
            for old in list(quote.items):
                self.db.delete(old)
            self.db.flush()
            for qi in items_to_persist:
                quote.items.append(qi)
        quote.subtotal_cents = subtotal
        total = subtotal - int(quote.discount_cents or 0) + int(quote.tax_cents or 0)
        quote.total_cents = max(0, total)

    def _next_number(self, tenant_id: UUID) -> str:
        n = self.db.execute(
            select(func.count(Quote.id)).where(Quote.tenant_id == tenant_id)
        ).scalar_one() or 0
        return f"COT-{n + 1:04d}"

    def _next_order_number(self, tenant_id: UUID) -> str:
        n = self.db.execute(
            select(func.count(Order.id)).where(Order.tenant_id == tenant_id)
        ).scalar_one() or 0
        return f"ORD-{n + 1:05d}"

    def _unique_token(self) -> str:
        for _ in range(8):
            tok = secrets.token_urlsafe(12)
            exists = self.db.execute(
                select(Quote.id).where(Quote.public_token == tok)
            ).scalar_one_or_none()
            if not exists:
                return tok
        return secrets.token_urlsafe(20)
