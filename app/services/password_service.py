"""PasswordService — recuperación y verificación de email."""
import logging
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError, UnauthorizedError, ValidationError
from app.models.token import AuthToken, TokenType
from app.models.user import User
from app.security import hash_password

logger = logging.getLogger("wowhub.password")

# Política de password
PASSWORD_MIN_LENGTH = 8
PASSWORD_PATTERN = re.compile(r"^(?=.*[A-Za-z])(?=.*\d).+$")  # al menos una letra y un dígito


def validate_password_strength(password: str) -> Optional[str]:
    """Retorna None si es válida, mensaje de error si no."""
    if len(password) < PASSWORD_MIN_LENGTH:
        return f"La contraseña debe tener al menos {PASSWORD_MIN_LENGTH} caracteres"
    if not PASSWORD_PATTERN.match(password):
        return "La contraseña debe tener al menos una letra y un número"
    return None


class PasswordService:
    def __init__(self, db: Session):
        self.db = db

    def request_reset(self, email: str, base_url: str) -> Optional[AuthToken]:
        """Genera token de reset y lo persiste. Retorna None si el email no existe (silencioso)."""
        user = self.db.execute(
            select(User).where(User.email == email.lower())
        ).scalar_one_or_none()
        if not user:
            return None  # No revelar si el email existe
        # Invalidar tokens previos del mismo tipo
        for old in self.db.execute(
            select(AuthToken).where(
                AuthToken.user_id == str(user.id),
                AuthToken.type == TokenType.PASSWORD_RESET,
                AuthToken.used_at == None,  # noqa: E711
            )
        ).scalars():
            old.used_at = datetime.now(timezone.utc)
        token = AuthToken(
            user_id=str(user.id),
            token=secrets.token_urlsafe(48),
            type=TokenType.PASSWORD_RESET,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        self.db.add(token)
        self.db.commit()
        self.db.refresh(token)
        return token

    def reset_password(self, token: str, new_password: str) -> User:
        err = validate_password_strength(new_password)
        if err:
            raise ValidationError(err)
        auth_token = self.db.execute(
            select(AuthToken).where(
                AuthToken.token == token,
                AuthToken.type == TokenType.PASSWORD_RESET,
            )
        ).scalar_one_or_none()
        if not auth_token:
            raise NotFoundError("Token inválido")
        if auth_token.used_at is not None:
            raise ConflictError("Este token ya fue utilizado")
        if auth_token.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
            raise ConflictError("Este token ha expirado")
        user = self.db.get(User, UUID(auth_token.user_id))
        if not user:
            raise NotFoundError("Usuario")
        user.password_hash = hash_password(new_password)
        auth_token.used_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(user)
        return user

    def create_verification_token(self, user: User) -> AuthToken:
        for old in self.db.execute(
            select(AuthToken).where(
                AuthToken.user_id == str(user.id),
                AuthToken.type == TokenType.EMAIL_VERIFICATION,
                AuthToken.used_at == None,  # noqa: E711
            )
        ).scalars():
            old.used_at = datetime.now(timezone.utc)
        token = AuthToken(
            user_id=str(user.id),
            token=secrets.token_urlsafe(48),
            type=TokenType.EMAIL_VERIFICATION,
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        )
        self.db.add(token)
        self.db.commit()
        self.db.refresh(token)
        return token

    def verify_email(self, token: str) -> User:
        auth_token = self.db.execute(
            select(AuthToken).where(
                AuthToken.token == token,
                AuthToken.type == TokenType.EMAIL_VERIFICATION,
            )
        ).scalar_one_or_none()
        if not auth_token:
            raise NotFoundError("Token inválido")
        if auth_token.used_at is not None:
            raise ConflictError("Este token ya fue utilizado")
        if auth_token.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
            raise ConflictError("Este token ha expirado")
        user = self.db.get(User, UUID(auth_token.user_id))
        if not user:
            raise NotFoundError("Usuario")
        auth_token.used_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(user)
        return user
