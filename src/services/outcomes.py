"""Track F: Outcomes persistence and honest ROI calculation service."""

from __future__ import annotations

import logging

from src.models.outcome import Outcome, OutcomeSummary
from src.services.accounts import AccountSession, load_workspace, save_workspace

logger = logging.getLogger(__name__)


def summarize_outcomes(outcomes: list[Outcome], plan_cost_usd: float = 12.0) -> OutcomeSummary:
    """Compute aggregate progress and ROI metrics.

    TRUTH RULE: Never invent modeled revenue.
    If moves_count == 0, net_roi_usd is None (displayed as '— Requires 1 logged result').
    """
    moves_count = len(outcomes)
    total_rev = round(sum(o.revenue for o in outcomes), 2)
    total_min = sum(o.minutes for o in outcomes)
    total_reach = sum(o.reach for o in outcomes)
    total_clicks = sum(o.clicks for o in outcomes)
    total_orders = sum(o.orders for o in outcomes)

    net_roi = None if moves_count == 0 else round(total_rev - plan_cost_usd, 2)

    return OutcomeSummary(
        moves_count=moves_count,
        total_revenue_usd=total_rev,
        total_minutes=total_min,
        total_reach=total_reach,
        total_clicks=total_clicks,
        total_orders=total_orders,
        plan_cost_usd=plan_cost_usd,
        net_roi_usd=net_roi,
        has_logged_result=moves_count > 0,
    )


async def load_account_outcomes(account: AccountSession) -> list[Outcome]:
    """Retrieve logged outcomes from the user's persisted workspace."""
    ws = await load_workspace(account)
    doc = ws.get("document") or {}
    raw_outcomes = doc.get("outcomes")
    if not isinstance(raw_outcomes, list):
        return []

    results: list[Outcome] = []
    for item in raw_outcomes:
        if isinstance(item, dict):
            try:
                results.append(Outcome.model_validate(item))
            except Exception as err:
                logger.warning("Skipping invalid outcome entry: %s", err)
    return results


async def save_account_outcome(account: AccountSession, outcome: Outcome) -> Outcome:
    """Atomically append a logged outcome to the user's persisted workspace."""
    ws = await load_workspace(account)
    doc = dict(ws.get("document") or {})
    raw_outcomes = list(doc.get("outcomes") or [])

    outcome_dict = outcome.model_dump(mode="json")
    raw_outcomes.append(outcome_dict)
    doc["outcomes"] = raw_outcomes

    await save_workspace(
        account,
        doc,
        expected_version=ws.get("version"),
        expected_owner=account.user_id,
    )
    return outcome
