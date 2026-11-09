"""Server-side PostHog capture for events the browser can't report reliably (payments).

Analytics must never break the request that triggered them: failures are logged and dropped.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

import httpx

from src.config import get_settings

logger = logging.getLogger(__name__)
_TIMEOUT = httpx.Timeout(3.0, connect=2.0)


def enabled() -> bool:
    return bool(get_settings().posthog_key.strip())


async def capture(event: str, distinct_id: str, properties: dict[str, Any] | None = None) -> bool:
    """Send one event; returns False (never raises) when disabled or PostHog is unreachable."""
    settings = get_settings()
    if not settings.posthog_key.strip() or not distinct_id:
        return False
    body = {
        "api_key": settings.posthog_key.strip(),
        "event": event,
        "distinct_id": distinct_id,
        "properties": {"$lib": "muse-server", **(properties or {})},
        "timestamp": datetime.now(UTC).isoformat(),
    }
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await client.post(settings.posthog_host.rstrip("/") + "/i/v0/e/", json=body)
        if response.status_code >= 400:
            logger.warning("PostHog capture %s rejected with HTTP %s", event, response.status_code)
            return False
        return True
    except httpx.HTTPError as err:
        logger.warning("PostHog capture %s failed: %s", event, type(err).__name__)
        return False
