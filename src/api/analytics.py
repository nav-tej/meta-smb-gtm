"""Public analytics configuration for the browser. Never a model call, never a secret."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Response

from src.config import get_settings

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/config")
async def analytics_config(response: Response) -> dict[str, Any]:
    """The PostHog project key is a public, write-only ingestion key; it is safe in browsers."""
    response.headers["Cache-Control"] = "public, max-age=300"
    settings = get_settings()
    key = settings.posthog_key.strip()
    if not key:
        return {"enabled": False}
    return {"enabled": True, "key": key, "host": settings.posthog_host.rstrip("/")}
