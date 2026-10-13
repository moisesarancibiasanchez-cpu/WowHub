"""LegalConsent: registro de consentimientos del usuario (términos, cookies, marketing)."""
from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class LegalConsent(BaseModel):
    __tablename__ = "legal_consents"

    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    document_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)  # terms, privacy, cookies, marketing
    document_version: Mapped[str] = mapped_column(String(20), nullable=False)
    ip: Mapped[str] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str] = mapped_column(String(500), nullable=True)
    accepted: Mapped[bool] = mapped_column(default=True, nullable=False)
    extra: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
