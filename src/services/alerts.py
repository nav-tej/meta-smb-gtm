"""Operator alerts by email (Resend) for failures a customer would notice: payments not
recorded, the weekly digest not sent. Throttled per kind per server instance, never raises."""

from __future__ import annotations

import html
import logging
import time

from src.clients import email
from src.config import get_settings

logger = logging.getLogger(__name__)

THROTTLE_SECONDS = 15 * 60
_last_sent: dict[str, float] = {}


async def alert(kind: str, detail: str) -> bool:
    """Email ALERT_EMAIL once per kind per 15 minutes. True if an email was accepted."""
    to = get_settings().alert_email.strip()
    now = time.monotonic()
    if (
        not to
        or not email.enabled()
        or now - _last_sent.get(kind, -THROTTLE_SECONDS) < THROTTLE_SECONDS
    ):
        return False
    _last_sent[kind] = now
    body = (
        f"<p><strong>{html.escape(kind)}</strong></p><p>{html.escape(detail)}</p>"
        "<p>Runbook: docs/launch/OPERATIONS.md in the repository.</p>"
    )
    try:
        return await email.send(to, f"[Muse alert] {kind}", body, f"{kind}\n\n{detail}")
    except Exception:  # alerts must never break the request that raised them
        logger.warning("Alert email failed for %s", kind)
        return False


def reset() -> None:
    _last_sent.clear()
