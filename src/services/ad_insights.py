"""Turn connected ad network insights rows into `CampaignPerformance` for the Bid Advisor.

Bridges `src/clients/ad_networks/` and `src/models/bids.py` without modifying `bid_advisor.py`.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date

from src.clients.ad_networks.base import AdInsightRow, AdNetworkReadAdapter
from src.clients.ad_networks.meta import MetaAdsReadClient
from src.models.bids import AdSetDailyPerformance, CampaignPerformance


def insights_to_campaign_performance(
    rows: Sequence[AdInsightRow],
    *,
    account_name: str = "Connected Ad Account",
    currency: str | None = None,
    ad_set_budgets: Mapping[str, float] | None = None,
) -> CampaignPerformance:
    """Convert normalized `AdInsightRow` records into a `CampaignPerformance` model.

    Raises `ValueError` when `rows` is empty so callers can surface an empty-account message
    before invoking `bid_advisor.compute_metrics()`.
    """
    if not rows:
        raise ValueError("Ad account returned no daily insights rows for the selected date range.")

    resolved_currency = (currency or rows[0].currency or "USD").strip().upper()
    if len(resolved_currency) != 3:
        resolved_currency = "USD"

    budget_lookup = ad_set_budgets or {}
    daily_rows: list[AdSetDailyPerformance] = []
    for item in rows:
        budget = item.daily_budget
        if budget is None and budget_lookup:
            budget = budget_lookup.get(item.ad_set_id) or budget_lookup.get(item.ad_set_name)

        daily_rows.append(
            AdSetDailyPerformance(
                day=item.day,
                campaign_name=item.campaign_name,
                ad_set_name=item.ad_set_name,
                impressions=item.impressions,
                clicks=item.clicks,
                conversions=item.conversions,
                spend=item.spend,
                conversion_value=item.conversion_value,
                frequency=item.frequency,
                daily_budget=budget,
            )
        )

    return CampaignPerformance(
        account_name=account_name,
        currency=resolved_currency,
        rows=daily_rows,
    )


async def fetch_meta_campaign_performance(
    account_id: str,
    *,
    start_date: date,
    end_date: date,
    account_name: str = "Meta Ad Account",
    currency: str | None = None,
    client: AdNetworkReadAdapter | None = None,
) -> CampaignPerformance:
    """Fetch daily Meta insights for `account_id` and map them into `CampaignPerformance`."""
    owns_client = client is None
    active_client: AdNetworkReadAdapter = client or MetaAdsReadClient()
    try:
        insight_rows = await active_client.fetch_campaign_insights(
            account_id,
            start_date=start_date,
            end_date=end_date,
        )
    finally:
        if owns_client:
            await active_client.aclose()

    return insights_to_campaign_performance(
        insight_rows,
        account_name=account_name,
        currency=currency,
    )
