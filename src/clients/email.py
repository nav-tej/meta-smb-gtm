"""Resend email delivery. Best effort: returns False instead of raising, never logs addresses."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from src.config import get_settings

logger = logging.getLogger(__name__)

RESEND_URL = "https://api.resend.com/emails"


def enabled() -> bool:
    settings = get_settings()
    return bool(settings.resend_api_key.strip() and settings.email_from.strip())


async def send(
    to: str,
    subject: str,
    html: str,
    text: str,
    *,
    headers: dict[str, str] | None = None,
    idempotency_key: str | None = None,
) -> bool:
    """Send one email. True only when Resend accepted it."""
    settings = get_settings()
    if not enabled() or not to:
        return False
    body: dict[str, Any] = {
        "from": settings.email_from,
        "to": [to],
        "subject": subject[:200],
        "html": html,
        "text": text,
    }
    if settings.email_reply_to:
        body["reply_to"] = settings.email_reply_to
    if headers:
        body["headers"] = headers
    request_headers = {"Authorization": f"Bearer {settings.resend_api_key.strip()}"}
    if idempotency_key:
        request_headers["Idempotency-Key"] = idempotency_key[:256]
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(10, connect=5)) as http:
            response = await http.post(RESEND_URL, json=body, headers=request_headers)
    except httpx.HTTPError as err:
        logger.warning("Email not sent: %s", type(err).__name__)
        return False
    if response.is_error:
        logger.warning("Email not sent: Resend status %s", response.status_code)
        return False
    return True
