"""GET /daily-brief: today's growth brief for /today (no model call; cached per day)."""

from typing import Annotated

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
) -> DailyBrief:
    await durable_state.hydrate_monitor()
    account = await resolve_account(request, response, require_verified=False)
    return await daily_brief(refresh=refresh, response=response, account=account)
