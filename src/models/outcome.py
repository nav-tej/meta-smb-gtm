"""Track F: Verified seller outcomes, move logging, and honest ROI metrics."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from pydantic import BaseModel, Field


class Outcome(BaseModel):
    """A verified business outcome logged by a seller for an actioned move."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    title: str = Field(min_length=1, max_length=150)
    date: str = Field(default_factory=lambda: datetime.now(UTC).date().isoformat())
    channel: str = Field(default="site", max_length=50)
    minutes: int = Field(default=15, ge=0)
    reach: int = Field(default=0, ge=0)
    clicks: int = Field(default=0, ge=0)
    orders: int = Field(default=0, ge=0)
    revenue: float = Field(default=0.0, ge=0.0)
    notes: str | None = Field(default=None, max_length=500)
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class OutcomeSummary(BaseModel):
    """Aggregate business metrics computed from seller-logged outcomes only."""

    moves_count: int = 0
    total_revenue_usd: float = 0.0
    total_minutes: int = 0
    total_reach: int = 0
    total_clicks: int = 0
    total_orders: int = 0
    plan_cost_usd: float = 12.0
    net_roi_usd: float | None = None
    has_logged_result: bool = False
