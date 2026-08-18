"""Automation Manager™ (Cap. 19.3) — orquestación de acciones del Growth Coach.

Este servicio es el "puente" entre las recomendaciones textuales que
devuelve el Growth Coach (Cap. 19.2) y las acciones reales que el
usuario puede ejecutar (crear promo, agendar reserva, mandar campaña).

Diseño:
- **ActionRegistry**: mapa de `ActionType` → handler. Cada handler es una
  función que recibe (db, tenant_id, user_id, role, params) y devuelve
  un `ActionResult`. Registrar uno nuevo = 1 entrada en REGISTRY.
- **execute()**: corre un handler. Valida params, chequea permisos,
  escribe `AutomationExecution` (audit log), commit / rollback.
- **preview()**: corre el handler con `dry_run=True`. NO escribe DB.
  Devuelve un `preview_text` listo para mostrar.
- **Permisos**: por rol de membresía. OWNER/ADMIN pueden todo; STAFF
  solo acciones de booking (no promo ni campaign); VIEWER no ejecuta.
- **Rate limit**: cuenta entradas a `/execute` (no a `/preview`).

Seguridad:
- El endpoint SIEMPRE exige `confirmed=true` + `dry_run=false` para
  ejecutar. Sin esto → 400.
- El handler SIEMPRE valida `params` con el Pydantic schema de su dominio
  (PromotionCreate, BookingIn, CampaignCreate). Si el schema rechaza,
  el handler rechaza con 422-like.
- La `tenant_id` SIEMPRE se toma del JWT (vía `TenantMembership`), NUNCA
  del body. Esto cierra el vector de cross-tenant write.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models.booking import Booking, BookingStatus
from app.models.promotion import Promotion
from app.models.tenant import TenantMembership, UserRole
from app.schemas.analytics import CampaignCreate
from app.schemas.automation import (
    ActionResult,
    ActionSpec,
    ActionType,
    AutomationRequest,
    AutomationResponse,
    ExecutionStatus,
)
from app.schemas.booking import BookingIn
from app.schemas.promotion import PromotionCreate

logger = logging.getLogger("wowhub.ai.automation")


# ── Excepciones ─────────────────────────────────────────────────
class AutomationError(Exception):
    """Error genérico del Automation Manager."""

    def __init__(
        self,
        message: str,
        status_code: int = 400,
        code: str = "automation_error",
    ):
        self.message = message
        self.status_code = status_code
        self.code = code
        super().__init__(message)


class ActionNotFoundError(AutomationError):
    def __init__(self, action_type: str):
        super().__init__(
            f"Acción '{action_type}' no registrada. "
            f"Acciones disponibles: {sorted(REGISTRY.keys())}",
            status_code=404,
            code="action_not_found",
        )


class PermissionDeniedError(AutomationError):
    def __init__(self, action_type: str, user_role: str):
        super().__init__(
            f"Tu rol ({user_role}) no puede ejecutar '{action_type}'.",
            status_code=403,
            code="permission_denied",
        )


class ConfirmationRequiredError(AutomationError):
    def __init__(self):
        super().__init__(
            "Para ejecutar una acción necesitás confirmar explícitamente "
            "(confirmed=true y dry_run=false).",
            status_code=400,
            code="confirmation_required",
        )


# ── Tipos de handlers ──────────────────────────────────────────
# Un handler recibe: (db, tenant_id, user_id, user_role, params, dry_run)
# y devuelve un ActionResult. No debe lanzar HTTPException: el manager
# mapea errores a códigos de error en el result.

HandlerFn = Callable[
    [Session, UUID, UUID, str, dict[str, Any], bool],
    ActionResult,
]


# ── Helpers ────────────────────────────────────────────────────
def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


# ── 1. Handler: create_promotion ───────────────────────────────
def _handle_create_promotion(
    db: Session,
    tenant_id: UUID,
    user_id: UUID,
    user_role: str,
    params: dict[str, Any],
    dry_run: bool,
) -> ActionResult:
    """Crea una Promotion. Valida con PromotionCreate (Pydantic)."""
    # 1) Validar params con el schema del dominio
    try:
        payload = PromotionCreate.model_validate(params)
    except Exception as e:
        raise AutomationError(
            f"Parámetros inválidos para create_promotion: {e}",
            status_code=422,
            code="invalid_params",
        )

    if dry_run:
        # Preview: NO escribir DB, devolver resumen legible
        preview = (
            f"Vas a crear la promoción **{payload.name}**:\n"
            f"  • Tipo: {payload.promo_type} / {payload.discount_type}\n"
            f"  • Descuento: {payload.discount_value}%\n"
            f"  • Aplica a: "
            f"{'todos los productos' if payload.applies_to_all else f'{len(payload.product_ids)} productos / {len(payload.category_ids)} categorías'}\n"
            f"  • Vigencia: {payload.starts_at or 'sin inicio'} → {payload.ends_at or 'sin fin'}\n"
            f"  • Code: {payload.code or '(sin code)'}\n"
            f"  • Pública: {payload.is_public} | Activa: {payload.is_active}"
        )
        return ActionResult(
            success=True,
            status="preview_ready",
            message=preview,
            resource_type="promotion",
            preview=preview,
            meta={
                "name": payload.name,
                "discount_type": payload.discount_type,
                "discount_value": payload.discount_value,
            },
        )

    # 2) Ejecutar: crear en DB
    data = payload.model_dump()
    data["product_ids"] = [str(x) for x in data.get("product_ids", [])]
    data["category_ids"] = [str(x) for x in data.get("category_ids", [])]
    promo = Promotion(**data, tenant_id=str(tenant_id))
    db.add(promo)
    db.commit()
    db.refresh(promo)

    return ActionResult(
        success=True,
        status="succeeded",
        message=f"Promoción '{promo.name}' creada correctamente.",
        resource_id=str(promo.id),
        resource_type="promotion",
        resource_url=f"/dashboard/promotions/{promo.id}",
        meta={"name": promo.name, "code": promo.code},
    )


# ── 2. Handler: create_booking ─────────────────────────────────
def _handle_create_booking(
    db: Session,
    tenant_id: UUID,
    user_id: UUID,
    user_role: str,
    params: dict[str, Any],
    dry_run: bool,
) -> ActionResult:
    """Agenda una reserva. Valida con BookingIn (Pydantic)."""
    # STAFF puede crear bookings; OWNER/ADMIN también.
    if user_role not in (UserRole.OWNER.value, UserRole.ADMIN.value, UserRole.STAFF.value):
        raise PermissionDeniedError("create_booking", user_role)

    try:
        payload = BookingIn.model_validate(params)
    except Exception as e:
        raise AutomationError(
            f"Parámetros inválidos para create_booking: {e}",
            status_code=422,
            code="invalid_params",
        )

    if dry_run:
        preview = (
            f"Vas a crear una reserva:\n"
            f"  • Cliente: {payload.customer_name} ({payload.customer_phone})\n"
            f"  • Email: {payload.customer_email or '(no provisto)'}\n"
            f"  • Sucursal: {payload.branch_id or 'default'}\n"
            f"  • Inicio: {payload.starts_at.isoformat()}\n"
            f"  • Fin: {payload.ends_at.isoformat()}\n"
            f"  • Precio: {payload.price_cents} {payload.currency}\n"
            f"  • Notas: {payload.notes or '(sin notas)'}"
        )
        return ActionResult(
            success=True,
            status="preview_ready",
            message=preview,
            resource_type="booking",
            preview=preview,
            meta={
                "customer_name": payload.customer_name,
                "starts_at": payload.starts_at.isoformat(),
            },
        )

    # Ejecutar: usar BookingService (re-usa lógica de availability + email)
    try:
        from app.services.booking_service import BookingService
        svc = BookingService(db, str(tenant_id))
        booking = svc.create(payload, send_confirmation=False)
    except Exception as e:
        db.rollback()
        logger.exception("create_booking failed")
        raise AutomationError(
            f"No se pudo crear la reserva: {e}",
            status_code=400,
            code="booking_creation_failed",
        )

    return ActionResult(
        success=True,
        status="succeeded",
        message=(
            f"Reserva agendada para {booking.customer_name} "
            f"el {booking.starts_at.isoformat()}."
        ),
        resource_id=str(booking.id),
        resource_type="booking",
        resource_url=f"/dashboard/bookings?focus={booking.id}",
        meta={
            "customer_name": booking.customer_name,
            "starts_at": booking.starts_at.isoformat(),
        },
    )


# ── 3. Handler: send_campaign ──────────────────────────────────
def _handle_send_campaign(
    db: Session,
    tenant_id: UUID,
    user_id: UUID,
    user_role: str,
    params: dict[str, Any],
    dry_run: bool,
) -> ActionResult:
    """Envía una campaña a un segmento. Valida con CampaignCreate.

    Solo OWNER/ADMIN. STAFF NO puede enviar campañas masivas.
    """
    if user_role not in (UserRole.OWNER.value, UserRole.ADMIN.value):
        raise PermissionDeniedError("send_campaign", user_role)

    try:
        payload = CampaignCreate.model_validate(params)
    except Exception as e:
        raise AutomationError(
            f"Parámetros inválidos para send_campaign: {e}",
            status_code=422,
            code="invalid_params",
        )

    if dry_run:
        # Preview: estimar destinatarios sin enviar
        try:
            from app.services.analytics_service import AnalyticsService
            analytics = AnalyticsService(db)
            seg = analytics.customer_segments(
                tenant_id,
                days_inactive=payload.days_inactive,
                days_new=payload.days_new,
                vip_min_orders=payload.vip_min_orders,
                vip_min_spent_cents=payload.vip_min_spent_cents,
            )
            # El segmento pedido
            target_count = int(seg.get(payload.segment, {}).get("count", 0) or 0)
        except Exception:
            target_count = -1  # no pudimos estimar, igual seguimos

        preview = (
            f"Vas a enviar la campaña **{payload.name}**:\n"
            f"  • Asunto: {payload.subject}\n"
            f"  • Canal: {payload.channel}\n"
            f"  • Segmento: {payload.segment}\n"
            f"  • Destinatarios estimados: {target_count if target_count >= 0 else 'no se pudo estimar'}\n"
            f"  • Solo opt-in marketing: {payload.only_marketing_opt_in}\n"
            f"  • Body (preview): {payload.body[:120]}{'…' if len(payload.body) > 120 else ''}"
        )
        return ActionResult(
            success=True,
            status="preview_ready",
            message=preview,
            resource_type="campaign",
            preview=preview,
            meta={
                "segment": payload.segment,
                "target_count_estimate": target_count,
            },
        )

    # Ejecutar: llamar al endpoint de campaigns internamente
    # No re-importamos el router (evita circular). Usamos el mismo path
    # que usa /api/v1/campaigns: AnalyticsService + email_service.
    try:
        from app.services.analytics_service import AnalyticsService
        from app.services.email_service import email_service

        analytics = AnalyticsService(db)
        seg = analytics.customer_segments(
            tenant_id,
            days_inactive=payload.days_inactive,
            days_new=payload.days_new,
            vip_min_orders=payload.vip_min_orders,
            vip_min_spent_cents=payload.vip_min_spent_cents,
        )
        customers = seg.get(payload.segment, {}).get("items", [])

        # Filtrar por opt-in si corresponde
        if payload.only_marketing_opt_in:
            customers = [c for c in customers if c.get("accepts_marketing", False)]

        # Límite duro
        MAX = 500
        if len(customers) > MAX:
            raise AutomationError(
                f"La campaña superaría el máximo de {MAX} destinatarios "
                f"({len(customers)} estimados). Reducí el segmento.",
                status_code=400,
                code="too_many_recipients",
            )

        sent = 0
        failed = 0
        errors: list[str] = []
        for cust in customers:
            email = cust.get("email")
            if not email:
                failed += 1
                continue
            try:
                email_service.send(
                    to=email,
                    subject=payload.subject,
                    html=f"<p>{payload.body}</p>",
                    text=payload.body,
                )
                sent += 1
            except Exception as e:
                failed += 1
                errors.append(f"{email}: {e}")

        return ActionResult(
            success=True,
            status="succeeded",
            message=(
                f"Campaña '{payload.name}' enviada: {sent} OK, {failed} fallaron."
            ),
            resource_type="campaign",
            meta={
                "sent": sent,
                "failed": failed,
                "skipped": len(customers) - sent - failed,
                "segment": payload.segment,
                "errors_sample": errors[:5],
            },
        )
    except AutomationError:
        raise
    except Exception as e:
        logger.exception("send_campaign failed")
        raise AutomationError(
            f"Error al enviar la campaña: {e}",
            status_code=500,
            code="campaign_send_failed",
        )


# ── Action Registry ────────────────────────────────────────────
# Mapa: ActionType → (handler, spec, required_role, schema_ref)
# Para agregar una acción nueva:
#   1. Definir el handler arriba (con validación Pydantic).
#   2. Agregar entrada acá.
#   3. Si la action_type no estaba en `Literal`, agregarla al schema.
REGISTRY: dict[str, dict[str, Any]] = {
    "create_promotion": {
        "handler": _handle_create_promotion,
        "required_role": "admin",  # OWNER | ADMIN
        "spec": ActionSpec(
            key="create_promotion",
            label="Crear promoción",
            description="Crea una nueva promoción en este tenant.",
            required_role="admin",
            requires_preview=True,
            params_schema={
                "name": "string (requerido, 2-160 chars)",
                "discount_type": "percent | fixed",
                "discount_value": "int >= 0",
                "starts_at": "ISO datetime o null",
                "ends_at": "ISO datetime o null",
                "applies_to_all": "bool (default true)",
                "product_ids": "list[UUID] (si no aplica a todos)",
                "category_ids": "list[UUID] (si no aplica a todos)",
            },
            example={
                "name": "2x1 Cafés",
                "discount_type": "percent",
                "discount_value": 50,
                "applies_to_all": False,
                "category_ids": ["uuid-cat-cafeteria"],
                "starts_at": "2026-08-19T00:00:00Z",
                "ends_at": "2026-08-26T23:59:59Z",
            },
        ),
    },
    "create_booking": {
        "handler": _handle_create_booking,
        "required_role": "staff",  # STAFF también puede
        "spec": ActionSpec(
            key="create_booking",
            label="Crear reserva",
            description="Agenda una reserva en nombre de un cliente.",
            required_role="staff",
            requires_preview=True,
            params_schema={
                "customer_name": "string (requerido)",
                "customer_phone": "string (requerido, 8-40 chars)",
                "customer_email": "string o null",
                "branch_id": "UUID o null",
                "starts_at": "ISO datetime (requerido)",
                "ends_at": "ISO datetime (requerido, > starts_at)",
                "price_cents": "int >= 0 (default 0)",
                "notes": "string o null",
            },
            example={
                "customer_name": "Juan Pérez",
                "customer_phone": "+56912345678",
                "customer_email": "juan@example.com",
                "starts_at": "2026-08-20T15:00:00Z",
                "ends_at": "2026-08-20T15:30:00Z",
            },
        ),
    },
    "send_campaign": {
        "handler": _handle_send_campaign,
        "required_role": "admin",  # NO staff
        "spec": ActionSpec(
            key="send_campaign",
            label="Enviar campaña",
            description="Envía una campaña de email a un segmento de clientes.",
            required_role="admin",
            requires_preview=True,
            params_schema={
                "name": "string (2-120 chars)",
                "subject": "string (2-200 chars)",
                "body": "string (2-5000 chars)",
                "segment": "all | existing | prospects | vip | inactive | new | local",
                "channel": "email (default) | log",
                "only_marketing_opt_in": "bool (default true)",
            },
            example={
                "name": "Reactivación Agosto",
                "subject": "Te extrañamos en WowHub Café",
                "body": "Hola {nombre}, tenemos novedades para vos...",
                "segment": "inactive",
            },
        ),
    },
}


# ── Permission check ───────────────────────────────────────────
def _check_permission(action_type: str, user_role: str) -> None:
    """Verifica que el rol del usuario puede ejecutar `action_type`.

    Roles: OWNER > ADMIN > STAFF > VIEWER
    VIEWER no puede ejecutar NADA (solo lectura).
    """
    if user_role == UserRole.VIEWER.value:
        raise PermissionDeniedError(action_type, user_role)

    required = REGISTRY[action_type]["required_role"]
    role_level = {
        UserRole.OWNER.value: 4,
        UserRole.ADMIN.value: 3,
        UserRole.STAFF.value: 2,
        UserRole.VIEWER.value: 1,
    }
    if role_level.get(user_role, 0) < role_level.get(required, 99):
        raise PermissionDeniedError(action_type, user_role)


# ── Preview cache (anti-CSRF, anti-doble-click) ────────────────
# Map: preview_id → (request_hash, expires_at)
# TTL = 10 minutos. Después de eso, /execute con ese preview_id falla.
_PREVIEW_CACHE: dict[str, tuple[str, datetime]] = {}
_PREVIEW_TTL_SECONDS = 600  # 10 min


def _preview_cache_put(req: AutomationRequest) -> str:
    preview_id = uuid4().hex
    # Hash estable de (action_type, params) para validar al ejecutar
    req_hash = _stable_hash(req.action_type, req.params)
    expires_at = _now_utc() + timedelta(seconds=_PREVIEW_TTL_SECONDS)
    _PREVIEW_CACHE[preview_id] = (req_hash, expires_at)
    return preview_id


def _preview_cache_validate_and_consume(preview_id: str, req: AutomationRequest) -> None:
    """Si el cliente mandó preview_id, validamos que coincida con el request
    y NO esté expirado. Si no coincide → 400. Si expiró → 400.
    """
    if preview_id not in _PREVIEW_CACHE:
        raise AutomationError(
            "preview_id inválido o expirado. Generá un nuevo preview.",
            status_code=400,
            code="invalid_preview_id",
        )
    stored_hash, expires_at = _PREVIEW_CACHE[preview_id]
    if _now_utc() > expires_at:
        del _PREVIEW_CACHE[preview_id]
        raise AutomationError(
            "El preview expiró (TTL 10 min). Generá uno nuevo.",
            status_code=400,
            code="preview_expired",
        )
    current_hash = _stable_hash(req.action_type, req.params)
    if current_hash != stored_hash:
        raise AutomationError(
            "Los params cambiaron desde el preview. Generá uno nuevo.",
            status_code=400,
            code="preview_drift",
        )
    # OK, lo consumimos (one-shot)
    del _PREVIEW_CACHE[preview_id]


def _stable_hash(action_type: str, params: dict[str, Any]) -> str:
    """Hash estable (no cripto) de (action_type, params ordenados)."""
    import hashlib
    canonical = json.dumps(
        {"a": action_type, "p": params},
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


# ── Rate limit ─────────────────────────────────────────────────
def check_automation_limit(db: Session, user_id: str) -> int:
    """Cuenta ejecuciones de automation (no previews) del usuario hoy.

    Si excede `ai_daily_automation_limit`, lanza `RateLimitExceeded`.
    Devuelve el conteo actual.
    """
    if settings.ai_daily_automation_limit <= 0:
        return 0

    # Importación local para evitar circular imports
    from app.models.automation import AutomationExecution

    start = _now_utc().replace(hour=0, minute=0, second=0, microsecond=0)
    stmt = (
        select(func.count(AutomationExecution.id))
        .where(
            AutomationExecution.user_id == user_id,
            AutomationExecution.created_at >= start,
            AutomationExecution.dry_run == False,  # noqa: E712
        )
    )
    used = db.execute(stmt).scalar_one() or 0
    if used >= settings.ai_daily_automation_limit:
        raise AutomationError(
            f"Alcanzaste el límite diario de Automation: "
            f"{int(used)}/{settings.ai_daily_automation_limit} ejecuciones.",
            status_code=429,
            code="rate_limited",
        )
    return int(used)


# ── Public API ─────────────────────────────────────────────────
def list_actions() -> list[ActionSpec]:
    """Devuelve la lista de `ActionSpec` registradas (para el frontend)."""
    return [entry["spec"] for entry in REGISTRY.values()]


def get_action_spec(action_type: str) -> ActionSpec:
    if action_type not in REGISTRY:
        raise ActionNotFoundError(action_type)
    return REGISTRY[action_type]["spec"]


def preview_action(
    db: Session,
    req: AutomationRequest,
    tenant_id: UUID,
    user_id: UUID,
    user_role: str,
) -> AutomationResponse:
    """Genera un preview de la acción (sin tocar la DB).

    VIEWER puede preview (es solo lectura). El bloqueo fuerte está en
    `execute_action` para que el viewer no rompa nada.
    """
    if req.action_type not in REGISTRY:
        raise ActionNotFoundError(req.action_type)

    handler: HandlerFn = REGISTRY[req.action_type]["handler"]
    result = handler(db, tenant_id, user_id, user_role, req.params, dry_run=True)

    # Generar preview_id (para que /execute lo referencie)
    preview_id = _preview_cache_put(req) if result.success else None

    return AutomationResponse(
        action_type=req.action_type,
        dry_run=True,
        confirmed=False,
        preview_id=preview_id,
        result=result,
        execution_id=None,
        created_at=_now_utc(),
    )


def execute_action(
    db: Session,
    req: AutomationRequest,
    tenant_id: UUID,
    user_id: UUID,
    user_role: str,
) -> AutomationResponse:
    """Ejecuta la acción. Escribe `AutomationExecution` (audit log)."""
    # 1) Validaciones básicas
    if req.action_type not in REGISTRY:
        raise ActionNotFoundError(req.action_type)
    if req.dry_run is not False or req.confirmed is not True:
        raise ConfirmationRequiredError()

    # 2) Permisos
    _check_permission(req.action_type, user_role)

    # 3) Rate limit (solo cuenta ejecuciones reales, no previews)
    check_automation_limit(db, str(user_id))

    # 4) Si vino preview_id, validarlo contra el cache
    if req.preview_id:
        try:
            _preview_cache_validate_and_consume(req.preview_id, req)
        except AutomationError:
            raise

    # 5) Ejecutar el handler
    handler: HandlerFn = REGISTRY[req.action_type]["handler"]
    result: ActionResult
    try:
        result = handler(db, tenant_id, user_id, user_role, req.params, dry_run=False)
    except AutomationError:
        # Rollback si el handler ya escribió algo
        db.rollback()
        result = ActionResult(
            success=False,
            status="failed",
            message="La acción falló. Detalles en error.",
            error="Ver respuesta.error",
        )
    except Exception as e:
        db.rollback()
        logger.exception("execute_action unexpected error")
        result = ActionResult(
            success=False,
            status="failed",
            message="Error inesperado al ejecutar la acción.",
            error=str(e),
        )

    # 6) Audit log
    from app.models.automation import AutomationExecution

    exec_log = AutomationExecution(
        tenant_id=tenant_id,
        user_id=user_id,
        action_type=req.action_type,
        status=result.status,
        dry_run=False,
        confirmed=True,
        source=req.source,
        source_insight_id=req.source_insight_id,
        notes=req.notes,
        resource_id=result.resource_id,
        resource_type=result.resource_type,
        resource_url=result.resource_url,
        error=result.error,
        params=req.params,  # JSON column
    )
    db.add(exec_log)
    try:
        db.commit()
        db.refresh(exec_log)
    except Exception:
        db.rollback()
        logger.exception("Failed to write AutomationExecution")
        # No fallamos la request entera, pero el resource YA fue creado
        # (commit del handler). El usuario recibe success=True pero sin audit.
        # Trade-off aceptado: el audit es best-effort, la creación NO.
        exec_log = None

    return AutomationResponse(
        action_type=req.action_type,
        dry_run=False,
        confirmed=True,
        preview_id=None,  # consumido
        result=result,
        execution_id=exec_log.id if exec_log else None,
        created_at=_now_utc(),
    )
