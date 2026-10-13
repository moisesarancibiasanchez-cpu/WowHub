"""PasswordReset + EmailVerification: tokens one-time para recuperación y verificación."""
import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class TokenType(str, enum.Enum):
    PASSWORD_RESET = "password_reset"
    EMAIL_VERIFICATION = "email_verification"
    INVITATION = "invitation"


class AuthToken(BaseModel):
    """Token one-time. Se invalida tras uso o al expirar."""
    __tablename__ = "auth_tokens"

    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    type: Mapped[TokenType] = mapped_column(
        Enum(TokenType, name="token_type"),
        nullable=False,
        index=True,
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Contexto opcional (ej: tenant al que se invita)
    context: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
