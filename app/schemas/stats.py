"""Schemas para Stats y Analytics."""
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class OverviewResponse(BaseModel):
    period_days: int
    orders: dict
    revenue: dict
    catalog: dict
    top_products: list[dict] = Field(default_factory=list)
    top_qrs: list[dict] = Field(default_factory=list)
    daily_series: list[dict] = Field(default_factory=list)
