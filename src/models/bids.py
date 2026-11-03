"""Pydantic v2 models for Flow 3: Bid Advisor."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from src.models.intel import CompetitorBrief, ResearchFinding

BidAction = Literal["increase", "decrease", "hold"]
BidStrategy = Literal["lowest_cost", "cost_cap", "bid_cap"]

# Every recommendation must cite one of these, and each maps to a field in AdSetMetrics.
TriggeringMetric = Literal[
    "roas",
    "cpa",
    "ctr",
    "cpc",
    "cpm",
    "conversions",
    "spend_share",
    "roas_trend",
    "ctr_trend",
    "cpa_trend",
    "frequency",
    "spend_pacing",
]


class AdSetDailyPerformance(BaseModel):
    """One ad set's results for one day, as in a Meta Ads Manager export.

    Raw counts are the source of truth. Ratio columns are optional: if the export omits them
    they are derived from the counts, and aggregation always recomputes from counts.
    """

    day: date
    campaign_name: str = Field(min_length=1)
    ad_set_name: str = Field(min_length=1)
    impressions: int = Field(ge=0)
    clicks: int = Field(ge=0)
    conversions: int = Field(ge=0)
    spend: float = Field(ge=0)
    conversion_value: float | None = Field(
        default=None, ge=0, description="Revenue attributed to conversions (purchase value)."
    )
    frequency: float | None = Field(default=None, ge=0)
    daily_budget: float | None = Field(default=None, ge=0)
    ctr: float | None = Field(default=None, ge=0, description="Clicks / impressions, as a %.")
    cpc: float | None = Field(default=None, ge=0)
    cpm: float | None = Field(default=None, ge=0)
    roas: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _fill_derived(self) -> AdSetDailyPerformance:
        if self.clicks > self.impressions:
            raise ValueError("clicks cannot exceed impressions")
        if self.ctr is None and self.impressions:
            self.ctr = round(self.clicks / self.impressions * 100, 4)
        if self.cpc is None and self.clicks:
            self.cpc = round(self.spend / self.clicks, 4)
        if self.cpm is None and self.impressions:
            self.cpm = round(self.spend / self.impressions * 1000, 4)
        if self.conversion_value is None and self.roas is not None:
            self.conversion_value = round(self.roas * self.spend, 2)
        if self.roas is None and self.conversion_value is not None and self.spend:
            self.roas = round(self.conversion_value / self.spend, 4)
        return self


class CampaignPerformance(BaseModel):
    """Performance data for one ad account over a date range."""

    account_name: str = ""
    currency: str = Field(default="USD", min_length=3, max_length=3)
    rows: list[AdSetDailyPerformance] = Field(min_length=1)


class PeriodTotals(BaseModel):
    """Summed counts and ratios recomputed from them (never averages of daily ratios)."""

    spend: float
    impressions: int
    clicks: int
    conversions: int
    conversion_value: float | None
    ctr: float | None = Field(description="%")
    cpc: float | None
    cpm: float | None
    cpa: float | None
    roas: float | None


class AdSetMetrics(BaseModel):
    """Deterministic, Python-computed metrics for one ad set. The LLM only reads these."""

    ad_set_name: str
    campaign_name: str
    days_active: int
    totals: PeriodTotals
    avg_daily_spend: float
    spend_share: float = Field(description="Share of account spend, 0-1.")
    conversion_share: float = Field(description="Share of account conversions, 0-1.")
    roas_vs_account: float | None = Field(description="Ad set ROAS / account ROAS. 1.0 = par.")
    cpa_vs_account: float | None = Field(description="Ad set CPA / account CPA. >1 is worse.")
    roas_trend_pct: float | None = Field(description="Late-half vs early-half ROAS, % change.")
    ctr_trend_pct: float | None = Field(description="Late-half vs early-half CTR, % change.")
    cpa_trend_pct: float | None = Field(description="Late-half vs early-half CPA, % change.")
    avg_frequency: float | None
    frequency_trend_pct: float | None
    spend_pacing: float | None = Field(description="Avg daily spend / daily budget, 0-1+.")
    flags: list[str] = Field(default_factory=list)


class PerformanceMetrics(BaseModel):
    """Account-level summary plus per-ad-set metrics, the full input Muse Spark reasons over."""

    account_name: str
    currency: str
    start_date: date
    end_date: date
    days: int
    account_totals: PeriodTotals
    ad_sets: list[AdSetMetrics]


class BidAdjustment(BaseModel):
    ad_set_name: str = Field(min_length=1)
    action: BidAction
    bid_strategy: BidStrategy | None = Field(
        default=None, description="Only set when recommending a strategy change."
    )
    triggering_metric: TriggeringMetric
    reasoning: str = Field(min_length=1, description="Plain language, cites the metric value.")
    expected_impact: str = Field(
        min_length=1, description="Expected direction of impact. Never an invented number."
    )


class BudgetShiftSuggestion(BaseModel):
    """What Muse Spark returns for a budget move. Amounts are computed in Python afterwards."""

    from_ad_set: str = Field(min_length=1)
    to_ad_set: str = Field(min_length=1)
    shift_percent: int = Field(
        ge=5, le=50, description="Share of the source ad set's daily spend to move, 5-50."
    )
    triggering_metric: TriggeringMetric
    reasoning: str = Field(min_length=1)


class BudgetReallocation(BudgetShiftSuggestion):
    daily_amount: float = Field(ge=0, description="Computed: source avg daily spend x percent.")
    currency: str


class PauseRecommendation(BaseModel):
    ad_set_name: str = Field(min_length=1)
    triggering_metric: TriggeringMetric
    reasoning: str = Field(min_length=1)
    alternative: str = Field(
        default="", description="A lighter option to try first, e.g. refreshing the creative."
    )


class AudienceSuggestion(BaseModel):
    audience: str = Field(min_length=1, description="Who to target, in plain words.")
    competitor_gap: str = Field(min_length=1, description="The competitor gap it exploits.")
    rationale: str = Field(min_length=1)
    how_to_test: str = Field(min_length=1, description="A five-minute setup step.")
    finding_ids: list[str] = Field(
        default_factory=list,
        description="Ids of the competitor research findings it relies on, e.g. ['F2'].",
    )


class BidRecommendationLLMOutput(BaseModel):
    """Structured output schema requested from Muse Spark."""

    performance_summary: str = Field(
        min_length=1, description="2-3 plain sentences on how the account is doing."
    )
    trend_analysis: list[str] = Field(
        default_factory=list, description="Notable trends, each citing a computed metric."
    )
    competitive_context: list[str] = Field(
        default_factory=list,
        description="How the competitor's positioning should shape spend decisions.",
    )
    bid_adjustments: list[BidAdjustment] = Field(default_factory=list)
    budget_shifts: list[BudgetShiftSuggestion] = Field(default_factory=list)
    pause_candidates: list[PauseRecommendation] = Field(default_factory=list)
    audience_suggestions: list[AudienceSuggestion] = Field(default_factory=list, max_length=5)
    next_steps: list[str] = Field(
        min_length=1, max_length=5, description="Top actions, most important first."
    )


class BidAdviceRequest(BaseModel):
    campaign: CampaignPerformance
    competitor_brief: CompetitorBrief
    seller_goal: str = Field(
        default="", max_length=500, description="e.g. 'more sales at the same spend'."
    )
    target_roas: float | None = Field(default=None, gt=0)
    target_cpa: float | None = Field(default=None, gt=0)


class BidRecommendation(BaseModel):
    """Final Bid Advisor output. Advisory only: nothing here is applied to an ad account."""

    account_name: str
    currency: str
    competitor_domain: str
    performance_summary: str
    trend_analysis: list[str]
    competitive_context: list[str]
    bid_adjustments: list[BidAdjustment]
    budget_reallocations: list[BudgetReallocation]
    pause_candidates: list[PauseRecommendation]
    audience_suggestions: list[AudienceSuggestion]
    next_steps: list[str]
    research_brief: list[ResearchFinding] = Field(
        default_factory=list,
        description="The cited competitor findings that recommendations reference by id.",
    )
    metrics: PerformanceMetrics
    model: str
