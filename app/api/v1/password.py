"""Password reset & email verification API."""
import logging
import os

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.database import get_db
from app.models.user import User
from app.schemas.password import (
    ForgotPasswordRequest, PasswordResetResponse,
    ResetPasswordRequest, VerifyEmailRequest,
)
from app.services.email_service import email_service
from app.services.password_service import PasswordService, validate_password_strength

logger = logging.getLogger("wowhub.password_api")
router = APIRouter(tags=["auth"])


@router.post("/auth/forgot-password", response_model=PasswordResetResponse)
def forgot_password(payload: ForgotPasswordRequest, db: Session = Depends(get_db)):
    """Solicita un email de recuperación de contraseña.

    Por seguridad, siempre retorna 200 sin revelar si el email existe.
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
    return {"ok": True, "message": "Si el email existe, recibirás instrucciones para restablecer tu contraseña."}


@router.post("/auth/reset-password", response_model=PasswordResetResponse)
def reset_password(payload: ResetPasswordRequest, db: Session = Depends(get_db)):
    """Restablece la contraseña usando un token válido."""
    err = validate_password_strength(payload.new_password)
    if err:
        from app.core.errors import ValidationError
        raise ValidationError(err)
    svc = PasswordService(db)
    svc.reset_password(payload.token, payload.new_password)
    return {"ok": True, "message": "Contraseña restablecida correctamente"}


@router.post("/auth/verify-email", response_model=PasswordResetResponse)
def verify_email(payload: VerifyEmailRequest, db: Session = Depends(get_db)):
    """Verifica el email del usuario."""
    svc = PasswordService(db)
    user = svc.verify_email(payload.token)
    return {"ok": True, "message": f"Email verificado para {user.email}"}


@router.post("/auth/send-verification", response_model=PasswordResetResponse)
def send_verification(email: str, db: Session = Depends(get_db)):
    """Re-envía el email de verificación."""
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
    return {"ok": True, "message": "Email de verificación enviado"}
