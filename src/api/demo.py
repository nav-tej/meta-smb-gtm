"""Spending guard for public deployments.

With DEMO_MODE on, routes that call Muse serve saved live results instead. A real call needs
`?live=true` plus an `X-Demo-Key` header matching DEMO_KEY, and is capped at
LIVE_CALLS_PER_HOUR. The cap is held in memory, so on serverless hosts it applies per running
instance (cold starts reset it); it bounds abuse rather than enforcing an exact global quota.
"""

from __future__ import annotations

import hmac
import logging
import time
from collections import deque
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Query, Request, status

from src.config import get_settings

logger = logging.getLogger(__name__)

WINDOW_SECONDS = 3600
_live_calls: deque[float] = deque()


def _reserve_live_slot(limit: int) -> int:
    now = time.monotonic()
    while _live_calls and now - _live_calls[0] > WINDOW_SECONDS:
        _live_calls.popleft()
    if len(_live_calls) >= limit:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Live call limit reached ({limit} per hour). Cached demo results still work.",
        )
    _live_calls.append(now)
    return limit - len(_live_calls)


async def live_mode(
    request: Request,
    live: Annotated[bool, Query(description="Make a real (billed) Muse call.")] = False,
    x_demo_key: Annotated[str | None, Header()] = None,
) -> bool:
    """True when this request may call Muse; False means serve the saved demo result."""
    settings = get_settings()
    if not settings.demo_mode:
        return True
    if not live:
        return False
    if not (
        settings.demo_key
        and x_demo_key
        and hmac.compare_digest(x_demo_key.encode(), settings.demo_key.encode())
    ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Live calls need a valid X-Demo-Key.")
    remaining = _reserve_live_slot(settings.live_calls_per_hour)
    logger.warning(
        "LIVE Muse call allowed: %s at %s (%d left this hour)",
        request.url.path,
        datetime.now(UTC).isoformat(),
        remaining,
    )
    return True


LiveMode = Annotated[bool, Depends(live_mode)]


def demo_unavailable(feature: str) -> HTTPException:
    return HTTPException(
        status.HTTP_403_FORBIDDEN,
        detail=(
            f"{feature} has no saved demo result. This deployment is in demo mode; "
            "add ?live=true with a valid X-Demo-Key header to run it live."
        ),
    )
