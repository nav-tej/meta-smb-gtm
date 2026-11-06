"""Competitor monitor routes: change log, on-demand/weekly checks and the weekly digest.

A check crawls public competitor pages (no Muse call, no credits). Hosted, it runs at most once
per MONITOR_COOLDOWN_SECONDS unless the presenter key or the cron secret is sent; otherwise
the latest stored run is returned with `X-Muse-Monitor: cooldown`.
"""

from __future__ import annotations

import hmac
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Query, Request, Response

from src.api.demo import valid_demo_key
from src.config import get_settings
from src.services import competitor_monitor as monitor

router = APIRouter(tags=["monitor"])


@router.get("/monitor", response_model=monitor.ChangeLog)
def get_change_log(
    limit: Annotated[int, Query(ge=1, le=60)] = 10,
) -> monitor.ChangeLog:
    """The stored change log, newest run first. Never crawls."""
    log = monitor.load_changelog()
    log.runs = log.runs[:limit]
    return log


async def _run_or_cooldown(response: Response, *, bypass: bool, trigger: str) -> monitor.MonitorRun:
    settings = get_settings()
    since = monitor.seconds_since_last_run()
    cooling = since is not None and since < settings.monitor_cooldown_seconds
    if cooling and not bypass:
        latest = monitor.load_changelog().runs
        if latest:
            response.headers["X-Muse-Monitor"] = "cooldown"
            return latest[0]
    response.headers["X-Muse-Monitor"] = "ran"
    return await monitor.run_monitor(trigger=trigger)  # type: ignore[arg-type]


@router.post("/monitor", response_model=monitor.MonitorRun)
async def run_check(
    response: Response,
    x_demo_key: Annotated[str | None, Header()] = None,
) -> monitor.MonitorRun:
    """Check every watched competitor now and log what changed since the last snapshot."""
    bypass = valid_demo_key(x_demo_key) or not get_settings().hosted_environment
    return await _run_or_cooldown(response, bypass=bypass, trigger="manual")


@router.get("/monitor/run", response_model=monitor.MonitorRun, include_in_schema=False)
async def cron_check(
    request: Request,
    response: Response,
    authorization: Annotated[str | None, Header()] = None,
) -> monitor.MonitorRun:
    """Weekly Vercel Cron entry point (see vercel.json)."""
    secret = get_settings().cron_secret
    if secret:
        expected = f"Bearer {secret}"
        if not (authorization and hmac.compare_digest(authorization, expected)):
            raise HTTPException(401, "This scheduled check needs the cron secret.")
        return await _run_or_cooldown(response, bypass=True, trigger="cron")
    if not request.headers.get("user-agent", "").startswith("vercel-cron"):
        raise HTTPException(403, "Use POST /api/v1/monitor to run a check.")
    return await _run_or_cooldown(response, bypass=False, trigger="cron")


@router.get("/weekly-digest", response_model=monitor.WeeklyDigest)
def get_weekly_digest() -> monitor.WeeklyDigest:
    """The last 7 days of competitor changes, from the monitor change log."""
    return monitor.weekly_digest()
