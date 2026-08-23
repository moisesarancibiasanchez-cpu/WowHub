"""Loyalty Pass API — endpoints para owner, POS y cliente.

Tres grupos de endpoints:
  /api/v1/tenants/{tenant_id}/loyalty/*      → owner (autenticado)
  /api/v1/loyalty/scan                       → POS (autenticado: garzón u owner)
  /api/v1/loyalty/c/{slug}/*                 → público (cliente, rate-limited)
"""
from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.core.errors import ForbiddenError, NotFoundError
from app.database import get_db
from app.deps import get_current_membership, get_current_user, get_tenant_for_membership
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.loyalty import (
    CampaignCreate, CampaignMetrics, CampaignOut, CampaignUpdate,
    CustomerLookupIn, CustomerRegisterIn, PassOut, QrTokenOut, ScanIn, ScanOut,
)
from app.services.loyalty_pass_service import (
    LoyaltyPassService, QR_TOKEN_TTL_SECONDS, get_active_campaign_by_slug,
    get_tenant_by_slug,
)

logger = logging.getLogger("wowhub.api.loyalty")

# ── Routers ────────────────────────────────────────────────
owner_router = APIRouter(prefix="/tenants/{tenant_id}/loyalty", tags=["loyalty"])
pos_router = APIRouter(prefix="/loyalty", tags=["loyalty"])
public_router = APIRouter(prefix="/loyalty", tags=["loyalty-public"])


# ── Helpers ───────────────────────────────────────────────
def _service(db: Session, tenant_id: str) -> LoyaltyPassService:
    return LoyaltyPassService(db, tenant_id=str(tenant_id))


# ════════════════════════════════════════════════════════════
# OWNER endpoints
# ════════════════════════════════════════════════════════════
@owner_router.get("/campaigns", response_model=list[CampaignOut])
def list_campaigns(
    tenant_id: UUID,
    include_inactive: bool = Query(False),
    user: User = Depends(get_current_user),
    membership=Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    svc = _service(db, tenant_id)
    items = svc.list_campaigns(include_inactive=include_inactive)
    out = []
    for c in items:
        co = CampaignOut.model_validate(c)
        co.cashier_pin_set = bool(c.cashier_pin)
        out.append(co)
    return out


@owner_router.post("/campaigns", response_model=CampaignOut, status_code=201)
def create_campaign(
    tenant_id: UUID,
    payload: CampaignCreate,
    user: User = Depends(get_current_user),
    membership=Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    svc = _service(db, tenant_id)
    c = svc.create_campaign(payload)
    out = CampaignOut.model_validate(c)
    out.cashier_pin_set = bool(c.cashier_pin)
    return out


@owner_router.get("/campaigns/{campaign_id}", response_model=CampaignOut)
def get_campaign(
    tenant_id: UUID,
    campaign_id: UUID,
    user: User = Depends(get_current_user),
    membership=Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    svc = _service(db, tenant_id)
    c = svc.get_campaign(campaign_id)
    if not c:
        raise HTTPException(404, "Campaña no encontrada")
    out = CampaignOut.model_validate(c)
    out.cashier_pin_set = bool(c.cashier_pin)
    return out


@owner_router.patch("/campaigns/{campaign_id}", response_model=CampaignOut)
def update_campaign(
    tenant_id: UUID,
    campaign_id: UUID,
    payload: CampaignUpdate,
    user: User = Depends(get_current_user),
    membership=Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    svc = _service(db, tenant_id)
    c = svc.update_campaign(campaign_id, payload)
    if not c:
        raise HTTPException(404, "Campaña no encontrada")
    out = CampaignOut.model_validate(c)
    out.cashier_pin_set = bool(c.cashier_pin)
    return out


@owner_router.delete("/campaigns/{campaign_id}", status_code=204)
def archive_campaign(
    tenant_id: UUID,
    campaign_id: UUID,
    user: User = Depends(get_current_user),
    membership=Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    svc = _service(db, tenant_id)
    if not svc.archive_campaign(campaign_id):
        raise HTTPException(404, "Campaña no encontrada")
    return None


@owner_router.get("/campaigns/{campaign_id}/metrics", response_model=CampaignMetrics)
def get_campaign_metrics(
    tenant_id: UUID,
    campaign_id: UUID,
    user: User = Depends(get_current_user),
    membership=Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    svc = _service(db, tenant_id)
    m = svc.basic_metrics(campaign_id)
    return CampaignMetrics(
        campaign_id=m["campaign_id"],
        active_passes=m["active_passes"],
        total_stamps_today=m["total_stamps_today"],
        total_rewards_today=m["total_rewards_today"],
        conversion_rate=m["conversion_rate"],
        avg_stamps_to_reward=m["avg_stamps_to_reward"],
    )


# ── QR Token (mostrador) ───────────────────────────────────
@owner_router.post("/campaigns/{campaign_id}/qr-token", response_model=QrTokenOut)
def issue_qr_token(
    tenant_id: UUID,
    campaign_id: UUID,
    device_fp: Optional[str] = Query(None, max_length=64),
    user: User = Depends(get_current_user),
    membership=Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    """Genera un nuevo token QR para imprimir en el mostrador.

    El frontend debe llamar a este endpoint cada 60s (auto-refresh).
    """
    svc = _service(db, tenant_id)
    token = svc.issue_counter_qr_token(campaign_id, user, device_fp=device_fp)
    return QrTokenOut(
        jti=token.jti,
        qr_payload=token.qr_payload,
        expires_at=token.expires_at,
        refresh_in_seconds=QR_TOKEN_TTL_SECONDS,
    )


# ════════════════════════════════════════════════════════════
# POS endpoints (autenticado: garzón u owner)
# ════════════════════════════════════════════════════════════
@pos_router.post("/scan", response_model=ScanOut)
def scan(
    payload: ScanIn,
    tenant: Tenant = Depends(get_tenant_for_membership),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Endpoint del escáner del POS.

    El frontend (admin/scanner) llama aquí después de leer:
    - el QR del mostrador (giratorio, con TTL 60s)
    - el QR del pass del cliente
    - opcionalmente, el PIN del garzón (si la campaña lo pide)
    """
    svc = _service(db, tenant_id=str(tenant.id))
    return svc.scan(
        qr_payload=payload.qr_payload,
        pass_serial=payload.pass_serial,
        cashier_pin=payload.cashier_pin,
        device_fp=payload.device_fp,
        user=user,
    )


# ════════════════════════════════════════════════════════════
# PUBLIC endpoints (cliente, sin auth, rate-limited via middleware)
# ════════════════════════════════════════════════════════════
@public_router.get("/c/{slug}/campaign")
def get_public_campaign(
    slug: str,
    db: Session = Depends(get_db),
):
    """Devuelve la info pública de la campaña activa de un tenant.

    NO expone PII, solo lo necesario para que el cliente vea la tarjeta
    y sepa qué recompensa obtiene.
    """
    campaign = get_active_campaign_by_slug(db, slug)
    if not campaign:
        raise HTTPException(404, "Comercio no encontrado o sin campaña activa")
    # Accedemos al tenant por slug (no hay relationship en el modelo)
    tenant = get_tenant_by_slug(db, slug)
    tenant_name = tenant.display_name if tenant else None
    return {
        "tenant_slug": slug,
        "tenant_name": tenant_name,
        "campaign": {
            "id": str(campaign.id),
            "name": campaign.name,
            "reward_label": campaign.reward_label,
            "stamps_required": campaign.stamps_required,
            "primary_color": campaign.primary_color,
            "text_color": campaign.text_color,
            "accent_color": campaign.accent_color,
            "logo_url": campaign.logo_url,
            "icon_url": campaign.icon_url,
        },
    }


@public_router.post("/c/{slug}/register", response_model=PassOut)
def public_register(
    slug: str,
    payload: CustomerRegisterIn,
    db: Session = Depends(get_db),
):
    """Alta rápida: el cliente se registra y obtiene su pase (PassOut)."""
    campaign = get_active_campaign_by_slug(db, slug)
    if not campaign:
        raise HTTPException(404, "Comercio no encontrado o sin campaña activa")
    svc = LoyaltyPassService(db, tenant_id=str(campaign.tenant_id))
    customer, pass_obj = svc.register_customer(payload, UUID(str(campaign.id)))
    return svc._to_pass_out(pass_obj, campaign)


# ── Lookup: recuperar un pase existente por email/phone (Fase 8) ──
# Diseño anti-enumeración: respondemos 404 (no 200 con datos parciales)
# si no hay match exacto. Rate-limit global del middleware ya protege
# contra fuerza bruta. Devolvemos el PassOut más reciente del cliente
# para esta campaña (si tiene varios, el primero emitido; en la práctica
# solo hay 1 pase activo por (cliente, campaña)).
@public_router.post("/c/{slug}/lookup", response_model=Optional[PassOut])
def public_lookup(
    slug: str,
    payload: CustomerLookupIn,  # schema laxo: solo email y phone
    db: Session = Depends(get_db),
):
    """Recuperar un pase existente por email o teléfono.

    Input: { email?, phone? }  (al menos uno requerido)
    Output: PassOut si hay match, 404 si no.
    """
    email = (payload.email or "").strip().lower() if payload.email else None
    phone = (payload.phone or "").strip() if payload.phone else None
    if not email and not phone:
        raise HTTPException(400, "Ingresa al menos email o teléfono.")
    campaign = get_active_campaign_by_slug(db, slug)
    if not campaign:
        raise HTTPException(404, "Comercio no encontrado o sin campaña activa")

    # Buscar cliente (tabla customers) que matchee por email o phone
    # en el tenant de la campaña. La tabla customers es multi-tenant.
    from sqlalchemy import select, or_
    from app.models.customer import Customer
    from app.models.loyalty_pass import CustomerPass

    stmt = select(Customer).where(
        Customer.tenant_id == str(campaign.tenant_id),
    )
    if email and phone:
        stmt = stmt.where(or_(Customer.email == email, Customer.phone == phone))
    elif email:
        stmt = stmt.where(Customer.email == email)
    else:
        stmt = stmt.where(Customer.phone == phone)
    customer = db.execute(stmt).scalar_one_or_none()
    if not customer:
        raise HTTPException(404, "No encontramos una tarjeta con esos datos.")

    # Buscar el pase más reciente (no redimido/revocado) del cliente
    # para esta campaña. Si no hay para ESTA campaña, devolvemos 404
    # (puede tener un pase en otra campaña, pero acá no aplica).
    pass_row = db.execute(
        select(CustomerPass)
        .where(
            CustomerPass.customer_id == str(customer.id),
            CustomerPass.campaign_id == str(campaign.id),
        )
        .order_by(CustomerPass.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    if not pass_row:
        raise HTTPException(404, "No hay un pase activo para este cliente en este comercio.")

    svc = LoyaltyPassService(db, tenant_id=str(campaign.tenant_id))
    return svc._to_pass_out(pass_row, campaign)
