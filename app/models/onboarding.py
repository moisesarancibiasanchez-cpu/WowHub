"""Onboarding: tracking del wizard de configuración inicial por tenant."""
from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel, TenantMixin


class OnboardingState(BaseModel, TenantMixin):
    __tablename__ = "onboarding_states"

    # Pasos completados: lista de keys
    completed_steps: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    # Paso actual
    current_step: Mapped[str] = mapped_column(String(40), default="welcome", nullable=False)
    # Datos capturados en el wizard
    wizard_data: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    # Score calculado
    wow_score: Mapped[int] = mapped_column(default=0, nullable=False)
    is_completed: Mapped[bool] = mapped_column(default=False, nullable=False)
