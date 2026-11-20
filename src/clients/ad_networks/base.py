"""Base protocol, Pydantic v2 boundary models, and typed errors for ad network adapters.

Read-only by design: this module defines no write or mutation methods. Any future write interface
requires explicit approval of the safety model in docs/launch/AD_NETWORKS_SPEC.md (Section 5).
"""

from __future__ import annotations

from datetime import date
from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel, Field

AdNetworkId = Literal["meta", "google_ads", "tiktok", "x", "linkedin"]


class AdNetworkError(Exception):
    """Base exception raised when an ad network API call or payload validation fails."""

    def __init__(
        self,
        message: str,
        *,
        network: AdNetworkId = "meta",
        status_code: int | None = None,
        error_code: int | str | None = None,
        error_subcode: int | str | None = None,
    ) -> None:
        super().__init__(message)
        self.network: AdNetworkId = network
        self.status_code = status_code
        self.error_code = error_code
        self.error_subcode = error_subcode


class AdNetworkDisabledError(AdNetworkError):
    """Raised when an ad network client is invoked while AD_CONNECT_ENABLED is false."""


class AdNetworkAuthError(AdNetworkError):
    """Raised when an access token is missing, expired, malformed, or revoked."""


class AdNetworkPermissionError(AdNetworkError):
    """Raised when the token lacks required read scopes or ad-account role access."""


class AdNetworkRateLimitError(AdNetworkError):
    """Raised when the ad network throttles requests due to quota or rate limits."""

    def __init__(
        self,
        message: str,
        *,
        network: AdNetworkId = "meta",
        status_code: int | None = None,
        error_code: int | str | None = None,
        error_subcode: int | str | None = None,
        retry_after_seconds: int | None = None,
    ) -> None:
        super().__init__(
            message,
            network=network,
            status_code=status_code,
            error_code=error_code,
            error_subcode=error_subcode,
        )
        self.retry_after_seconds = retry_after_seconds


class AdAccountSummary(BaseModel):
    """Normalized summary of an advertiser's ad account on a connected network."""

    network: AdNetworkId = "meta"
    account_id: str = Field(min_length=1, description="Provider account ID, e.g. 'act_123456'.")
    name: str = ""
    currency: str = Field(default="USD", min_length=3, max_length=3)
    timezone_name: str = "UTC"
    account_status: str = "ACTIVE"


class AdCampaignSummary(BaseModel):
    """Normalized campaign metadata returned from a read-only campaign listing."""

    network: AdNetworkId = "meta"
    campaign_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    status: str = "PAUSED"
    effective_status: str | None = None
    objective: str | None = None
    daily_budget: float | None = Field(
        default=None, ge=0, description="Daily budget in major currency units (e.g. USD dollars)."
    )


class AdInsightRow(BaseModel):
    """One day of performance metrics for a single ad set (or campaign fallback)."""

    network: AdNetworkId = "meta"
    day: date
    campaign_id: str = ""
    campaign_name: str = Field(min_length=1)
    ad_set_id: str = ""
    ad_set_name: str = Field(min_length=1)
    impressions: int = Field(ge=0)
    clicks: int = Field(ge=0)
    conversions: int = Field(default=0, ge=0)
    spend: float = Field(ge=0)
    conversion_value: float | None = Field(default=None, ge=0)
    frequency: float | None = Field(default=None, ge=0)
    daily_budget: float | None = Field(default=None, ge=0)
    currency: str = Field(default="USD", min_length=3, max_length=3)


@runtime_checkable
class AdNetworkReadAdapter(Protocol):
    """Read-only interface that every ad network client adapter implements."""

    network: AdNetworkId

    async def aclose(self) -> None:
        """Close the underlying HTTP client if owned by this adapter."""
        ...

    async def list_ad_accounts(self) -> list[AdAccountSummary]:
        """List ad accounts accessible to the authenticated user token."""
        ...

    async def list_campaigns(self, account_id: str) -> list[AdCampaignSummary]:
        """List campaigns for the given ad account."""
        ...

    async def fetch_campaign_insights(
        self,
        account_id: str,
        *,
        start_date: date,
        end_date: date,
    ) -> list[AdInsightRow]:
        """Fetch daily performance insights rows for an ad account over [start_date, end_date]."""
        ...
