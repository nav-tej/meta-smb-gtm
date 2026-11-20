"""Track K: 14-day trial entitlement, baseline capture, and retention models."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Literal

from pydantic import BaseModel, Field

TrialStatus = Literal["active", "expired", "converted", "cancelled"]


class BaselineMetrics(BaseModel):
    """Day-0 optional baseline metrics captured during trial setup."""

    captured_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    posts_last_month: int = Field(default=0, ge=0)
    orders_last_month: int = Field(default=0, ge=0)
    followers_count: int = Field(default=0, ge=0)
    monthly_revenue_usd: float = Field(default=0.0, ge=0.0)


class TrialEntitlement(BaseModel):
    """14-day free trial entitlement model.

    Configurable values:
    - run_allowance: number of live runs granted (config: trial_runs)
    - requires_card: whether credit card is required upfront (config: trial_requires_card)
    """

    account_id: str
    started_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    duration_days: int = Field(default=14, ge=1, le=90)
    expires_at: str = Field(
        default_factory=lambda: (datetime.now(UTC) + timedelta(days=14)).isoformat()
    )
    run_allowance: int = Field(default=3, ge=0)
    runs_used: int = Field(default=0, ge=0)
    requires_card: bool = False
    card_attached: bool = False
    status: TrialStatus = "active"

    @property
    def runs_remaining(self) -> int:
        return max(0, self.run_allowance - self.runs_used)

    def is_active(self, now: datetime | None = None) -> bool:
        if self.status != "active":
            return False
        current_time = now if now is not None else datetime.now(UTC)
        try:
            exp = datetime.fromisoformat(self.expires_at)
            return current_time <= exp
        except Exception:
            return False

    def days_remaining(self, now: datetime | None = None) -> int:
        current_time = now if now is not None else datetime.now(UTC)
        try:
            exp = datetime.fromisoformat(self.expires_at)
            diff = exp - current_time
            return max(0, diff.days + (1 if diff.seconds > 0 else 0))
        except Exception:
            return 0


class TrialActivity(BaseModel):
    """Weekly activity tracking to measure Weekly Active Sellers (WAS)."""

    recommendations_acted: int = Field(default=0, ge=0)
    posts_exported: int = Field(default=0, ge=0)
    results_logged: int = Field(default=0, ge=0)
    directives_steered: int = Field(default=0, ge=0)
    active_weeks: list[int] = Field(default_factory=list)

    @property
    def is_weekly_active(self) -> bool:
        """A seller is active in a week if they complete >= 1 meaningful action."""
        return (
            self.recommendations_acted > 0
            or self.posts_exported > 0
            or self.results_logged > 0
            or self.directives_steered > 0
        )


class TwoWeekSummary(BaseModel):
    """Day-12 'Your first two weeks' summary presented before the plan prompt.

    TRUTH RULE: Only real counts of actual actions and logged revenue.
    Never invent projected or simulated lift.
    """

    recommendations_done: int = 0
    posts_made: int = 0
    results_logged: int = 0
    competitor_changes_caught: int = 0
    has_logged_revenue: bool = False
    logged_revenue_usd: float = 0.0
    is_activation_achieved: bool = False
    truth_rule_verified: bool = True
