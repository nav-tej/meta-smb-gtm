"""Track F: Outcomes and progress endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, Request, Response
from pydantic import BaseModel, Field

from src.models.outcome import Outcome, OutcomeSummary
from src.services.accounts import AccountSession, resolve_account, verify_workspace_owner
from src.services.outcomes import (
    load_account_outcomes,
    save_account_outcome,
    summarize_outcomes,
)

router = APIRouter(prefix="/outcomes", tags=["outcomes"])


class OutcomeCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=150)
    date: str | None = None
    channel: str = Field(default="site", max_length=50)
    minutes: int = Field(default=15, ge=0)
    reach: int = Field(default=0, ge=0)
    clicks: int = Field(default=0, ge=0)
    orders: int = Field(default=0, ge=0)
    revenue: float = Field(default=0.0, ge=0.0)
    notes: str | None = Field(default=None, max_length=500)


class OutcomesListResponse(BaseModel):
    outcomes: list[Outcome]
    summary: OutcomeSummary


class OutcomeResponse(BaseModel):
    outcome: Outcome
    summary: OutcomeSummary


async def _get_account_plan_cost(account: AccountSession | None) -> float:
    if not account:
        return 0.0
    try:
        from src.services.accounts import snapshot

        snap = await snapshot(account)
        plan = (snap.get("usage") or {}).get("plan")
        # A free account is stored as "trial" (3 free runs); it costs nothing.
        if plan in ("trial", "free"):
            return 0.0
        if plan == "unlimited":
            return 29.0
        if plan == "starter":
            return 12.0
    except Exception:
        pass
    return 12.0


@router.get("", response_model=OutcomesListResponse)
async def list_outcomes(
    request: Request,
    response: Response,
    x_muse_owner: str | None = Header(default=None),
) -> OutcomesListResponse:
    """Retrieve logged outcomes and honest ROI summary for the signed-in account."""
    account = await resolve_account(request, response, require_verified=False)
    if not account:
        return OutcomesListResponse(outcomes=[], summary=summarize_outcomes([], plan_cost_usd=0.0))

    verify_workspace_owner(account, x_muse_owner)
    outcomes = await load_account_outcomes(account)
    plan_cost = await _get_account_plan_cost(account)
    summary = summarize_outcomes(outcomes, plan_cost_usd=plan_cost)
    return OutcomesListResponse(outcomes=outcomes, summary=summary)


@router.post("", response_model=OutcomeResponse)
async def create_outcome(
    body: OutcomeCreateRequest,
    request: Request,
    response: Response,
    x_muse_owner: str | None = Header(default=None),
) -> OutcomeResponse:
    """Log a verified business outcome to the signed-in account workspace."""
    account = await resolve_account(request, response, require_verified=True)
    assert account is not None
    verify_workspace_owner(account, x_muse_owner, require_binding=True)

    kwargs: dict[str, Any] = {
        "title": body.title,
        "channel": body.channel,
        "minutes": body.minutes,
        "reach": body.reach,
        "clicks": body.clicks,
        "orders": body.orders,
        "revenue": body.revenue,
        "notes": body.notes,
    }
    if body.date:
        kwargs["date"] = body.date
    outcome = Outcome(**kwargs)
    saved = await save_account_outcome(account, outcome)
    all_outcomes = await load_account_outcomes(account)
    plan_cost = await _get_account_plan_cost(account)
    summary = summarize_outcomes(all_outcomes, plan_cost_usd=plan_cost)
    return OutcomeResponse(outcome=saved, summary=summary)


@router.get("/summary", response_model=OutcomeSummary)
async def get_summary(
    request: Request,
    response: Response,
    x_muse_owner: str | None = Header(default=None),
) -> OutcomeSummary:
    """Compute aggregate progress metrics from seller-logged outcomes."""
    account = await resolve_account(request, response, require_verified=False)
    if not account:
        return summarize_outcomes([], plan_cost_usd=0.0)

    verify_workspace_owner(account, x_muse_owner)
    outcomes = await load_account_outcomes(account)
    plan_cost = await _get_account_plan_cost(account)
    return summarize_outcomes(outcomes, plan_cost_usd=plan_cost)
