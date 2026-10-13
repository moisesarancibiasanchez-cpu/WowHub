"""Password reset & email verification API."""
import logging
import os

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.database import get_db
from app.models.user import User
from app.schemas.password import (
    ForgotPasswordRequest, PasswordResetResponse,
    ResetPasswordRequest, VerifyEmailRequest,
)
from app.services.audit_service import AuditService, request_meta
from app.services.email_service import email_service
from app.services.password_service import PasswordService, validate_password_strength

logger = logging.getLogger("wowhub.password_api")
router = APIRouter(tags=["auth"])


@router.post("/auth/forgot-password", response_model=PasswordResetResponse)
def forgot_password(payload: ForgotPasswordRequest, request: Request, db: Session = Depends(get_db)):
    """Solicita un email de recuperación de contraseña.

    Por seguridad, siempre retorna 200 sin revelar si el email existe.
    HU_40 — audita ``auth.password_forgot`` con actor=None y email en ``extra``
    (no revelamos en logs si el email existe, sólo registramos la solicitud).
    """
    svc = PasswordService(db)
    token = svc.request_reset(payload.email.lower(), base_url=os.getenv("BASE_URL", ""))
    if token:
        # Generar URL de reset
        base = os.getenv("FRONT_URL", "http://localhost:3000")
        reset_url = f"{base}/reset-password?token={token.token}"
        # Enviar email
        try:
            email_service.send_password_reset(to=payload.email.lower(), reset_url=reset_url)
            logger.info("Email de reset enviado a %s", payload.email)
        except Exception as e:
            logger.warning("Error enviando email de reset: %s", e)
    # HU_40 — Auditoría (best-effort).
    try:
        _ip, _ua = request_meta(request)
        AuditService(db).log(
            tenant_id=None,
            actor=None,
            action="auth.password_forgot",
            resource_type="user",
            resource_id=None,
            method="POST",
            path=request.url.path,
            ip=_ip,
            user_agent=_ua,
            status_code=200,
            description="Solicitud de recuperación de contraseña",
            extra={"email": payload.email.lower(), "delivered": bool(token)},
        )
    except Exception as exc:  # pragma: no cover — defensivo
        logger.warning("auth.password_forgot audit log failed: %s", exc)
    return {"ok": True, "message": "Si el email existe, recibirás instrucciones para restablecer tu contraseña."}


@router.post("/auth/reset-password", response_model=PasswordResetResponse)
def reset_password(payload: ResetPasswordRequest, request: Request, db: Session = Depends(get_db)):
    """Restablece la contraseña usando un token válido.

    HU_40 — audita ``auth.password_reset`` con actor=user al que pertenece
    el token (no por email del payload, sino por el ``user_id`` del token).
    """
    err = validate_password_strength(payload.new_password)
    if err:
        from app.core.errors import ValidationError
        raise ValidationError(err)
    svc = PasswordService(db)
    user = svc.reset_password(payload.token, payload.new_password)
    try:
        _ip, _ua = request_meta(request)
        AuditService(db).log(
            tenant_id=None,
            actor=user,
            action="auth.password_reset",
            resource_type="user",
            resource_id=str(user.id),
            method="POST",
            path=request.url.path,
            ip=_ip,
            user_agent=_ua,
            status_code=200,
            description=f"Contraseña restablecida para {user.email}",
            extra={"email": user.email},
        )
    except Exception as exc:  # pragma: no cover — defensivo
        logger.warning("auth.password_reset audit log failed: %s", exc)
    return {"ok": True, "message": "Contraseña restablecida correctamente"}


@router.post("/auth/verify-email", response_model=PasswordResetResponse)
def verify_email(payload: VerifyEmailRequest, request: Request, db: Session = Depends(get_db)):
    """Verifica el email del usuario.

    HU_40 — audita ``auth.email_verified`` con actor=user al que pertenece el
    token de verificación.
    """
    svc = PasswordService(db)
    user = svc.verify_email(payload.token)
    try:
        _ip, _ua = request_meta(request)
        AuditService(db).log(
            tenant_id=None,
            actor=user,
            action="auth.email_verified",
            resource_type="user",
            resource_id=str(user.id),
            method="POST",
            path=request.url.path,
            ip=_ip,
            user_agent=_ua,
            status_code=200,
            description=f"Email verificado para {user.email}",
            extra={"email": user.email},
        )
    except Exception as exc:  # pragma: no cover — defensivo
        logger.warning("auth.email_verified audit log failed: %s", exc)
    return {"ok": True, "message": f"Email verificado para {user.email}"}


@router.post("/auth/send-verification", response_model=PasswordResetResponse)
def send_verification(email: str, request: Request, db: Session = Depends(get_db)):
    """Re-envía el email de verificación.

    HU_40 — audita ``auth.email_verification_sent`` con actor=user al que se
    le re-envía el email (a diferencia de ``auth.password_forgot``, este
    endpoint SÍ requiere que el usuario exista).
    """
    from sqlalchemy import select
    user = db.execute(select(User).where(User.email == email.lower())).scalar_one_or_none()
    if not user:
        raise NotFoundError("Usuario")
    svc = PasswordService(db)
    token = svc.create_verification_token(user)
    base = os.getenv("FRONT_URL", "http://localhost:3000")
    verify_url = f"{base}/verify-email?token={token.token}"
    try:
        from app.services.email_service import email_service
        email_service.send(
            to=user.email,
            subject="Verifica tu email — WowHub",
            html=f'<p>Hola {user.full_name},</p><p><a href="{verify_url}">Verificar mi email</a></p>',
        )
    except Exception as e:
        logger.warning("Error enviando email de verificación: %s", e)
    try:
        _ip, _ua = request_meta(request)
        AuditService(db).log(
            tenant_id=None,
            actor=user,
            action="auth.email_verification_sent",
            resource_type="user",
            resource_id=str(user.id),
            method="POST",
            path=request.url.path,
            ip=_ip,
            user_agent=_ua,
            status_code=200,
            description=f"Email de verificación re-enviado a {user.email}",
            extra={"email": user.email},
        )
    except Exception as exc:  # pragma: no cover — defensivo
        logger.warning("auth.email_verification_sent audit log failed: %s", exc)
    return {"ok": True, "message": "Email de verificación enviado"}
