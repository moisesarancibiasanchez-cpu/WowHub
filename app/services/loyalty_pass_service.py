"""LoyaltyPassService — sistema de fidelización con tarjetas digitales (Fase 1 y 2).

Responsabilidades:
- CRUD de campañas (multi-tenant)
- Alta de clientes y emisión de pases
- Generación de tokens QR rotativos del mostrador (Fase 2)
- Validación 1-shot de jti + PIN de garzón
- Auditoría de estampillas
- Métricas simples para el admin

Diseño de seguridad:
- qr_payload del mostrador: JWT firmado con HS256, jti único, exp=60s
- qr_payload del cliente: JWT firmado con HS256, jti estable, exp=1 año
- 1-scan enforcement: la fila QrToken se marca consumed_at al primer uso
- Anti-replay: la API rechaza qr_payload con jti ya consumido
- Anti-fraude: el PIN del garzón es obligatorio si la campaña lo define
"""
from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID, uuid4

from fastapi import HTTPException
from jose import JWTError, jwt
from sqlalchemy import select, func, and_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.models.customer import Customer
from app.models.loyalty_pass import (
    CustomerPass, LoyaltyCampaign, PassSource, PassStamp, PassStatus,
    QrToken, QrTokenKind, StampReason,
)
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.loyalty import (
    CampaignCreate, CampaignUpdate, CustomerRegisterIn, PassOut, ScanOut,
)

logger = logging.getLogger("wowhub.loyalty_pass")

# ── Constantes ─────────────────────────────────────────────
QR_TOKEN_TTL_SECONDS = 60            # vida útil de cada QR del mostrador
QR_TOKEN_MAX_CLOCK_SKEW = 5          # tolerancia en segundos
PASS_QR_TTL_DAYS = 365               # vida útil del pass del cliente
MAX_STAMPS_PER_SCAN = 1              # Fase 1: 1 sello por scan


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _hash_pin(pin: str) -> str:
    """Hash determinístico del PIN (no es password, no necesita sal)."""
    return hashlib.sha256(pin.encode("utf-8")).hexdigest()


# ── Campaign CRUD ──────────────────────────────────────────
class LoyaltyPassService:
    def __init__(self, db: Session, tenant_id: str):
        self.db = db
        self.tenant_id = tenant_id

    # ── Campañas ───────────────────────────────────────────
    def list_campaigns(self, include_inactive: bool = False) -> list[LoyaltyCampaign]:
        q = select(LoyaltyCampaign).where(LoyaltyCampaign.tenant_id == self.tenant_id)
        if not include_inactive:
            q = q.where(LoyaltyCampaign.is_active.is_(True))
        q = q.order_by(LoyaltyCampaign.created_at.desc())
        return list(self.db.execute(q).scalars())

    def get_campaign(self, campaign_id: UUID) -> Optional[LoyaltyCampaign]:
        return self.db.execute(
            select(LoyaltyCampaign).where(
                LoyaltyCampaign.id == str(campaign_id),
                LoyaltyCampaign.tenant_id == self.tenant_id,
            )
        ).scalar_one_or_none()

    def create_campaign(self, payload: CampaignCreate) -> LoyaltyCampaign:
        data = payload.model_dump()
        pin = data.pop("cashier_pin", None)
        if pin:
            data["cashier_pin"] = _hash_pin(pin)
        c = LoyaltyCampaign(**data, tenant_id=self.tenant_id)
        self.db.add(c)
        self.db.commit()
        self.db.refresh(c)
        return c

    def update_campaign(
        self, campaign_id: UUID, payload: CampaignUpdate
    ) -> Optional[LoyaltyCampaign]:
        c = self.get_campaign(campaign_id)
        if not c:
            return None
        data = payload.model_dump(exclude_unset=True)
        pin = data.pop("cashier_pin", None)
        if pin is not None:
            if pin == "":
                # Se permite quitar el PIN pasando string vacío
                c.cashier_pin = None
            else:
                c.cashier_pin = _hash_pin(pin)
        for k, v in data.items():
            setattr(c, k, v)
        self.db.commit()
        self.db.refresh(c)
        return c

    def archive_campaign(self, campaign_id: UUID) -> bool:
        c = self.get_campaign(campaign_id)
        if not c:
            return False
        c.is_active = False
        self.db.commit()
        return True

    # ── Customer alta + emisión de pass ───────────────────
    def register_customer(
        self, payload: CustomerRegisterIn, campaign_id: UUID,
    ) -> tuple[Customer, CustomerPass]:
        """Crea o reusa un Customer para este tenant, y emite un Pass.

        - Reusa el Customer por email o phone si existe
        - Crea un nuevo Pass (o reusa el activo)
        """
        campaign = self.get_campaign(campaign_id)
        if not campaign or not campaign.is_active:
            raise HTTPException(404, "Campaña no encontrada o inactiva")

        # Validar que al menos uno venga
        if not payload.email and not payload.phone:
            raise HTTPException(422, "Debes proporcionar email o teléfono")

        # Buscar customer existente por email/phone
        q = select(Customer).where(
            Customer.tenant_id == self.tenant_id,
            Customer.is_active.is_(True),
        )
        if payload.email:
            q = q.where(Customer.email == payload.email)
        elif payload.phone:
            q = q.where(Customer.phone == payload.phone)
        customer = self.db.execute(q).scalar_one_or_none()

        if not customer:
            customer = Customer(
                tenant_id=self.tenant_id,
                full_name=payload.full_name,
                email=payload.email,
                phone=payload.phone,
                accepts_marketing=payload.accepts_marketing,
                is_active=True,
            )
            self.db.add(customer)
            self.db.flush()  # para tener ID
        else:
            # Actualizar nombre si viene
            if payload.full_name and payload.full_name != customer.full_name:
                customer.full_name = payload.full_name

        # Buscar pass existente para este (customer, campaign)
        existing = self.db.execute(
            select(CustomerPass).where(
                CustomerPass.tenant_id == self.tenant_id,
                CustomerPass.campaign_id == str(campaign.id),
                CustomerPass.customer_id == str(customer.id),
            )
        ).scalar_one_or_none()

        if existing and existing.status in (PassStatus.ACTIVE.value, PassStatus.REDEEMED.value):
            # Reusar el existente (reissue si fue redeemed)
            if existing.status == PassStatus.REDEEMED.value:
                existing.status = PassStatus.ACTIVE.value
                existing.stamps_current = 0
            # Refrescar qr_payload
            existing.qr_payload = self._mint_pass_qr(existing)
            existing.last_stamp_at = None
            self.db.commit()
            self.db.refresh(existing)
            return customer, existing

        # Crear pass nuevo
        serial = self._build_serial(customer.id, campaign.id)
        now = _now()
        pass_obj = CustomerPass(
            tenant_id=self.tenant_id,
            campaign_id=str(campaign.id),
            customer_id=str(customer.id),
            serial_number=serial,
            source=PassSource.WEB.value,
            status=PassStatus.ACTIVE.value,
            stamps_current=0,
            rewards_earned=0,
            qr_payload="",  # se setea abajo
            installed_at=now,
            expires_at=now + timedelta(days=PASS_QR_TTL_DAYS),
        )
        self.db.add(pass_obj)
        self.db.flush()
        pass_obj.qr_payload = self._mint_pass_qr(pass_obj)
        # Métrica denormalizada
        campaign.total_passes = (campaign.total_passes or 0) + 1
        try:
            self.db.commit()
        except IntegrityError as e:
            self.db.rollback()
            logger.warning("Pass duplicado al registrar: %s", e)
            raise HTTPException(409, "Este cliente ya tiene un pase para esta campaña")
        self.db.refresh(pass_obj)
        return customer, pass_obj

    def get_pass_by_serial(self, serial: str) -> Optional[CustomerPass]:
        return self.db.execute(
            select(CustomerPass).where(
                CustomerPass.tenant_id == self.tenant_id,
                CustomerPass.serial_number == serial,
            )
        ).scalar_one_or_none()

    # ── QR Token (mostrador, rotativo) ─────────────────────
    def issue_counter_qr_token(
        self, campaign_id: UUID, user: User, device_fp: Optional[str] = None,
        ttl_seconds: int = QR_TOKEN_TTL_SECONDS,
    ) -> QrToken:
        """Genera un nuevo token QR para el mostrador. 1-shot."""
        campaign = self.get_campaign(campaign_id)
        if not campaign or not campaign.is_active:
            raise HTTPException(404, "Campaña no encontrada o inactiva")

        jti = secrets.token_urlsafe(24)
        now = _now()
        token = QrToken(
            tenant_id=self.tenant_id,
            campaign_id=str(campaign.id),
            jti=jti,
            created_by=str(user.id),
            kind=QrTokenKind.COUNTER.value,
            expires_at=now + timedelta(seconds=ttl_seconds),
            device_fp=device_fp,
        )
        # Firmamos el payload (el QR que se imprime)
        token.qr_payload = self._sign_qr_token(
            jti=jti,
            tenant_id=self.tenant_id,
            campaign_id=str(campaign.id),
            kind=QrTokenKind.COUNTER.value,
            expires_at=token.expires_at,
        )
        self.db.add(token)
        self.db.commit()
        self.db.refresh(token)
        return token

    def validate_counter_qr_token(
        self, qr_payload: str, expected_campaign_id: Optional[str] = None,
    ) -> QrToken:
        """Valida y consume un token del mostrador.

        Returns: QrToken (la fila original) si todo OK.
        Raises HTTPException con error_code si algo falla.
        """
        try:
            claims = jwt.decode(
                qr_payload, settings.jwt_secret, algorithms=[settings.jwt_algorithm],
            )
        except JWTError as e:
            raise HTTPException(401, f"QR inválido: {e}")

        # Validar que sea un token de mostrador (no un pass de cliente)
        if claims.get("kind") != QrTokenKind.COUNTER.value:
            raise HTTPException(401, "Este QR no es del mostrador")

        # Validar tenant (aislamiento)
        if claims.get("tid") != self.tenant_id:
            raise HTTPException(403, "QR de otro comercio")

        jti = claims.get("jti")
        if not jti:
            raise HTTPException(401, "QR sin jti")

        # Validar exp con tolerancia
        exp = claims.get("exp")
        if exp is not None:
            now_ts = int(_now().timestamp())
            if now_ts > int(exp) + QR_TOKEN_MAX_CLOCK_SKEW:
                raise HTTPException(401, "QR expirado — solicita uno nuevo")

        # Buscar fila y validar estado
        token = self.db.execute(
            select(QrToken).where(
                QrToken.jti == jti,
                QrToken.tenant_id == self.tenant_id,
            )
        ).scalar_one_or_none()
        if not token:
            raise HTTPException(401, "QR no encontrado")

        if expected_campaign_id and str(token.campaign_id) != str(expected_campaign_id):
            raise HTTPException(400, "QR no corresponde a esta campaña")

        if token.consumed_at is not None:
            # Anti-replay: el token ya se usó
            raise HTTPException(409, "Este QR ya fue usado")

        if token.expires_at.replace(tzinfo=timezone.utc) < (_now() - timedelta(seconds=QR_TOKEN_MAX_CLOCK_SKEW)):
            raise HTTPException(401, "QR expirado")

        return token

    # ── Scan (POS) ─────────────────────────────────────────
    def scan(
        self,
        qr_payload: str,
        pass_serial: str,
        cashier_pin: Optional[str],
        device_fp: Optional[str],
        user: User,
    ) -> ScanOut:
        """Procesa un escaneo del POS. Suma 1 sello al pass.

        Validaciones:
          1. qr_payload del mostrador es válido, vigente, 1-shot
          2. pass_serial existe y está activo
          3. PIN de garzón si la campaña lo requiere
          4. campaign del token == campaign del pass
        """
        # 1) Validar y obtener el token del mostrador
        try:
            token = self.validate_counter_qr_token(qr_payload)
        except HTTPException as e:
            return ScanOut(ok=False, error=str(e.detail), error_code="qr_invalid")

        # 2) Buscar el pass del cliente
        customer_pass = self.get_pass_by_serial(pass_serial)
        if not customer_pass:
            return ScanOut(ok=False, error="Pase no encontrado", error_code="pass_not_found")
        if customer_pass.status not in (PassStatus.ACTIVE.value, PassStatus.REDEEMED.value):
            return ScanOut(ok=False, error=f"Pase en estado {customer_pass.status}", error_code="pass_inactive")
        if str(customer_pass.tenant_id) != str(self.tenant_id):
            return ScanOut(ok=False, error="Pase de otro comercio", error_code="tenant_mismatch")
        if str(customer_pass.campaign_id) != str(token.campaign_id):
            return ScanOut(ok=False, error="El QR del mostrador y el pase son de campañas distintas",
                           error_code="campaign_mismatch")

        # 3) PIN de garzón
        campaign = self.get_campaign(UUID(str(token.campaign_id)))
        if campaign.cashier_pin:
            if not cashier_pin or _hash_pin(cashier_pin) != campaign.cashier_pin:
                return ScanOut(ok=False, error="PIN incorrecto", error_code="pin_invalid")

        # 4) Marcar el token como consumido (atómico: 1-shot)
        token.consumed_at = _now()
        token.consumed_by_pass = str(customer_pass.id)
        token.consumed_by_user = str(user.id)

        # 5) Si el pass está en estado REDEEMED, lo reseteamos a 0 antes
        if customer_pass.status == PassStatus.REDEEMED.value:
            customer_pass.status = PassStatus.ACTIVE.value
            customer_pass.stamps_current = 0

        # 6) Sumar sello
        customer_pass.stamps_current = (customer_pass.stamps_current or 0) + MAX_STAMPS_PER_SCAN
        customer_pass.last_stamp_at = _now()

        reward_unlocked = False
        if customer_pass.stamps_current >= campaign.stamps_required:
            customer_pass.stamps_current = 0
            customer_pass.rewards_earned = (customer_pass.rewards_earned or 0) + 1
            customer_pass.status = PassStatus.REDEEMED.value
            customer_pass.redeemed_at = _now()
            reward_unlocked = True
            campaign.total_rewards_redeemed = (campaign.total_rewards_redeemed or 0) + 1

        campaign.total_stamps_issued = (campaign.total_stamps_issued or 0) + 1

        # 7) Auditoría
        stamp = PassStamp(
            tenant_id=self.tenant_id,
            pass_id=str(customer_pass.id),
            campaign_id=str(campaign.id),
            delta=MAX_STAMPS_PER_SCAN,
            reason=StampReason.SCAN.value,
            scanned_by=str(user.id),
            cashier_pin_validated=bool(campaign.cashier_pin),
            device_fp=device_fp,
            qr_token_jti=token.jti,
            stamps_after=customer_pass.stamps_current,
            reward_unlocked=reward_unlocked,
        )
        self.db.add(stamp)
        self.db.commit()
        self.db.refresh(customer_pass)
        self.db.refresh(campaign)

        # 8) Refrescar el qr_payload del cliente (rotación post-scan opcional)
        # En Fase 1 NO rotamos el del cliente — solo el del mostrador.

        return ScanOut(
            ok=True,
            error=None,
            error_code=None,
            pass_=self._to_pass_out(customer_pass, campaign),
            reward_unlocked=reward_unlocked,
            reward_label=campaign.reward_label if reward_unlocked else None,
            stamps_after=customer_pass.stamps_current,
        )

    # ── Métricas (placeholder Fase 5) ─────────────────────
    def basic_metrics(self, campaign_id: UUID) -> dict:
        c = self.get_campaign(campaign_id)
        if not c:
            raise HTTPException(404, "Campaña no encontrada")
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        stamps_today = self.db.execute(
            select(func.count()).select_from(PassStamp).where(
                PassStamp.tenant_id == self.tenant_id,
                PassStamp.campaign_id == str(campaign_id),
                PassStamp.created_at >= today_start,
            )
        ).scalar_one() or 0
        rewards_today = self.db.execute(
            select(func.count()).select_from(PassStamp).where(
                PassStamp.tenant_id == self.tenant_id,
                PassStamp.campaign_id == str(campaign_id),
                PassStamp.created_at >= today_start,
                PassStamp.reward_unlocked.is_(True),
            )
        ).scalar_one() or 0
        active = self.db.execute(
            select(func.count()).select_from(CustomerPass).where(
                CustomerPass.tenant_id == self.tenant_id,
                CustomerPass.campaign_id == str(campaign_id),
                CustomerPass.status.in_([PassStatus.ACTIVE.value, PassStatus.REDEEMED.value]),
            )
        ).scalar_one() or 0
        # Conversión: scans que terminaron en reward
        total_scans = self.db.execute(
            select(func.count()).select_from(PassStamp).where(
                PassStamp.tenant_id == self.tenant_id,
                PassStamp.campaign_id == str(campaign_id),
                PassStamp.reason == StampReason.SCAN.value,
            )
        ).scalar_one() or 0
        conv = (c.total_rewards_redeemed / c.total_stamps_issued) if c.total_stamps_issued else 0.0
        return {
            "campaign_id": str(c.id),
            "active_passes": int(active),
            "total_stamps_today": int(stamps_today),
            "total_rewards_today": int(rewards_today),
            "total_scans": int(total_scans),
            "conversion_rate": float(conv),
            "avg_stamps_to_reward": (
                float(c.total_stamps_issued) / float(c.total_rewards_redeemed)
                if c.total_rewards_redeemed else 0.0
            ),
        }

    # ── Helpers internos ──────────────────────────────────
    def _build_serial(self, customer_id, campaign_id) -> str:
        # serial = wh:<tenant>:<campaign>:<customer>  (estable, no opaco al cliente
        # para que el owner pueda buscarlo, pero suficientemente identificable)
        return f"wh:{self.tenant_id[:8]}:{str(campaign_id)[:8]}:{str(customer_id)[:8]}"

    def _mint_pass_qr(self, pass_obj: CustomerPass) -> str:
        """Firma el QR del cliente (no 1-shot, dura PASS_QR_TTL_DAYS)."""
        return self._sign_pass_qr(
            tenant_id=self.tenant_id,
            serial=pass_obj.serial_number,
            campaign_id=str(pass_obj.campaign_id),
            customer_id=str(pass_obj.customer_id),
            expires_at=pass_obj.expires_at or (_now() + timedelta(days=PASS_QR_TTL_DAYS)),
        )

    def _sign_qr_token(
        self, *, jti: str, tenant_id: str, campaign_id: str, kind: str,
        expires_at: datetime,
    ) -> str:
        now = _now()
        payload = {
            "sub": "wowhub_qr_token",
            "jti": jti,
            "tid": tenant_id,
            "cid": campaign_id,
            "kind": kind,
            "iat": int(now.timestamp()),
            "exp": int(expires_at.timestamp()),
        }
        return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)

    def _sign_pass_qr(
        self, *, tenant_id: str, serial: str, campaign_id: str, customer_id: str,
        expires_at: datetime,
    ) -> str:
        now = _now()
        payload = {
            "sub": "wowhub_customer_pass",
            "jti": serial,            # usamos el serial como jti estable
            "tid": tenant_id,
            "cid": campaign_id,
            "cuid": customer_id,
            "kind": "pass",
            "iat": int(now.timestamp()),
            "exp": int(expires_at.timestamp()),
        }
        return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)

    def _to_pass_out(self, p: CustomerPass, c: LoyaltyCampaign) -> PassOut:
        return PassOut(
            id=p.id,
            campaign_id=p.campaign_id,
            serial_number=p.serial_number,
            status=PassStatus(p.status),
            stamps_current=p.stamps_current,
            stamps_required=c.stamps_required,
            rewards_earned=p.rewards_earned,
            reward_label=c.reward_label,
            primary_color=c.primary_color,
            text_color=c.text_color,
            logo_url=c.logo_url,
            icon_url=c.icon_url,
            accent_color=c.accent_color,
            # V2 metallic gradient — 5 stops + angle + sheen
            metal_c1=c.metal_c1,
            metal_c2=c.metal_c2,
            metal_c3=c.metal_c3,
            metal_c4=c.metal_c4,
            metal_c5=c.metal_c5,
            metal_angle=c.metal_angle,
            sheen_opacity=c.sheen_opacity,
            qr_payload=p.qr_payload,
            last_stamp_at=p.last_stamp_at,
            installed_at=p.installed_at,
            expires_at=p.expires_at,
        )


# ── Helpers públicos (estáticos, sin estado) ───────────────
def get_tenant_by_slug(db: Session, slug: str) -> Optional[Tenant]:
    return db.execute(select(Tenant).where(Tenant.slug == slug)).scalar_one_or_none()


def get_active_campaign_by_slug(db: Session, slug: str) -> Optional[LoyaltyCampaign]:
    """Para el landing público: tenant + primera campaña activa."""
    t = get_tenant_by_slug(db, slug)
    if not t or not t.is_active:
        return None
    return db.execute(
        select(LoyaltyCampaign).where(
            LoyaltyCampaign.tenant_id == str(t.id),
            LoyaltyCampaign.is_active.is_(True),
        ).order_by(LoyaltyCampaign.created_at.desc()).limit(1)
    ).scalar_one_or_none()
