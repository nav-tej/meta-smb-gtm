"""In-memory hourly cap on presenter live calls (DEMO_KEY path).

A slot is reserved when a live request is allowed. If that request is then answered from the
result cache, no Muse call happens, so the slot is handed back. The cap is per running instance
(serverless cold starts reset it); it bounds abuse rather than enforcing a global quota.
"""

from __future__ import annotations

import time
from collections import deque
from contextvars import ContextVar

from fastapi import HTTPException, status

WINDOW_SECONDS = 3600
_live_calls: deque[float] = deque()
_reserved_here: ContextVar[float | None] = ContextVar("live_slot_reserved", default=None)


def reserve(limit: int) -> int:
    """Reserve one live call for this request, or raise 429 when the hour's cap is used."""
    now = time.monotonic()
    while _live_calls and now - _live_calls[0] > WINDOW_SECONDS:
        _live_calls.popleft()
    if len(_live_calls) >= limit:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Live call limit reached ({limit} per hour). Cached demo results still work.",
        )
    _live_calls.append(now)
    _reserved_here.set(now)
    return limit - len(_live_calls)


def release_reserved() -> bool:
    """Give back this request's slot (used when a cache hit means no Muse call was made)."""
    stamp = _reserved_here.get()
    if stamp is None:
        return False
    _reserved_here.set(None)
    try:
        _live_calls.remove(stamp)
    except ValueError:
        return False
    return True


def used() -> int:
    return len(_live_calls)


def reset() -> None:
    _live_calls.clear()
    _reserved_here.set(None)
