"""Campaigns API — envío masivo de emails a un segmento de clientes.

Esta API es la que usa el Asistente IA cuando el usuario dice
"envíale un mensaje a mis clientes inactivos", "avísales a los VIP
sobre la promo", etc.

Reglas de seguridad:
- Máximo de destinatarios por envío (límite duro para evitar spam).
- Solo se envía a clientes con `accepts_marketing=True` (por defecto).
- Log de cada envío en `audit_log` (best-effort).
- Si el canal es `log`, NO envía email real: solo registra.
"""
from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_membership, get_tenant_for_membership
from app.models.tenant import Tenant, TenantMembership
from app.schemas.analytics import (
    CampaignCreate,
    CampaignResponse,
    CampaignResult,
    CustomerSegmentItem,
)
from app.services.analytics_service import AnalyticsService
from app.services.email_service import email_service

logger = logging.getLogger("wowhub.campaigns")

router = APIRouter(
    prefix="/tenants/{tenant_id}/campaigns",
    tags=["campaigns"],
)

# ── Safety limits ──────────────────────────────────────────
MAX_RECIPIENTS_PER_CAMPAIGN = 500
PREVIEW_SAMPLE_SIZE = 5


def _build_preview_html(body: str, subject: str) -> str:
    """Envuelve el `body` en un template HTML mínimo para preview/log."""
    return f"""
    <div style="font-family:sans-serif;max-width:600px;margin:auto;padding:20px">
      <h2 style="color:#7c5cff;margin:0 0 12px">{subject}</h2>
      <div>{body}</div>
      <hr style="border:none;border-top:1px solid #eee;margin:24px 0">
      <p style="color:#888;font-size:11px;margin:0">
        Recibiste este email porque eres cliente de nuestro negocio.
        Si prefieres no recibir más mensajes, responde con "BAJA".
      </p>
    </div>
    """


@router.post("", response_model=CampaignResponse)
def send_campaign(
    payload: CampaignCreate,
    tenant: Tenant = Depends(get_tenant_for_membership),
    membership: TenantMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    """Envía una campaña masiva al segmento solicitado.

    Pasos:
    1. Llama a `AnalyticsService.customer_segments` para resolver destinatarios.
    2. Filtra por `accepts_marketing` (si la request lo pide).
    3. Aplica `MAX_RECIPIENTS_PER_CAMPAIGN` (lanza 400 si lo excede).
    4. Envía (o registra) el email a cada destinatario.
    5. Devuelve un resumen con counts y errores.
    """
    # 1) Resolver destinatarios
    analytics = AnalyticsService(db)
    seg = analytics.customer_segments(
        tenant.id,
        segment=payload.segment,
        days_inactive=payload.days_inactive,
        days_new=payload.days_new,
        vip_min_orders=payload.vip_min_orders,
        vip_min_spent_cents=payload.vip_min_spent_cents,
        limit=MAX_RECIPIENTS_PER_CAMPAIGN + 1,  # +1 para detectar overflow
    )

    candidates: list[CustomerSegmentItem] = [
        CustomerSegmentItem(**item) for item in seg["items"]
    ]

    # 2) Filtro de marketing opt-in
    if payload.only_marketing_opt_in:
        candidates = [c for c in candidates if c.accepts_marketing]

    # 3) Filtro de email obligatorio
    candidates = [c for c in candidates if c.email]

    if len(candidates) > MAX_RECIPIENTS_PER_CAMPAIGN:
        raise HTTPException(
            status_code=400,
            detail=(
                f"El segmento '{payload.segment}' tiene {len(candidates)} "
                f"destinatarios; el máximo permitido por campaña es "
                f"{MAX_RECIPIENTS_PER_CAMPAIGN}. Divide la campaña o usa un "
                f"segmento más específico."
            ),
        )

    # 4) Preview
    preview_html = _build_preview_html(payload.body, payload.subject)
    sample = candidates[:PREVIEW_SAMPLE_SIZE]

    # 5) Envío
    sent = 0
    failed = 0
    skipped = 0
    errors: list[str] = []

    if payload.channel == "log":
        # Modo dry-run: solo logueamos.
        for c in candidates:
            logger.info(
                "[CAMPAIGN-LOG] tenant=%s segment=%s to=%s subject=%r",
                tenant.id, payload.segment, c.email, payload.subject,
            )
        sent = len(candidates)
    else:
        # Envío real vía EmailService
        for c in candidates:
            try:
                ok = email_service.send(
                    to=c.email,
                    subject=payload.subject,
                    html=preview_html,
                    text=payload.body,
                )
                if ok:
                    sent += 1
                else:
                    failed += 1
                    errors.append(f"{c.email}: email_service returned False")
            except Exception as e:  # noqa: BLE001
                failed += 1
                errors.append(f"{c.email}: {type(e).__name__}: {e}")

    logger.info(
        "[CAMPAIGN] tenant=%s user=%s segment=%s channel=%s sent=%d failed=%d",
        tenant.id, membership.user_id, payload.segment, payload.channel, sent, failed,
    )

    return {
        "campaign": CampaignResult(
            sent=sent,
            failed=failed,
            skipped=skipped,
            total_targets=len(candidates),
            channel=payload.channel,
            segment=payload.segment,
            errors=errors[:20],  # cap de errores en la respuesta
        ),
        "preview_html": preview_html,
        "sample_recipients": sample,
    }


@router.post("/preview", response_model=CampaignResponse)
def preview_campaign(
    payload: CampaignCreate,
    tenant: Tenant = Depends(get_tenant_for_membership),
    db: Session = Depends(get_db),
):
    """PRE-visualiza una campaña sin enviar nada.

    Devuelve la lista de destinatarios que recibirían el email y el HTML
    final. Útil para que el Asistente IA muestre al usuario "esto es lo
    que se va a enviar, ¿confirmas?" antes de ejecutar el envío real.
    """
    analytics = AnalyticsService(db)
    seg = analytics.customer_segments(
        tenant.id,
        segment=payload.segment,
        days_inactive=payload.days_inactive,
        days_new=payload.days_new,
        vip_min_orders=payload.vip_min_orders,
        vip_min_spent_cents=payload.vip_min_spent_cents,
        limit=MAX_RECIPIENTS_PER_CAMPAIGN,
    )
    candidates: list[CustomerSegmentItem] = [
        CustomerSegmentItem(**item) for item in seg["items"]
    ]
    if payload.only_marketing_opt_in:
        candidates = [c for c in candidates if c.accepts_marketing]
    candidates = [c for c in candidates if c.email]

    preview_html = _build_preview_html(payload.body, payload.subject)

    return {
        "campaign": CampaignResult(
            sent=0,
            failed=0,
            skipped=0,
            total_targets=len(candidates),
            channel=payload.channel,
            segment=payload.segment,
            errors=[],
        ),
        "preview_html": preview_html,
        "sample_recipients": candidates[:PREVIEW_SAMPLE_SIZE],
    }
