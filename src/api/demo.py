"""Spending guard for public deployments.

With DEMO_MODE on, routes that call Muse serve saved live results instead. A real call needs
`?live=true` plus either a verified account with runs remaining (ACCOUNTS_REQUIRED) or an
`X-Demo-Key` header matching DEMO_KEY (legacy presenter path), and is capped at
LIVE_CALLS_PER_HOUR. The cap is held in memory, so on serverless hosts it applies per running
instance (cold starts reset it); it bounds abuse rather than enforcing an exact global quota.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
from collections import deque
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Annotated
from uuid import uuid4

from fastapi import Depends, Header, HTTPException, Query, Request, status

from src.config import get_settings
from src.services import live_quota

logger = logging.getLogger(__name__)

WINDOW_SECONDS = live_quota.WINDOW_SECONDS
# Same deque object as live_quota's, kept here for existing callers and tests.
_live_calls: deque[float] = live_quota._live_calls
_reserve_live_slot = live_quota.reserve


def _client_ip_hash(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    ip = forwarded.split(",", 1)[0].strip() or (request.client.host if request.client else "")
    return hashlib.sha256(ip.encode()).hexdigest()


async def live_mode(
    request: Request,
    live: Annotated[bool, Query(description="Make a real (billed) Muse call.")] = False,
    x_demo_key: Annotated[str | None, Header()] = None,
) -> AsyncIterator[bool]:
    """Yield True when this request may call Muse; False means saved demo result.

    With accounts enabled, one run is authorized per live request and finished when
    the route completes, so 1 run = 1 live action against the user's quota.
    """
    from src.services import usage_meter
    from src.services.accounts import resolve_account

    settings = get_settings()
    if (
        not settings.accounts_required
        and not settings.demo_mode
        and not settings.hosted_environment
    ):
        yield True
        return
    if not live:
        yield False
        return
    if settings.accounts_required:
        account = await resolve_account(request, require_verified=True)
        assert account is not None
        operation_id = await usage_meter.authorize_operation(
            account.user_id, _client_ip_hash(request), str(uuid4()), account.session_id
        )
        logger.warning(
            "LIVE Muse run authorized: %s user=%s op=%s",
            request.url.path,
            account.user_id,
            operation_id,
        )
        try:
            yield True
        finally:
            await usage_meter.finish_operation("completed", operation_id=operation_id)
        return
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
    yield True


LiveMode = Annotated[bool, Depends(live_mode)]


def demo_unavailable(feature: str) -> HTTPException:
    return HTTPException(
        status.HTTP_403_FORBIDDEN,
        detail=(
            f"{feature} has no saved demo result. This deployment is in demo mode; "
            "add ?live=true with a valid X-Demo-Key header to run it live."
        ),
    )
