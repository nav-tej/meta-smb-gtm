"""GET /daily-brief: today's growth brief for /today (no model call; cached per day)."""

from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, Request, Response

from src.api.cache_policy import cache_for_everyone, never_cache
from src.services import durable_state
from src.services.accounts import resolve_account
from src.services.daily_brief import DailyBrief, SetupIncompleteError, daily_brief

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
    if workspace == "own":
        never_cache(response)
        headers = {"Cache-Control": "private, no-store"}
        account = await resolve_account(request, response, require_verified=False)
        if account is None:
            raise HTTPException(401, "Sign in to see your brief", headers=headers)
        try:
            return await daily_brief(refresh=refresh, response=response, account=account)
        except SetupIncompleteError as err:
            raise HTTPException(409, "Finish setup first", headers=headers) from err

    await durable_state.hydrate_monitor()
    if refresh:
        never_cache(response)
    else:
        cache_for_everyone(response)
    return await daily_brief(refresh=refresh, response=response)
