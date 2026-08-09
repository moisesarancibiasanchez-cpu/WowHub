"""Schemas de SiteConfig (configuración global del sitio, singleton)."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.services.site_config_service import VALID_THEMES


class SiteConfigOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    home_theme: str
    maintenance_mode: bool
    maintenance_message: str
    updated_at: datetime


class SiteConfigUpdate(BaseModel):
    """Schema para actualizar campos del SiteConfig (todos opcionales)."""
    home_theme: Optional[str] = Field(None, max_length=20)
    maintenance_mode: Optional[bool] = None
    maintenance_message: Optional[str] = Field(None, max_length=500)

    @field_validator("home_theme")
    @classmethod
    def theme_must_be_valid(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip().lower()
        if v not in VALID_THEMES:
            raise ValueError(
                f"home_theme debe ser uno de: {', '.join(VALID_THEMES)}"
            )
        return v


class HomeThemeUpdate(BaseModel):
    """Schema específico para cambiar sólo el tema de la portada."""
    theme: str = Field(..., max_length=20)

    @field_validator("theme")
    @classmethod
    def theme_must_be_valid(cls, v: str) -> str:
        v = (v or "").strip().lower()
        if v not in VALID_THEMES:
            raise ValueError(
                f"theme debe ser uno de: {', '.join(VALID_THEMES)}"
            )
        return v
