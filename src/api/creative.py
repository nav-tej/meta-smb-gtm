"""Ad Creative Studio routes (Flow 2)."""

import base64
import binascii
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field

from src.api.demo import LiveMode, demo_unavailable
from src.api.media_delivery import MediaResponseTooLargeError, attach_inline_media
from src.clients.comfyui import SUPPORTED_COMFY_WORKFLOWS, discover_comfy_cli
from src.clients.meta import MetaAPIError, get_meta_client
from src.models.creative import CreativeSet, EditableCreativeBrief, GenerateAdsRequest
from src.services import demo, result_cache
from src.services.ad_creative import AdCreativeService

router = APIRouter(tags=["creative"])


class VoiceNoteRequest(BaseModel):
    audio_base64: str = Field(
        min_length=4, description="Base64-encoded WAV/MP3/WebM audio bytes from seller voice note."
    )
    filename: str = Field(default="voice_note.wav", max_length=120)


def get_ad_creative_service() -> AdCreativeService:
    return AdCreativeService()


@router.get("/creative-models")
async def list_creative_models() -> dict[str, Any]:
    """Return available Meta + ComfyUI workflows (Krea 3, LTX-2.5 DFR, MiniMax H3) and CLI info."""
    return {
        "meta_models": {
            "brief_and_vision": "muse-spark-1.3 (/v1/chat/completions)",
            "deep_reasoning": "muse-wonder-1.0 (/v1/responses)",
            "segmentation": "sam-3.1 (/v1/responses)",
            "image_generation": "muse-image-1.0 (/v1/images/generations)",
            "image_edit": "muse-image-1.0 (/v1/images/edits)",
            "image_workflows": {
                "product_visuals": (
                    "muse-image-1.0 (/v1/responses, reasoning=high) — "
                    "Product campaign visuals (mirrors ComfyUI Ideogram 4 / FLUX)"
                ),
                "restore_enhance": (
                    "muse-image-1.0 (/v1/responses, reasoning=high) — "
                    "Studio detail & resolution restoration (mirrors 4x-UltraSharp / Relight)"
                ),
                "multi_image_combine": (
                    "muse-image-1.0 (/v1/responses, reasoning=high) — "
                    "Multi-image diptych/bundle/style-ref combine (mirrors Krea-2 Style Ref)"
                ),
            },
            "audio_transcription": "muse-voice-transcribe-1.0 (/v1/audio/transcriptions)",
        },
        "comfyui_workflows": SUPPORTED_COMFY_WORKFLOWS,
        "comfy_cli": discover_comfy_cli(),
    }


@router.post("/transcribe-voice")
async def transcribe_voice(request: VoiceNoteRequest, live: LiveMode) -> dict[str, str]:
    """Transcribe a seller's spoken voice note into text via `muse-voice-transcribe-1.0`."""
    if not live:
        raise demo_unavailable("Voice transcription")
    raw = request.audio_base64.strip()
    if "," in raw and raw.startswith("data:"):
        raw = raw.split(",", 1)[1]
    try:
        audio_bytes = base64.b64decode(raw, validate=True)
    except binascii.Error as err:
        raise MetaAPIError(f"Invalid base64 audio payload: {err}") from err
    transcript = await get_meta_client().transcribe_audio(audio_bytes, filename=request.filename)
    return {"transcript": transcript, "model": "muse-voice-transcribe-1.0"}


GenerateAdsResponse = Annotated[CreativeSet | EditableCreativeBrief, Field(discriminator="kind")]


@router.post("/generate-ads", response_model=GenerateAdsResponse)
async def generate_ads(
    request: GenerateAdsRequest,
    service: Annotated[AdCreativeService, Depends(get_ad_creative_service)],
    live: LiveMode,
    response: Response,
) -> CreativeSet | EditableCreativeBrief:
    """draft=true returns a brief to review (kind="draft"); send it back as `brief` to render."""
    if not live and request.draft:
        return demo.demo_creative_draft(request)
    if not live:
        return demo.demo_creative_set(request)
    if request.draft:
        return await result_cache.cached(
            "generate-ads-draft",
            request,
            EditableCreativeBrief,
            lambda: service.draft(request),
            response,
        )

    async def render() -> CreativeSet:
        # Cache the delivered set (with inline media), so a hit needs no output files.
        return attach_inline_media(await service.generate(request))

    try:
        return await result_cache.cached("generate-ads", request, CreativeSet, render, response)
    except MediaResponseTooLargeError as err:
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE,
            detail={
                "error": "media_response_too_large",
                "message": f"{err} Try fewer placements or variants.",
                "estimated_bytes": err.estimated_bytes,
                "limit_bytes": err.limit_bytes,
            },
        ) from err
