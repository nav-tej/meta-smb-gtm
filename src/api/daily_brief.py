"""GET /daily-brief: today's growth brief for /today (no model call; cached per day)."""

from typing import Annotated, Literal

from fastapi import APIRouter, Query, Request, Response

from src.services import durable_state
from src.services.accounts import resolve_account
from src.services.daily_brief import DailyBrief, daily_brief

router = APIRouter(tags=["daily"])


@router.get("/daily-brief", response_model=DailyBrief)
async def get_daily_brief(
    request: Request,
    response: Response,
    refresh: Annotated[
        bool, Query(description="Rebuild today's brief from saved and cached data.")
    ] = False,
    workspace: Annotated[
        Literal["sample", "own"],
        Query(description="Which brief: the sample shop's (default) or the seller's own."),
    ] = "sample",
) -> DailyBrief:
    await durable_state.hydrate_monitor()
    # Every page that shows a brief today shows the sample shop's (/today in sample mode, home
    # notifications, the digest). Building the seller's own brief only on request keeps a signed-in
    # seller who opens the sample from seeing their own competitors inside the sample's frame.
    account = (
        await resolve_account(request, response, require_verified=False)
        if workspace == "own"
        else None
    )
    return await daily_brief(refresh=refresh, response=response, account=account)
