"""BookingService — lógica de negocio para reservas (Fase 2).

Responsabilidades:
- CRUD de reservas multi-tenant
- Validación de conflictos (no se solapan reservas en la misma sucursal)
- Validación de horarios de sucursal (Branch.hours)
- Envío de notificaciones (confirmación, recordatorio, cancelación)
- Cálculo de slots disponibles para la UI de agenda
- Métricas para el dashboard

Diseño de horarios de sucursal (Branch.hours):
- Es un dict JSON con la forma:
  {
    "mon": {"open": "09:00", "close": "20:00"},
    "tue": {"open": "09:00", "close": "20:00"},
    ...
    "sun": null,            # cerrado
    "exceptions": {          # opcional: feriados / días especiales
      "2026-12-25": null,    # cerrado
      "2026-12-31": {"open": "10:00", "close": "15:00"}
    }
  }
- Si el dict está vacío, se considera 24/7.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, time, timedelta, timezone
from typing import Iterable, Optional
from uuid import UUID, uuid4

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.models.booking import Booking, BookingStatus
from app.models.branch import Branch
from app.models.customer import Customer
from app.models.product import Product
from app.models.tenant import Tenant
from app.schemas.booking import (
    AvailabilityQuery, AvailabilityResponse, AvailabilitySlot,
    BookingIn, BookingOut, BookingStats, PublicBookingIn,
)
from app.services.notification_service import NotificationService

logger = logging.getLogger("wowhub.booking")

# Mapeo Python weekday() (0=lunes) → clave Branch.hours
_WEEKDAY_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def _ensure_aware(dt: datetime) -> datetime:
    """Si un datetime viene naive (desde la DB en algunos motores), lo
    marcamos como UTC. Esto evita comparaciones inconsistentes."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _parse_hhmm(s: str) -> time:
    """Parsea 'HH:MM' o 'HH:MM:SS' a datetime.time."""
    m = re.match(r"^(\d{1,2}):(\d{2})(?::(\d{2}))?$", s.strip())
    if not m:
        raise ValueError(f"hora inválida: {s!r}")
    h, mm, ss = m.groups()
    return time(int(h), int(mm), int(ss or 0))


def _fmt_when(dt: datetime) -> str:
    """Formato humano para emails ('Lunes 16 de agosto, 15:30')."""
    dt = _ensure_aware(dt)
    local = dt.astimezone()  # hora local del server
    dias = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
    meses = [
        "enero", "febrero", "marzo", "abril", "mayo", "junio",
        "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
    ]
    return (
        f"{dias[local.weekday()]} {local.day} de {meses[local.month - 1]}, "
        f"{local.hour:02d}:{local.minute:02d}"
    )


class BookingService:
    """Lógica de negocio de reservas. Multi-tenant."""

    def __init__(self, db: Session, tenant_id: str):
        self.db = db
        self.tenant_id = tenant_id
        self.notifier = NotificationService(db)

    # ── Helpers internos ─────────────────────────────────
    def _branch_window_for_range(
        self, branch: Branch, starts_at: datetime, ends_at: datetime
    ) -> bool:
        """Valida que [starts_at, ends_at) cae dentro del horario de la
        sucursal. Si la sucursal no tiene horarios definidos, acepta 24/7.
        Si la sucursal está cerrada ese día, lanza ValidationError.
        Si la hora cae fuera del rango de apertura, lanza ValidationError.
        """
        if not branch.hours:
            return True
        starts_at = _ensure_aware(starts_at)
        ends_at = _ensure_aware(ends_at)
        # Verificamos cada día que toca la reserva
        cur = starts_at
        while cur.date() <= ends_at.date():
            key = _WEEKDAY_KEYS[cur.weekday()]
            day_window = branch.hours.get(key)
            exceptions = branch.hours.get("exceptions") or {}
            ex_key = cur.strftime("%Y-%m-%d")
            if ex_key in exceptions:
                day_window = exceptions[ex_key]

            if day_window is None:
                # Cerrado ese día
                if cur.date() == starts_at.date() and starts_at.hour > 0:
                    # Si la reserva empieza ese día cerrado
                    if cur.date() == starts_at.date() and ends_at.date() == starts_at.date():
                        raise ValidationError(
                            f"La sucursal '{branch.name}' está cerrada ese día"
                        )
            elif isinstance(day_window, dict):
                open_s = day_window.get("open")
                close_s = day_window.get("close")
                if not open_s or not close_s:
                    # Tratar como cerrado
                    raise ValidationError(
                        f"La sucursal '{branch.name}' no tiene horario definido para {key}"
                    )
                try:
                    open_t = _parse_hhmm(open_s)
                    close_t = _parse_hhmm(close_s)
                except ValueError as e:
                    logger.warning("horario malformado en branch %s: %s", branch.id, e)
                    return True
                # Sólo aplicamos la validación al día de inicio
                if cur.date() == starts_at.date():
                    if starts_at.time() < open_t or ends_at.time() > close_t:
                        raise ValidationError(
                            f"Horario fuera de apertura de la sucursal "
                            f"({open_s}–{close_s})"
                        )
            cur = cur + timedelta(days=1)
        return True

    def _check_conflict(
        self,
        branch_id: Optional[str],
        starts_at: datetime,
        ends_at: datetime,
        exclude_booking_id: Optional[UUID] = None,
    ) -> list[Booking]:
        """Devuelve la lista de reservas que se solapan con [starts_at, ends_at)
        en la misma sucursal (o en cualquier sucursal si branch_id es None).
        Estados que SÍ cuentan como conflicto: pending, confirmed, completed.
        Estados que NO cuentan: canceled, no_show.
        """
        starts_at = _ensure_aware(starts_at)
        ends_at = _ensure_aware(ends_at)
        q = select(Booking).where(
            Booking.tenant_id == self.tenant_id,
            Booking.status.in_([
                BookingStatus.PENDING,
                BookingStatus.CONFIRMED,
                BookingStatus.COMPLETED,
            ]),
            # solapamiento: existing.starts < new.ends AND existing.ends > new.starts
            Booking.starts_at < ends_at,
            Booking.ends_at > starts_at,
        )
        if branch_id:
            q = q.where(Booking.branch_id == str(branch_id))
        if exclude_booking_id:
            q = q.where(Booking.id != str(exclude_booking_id))
        return list(self.db.execute(q).scalars())

    # ── CRUD ─────────────────────────────────────────────
    def get(self, booking_id: UUID) -> Optional[Booking]:
        return self.db.execute(
            select(Booking).where(
                Booking.id == str(booking_id),
                Booking.tenant_id == self.tenant_id,
            )
        ).scalar_one_or_none()

    def get_or_404(self, booking_id: UUID) -> Booking:
        b = self.get(booking_id)
        if not b:
            raise NotFoundError("Reserva")
        return b

    def list(
        self,
        *,
        status: Optional[BookingStatus] = None,
        branch_id: Optional[UUID] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        customer_id: Optional[UUID] = None,
        limit: int = 200,
    ) -> list[Booking]:
        q = select(Booking).where(Booking.tenant_id == self.tenant_id)
        if status:
            q = q.where(Booking.status == status)
        if branch_id:
            q = q.where(Booking.branch_id == str(branch_id))
        if date_from:
            q = q.where(Booking.starts_at >= _ensure_aware(date_from))
        if date_to:
            q = q.where(Booking.starts_at <= _ensure_aware(date_to))
        if customer_id:
            q = q.where(Booking.customer_id == str(customer_id))
        q = q.order_by(Booking.starts_at.asc()).limit(min(limit, 1000))
        return list(self.db.execute(q).scalars())

    def create(
        self,
        payload: BookingIn | PublicBookingIn,
        *,
        send_confirmation: bool = True,
    ) -> Booking:
        # 1) Validar ventana
        if payload.ends_at <= payload.starts_at:
            raise ValidationError("ends_at debe ser mayor que starts_at")

        # 2) Si hay branch_id, validar que pertenece al tenant y la ventana horaria
        branch: Optional[Branch] = None
        if payload.branch_id:
            # Usamos un SELECT explícito en lugar de db.get() para evitar
            # problemas de binding con TypeDecorator(GUID) en SQLite.
            branch_id_str = str(payload.branch_id)
            branch = self.db.execute(
                select(Branch).where(Branch.id == branch_id_str)
            ).scalar_one_or_none()
            if not branch or str(branch.tenant_id) != str(self.tenant_id):
                raise NotFoundError("Sucursal")
            if not branch.is_active:
                raise ValidationError(f"La sucursal '{branch.name}' no está activa")
            self._branch_window_for_range(branch, payload.starts_at, payload.ends_at)

        # 3) Validar conflictos
        conflicts = self._check_conflict(
            str(payload.branch_id) if payload.branch_id else None,
            payload.starts_at,
            payload.ends_at,
        )
        if conflicts:
            c = conflicts[0]
            raise ConflictError(
                f"Ya existe una reserva en ese horario "
                f"({c.customer_name}, {c.starts_at.isoformat()}–{c.ends_at.isoformat()})"
            )

        # 4) Resolver / crear customer si es PublicBookingIn
        customer_id: Optional[str] = None
        if isinstance(payload, PublicBookingIn) and (payload.customer_email or payload.customer_phone):
            existing = None
            if payload.customer_email:
                existing = self.db.execute(
                    select(Customer).where(
                        Customer.tenant_id == self.tenant_id,
                        Customer.email == payload.customer_email.lower(),
                    )
                ).scalar_one_or_none()
            if not existing and payload.customer_phone:
                existing = self.db.execute(
                    select(Customer).where(
                        Customer.tenant_id == self.tenant_id,
                        Customer.phone == payload.customer_phone,
                    )
                ).scalar_one_or_none()
            if existing:
                customer_id = str(existing.id)
                # Si estaba en PENDING auto-confirmamos
                if not existing.accepts_marketing and (payload.customer_email or payload.customer_phone):
                    pass
            else:
                # Crear guest
                c = Customer(
                    tenant_id=self.tenant_id,
                    full_name=payload.customer_name,
                    email=(payload.customer_email or "").lower() or None,
                    phone=payload.customer_phone,
                    accepts_marketing=False,
                )
                self.db.add(c)
                self.db.flush()
                customer_id = str(c.id)

        # 5) Validar product_id si viene
        if payload.product_id:
            product_id_str = str(payload.product_id)
            prod = self.db.execute(
                select(Product).where(Product.id == product_id_str)
            ).scalar_one_or_none()
            if not prod or str(prod.tenant_id) != str(self.tenant_id):
                raise NotFoundError("Servicio / Producto")

        # 6) Crear booking
        data = payload.model_dump(exclude={"accepts_terms"}, exclude_none=False)
        # aceptar términos aplica sólo a PublicBookingIn
        data.pop("accepts_terms", None)

        b = Booking(
            tenant_id=self.tenant_id,
            customer_name=payload.customer_name,
            customer_phone=payload.customer_phone,
            customer_email=(payload.customer_email or "").lower() or None,
            branch_id=str(payload.branch_id) if payload.branch_id else None,
            product_id=str(payload.product_id) if payload.product_id else None,
            customer_id=customer_id,
            starts_at=payload.starts_at,
            ends_at=payload.ends_at,
            price_cents=getattr(payload, "price_cents", 0) or 0,
            currency=getattr(payload, "currency", "CLP") or "CLP",
            notes=payload.notes,
            staff_name=payload.staff_name,
            status=payload.status if hasattr(payload, "status") else BookingStatus.PENDING,
            extra=getattr(payload, "extra", {}) or {},
        )
        self.db.add(b)
        self.db.commit()
        self.db.refresh(b)

        # 7) Notificar
        if send_confirmation and b.customer_email:
            try:
                when = _fmt_when(b.starts_at)
                where = branch.address if branch else "WowHub"
                self.notifier.notify_booking_confirmed(
                    customer_email=b.customer_email,
                    booking_id=str(b.id),
                    when=when,
                    where=where,
                )
            except Exception as e:
                logger.warning("No se pudo notificar booking %s: %s", b.id, e)

        return b

    def update(
        self, booking_id: UUID, *, status: Optional[BookingStatus] = None,
        notes: Optional[str] = None, staff_name: Optional[str] = None,
        starts_at: Optional[datetime] = None, ends_at: Optional[datetime] = None,
    ) -> Booking:
        b = self.get_or_404(booking_id)
        # Si cambia el slot, validar
        new_start = starts_at or b.starts_at
        new_end = ends_at or b.ends_at
        if (starts_at or ends_at) and new_end <= new_start:
            raise ValidationError("ends_at debe ser mayor que starts_at")
        if (starts_at or ends_at):
            branch = None
            if b.branch_id:
                branch = self.db.execute(
                    select(Branch).where(Branch.id == str(b.branch_id))
                ).scalar_one_or_none()
                if branch:
                    self._branch_window_for_range(branch, new_start, new_end)
            conflicts = self._check_conflict(
                b.branch_id, new_start, new_end, exclude_booking_id=b.id
            )
            if conflicts:
                c = conflicts[0]
                raise ConflictError(
                    f"Conflicto con reserva existente ({c.customer_name}, "
                    f"{c.starts_at.isoformat()})"
                )
            b.starts_at = new_start
            b.ends_at = new_end
        if status:
            b.status = status
        if notes is not None:
            b.notes = notes
        if staff_name is not None:
            b.staff_name = staff_name
        self.db.commit()
        self.db.refresh(b)
        return b

    def cancel(self, booking_id: UUID, *, reason: Optional[str] = None) -> Booking:
        b = self.get_or_404(booking_id)
        b.status = BookingStatus.CANCELED
        if reason:
            existing = b.notes or ""
            b.notes = (existing + f"\n[Cancelada] {reason}").strip()
        self.db.commit()
        self.db.refresh(b)
        return b

    def confirm(self, booking_id: UUID) -> Booking:
        b = self.get_or_404(booking_id)
        b.status = BookingStatus.CONFIRMED
        self.db.commit()
        self.db.refresh(b)
        # Reenviar email
        if b.customer_email:
            try:
                branch = None
                if b.branch_id:
                    branch = self.db.execute(
                        select(Branch).where(Branch.id == str(b.branch_id))
                    ).scalar_one_or_none()
                where = branch.address if branch else "WowHub"
                self.notifier.notify_booking_confirmed(
                    customer_email=b.customer_email,
                    booking_id=str(b.id),
                    when=_fmt_when(b.starts_at),
                    where=where,
                )
            except Exception as e:
                logger.warning("No se pudo reenviar confirmación: %s", e)
        return b

    def complete(self, booking_id: UUID) -> Booking:
        b = self.get_or_404(booking_id)
        b.status = BookingStatus.COMPLETED
        self.db.commit()
        self.db.refresh(b)
        return b

    def mark_no_show(self, booking_id: UUID) -> Booking:
        b = self.get_or_404(booking_id)
        b.status = BookingStatus.NO_SHOW
        self.db.commit()
        self.db.refresh(b)
        return b

    def delete(self, booking_id: UUID) -> None:
        b = self.get_or_404(booking_id)
        self.db.delete(b)
        self.db.commit()

    # ── Availability ─────────────────────────────────────
    def get_availability(self, q: AvailabilityQuery) -> AvailabilityResponse:
        """Devuelve los slots disponibles en [date_from, date_to] con paso
        `slot_step_minutes` y duración `duration_minutes`.
        Si `branch_id` viene, se valida contra los horarios de la sucursal.
        """
        branch: Optional[Branch] = None
        if q.branch_id:
            branch = self.db.execute(
                select(Branch).where(Branch.id == str(q.branch_id))
            ).scalar_one_or_none()
            if not branch or str(branch.tenant_id) != str(self.tenant_id):
                raise NotFoundError("Sucursal")

        # Traer todas las reservas del rango (sólo activas)
        from datetime import datetime as _dt
        existing = self.db.execute(
            select(Booking).where(
                Booking.tenant_id == self.tenant_id,
                Booking.status.in_([
                    BookingStatus.PENDING,
                    BookingStatus.CONFIRMED,
                    BookingStatus.COMPLETED,
                ]),
                Booking.starts_at < _ensure_aware(q.date_to),
                Booking.ends_at > _ensure_aware(q.date_from),
                *([Booking.branch_id == str(q.branch_id)] if q.branch_id else []),
            )
        ).scalars().all()

        # Generar slots
        slots: list[AvailabilitySlot] = []
        step = timedelta(minutes=q.slot_step_minutes)
        duration = timedelta(minutes=q.duration_minutes)
        cur = _ensure_aware(q.date_from)
        end_limit = _ensure_aware(q.date_to)
        while cur + duration <= end_limit:
            slot_end = cur + duration
            available = True
            conflicts: list[UUID] = []
            in_hours = True
            # Validar horario de sucursal
            if branch and branch.hours:
                try:
                    self._branch_window_for_range(branch, cur, slot_end)
                except ValidationError:
                    in_hours = False
            if not in_hours:
                available = False
            else:
                for ex in existing:
                    ex_start = _ensure_aware(ex.starts_at)
                    ex_end = _ensure_aware(ex.ends_at)
                    if ex_start < slot_end and ex_end > cur:
                        available = False
                        conflicts.append(ex.id)
                        break
            slots.append(AvailabilitySlot(
                starts_at=cur,
                ends_at=slot_end,
                available=available,
                conflicts_with=conflicts,
            ))
            cur = cur + step

        return AvailabilityResponse(
            branch_id=q.branch_id,
            branch_name=branch.name if branch else None,
            date_from=q.date_from,
            date_to=q.date_to,
            slot_step_minutes=q.slot_step_minutes,
            duration_minutes=q.duration_minutes,
            slots=slots,
            total_slots=len(slots),
            available_slots=sum(1 for s in slots if s.available),
        )

    # ── Métricas ─────────────────────────────────────────
    def stats(self) -> BookingStats:
        from sqlalchemy import func
        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = today_start + timedelta(days=1)

        # Conteos por status
        rows = self.db.execute(
            select(Booking.status, func.count(Booking.id))
            .where(Booking.tenant_id == self.tenant_id)
            .group_by(Booking.status)
        ).all()
        by_status = {row[0]: row[1] for row in rows}
        total = sum(by_status.values())

        # Hoy
        today_count = self.db.execute(
            select(func.count(Booking.id)).where(
                Booking.tenant_id == self.tenant_id,
                Booking.starts_at >= today_start,
                Booking.starts_at < today_end,
            )
        ).scalar() or 0

        # Próximas (futuras y no canceladas)
        upcoming_count = self.db.execute(
            select(func.count(Booking.id)).where(
                Booking.tenant_id == self.tenant_id,
                Booking.starts_at >= now,
                Booking.status.in_([BookingStatus.PENDING, BookingStatus.CONFIRMED]),
            )
        ).scalar() or 0

        # Revenue (sólo completadas)
        rev = self.db.execute(
            select(func.coalesce(func.sum(Booking.price_cents), 0)).where(
                Booking.tenant_id == self.tenant_id,
                Booking.status == BookingStatus.COMPLETED,
            )
        ).scalar() or 0
        currency_row = self.db.execute(
            select(Booking.currency)
            .where(
                Booking.tenant_id == self.tenant_id,
                Booking.currency.isnot(None),
            )
            .limit(1)
        ).first()
        currency = currency_row[0] if currency_row and currency_row[0] else "CLP"

        return BookingStats(
            total=total,
            pending=by_status.get(BookingStatus.PENDING, 0),
            confirmed=by_status.get(BookingStatus.CONFIRMED, 0),
            completed=by_status.get(BookingStatus.COMPLETED, 0),
            canceled=by_status.get(BookingStatus.CANCELED, 0),
            no_show=by_status.get(BookingStatus.NO_SHOW, 0),
            today_count=today_count,
            upcoming_count=upcoming_count,
            revenue_cents=int(rev),
            currency=currency,
        )
