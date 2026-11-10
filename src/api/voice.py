"""Track J: Seller Voice Profile endpoints."""

from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, Header, Request, Response
from pydantic import BaseModel

from src.models.voice import VoiceAdjustment, VoiceProfile
from src.services.accounts import (
    load_workspace,
    resolve_account,
    save_workspace,
    verify_workspace_owner,
)
from src.services.voice_profile import adjust_voice_profile

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/voice", tags=["voice"])


class VoiceTuneRequest(BaseModel):
    rating: Literal["thumbs_up", "thumbs_down"] = "thumbs_up"
    adjustment: VoiceAdjustment | None = None
    reco_id: str | None = None


class VoiceProfileResponse(BaseModel):
    profile: VoiceProfile
    status: str = "ok"


@router.get("/profile", response_model=VoiceProfileResponse)
async def get_voice_profile(
    request: Request,
    response: Response,
    x_muse_owner: str | None = Header(default=None),
) -> VoiceProfileResponse:
    """Retrieve seller's VoiceProfile from workspace or return default profile."""
    account = await resolve_account(request, response, require_verified=False)
    if not account:
        return VoiceProfileResponse(profile=VoiceProfile())

    verify_workspace_owner(account, x_muse_owner)
    try:
        ws = await load_workspace(account)
        doc = ws.get("document") or {}
        raw = doc.get("voice_profile")
        if raw and isinstance(raw, dict):
            return VoiceProfileResponse(profile=VoiceProfile.model_validate(raw))
    except Exception as err:
        logger.debug("Failed loading voice profile from workspace: %s", err)

    return VoiceProfileResponse(profile=VoiceProfile())


@router.post("/tune", response_model=VoiceProfileResponse)
async def tune_voice_profile(
    body: VoiceTuneRequest,
    request: Request,
    response: Response,
    x_muse_owner: str | None = Header(default=None),
) -> VoiceProfileResponse:
    """Apply seller feedback (thumbs up/down, more casual, more formal, shorter)."""
    account = await resolve_account(request, response, require_verified=False)
    if not account:
        default_prof = VoiceProfile()
        if body.adjustment:
            default_prof = adjust_voice_profile(default_prof, body.adjustment)
        return VoiceProfileResponse(profile=default_prof, status="tuned_locally")

    verify_workspace_owner(account, x_muse_owner)
    ws = await load_workspace(account)
    doc = dict(ws.get("document") or {})

    raw = doc.get("voice_profile")
    current_profile = (
        VoiceProfile.model_validate(raw) if raw and isinstance(raw, dict) else VoiceProfile()
    )

    if body.adjustment:
        current_profile = adjust_voice_profile(current_profile, body.adjustment)

    doc["voice_profile"] = current_profile.model_dump(mode="json")
    await save_workspace(
        account,
        doc,
        expected_version=ws.get("version"),
        expected_owner=account.user_id,
    )

    return VoiceProfileResponse(profile=current_profile, status="saved")
