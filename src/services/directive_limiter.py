"""Track I: Rate limiting and guardrails for Research Directives."""

from __future__ import annotations

import time
from collections import defaultdict

DEFAULT_DIRECTIVE_LIMIT = 10
DEFAULT_DIRECTIVE_WINDOW_SECONDS = 3600

# Maps account_id -> list of float timestamps
_directive_rate_store: dict[str, list[float]] = defaultdict(list)


def check_directive_rate_limit(
    account_id: str,
    limit: int = DEFAULT_DIRECTIVE_LIMIT,
    window_seconds: int = DEFAULT_DIRECTIVE_WINDOW_SECONDS,
    now: float | None = None,
) -> bool:
    """Return True if within rate limit, False if rate limit is exceeded."""
    if not account_id:
        return True
    current = now if now is not None else time.time()
    cutoff = current - window_seconds

    # Filter out timestamps older than the sliding window
    calls = [t for t in _directive_rate_store[account_id] if t > cutoff]
    if len(calls) >= limit:
        return False

    calls.append(current)
    _directive_rate_store[account_id] = calls
    return True


def reset_directive_rate_limits() -> None:
    """Reset rate limiter store (used for tests)."""
    _directive_rate_store.clear()
